"""Fase H (2026-09-10, "PROMPT DE EVOLUÇÃO" -- multicontexto: combinar até
3 coleções numa pergunta só). `collection_names` é aditivo -- ausente/vazio
preserva 100% o comportamento de sempre (coberto pelos testes já
existentes de test_endpoints.py, não repetido aqui).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from api import auth
from api.main import app


def _login_as(user_id: str):
    app.dependency_overrides[auth.get_current_user] = lambda: {
        "token": "t",
        "user": {"id": user_id, "email": f"{user_id}@docksmith.local"},
    }


def _scrape(client, url: str, collection_name: str, session_id: str | None = None, data: str = "conteúdo de teste"):
    payload = {"url": url, "collection_name": collection_name, "max_depth": 0}
    if session_id:
        payload["session_id"] = session_id
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value={"success": True, "data": [data]})
        return client.post("/scrape", json=payload)


def _fake_rag():
    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = True
    fake_rag.ask_question_with_sources.return_value = {"answer": "ok", "sources": []}
    return fake_rag


def test_chat_combines_two_collections_and_prefixes_provenance_by_source(client):
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-a", data="conteúdo real da coleção a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "colecao-b", session_id=session_id, data="conteúdo real da coleção b")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={
                "session_id": session_id, "collection_name": "colecao-a",
                "collection_names": ["colecao-a", "colecao-b"], "question": "p",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["collection_name"] == "colecao-a + colecao-b"

    call_args = fake_rag.load_collection.call_args
    docs_arg = call_args.args[0]
    labels_arg = call_args.args[6]
    assert docs_arg == ["conteúdo real da coleção a", "conteúdo real da coleção b"]
    # Nenhum rótulo próprio (raspagem por URL nunca escreve collection_labels)
    # -- cai no fallback prefixado pelo nome de origem, não no genérico
    # "documento_0"/"documento_0" repetido e ambíguo entre as 2 coleções.
    assert labels_arg == ["colecao-a - documento_0", "colecao-b - documento_0"]


def test_chat_rejects_more_than_three_collection_names(client):
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "a")
    session_id = resp_a.json()["session_id"]

    resp = client.post(
        "/chat",
        json={
            "session_id": session_id, "collection_name": "a",
            "collection_names": ["a", "b", "c", "d"], "question": "p",
        },
    )
    assert resp.status_code == 422  # validação do Pydantic (Field(max_length=3)), nem chega no handler


def test_chat_with_unknown_collection_in_collection_names_returns_404(client):
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-real")
    session_id = resp_a.json()["session_id"]

    resp = client.post(
        "/chat",
        json={
            "session_id": session_id, "collection_name": "colecao-real",
            "collection_names": ["colecao-real", "colecao-que-nao-existe"], "question": "p",
        },
    )
    assert resp.status_code == 404
    assert "colecao-que-nao-existe" in resp.json()["detail"]


def test_chat_combining_three_collections_works_and_is_cached_as_one_unit(client):
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "c-a", data="conteúdo a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "c-b", session_id=session_id, data="conteúdo b")
    _scrape(client, "https://c.com", "c-c", session_id=session_id, data="conteúdo c")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        first = client.post(
            "/chat",
            json={
                "session_id": session_id, "collection_name": "c-a",
                "collection_names": ["c-a", "c-b", "c-c"], "question": "p1",
            },
        )
        second = client.post(
            "/chat",
            json={
                "session_id": session_id, "collection_name": "c-a",
                "collection_names": ["c-a", "c-b", "c-c"], "question": "p2",
            },
        )
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["was_cached"] is False
    assert second.json()["was_cached"] is True  # mesma combinação -- reaproveita o índice já montado
    assert fake_rag.load_collection.call_count == 1  # só indexou 1 vez pra 3 coleções combinadas


def test_uploading_pdf_into_one_of_the_combined_collections_invalidates_the_combined_cache_entry(client):
    """`index_cache.invalidate_collection` precisa achar a entrada mesmo
    quando o nome está DENTRO de uma tupla de multicontexto, não só como
    string solta -- ver Fase E."""
    import fitz

    def _pdf_bytes(text: str) -> bytes:
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), text)
        data = pdf.tobytes()
        pdf.close()
        return data

    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-a", data="conteúdo a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "colecao-b", session_id=session_id, data="conteúdo b")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        first = client.post(
            "/chat",
            json={
                "session_id": session_id, "collection_name": "colecao-a",
                "collection_names": ["colecao-a", "colecao-b"], "question": "p",
            },
        )
        assert first.json()["was_cached"] is False

        client.post(
            "/documents/upload",
            files={"file": ("novo.pdf", _pdf_bytes("conteúdo novo"), "application/pdf")},
            data={"collection_name": "colecao-a", "session_id": session_id},
        )

        second = client.post(
            "/chat",
            json={
                "session_id": session_id, "collection_name": "colecao-a",
                "collection_names": ["colecao-a", "colecao-b"], "question": "p2",
            },
        )
    assert second.status_code == 200
    assert second.json()["was_cached"] is False  # entrada combinada foi invalidada, precisou reindexar
    assert fake_rag.load_collection.call_count == 2
