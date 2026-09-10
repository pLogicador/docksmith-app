"""Cache LRU de índices RAG residentes em memória, por sessão (Fase E da
evolução "livros grandes", 2026-09-10).

Antes desta fase, `api/sessions.py` guardava no máximo 1 índice carregado
por sessão (`session["rag_service"]`/`session["loaded_signature"]`) --
trocar de coleção sempre forçava reindexação completa, mesmo pra uma
coleção já indexada minutos antes. Este módulo generaliza isso pra um
dicionário de N entradas (`session["loaded_indices"]`), com 2 controles
de evicção independentes (memória E quantidade, o que estourar primeiro)
e um orçamento cumulativo de chunks por sessão -- tudo puramente
funcional (recebe/devolve o dict, nunca guarda estado global próprio),
fácil de testar isolado do FastAPI/sessions.

Cada entrada de `loaded_indices` tem a forma:
    {
        "rag_service": RAGService,
        "estimated_mb": float,   # custo de RAM estimado (resource_estimate.py)
        "chunk_count": int,      # estimated_chunks, mesma fonte
        "last_used": float,      # time.time() da última pergunta respondida
    }
chaveada por uma signature-key (tupla) cujo 1º elemento é sempre o(s)
nome(s) de coleção envolvidos -- ver api/routers/chat.py.
"""

from __future__ import annotations

from . import config
from .logging_config import get_logger

logger = get_logger(__name__)


def total_indexed_mb(loaded_indices: dict) -> float:
    return sum(entry["estimated_mb"] for entry in loaded_indices.values())


def total_indexed_chunks(loaded_indices: dict) -> int:
    return sum(entry["chunk_count"] for entry in loaded_indices.values())


def evict_to_fit(
    loaded_indices: dict,
    *,
    incoming_mb: float,
    max_mb: float | None = None,
    max_entries: int | None = None,
) -> list:
    """Remove as entradas menos usadas recentemente (LRU, por `last_used`)
    até que AMBOS os tetos voltem a caber para a entrada que está prestes
    a ser indexada: memória (residente + `incoming_mb` <= `max_mb`) E
    quantidade (residentes + 1 novo slot <= `max_entries`). Os 2
    controles são independentes -- dispara a evicção quando QUALQUER um
    dos dois é ultrapassado, o que vier primeiro (pedido explícito do
    usuário, "AJUSTES FINAIS": "teto por quantidade de coleções em cache,
    não só por memória").

    Nunca bloqueia a indexação em si -- sempre existe uma saída (remover
    entradas até `loaded_indices` ficar vazio, se necessário), mesmo
    princípio já usado nas cotas do R2 (nunca impede o upload, só ajusta
    o que fica guardado). Devolve as signature-keys removidas, na ordem
    em que foram evictadas (pra log/teste)."""
    max_mb = config.DOCSMITH_MAX_SESSION_INDEX_MB if max_mb is None else max_mb
    max_entries = config.DOCSMITH_MAX_CACHED_COLLECTIONS if max_entries is None else max_entries

    evicted: list = []
    while loaded_indices:
        over_memory = total_indexed_mb(loaded_indices) + incoming_mb > max_mb
        over_count = len(loaded_indices) + 1 > max_entries
        if not over_memory and not over_count:
            break
        lru_key = min(loaded_indices, key=lambda key: loaded_indices[key]["last_used"])
        loaded_indices.pop(lru_key)
        evicted.append(lru_key)

    if evicted:
        logger.info("Cache LRU evictou %d índice(s): %s", len(evicted), evicted)
    return evicted


def invalidate_collection(loaded_indices: dict, collection_name: str) -> list:
    """Remove toda entrada do cache cujo nome de coleção (1º elemento da
    signature-key -- uma string pra coleção única, uma tupla de strings
    pra multicontexto, ver Fase H) inclui `collection_name`. Um upload
    novo pra essa coleção invalida qualquer índice já carregado dela,
    não importa sob qual combinação de provider/model/depth foi indexado
    -- mesmo princípio que já existia com o slot único antigo
    (`session["loaded_signature"]`), só que agora precisa varrer todas
    as entradas em vez de checar 1 só."""
    stale = [
        key
        for key in loaded_indices
        if key[0] == collection_name or (isinstance(key[0], tuple) and collection_name in key[0])
    ]
    for key in stale:
        loaded_indices.pop(key)
    return stale
