"""Isolamento entre sessões/usuários e comportamento de TTL — puro, sem HTTP.

Estado em memória (api/sessions.py) é a única coisa que impede um usuário de
ver a sessão/coleção de outro; sem teste automatizado aqui, uma regressão
silenciosa nisso vazaria dados entre contas.
"""

from api import sessions


def test_user_cannot_access_another_users_session():
    sid_a = sessions.create_session("user-a")
    sid_b = sessions.create_session("user-b")

    assert sessions.get_session(sid_a, "user-a") is not None
    assert sessions.get_session(sid_a, "user-b") is None
    assert sessions.get_session(sid_b, "user-b") is not None
    assert sessions.get_session(sid_b, "user-a") is None


def test_get_or_create_session_reuses_existing_for_same_user():
    sid, session = sessions.get_or_create_session(None, "user-x")
    sid2, session2 = sessions.get_or_create_session(sid, "user-x")
    assert sid == sid2
    assert session is session2


def test_get_or_create_session_ignores_session_id_from_wrong_user():
    sid, _ = sessions.get_or_create_session(None, "user-x")
    new_sid, _ = sessions.get_or_create_session(sid, "user-y")
    assert new_sid != sid


def test_expired_session_is_cleaned_up():
    sid = sessions.create_session("user-y")
    with sessions._lock:
        sessions._sessions[sid]["last_seen"] -= 10**9  # bem além do TTL
    assert sessions.get_session(sid, "user-y") is None
