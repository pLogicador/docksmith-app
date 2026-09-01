"""Faxina periódica de sessões (achado real, 2026-09-01) — end-to-end via o
lifespan real da app, não só a função isolada (já coberta em
test_sessions.py). Confirma que o loop de background de fato roda sozinho,
sem depender de nenhuma requisição pra disparar a limpeza.
"""

import time

from fastapi.testclient import TestClient

from api import config, sessions
from api.main import app


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
