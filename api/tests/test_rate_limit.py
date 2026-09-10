"""Rate limiting por usuário (prompt-mestre "Docksmith" §48). Testes
diretos do módulo (rápidos, sem TestClient) + 1 teste de integração via
endpoint real confirmando o 429."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import config, rate_limit
from api.main import app
from api import auth


def _login_as(user_id: str):
    app.dependency_overrides[auth.get_current_user] = lambda: {
        "token": "t",
        "user": {"id": user_id, "email": f"{user_id}@docksmith.local"},
    }


class TestCheckRateLimitDirect:
    def test_allows_requests_up_to_the_limit(self, monkeypatch):
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", 3)
        for _ in range(3):
            rate_limit.check_rate_limit("user-a", "scrape")  # não deve levantar

    def test_rejects_the_request_that_exceeds_the_limit(self, monkeypatch):
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", 2)
        rate_limit.check_rate_limit("user-a", "scrape")
        rate_limit.check_rate_limit("user-a", "scrape")
        with pytest.raises(HTTPException) as exc_info:
            rate_limit.check_rate_limit("user-a", "scrape")
        assert exc_info.value.status_code == 429
        assert "Retry-After" in exc_info.value.headers

    def test_limit_is_isolated_per_user(self, monkeypatch):
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", 1)
        rate_limit.check_rate_limit("user-a", "scrape")
        rate_limit.check_rate_limit("user-b", "scrape")  # usuário diferente, própria cota

        with pytest.raises(HTTPException):
            rate_limit.check_rate_limit("user-a", "scrape")

    def test_limit_is_isolated_per_category(self, monkeypatch):
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", 1)
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_CHAT_PER_MINUTE", 1)
        rate_limit.check_rate_limit("user-a", "scrape")
        rate_limit.check_rate_limit("user-a", "chat")  # categoria diferente, própria cota

    def test_zero_disables_the_category(self, monkeypatch):
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", 0)
        for _ in range(50):
            rate_limit.check_rate_limit("user-a", "scrape")  # nunca levanta com o limite desligado

    def test_old_hits_outside_the_window_are_forgotten(self, monkeypatch):
        monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_SCRAPE_PER_MINUTE", 1)
        key = ("user-a", "scrape")
        rate_limit.check_rate_limit("user-a", "scrape")
        # Simula que a única requisição já registrada aconteceu há muito
        # tempo (fora da janela de 60s) -- a próxima deveria ser permitida
        # de novo, sem precisar esperar de verdade no teste.
        rate_limit._hits[key][0] -= 3600
        rate_limit.check_rate_limit("user-a", "scrape")  # não deve levantar


def test_upload_endpoint_returns_429_after_exceeding_the_limit(client, monkeypatch):
    # `api.routers.documents` importa o MESMO objeto de módulo `config`
    # (singleton em sys.modules) -- um único patch aqui já vale pra
    # qualquer lugar que leia `config.DOCSMITH_RATE_LIMIT_UPLOAD_PER_MINUTE`.
    monkeypatch.setattr(config, "DOCSMITH_RATE_LIMIT_UPLOAD_PER_MINUTE", 1)

    _login_as("user-1")
    files = {"file": ("a.pdf", b"%PDF-1.4 conteudo qualquer", "application/pdf")}
    data = {"collection_name": "c"}

    # A 1ª chamada pode falhar por PDF inválido (não é o que este teste
    # mede) -- só a 2ª precisa necessariamente bater no rate limit, já
    # aplicado ANTES da validação do arquivo em si.
    client.post("/documents/upload", files=files, data=data)
    resp = client.post("/documents/upload", files=files, data=data)
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
