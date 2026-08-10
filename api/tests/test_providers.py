"""Catálogo de provedores/modelos e teste de conexão.

O teste mais importante aqui é o de regressão: garante que toda recomendação
em RECOMMENDATIONS aponta pra um provider+model que realmente existe em
PROVIDER_CATALOG — se alguém editar um dos dois sem atualizar o outro, esse
teste quebra antes de virar um bug em produção.
"""

import asyncio
from unittest.mock import patch

from api.providers import PROVIDER_CATALOG, RECOMMENDATIONS
from api.providers import test_connection as check_provider_connection


def _run(coro):
    return asyncio.run(coro)


def test_recommendations_reference_real_providers_and_models():
    catalog_by_id = {p["id"]: p for p in PROVIDER_CATALOG}
    assert len(RECOMMENDATIONS) > 0
    for rec in RECOMMENDATIONS:
        assert rec["provider"] in catalog_by_id, f"recomendação usa provider inexistente: {rec['provider']}"
        provider = catalog_by_id[rec["provider"]]
        assert rec["model"] in provider["models"], f"recomendação usa modelo não suportado: {rec['model']}"
        assert rec["requiresApiKey"] == provider["requiresApiKey"], (
            f"recomendação '{rec['id']}' diverge do requiresApiKey real do provider"
        )


def test_provider_requiring_key_has_api_key_help():
    for provider in PROVIDER_CATALOG:
        if provider["requiresApiKey"]:
            assert provider["apiKeyHelp"] is not None, f"{provider['id']} exige chave mas não tem apiKeyHelp"
            assert provider["apiKeyHelp"]["url"].startswith("https://")


def test_connection_without_api_key_and_no_server_default_fails():
    with patch("api.providers.config.GROQ_API_KEY", None):
        ok, error = _run(check_provider_connection("groq", None, None))
    assert ok is False
    assert error


def test_connection_success_does_not_leak_api_key_in_error():
    with patch("api.providers.build_chat_llm") as mock_build:
        mock_build.return_value.invoke.return_value = "pong"
        ok, error = _run(check_provider_connection("groq", None, "chave-secreta-do-usuario"))
    assert ok is True
    assert error is None


def test_connection_failure_truncates_error_and_never_echoes_key():
    with patch("api.providers.build_chat_llm") as mock_build:
        mock_build.return_value.invoke.side_effect = RuntimeError("provider indisponível")
        ok, error = _run(check_provider_connection("openai", None, "sk-chave-do-usuario-aqui"))
    assert ok is False
    assert "sk-chave-do-usuario-aqui" not in (error or "")
