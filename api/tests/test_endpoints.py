"""Endpoints principais (/scrape, /chat) — scraping real e chamadas de LLM
mockadas (não é objetivo desta suíte re-testar o motor de RAG/scraping em si,
já validado manualmente; o objetivo é a camada de API: roteamento, sessão,
validação, erros).
"""

from unittest.mock import AsyncMock, MagicMock, patch

import fitz

from api import auth
from api.main import app


def _login_as(user_id: str):
    app.dependency_overrides[auth.get_current_user] = lambda: {
        "token": "t",
        "user": {"id": user_id, "email": f"{user_id}@docksmith.local"},
    }


def _pdf_bytes(pages_text: list[str]) -> bytes:
    pdf = fitz.open()
    for text in pages_text:
        page = pdf.new_page()
        page.insert_text((72, 72), text)
    data = pdf.tobytes()
    pdf.close()
    return data


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


def test_chat_response_carries_the_real_citation_metadata(client):
    """Achado real (2026-09-02, encontrado testando um upload de PDF real
    ponta a ponta): `RAGService.ask_question_with_sources` já calcula
    document_index/chunk_index/source_label desde a 1ª rodada da Fase I,
    mas `api/schemas.py::SourceExcerpt` nunca os declarava -- Pydantic
    descartava os 3 campos silenciosamente antes da resposta chegar ao
    cliente. Regression guard: confirma que os 3 sobrevivem até o JSON
    final da API, não só dentro do dict interno do RAGService."""
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
        "sources": [
            {
                "index": 0,
                "excerpt": "trecho de teste",
                "document_index": 0,
                "chunk_index": 3,
                "source_label": "manual.pdf - página 2",
            }
        ],
    }
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "c", "question": "pergunta de teste"},
        )
    assert resp.status_code == 200
    source = resp.json()["sources"][0]
    assert source["document_index"] == 0
    assert source["chunk_index"] == 3
    assert source["source_label"] == "manual.pdf - página 2"


def test_chat_response_carries_intent_and_structural_source_fields(client):
    """3ª rodada (prompt-mestre §13/§16/§17): mesmo achado real de
    api/schemas.py silenciosamente descartando campos não declarados --
    agora pra chapter/section/page_start/page_end/intent."""
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
        "answer": "Capítulo 7: Segurança",
        "intent": "structural_search",
        "sources": [
            {
                "index": 0,
                "excerpt": "trecho de teste",
                "chapter": "Capítulo 7: Segurança",
                "section": None,
                "page_start": 120,
                "page_end": 124,
            }
        ],
    }
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "c", "question": "qual o título do capítulo 7?"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["intent"] == "structural_search"
    source = body["sources"][0]
    assert source["chapter"] == "Capítulo 7: Segurança"
    assert source["page_start"] == 120
    assert source["page_end"] == 124


def test_chat_response_carries_the_reranking_notice_when_present(client):
    """2026-09-02, 4ª rodada: mesmo achado real de campo silenciosamente
    descartado por api/schemas.py -- agora pro `notice` (aviso de que o
    reranking não pôde ser aplicado numa comparação)."""
    _login_as("user-1")
    fake_scrape = {"success": True, "data": ["conteúdo de teste"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_scrape)
        scrape_resp = client.post(
            "/scrape", json={"url": "https://exemplo.com", "collection_name": "c2", "max_depth": 0}
        )
    session_id = scrape_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = True
    fake_rag.ask_question_with_sources.return_value = {
        "answer": "Comparação concluída.",
        "intent": "compare",
        "notice": "O passo extra de reordenar os trechos por relevância não pôde ser aplicado agora.",
        "sources": [],
    }
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "c2", "question": "compare o capítulo 1 e o 2"},
        )
    assert resp.status_code == 200
    assert "reordenar" in resp.json()["notice"]


def test_chat_response_notice_defaults_to_none_for_normal_answers(client):
    """A esmagadora maioria das respostas não passa por reranking nenhum
    -- `notice` precisa continuar ausente/None, não aparecer como ruído em
    toda resposta."""
    _login_as("user-1")
    fake_scrape = {"success": True, "data": ["conteúdo de teste"]}
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(return_value=fake_scrape)
        scrape_resp = client.post(
            "/scrape", json={"url": "https://exemplo.com", "collection_name": "c3", "max_depth": 0}
        )
    session_id = scrape_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = True
    fake_rag.ask_question_with_sources.return_value = {
        "answer": "Resposta normal.", "intent": "semantic_synthesis", "sources": [],
    }
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "c3", "question": "pergunta qualquer"},
        )
    assert resp.status_code == 200
    assert resp.json()["notice"] is None


def test_chat_passes_uploaded_document_structure_to_load_collection(client):
    """Confirma o fio de ponta a ponta: session["collection_structure"]
    (populado por /documents/upload) chega até
    RAGService.load_collection(..., structure_metadata=...) via /chat --
    sem isso, query_engine.py nunca teria chapter/section/página pra
    filtrar, mesmo com um PDF real já indexado."""
    _login_as("user-1")
    upload_resp = client.post(
        "/documents/upload",
        files={"file": ("manual.pdf", _pdf_bytes(["página um do manual", "página dois do manual"]), "application/pdf")},
        data={"collection_name": "manual-estruturado"},
    )
    session_id = upload_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = True
    fake_rag.ask_question_with_sources.return_value = {"answer": "ok", "sources": [], "intent": "semantic_synthesis"}
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        resp = client.post(
            "/chat",
            json={"session_id": session_id, "collection_name": "manual-estruturado", "question": "qualquer pergunta"},
        )
    assert resp.status_code == 200

    call_args = fake_rag.load_collection.call_args
    structure_metadata_arg = call_args.args[7] if len(call_args.args) > 7 else call_args.kwargs.get("structure_metadata")
    assert structure_metadata_arg is not None
    assert len(structure_metadata_arg) == 2
    assert structure_metadata_arg[0]["page_start"] == 1
    assert structure_metadata_arg[1]["page_start"] == 2


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


# ===== Fase E (2026-09-10, "AJUSTES FINAIS"/"OBSERVAÇÕES FINAIS" -- cache
# LRU por sessão com 2 tetos independentes + orçamento cumulativo de
# chunks) =====


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


def test_chat_reports_was_cached_false_first_then_true_on_repeat(client):
    _login_as("user-1")
    session_id = _scrape(client, "https://exemplo.com", "c").json()["session_id"]

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        first = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p1"})
        second = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p2"})

    assert first.json()["was_cached"] is False
    assert second.json()["was_cached"] is True
    assert fake_rag.load_collection.call_count == 1  # só indexou 1 vez, a 2ª pergunta reaproveitou


def test_chat_keeps_two_small_collections_cached_at_the_same_time_by_default(client):
    """2 coleções pequenas cabem tranquilamente dentro do teto default de
    800MB e do teto default de 3 coleções -- perguntar na 1ª de novo,
    depois de já ter perguntado na 2ª, não deveria reindexar."""
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-a", data="conteúdo a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "colecao-b", session_id=session_id, data="conteúdo b")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        r1 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})
        r2 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-b", "question": "p"})
        r3 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})

    assert r1.json()["was_cached"] is False
    assert r2.json()["was_cached"] is False
    assert r3.json()["was_cached"] is True  # ainda residente, não precisou reindexar
    assert fake_rag.load_collection.call_count == 2  # só a e b, cada uma 1 vez


def test_chat_evicts_least_recently_used_collection_when_count_cap_is_exceeded(client, monkeypatch):
    """Teto de QUANTIDADE, isolado (memória de sobra) -- confirma que os 2
    controles são de fato independentes, não só o de memória."""
    from api import config

    monkeypatch.setattr(config, "DOCSMITH_MAX_CACHED_COLLECTIONS", 1)
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-a", data="conteúdo a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "colecao-b", session_id=session_id, data="conteúdo b")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        r1 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})
        r2 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-b", "question": "p"})  # evicta a
        r3 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})  # reindexa a

    assert [r1.json()["was_cached"], r2.json()["was_cached"], r3.json()["was_cached"]] == [False, False, False]
    assert fake_rag.load_collection.call_count == 3  # a, b, a de novo (evictada no meio)


def test_chat_evicts_by_memory_cap_even_when_count_cap_has_room(client, monkeypatch):
    """Teto de MEMÓRIA, isolado (quantidade teria espaço de sobra) --
    confirma o outro lado da independência dos 2 controles."""
    from api import config

    monkeypatch.setattr(config, "DOCSMITH_MAX_SESSION_INDEX_MB", 61)  # cabe ~1 coleção (custo fixo ~60MB)
    monkeypatch.setattr(config, "DOCSMITH_MAX_CACHED_COLLECTIONS", 10)  # quantidade não seria o gargalo
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-a", data="conteúdo a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "colecao-b", session_id=session_id, data="conteúdo b")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        r1 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})
        r2 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-b", "question": "p"})
        r3 = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})

    assert [r1.json()["was_cached"], r2.json()["was_cached"], r3.json()["was_cached"]] == [False, False, False]
    assert fake_rag.load_collection.call_count == 3


def test_chat_blocks_when_cumulative_session_chunk_budget_is_exceeded(client, monkeypatch):
    """Diferente do bloqueio de coleção grande isolada (já existente): este
    soma tudo que já está residente no cache desta sessão + a nova."""
    from api import config

    monkeypatch.setattr(config, "DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION", 1)
    _login_as("user-1")
    resp_a = _scrape(client, "https://a.com", "colecao-a", data="conteúdo a")
    session_id = resp_a.json()["session_id"]
    _scrape(client, "https://b.com", "colecao-b", session_id=session_id, data="conteúdo b")

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        ok = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-a", "question": "p"})
        assert ok.status_code == 200

        blocked = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-b", "question": "p"})
        assert blocked.status_code == 413
        detail = blocked.json()["detail"]
        assert detail["requires_confirmation"] is True
        assert detail["message"] == "O documento ultrapassa o limite de processamento desta sessão. Deseja continuar?"

        confirmed = client.post(
            "/chat",
            json={
                "session_id": session_id, "collection_name": "colecao-b", "question": "p",
                "confirm_large_collection": True,
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["was_cached"] is False


def test_uploading_into_an_already_cached_collection_invalidates_the_index(client):
    _login_as("user-1")
    upload = client.post(
        "/documents/upload",
        files={"file": ("a.pdf", _pdf_bytes(["página um"]), "application/pdf")},
        data={"collection_name": "colecao-viva"},
    )
    session_id = upload.json()["session_id"]

    fake_rag = _fake_rag()
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        first = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-viva", "question": "p"})
        assert first.json()["was_cached"] is False

        client.post(
            "/documents/upload",
            files={"file": ("b.pdf", _pdf_bytes(["página dois"]), "application/pdf")},
            data={"collection_name": "colecao-viva", "session_id": session_id},
        )

        second = client.post("/chat", json={"session_id": session_id, "collection_name": "colecao-viva", "question": "p"})
        assert second.json()["was_cached"] is False  # invalidada pelo upload novo, precisou reindexar

    assert fake_rag.load_collection.call_count == 2
