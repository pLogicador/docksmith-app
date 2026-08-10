"""Autenticação: ausente, inválido, válido, bypass de dev.

Mocka só a chamada HTTP pro subscription_access_api (fonte da verdade real de
autorização) — não reimplementa nem reinterpreta a regra de acesso, só
confirma que a api/ trata cada resposta dele corretamente.
"""

from unittest.mock import AsyncMock, patch

import httpx


def test_missing_token_returns_401(client):
    resp = client.post("/models/test-connection", json={"provider": "groq"})
    assert resp.status_code == 401


def test_invalid_token_returns_401(client):
    fake_validate = httpx.Response(401, json={"detail": "invalid"})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_validate)):
        resp = client.post(
            "/models/test-connection",
            json={"provider": "groq"},
            headers={"Authorization": "Bearer token-invalido"},
        )
    assert resp.status_code == 401


def test_subscription_access_api_unreachable_returns_502(client):
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.ConnectError("recusado"))):
        resp = client.post(
            "/models/test-connection",
            json={"provider": "groq"},
            headers={"Authorization": "Bearer qualquer-coisa"},
        )
    assert resp.status_code == 502


def test_valid_token_reaches_the_route(client):
    fake_validate = httpx.Response(200, json={"user": {"id": 42, "email": "a@b.com"}})
    with (
        patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_validate)),
        patch("api.routers.models.test_connection", new=AsyncMock(return_value=(True, None))),
    ):
        resp = client.post(
            "/models/test-connection",
            json={"provider": "groq"},
            headers={"Authorization": "Bearer token-real"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "error": None}


def test_dev_bypass_token_works_when_enabled(client):
    # DOCKSMITH_API_DEV_BYPASS_AUTH=true setado no conftest antes do import.
    with patch("api.routers.models.test_connection", new=AsyncMock(return_value=(True, None))):
        resp = client.post(
            "/models/test-connection",
            json={"provider": "groq"},
            headers={"Authorization": "Bearer dev-bypass-token"},
        )
    assert resp.status_code == 200


def test_wrong_bypass_string_is_rejected_even_with_bypass_enabled(client):
    """Bypass só aceita o literal exato "dev-bypass-token" — qualquer outra
    string cai na validação real contra o subscription_access_api."""
    fake_validate = httpx.Response(401, json={})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=fake_validate)):
        resp = client.post(
            "/models/test-connection",
            json={"provider": "groq"},
            headers={"Authorization": "Bearer dev-bypass-toke"},  # quase igual, não é
        )
    assert resp.status_code == 401
