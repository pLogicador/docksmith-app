"""Fase F (2026-09-10, "PROMPT DE EVOLUÇÃO"/"OBSERVAÇÕES FINAIS" --
checkpoints de processamento observáveis, sem reinício automático em
falha). Ver api/schemas.py::CollectionStatus para os 7 estados possíveis
e o que cada um significa nesta implementação.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fitz

from api import auth, config
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


def _status_of(client, session_id: str, name: str) -> str | None:
    resp = client.get(f"/sessions/{session_id}")
    assert resp.status_code == 200
    for entry in resp.json()["collections"]:
        if entry["name"] == name:
            return entry["status"]
    return None


def test_upload_sets_status_uploaded_after_successful_extraction(client):
    _login_as("user-1")
    resp = client.post(
        "/documents/upload",
        files={"file": ("a.pdf", _pdf_bytes(["página um"]), "application/pdf")},
        data={"collection_name": "c"},
    )
    session_id = resp.json()["session_id"]
    assert _status_of(client, session_id, "c") == "uploaded"


def test_upload_over_page_limit_sets_status_failed_reusing_a_known_session(client, monkeypatch):
    """Achado real corrigido nesta fase: antes, uma extração que falhava
    nunca criava sessão nenhuma -- "failed" ficava impossível de observar
    porque a coleção nunca aparecia em GET /sessions/{id}. Corrigido
    reordenando (sessão existe ANTES da extração) e fazendo o endpoint de
    status incluir também coleções que só existem em `collection_status`.
    O 422 de página-acima-do-limite não devolve `session_id` no corpo --
    por isso este teste cria a sessão primeiro com um upload pequeno bem-
    sucedido, e reusa esse `session_id` pro upload que falha."""
    monkeypatch.setattr(config, "DOCSMITH_MAX_PAGES", 300)
    _login_as("user-1")
    # Cria uma sessão de verdade primeiro (upload pequeno, dentro do limite).
    first = client.post(
        "/documents/upload",
        files={"file": ("pequeno.pdf", _pdf_bytes(["x"]), "application/pdf")},
        data={"collection_name": "c-pequena"},
    )
    session_id = first.json()["session_id"]

    monkeypatch.setattr(config, "DOCSMITH_MAX_PAGES", 2)
    failed = client.post(
        "/documents/upload",
        files={"file": ("grande.pdf", _pdf_bytes([f"página {i}" for i in range(5)]), "application/pdf")},
        data={"collection_name": "c-grande", "session_id": session_id},
    )
    assert failed.status_code == 422
    assert _status_of(client, session_id, "c-grande") == "failed"
    # A coleção pequena continua "uploaded", intocada pela falha da outra.
    assert _status_of(client, session_id, "c-pequena") == "uploaded"


def test_upload_split_sets_status_uploaded_for_each_part_and_nothing_for_the_base_name(client, monkeypatch):
    monkeypatch.setattr(config, "DOCSMITH_MAX_PAGES", 300)
    _login_as("user-1")
    resp = client.post(
        "/documents/upload/split",
        files={"file": ("livro.pdf", _pdf_bytes([f"p{i}" for i in range(3)]), "application/pdf")},
        data={"collection_name": "livro-base"},
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    part_name = resp.json()["parts"][0]["collection_name"]

    assert _status_of(client, session_id, part_name) == "uploaded"
    # o nome-base em si nunca virou uma coleção real -- não deve aparecer.
    status_resp = client.get(f"/sessions/{session_id}")
    names = [c["name"] for c in status_resp.json()["collections"]]
    assert "livro-base" not in names


def test_scrape_sets_status_uploaded(client):
    from unittest.mock import AsyncMock

    _login_as("user-1")
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(
            return_value={"success": True, "data": ["conteúdo raspado"]}
        )
        resp = client.post("/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0})
    session_id = resp.json()["session_id"]
    assert _status_of(client, session_id, "c") == "uploaded"


def test_chat_transitions_status_to_ready_after_successful_indexing(client):
    from unittest.mock import AsyncMock

    _login_as("user-1")
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(
            return_value={"success": True, "data": ["conteúdo de teste"]}
        )
        scrape_resp = client.post("/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0})
    session_id = scrape_resp.json()["session_id"]
    assert _status_of(client, session_id, "c") == "uploaded"

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = True
    fake_rag.ask_question_with_sources.return_value = {"answer": "ok", "sources": []}
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        chat_resp = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p"})
    assert chat_resp.status_code == 200
    assert _status_of(client, session_id, "c") == "ready"


def test_chat_transitions_status_to_failed_when_indexing_returns_false_and_it_stays_visible(client):
    from unittest.mock import AsyncMock

    _login_as("user-1")
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(
            return_value={"success": True, "data": ["conteúdo"]}
        )
        scrape_resp = client.post("/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0})
    session_id = scrape_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.return_value = False
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        chat_resp = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p"})
    assert chat_resp.status_code == 500
    # "failed" fica visível -- não é apagado, não é escondido, e ninguém
    # tentou de novo sozinho (só 1 chamada real a load_collection).
    assert _status_of(client, session_id, "c") == "failed"
    assert fake_rag.load_collection.call_count == 1


def test_chat_transitions_status_to_failed_when_indexing_raises_an_unexpected_exception(client):
    """Diferente do teste acima (load_collection devolve False de forma
    controlada) -- aqui a própria chamada explode. Confirma que o
    try/except em api/routers/chat.py também marca "failed", não deixa a
    exceção vazar como um 500 genérico sem nenhum estado registrado."""
    from unittest.mock import AsyncMock

    _login_as("user-1")
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(
            return_value={"success": True, "data": ["conteúdo"]}
        )
        scrape_resp = client.post("/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0})
    session_id = scrape_resp.json()["session_id"]

    fake_rag = MagicMock()
    fake_rag.load_collection.side_effect = RuntimeError("provedor de embeddings indisponível")
    with patch("api.routers.chat.RAGService", return_value=fake_rag):
        chat_resp = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p"})
    assert chat_resp.status_code == 500
    assert _status_of(client, session_id, "c") == "failed"


def test_a_retry_after_failure_can_succeed_and_overwrites_the_failed_status(client):
    """"Sem retry automático em loop" != "não pode tentar de novo" -- o
    usuário reenviando a pergunta É uma nova tentativa real, e ela
    reescreve "failed" normalmente se der certo desta vez."""
    from unittest.mock import AsyncMock

    _login_as("user-1")
    with patch("api.routers.scrape.ScrapingService") as MockScraper:
        MockScraper.return_value.scrape_website_async = AsyncMock(
            return_value={"success": True, "data": ["conteúdo"]}
        )
        scrape_resp = client.post("/scrape", json={"url": "https://exemplo.com", "collection_name": "c", "max_depth": 0})
    session_id = scrape_resp.json()["session_id"]

    fake_rag_fails = MagicMock()
    fake_rag_fails.load_collection.return_value = False
    with patch("api.routers.chat.RAGService", return_value=fake_rag_fails):
        first = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p"})
    assert first.status_code == 500
    assert _status_of(client, session_id, "c") == "failed"

    fake_rag_ok = MagicMock()
    fake_rag_ok.load_collection.return_value = True
    fake_rag_ok.ask_question_with_sources.return_value = {"answer": "ok", "sources": []}
    with patch("api.routers.chat.RAGService", return_value=fake_rag_ok):
        second = client.post("/chat", json={"session_id": session_id, "collection_name": "c", "question": "p"})
    assert second.status_code == 200
    assert _status_of(client, session_id, "c") == "ready"


def test_restored_session_reports_uploaded_status_for_every_restored_collection():
    """Restauração via R2 (4ª rodada) -- coleção volta com o texto, mas
    precisa ser reindexada; o status precisa refletir isso ("uploaded",
    não "ready"/"indexed", que implicariam um índice já pronto que na
    verdade não existe mais)."""
    from api import sessions

    sessions.restore_session(
        "sid-status-restaurado",
        "user-1",
        collections={"manual": ["texto"], "outra": ["texto 2"]},
    )
    session = sessions.get_session("sid-status-restaurado", "user-1")
    assert session["collection_status"] == {"manual": "uploaded", "outra": "uploaded"}
