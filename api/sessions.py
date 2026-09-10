"""Estado de sessão em memória do processo — sem banco de dados, sem disco.

Mesmo padrão já usado em subscription_access_api/app.py para o dicionário
`tokens` (dict em memória + lock + faxina por TTL), aplicado aqui para
guardar as coleções raspadas e o RAGService carregado de cada sessão.
"""

import threading
import time
import uuid

from . import config
from .logging_config import get_logger

logger = get_logger(__name__)

_sessions: dict[str, dict] = {}
_lock = threading.Lock()


def _cleanup_expired_locked() -> list[dict]:
    now = time.time()
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session["last_seen"] > config.SESSION_TTL_SECONDS
    ]
    removed = []
    for session_id in expired:
        session = _sessions.pop(session_id, None)
        if session is not None:
            # user_id precisa ser capturado AQUI (antes do dict sumir) --
            # é o único jeito de, depois, apagar os objetos dessa sessão
            # no R2 (2026-09-02, 4ª rodada), já que o prefixo do R2 inclui
            # o hash do user_id (ver api/r2_storage.py).
            removed.append({"session_id": session_id, "user_id": session.get("user_id")})
        logger.info("Sessão expirada removida: %s", session_id)
    return removed


def cleanup_expired() -> int:
    """Mesma faxina de `_cleanup_expired_locked`, exposta pra ser chamada de
    fora (a tarefa periódica em `main.py`) sem depender de alguém criar ou
    acessar uma sessão pra disparar a limpeza. Devolve quantas sessões
    existiam ANTES da faxina, só para dar visibilidade no log de quem chama
    (nunca logamos o quê tinha dentro de cada sessão, só a contagem).
    Contrato preservado 1:1 (testado em test_sessions.py) -- ver
    `cleanup_expired_with_details` abaixo pra quem precisa saber QUAIS
    sessões foram removidas, não só quantas.
    """
    with _lock:
        before = len(_sessions)
        _cleanup_expired_locked()
        return before


def cleanup_expired_with_details() -> tuple[int, list[dict]]:
    """Mesma faxina de `cleanup_expired()`, mas também devolve
    `[{"session_id", "user_id"}, ...]` das sessões removidas nesta rodada
    -- usado só pelo loop de fundo (api/main.py) pra também apagar os
    objetos R2 associados a cada uma. Deliberadamente uma função NOVA (não
    uma mudança de assinatura de `cleanup_expired()`) pra não quebrar o
    contrato `-> int` já coberto por teste, e pra deixar bem claro que só
    o loop de fundo deve chamar esta versão -- o caminho síncrono/reativo
    (create_session/get_session, dentro do lock, no meio de uma requisição
    HTTP) nunca deve disparar uma chamada de rede ao R2."""
    with _lock:
        before = len(_sessions)
        removed = _cleanup_expired_locked()
        return before, removed


def create_session(user_id) -> str:
    with _lock:
        _cleanup_expired_locked()
        session_id = uuid.uuid4().hex
        _sessions[session_id] = {
            "user_id": user_id,
            "collections": {},
            # Rótulo de proveniência por documento (2026-09-02, prompt-mestre
            # "Docksmith" §11), paralelo a `collections[nome]` -- só
            # populado por upload de PDF/DOCX (api/routers/documents.py);
            # coleções raspadas por URL nunca escrevem aqui, então
            # `collection_labels.get(nome)` continua `None` pra elas e
            # `RAGService.load_collection` cai no rótulo genérico
            # `documento_{i}` de sempre (comportamento 100% preservado).
            "collection_labels": {},
            # Estrutura real (capítulo/seção/página, 3ª rodada, prompt-mestre
            # §13/§16) por documento -- paralela a `collections[nome]`,
            # mesmo padrão de `collection_labels` acima: só populada por
            # upload de PDF/DOCX (api/routers/documents.py); coleções
            # raspadas por URL nunca escrevem aqui, então
            # `collection_structure.get(nome)` continua `None` pra elas e
            # `RAGService.load_collection`/`query_engine.py` tratam isso
            # como "essa busca estrutural não se aplica", nunca como erro.
            "collection_structure": {},
            # Cache LRU de índices RAG residentes em memória (Fase E,
            # 2026-09-10) -- dict de signature-key -> {"rag_service",
            # "estimated_mb", "chunk_count", "last_used"}, ver
            # api/index_cache.py. Substitui o antigo slot único
            # `rag_service`/`loaded_signature`: um dict vazio já é o caso
            # particular "nada indexado ainda", e um dict com no máximo 1
            # entrada é exatamente o comportamento anterior, se o teto de
            # coleções em cache fosse 1.
            "loaded_indices": {},
            # Checkpoints de processamento observáveis (Fase F, 2026-09-10)
            # -- dict de nome-de-coleção -> estado real (ver
            # schemas.py::CollectionStatus). Só rastreia coleções que
            # chegaram a existir de verdade em `collections` -- nunca uma
            # entrada "fantasma" pra um upload que falhou antes de criar
            # nada. Em falha de indexação, o estado fica visivelmente
            # "failed" (não é apagado nem reescrito sozinho) até a
            # próxima tentativa real de pergunta nessa coleção.
            "collection_status": {},
            "last_seen": time.time(),
        }
        logger.info("Sessão criada: %s", session_id)
        return session_id


def get_session(session_id: str, user_id) -> dict | None:
    with _lock:
        _cleanup_expired_locked()
        session = _sessions.get(session_id)
        if not session or session["user_id"] != user_id:
            return None
        session["last_seen"] = time.time()
        return session


def restore_session(
    session_id: str,
    user_id,
    *,
    collections: dict[str, list[str]] | None = None,
    collection_labels: dict[str, list[str]] | None = None,
    collection_structure: dict[str, list[dict]] | None = None,
) -> None:
    """Recria uma sessão com o MESMO `session_id` que o cliente já tinha —
    não gera um id novo, ao contrário de `create_session` (2026-09-02, 4ª
    rodada). Usada só pela restauração a partir do R2 (ver
    `POST /sessions/{id}/restore` em api/routers/documents.py), pra que o
    frontend não precise saber que, por trás, o processo reiniciou e a
    sessão em memória tinha sumido — ele continua mandando o mesmo
    `session_id` de sempre e ele volta a funcionar. Se por acaso já
    existir uma sessão viva com esse id, ela é sobrescrita — o chamador só
    invoca isto depois de confirmar, via `get_session`, que não havia
    nenhuma."""
    with _lock:
        _sessions[session_id] = {
            "user_id": user_id,
            "collections": collections or {},
            "collection_labels": collection_labels or {},
            "collection_structure": collection_structure or {},
            "loaded_indices": {},
            "collection_status": dict.fromkeys(collections or {}, "uploaded"),
            "last_seen": time.time(),
        }
        logger.info("Sessão restaurada a partir do R2: %s", session_id)


def get_or_create_session(session_id: str | None, user_id) -> tuple[str, dict]:
    if session_id:
        session = get_session(session_id, user_id)
        if session is not None:
            return session_id, session
    new_id = create_session(user_id)
    return new_id, get_session(new_id, user_id)
