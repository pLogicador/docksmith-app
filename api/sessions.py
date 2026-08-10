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


def _cleanup_expired_locked() -> None:
    now = time.time()
    expired = [
        session_id
        for session_id, session in _sessions.items()
        if now - session["last_seen"] > config.SESSION_TTL_SECONDS
    ]
    for session_id in expired:
        _sessions.pop(session_id, None)
        logger.info("Sessão expirada removida: %s", session_id)


def create_session(user_id) -> str:
    with _lock:
        _cleanup_expired_locked()
        session_id = uuid.uuid4().hex
        _sessions[session_id] = {
            "user_id": user_id,
            "collections": {},
            "rag_service": None,
            "loaded_signature": None,
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


def get_or_create_session(session_id: str | None, user_id) -> tuple[str, dict]:
    if session_id:
        session = get_session(session_id, user_id)
        if session is not None:
            return session_id, session
    new_id = create_session(user_id)
    return new_id, get_session(new_id, user_id)
