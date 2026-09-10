"""Rate limiting (prompt-mestre "Docksmith" §48: "implementar limites por
IP/usuário/sessão/endpoint/tipo de tarefa... especialmente upload,
crawling, OCR, embeddings, consultas LLM. Nunca confiar apenas no
frontend").

Escopo desta rodada: janela deslizante em memória do processo, por
(usuário, categoria de endpoint) -- consistente com o resto da
arquitetura atual do Docksmith (sessões também são só em memória, sem
Redis nesta fase, ver docs/AUDITORIA_E_MIGRACAO_RAG.md). Preparado para
trocar por Redis (contadores compartilhados entre processos) sem mudar
os call sites: a única API pública é `check_rate_limit`, chamada como
dependency do FastAPI.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from . import config

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _limit_for(category: str) -> tuple[int, int]:
    """Lê `config` a cada chamada (não um dict congelado no import) --
    permite reconfigurar via env var em runtime e, principalmente, permite
    testes fazerem `monkeypatch.setattr(config, ...)` e verem o efeito
    imediatamente, sem precisar recarregar o módulo."""
    if category == "scrape":
        return config.DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE, 60
    if category == "upload":
        return config.DOCSMITH_RATE_LIMIT_UPLOAD_PER_MINUTE, 60
    if category == "chat":
        return config.DOCSMITH_RATE_LIMIT_CHAT_PER_MINUTE, 60
    raise ValueError(f"categoria de rate limit desconhecida: {category}")


def check_rate_limit(user_id: str, category: str) -> None:
    """Levanta HTTPException(429) se `user_id` já excedeu o limite da
    categoria na janela atual; senão, registra esta requisição e retorna
    normalmente. `user_id` nunca é confiável vindo do cliente -- sempre
    vem de `auth.get_current_user` (o token já validado), nunca de um
    campo do corpo da requisição.
    """
    limit, window_seconds = _limit_for(category)
    if limit <= 0:
        return  # 0/negativo = categoria desligada (só para testes/ambientes especiais)

    key = (user_id, category)
    now = time.time()
    with _lock:
        hits = _hits[key]
        cutoff = now - window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= limit:
            retry_after = int(window_seconds - (now - hits[0])) + 1
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Muitas requisições de '{category}' em pouco tempo "
                    f"(limite: {limit} por {window_seconds}s). Tente de novo em {retry_after}s."
                ),
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)


def reset_all() -> None:
    """Só para testes -- limpa todo o estado em memória entre casos de teste."""
    with _lock:
        _hits.clear()
