"""Faxina periódica de sessões (achado real, 2026-09-01) — end-to-end via o
lifespan real da app, não só a função isolada (já coberta em
test_sessions.py). Confirma que o loop de background de fato roda sozinho,
sem depender de nenhuma requisição pra disparar a limpeza.
"""

import time

from fastapi.testclient import TestClient

from api import config, r2_storage, sessions
from api.main import app
from api.tests.test_r2_storage import _FakeR2Client


def test_background_loop_cleans_up_expired_sessions_with_zero_requests(monkeypatch):
    # Intervalo bem curto só pra este teste não esperar os 300s reais do
    # default de produção — nenhum outro teste é afetado (config é lido uma
    # vez por chamada em main.py, não cacheado num valor de import-time).
    monkeypatch.setattr(config, "SESSION_CLEANUP_INTERVAL_SECONDS", 0.05)

    sid = sessions.create_session("user-bg")
    with sessions._lock:
        sessions._sessions[sid]["last_seen"] -= 10**9  # já nasce expirada

    # TestClient como context manager aciona o lifespan de verdade
    # (startup cria a tarefa de background, shutdown cancela) — sem isso,
    # o loop nunca chega a rodar nem uma vez.
    with TestClient(app):
        time.sleep(0.2)  # dá tempo pra pelo menos 1 ciclo do loop rodar

    with sessions._lock:
        assert sid not in sessions._sessions, (
            "a sessão vencida deveria ter sido removida pela faxina de "
            "background, sem nenhuma requisição HTTP ter sido feita"
        )


def test_background_loop_also_deletes_the_expired_sessions_r2_objects(monkeypatch):
    """2026-09-02, 4ª rodada: a mesma faxina periódica que já remove a
    sessão da memória também apaga os objetos R2 dessa sessão -- "após
    finalizar a sessão, limpa se houver algo". Nunca no caminho síncrono/
    reativo (create_session/get_session) -- só aqui, no loop de fundo."""
    monkeypatch.setattr(config, "SESSION_CLEANUP_INTERVAL_SECONDS", 0.05)
    monkeypatch.setattr(config, "R2_ACCOUNT_ID", "acc")
    monkeypatch.setattr(config, "R2_ACCESS_KEY_ID", "key")
    monkeypatch.setattr(config, "R2_SECRET_ACCESS_KEY", "secret")
    monkeypatch.setattr(config, "R2_BUCKET_NAME", "bucket")
    fake = _FakeR2Client()
    monkeypatch.setattr(r2_storage, "_get_client", lambda: fake)

    sid = sessions.create_session("user-bg-r2")
    r2_storage.upload_raw_bytes(
        user_id="user-bg-r2", session_id=sid, collection_name="c", filename="a.pdf", raw_bytes=b"x",
    )
    assert fake.objects  # confirma que o objeto de fato foi criado antes de expirar a sessão
    with sessions._lock:
        sessions._sessions[sid]["last_seen"] -= 10**9

    with TestClient(app):
        time.sleep(0.2)

    assert not fake.objects, "o objeto R2 da sessão vencida deveria ter sido apagado pela faxina periódica"
