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


# ===== cleanup_expired (achado real, 2026-09-01) =====
#
# A limpeza só rodava de forma reativa (dentro de create_session()/
# get_session()) — sem tráfego novo, sessões vencidas ficavam presas na
# memória. cleanup_expired() é a mesma faxina, exposta pra ser chamada de
# fora por uma tarefa periódica independente de tráfego (ver main.py).


def test_cleanup_expired_removes_expired_sessions_without_any_traffic():
    """Diferente de get_session()/create_session(), isto NUNCA deve exigir
    que alguém "toque" numa sessão pra removê-la."""
    sid = sessions.create_session("user-z")
    with sessions._lock:
        sessions._sessions[sid]["last_seen"] -= 10**9

    sessions.cleanup_expired()

    with sessions._lock:
        assert sid not in sessions._sessions


def test_cleanup_expired_keeps_sessions_still_within_ttl():
    sid = sessions.create_session("user-fresh")
    sessions.cleanup_expired()
    with sessions._lock:
        assert sid in sessions._sessions


def test_cleanup_expired_returns_the_count_before_cleaning():
    # _isolate_state (conftest.py) garante que o dict começa vazio aqui.
    sid_a = sessions.create_session("user-count-a")
    sid_b = sessions.create_session("user-count-b")
    with sessions._lock:
        sessions._sessions[sid_a]["last_seen"] -= 10**9

    before = sessions.cleanup_expired()

    assert before == 2  # sid_a + sid_b existiam antes da faxina
    with sessions._lock:
        assert sid_a not in sessions._sessions
        assert sid_b in sessions._sessions


# ===== cleanup_expired_with_details / restore_session (2026-09-02, 4ª
# rodada) -- suporte pra faxina/restauração de objetos R2, ver
# api/r2_storage.py e api/main.py._session_cleanup_loop. =====


def test_cleanup_expired_with_details_reports_session_id_and_user_id():
    sid = sessions.create_session("user-r2")
    with sessions._lock:
        sessions._sessions[sid]["last_seen"] -= 10**9

    before, removed = sessions.cleanup_expired_with_details()

    assert before == 1
    assert removed == [{"session_id": sid, "user_id": "user-r2"}]


def test_cleanup_expired_with_details_reports_nothing_when_no_session_expired():
    sessions.create_session("user-fresh-2")
    before, removed = sessions.cleanup_expired_with_details()
    assert before == 1
    assert removed == []


def test_cleanup_expired_int_contract_is_unaffected_by_the_new_details_function():
    """`cleanup_expired()` (contrato antigo, `-> int`) continua se
    comportando exatamente como antes -- a função nova é aditiva, não uma
    substituição."""
    sid = sessions.create_session("user-old-contract")
    with sessions._lock:
        sessions._sessions[sid]["last_seen"] -= 10**9
    before = sessions.cleanup_expired()
    assert isinstance(before, int)
    assert before == 1


def test_restore_session_recreates_under_the_exact_same_session_id():
    """Diferente de create_session (que sempre gera um id novo),
    restore_session usa o id que o cliente já tinha -- essencial pra ele
    continuar funcionando sem saber que, por trás, a sessão em memória
    tinha sumido e foi reconstruída a partir do R2."""
    fake_session_id = "id-que-o-cliente-ja-tinha"
    assert sessions.get_session(fake_session_id, "user-1") is None  # não existe ainda

    sessions.restore_session(
        fake_session_id,
        "user-1",
        collections={"manual": ["texto restaurado"]},
        collection_labels={"manual": ["manual.pdf - página 1"]},
        collection_structure={"manual": [{"chapter": None, "section": None, "page_start": 1, "page_end": 1}]},
    )

    restored = sessions.get_session(fake_session_id, "user-1")
    assert restored is not None
    assert restored["collections"]["manual"] == ["texto restaurado"]
    assert restored["loaded_indices"] == {}  # precisa ser reindexado, não veio pronto


def test_restore_session_is_only_visible_to_the_original_owner():
    sessions.restore_session("sid-restaurado", "dono-real", collections={"c": ["x"]})
    assert sessions.get_session("sid-restaurado", "outra-pessoa") is None
    assert sessions.get_session("sid-restaurado", "dono-real") is not None
