"""Endpoints principais (/scrape, /chat) — scraping real e chamadas de LLM
mockadas (não é objetivo desta suíte re-testar o motor de RAG/scraping em si,
já validado manualmente; o objetivo é a camada de API: roteamento, sessão,
validação, erros).
"""

from unittest.mock import AsyncMock, MagicMock, patch

from api import auth
from api.main import app


def _login_as(user_id: str):
    app.dependency_overrides[auth.get_current_user] = lambda: {
        "token": "t",
        "user": {"id": user_id, "email": f"{user_id}@docksmith.local"},
    }


def test_scrape_creates_collection(client):
    _login_as("user-1")
    fake_result = {"success": True, "data": ["# título\nconteúdo de teste raspado"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_result)
        resp = client.post(
            "/scrape",
            json={"url": "https://exemplo.com/doc", "collection_name": "colecao-teste", "max_depth": 0},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["collection_name"] == "colecao-teste"
    assert body["document_count"] == 1
    assert body["session_id"]


def test_scrape_failure_returns_422(client):
    _login_as("user-1")
    fake_result = {"success": False, "error": "site indisponível"}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_result)
        resp = client.post(
            "/scrape",
            json={"url": "https://exemplo.com/fora-do-ar", "collection_name": "c", "max_depth": 0},
        )
    assert resp.status_code == 422


def test_scrape_requires_auth(client):
    resp = client.post("/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0})
    assert resp.status_code == 401


def test_chat_with_unknown_session_returns_404(client):
    _login_as("user-1")
    resp = client.post(
        "/chat",
        json={"session_id": "sessao-que-nao-existe", "collection_name": "c", "question": "oi"},
    )
    assert resp.status_code == 404


def test_chat_with_unknown_collection_returns_404(client):
    _login_as("user-1")
    fake_result = {"success": True, "data": ["conteúdo"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_result)
        scrape_resp = client.post(
            "/scrape", json={"url": "https://exemplo.com", "collection_name": "c-real", "max_depth": 0}
        )
    session_id = scrape_resp.json()["session_id"]

    resp = client.post(
        "/chat",
        json={"session_id": session_id, "collection_name": "c-que-nao-existe", "question": "oi"},
    )
    assert resp.status_code == 404


def test_chat_provider_requiring_key_without_key_returns_400(client):
    _login_as("user-1")
    fake_result = {"success": True, "data": ["conteúdo"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_result)
        scrape_resp = client.post(
            "/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0}
        )
    session_id = scrape_resp.json()["session_id"]

    resp = client.post(
        "/chat",
        json={
            "session_id": session_id,
            "collection_name": "c",
            "question": "oi",
            "provider": "anthropic",
            "api_key": None,
        },
    )
    assert resp.status_code == 400


def test_chat_happy_path_returns_answer_with_sources(client):
    _login_as("user-1")
    fake_scrape = {"success": True, "data": ["conteúdo de teste"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_scrape)
        scrape_resp = client.post(
            "/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0}
        )
    session_id = scrape_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = True
    fake_rag.ask_question_with_sources.return_value = {
        "answer": "Resposta de teste.",
        "sources": [{"index": 0, "excerpt": "trecho de teste"}],
    }
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "c", "question": "pergunta de teste"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Resposta de teste."
    assert len(body["sources"]) == 1
    assert body["provider"] == "groq"


def test_chat_reindex_failure_returns_500(client):
    _login_as("user-1")
    fake_scrape = {"success": True, "data": ["conteúdo"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_scrape)
        scrape_resp = client.post(
            "/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0}
        )
    session_id = scrape_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = False
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "c", "question": "pergunta"},
        )
    assert resp.status_code == 500
