"""Cobertura real do pipeline de RAG (docksmith/service/rag.py) --
primeira suíte de testes deste módulo (2026-09-02, prompt-mestre
"Docksmith"): antes, só a camada de API o exercitava, sempre com
`RAGService` mockado (`api/tests/test_endpoints.py`), então nada
verificava o retriever híbrido de verdade. Cada teste aqui usa uma
coleção pequena real, sem chamar nenhum provedor de LLM de verdade (a
chave passada é falsa de propósito -- `load_collection`/`_get_relevant_
documents` nunca fazem uma chamada de rede, só `ask_question_with_sources`
faria, e não é exercitado aqui).
"""

from __future__ import annotations

from docksmith.service.rag import RAGService, HybridRetriever

DOCS = [
    "O Docksmith é uma ferramenta de extração de conhecimento técnico. "
    "Ele usa RAG (Retrieval-Augmented Generation) para responder perguntas "
    "sobre documentação técnica. O sistema de indexação híbrida combina "
    "busca léxica BM25 com busca vetorial densa via FAISS.",
    "A arquitetura do produto tem duas camadas principais: a camada de API "
    "(FastAPI, fina) e o motor real (compartilhado com o Streamlit legado). "
    "O código-fonte principal do RAG fica em docksmith/service/rag.py.",
    "Preços e planos: o produto tem um plano gratuito e um plano premium. "
    "O código FITID é usado em outro produto do ecossistema, ANZ Finance, "
    "para deduplicar transações bancárias -- não tem relação com o Docksmith.",
]


def test_old_positional_signature_still_works():
    """Compatibilidade inegociável: o Streamlit legado chama
    `load_collection(docs, groq_key)`, só posicional -- ver
    docs/05-streamlit-legado.md."""
    service = RAGService()
    ok = service.load_collection(DOCS, "fake-groq-key-for-index-building")
    assert ok is True
    assert isinstance(service.retriever, HybridRetriever)


def test_new_signature_with_source_labels_still_works():
    service = RAGService()
    ok = service.load_collection(
        DOCS,
        provider="groq",
        api_key="fake-groq-key-for-index-building",
        depth="profunda",
        source_labels=["intro.md", "arquitetura.md", "precos.md"],
    )
    assert ok is True


def test_every_chunk_carries_provenance_metadata():
    service = RAGService()
    service.load_collection(DOCS, "fake-key", source_labels=["intro.md", "arquitetura.md", "precos.md"])

    metas = [c.metadata for c in service.retriever.chunks]
    assert len(metas) == 3
    for i, meta in enumerate(metas):
        assert meta["document_index"] == i
        assert meta["chunk_index"] == i
        assert meta["source_label"] in {"intro.md", "arquitetura.md", "precos.md"}


def test_lexical_signal_surfaces_exact_term_match_first():
    """Prova que o BM25 (léxico) está de fato contribuindo pra fusão RRF,
    não só o denso: "FITID" só aparece no 3º documento -- uma busca por
    esse termo exato deveria ranquear esse documento primeiro."""
    service = RAGService()
    service.load_collection(DOCS, "fake-key")

    results = service.retriever._get_relevant_documents("O que é FITID?", run_manager=None)

    assert len(results) > 0
    assert "FITID" in results[0].page_content


def test_semantic_query_without_exact_term_still_returns_results():
    service = RAGService()
    service.load_collection(DOCS, "fake-key")

    results = service.retriever._get_relevant_documents("como o sistema encontra informação relevante", run_manager=None)

    assert len(results) > 0


def test_no_collection_loaded_returns_the_original_placeholder_message():
    service = RAGService()
    assert service.ask_question_with_sources("qualquer coisa") == {"answer": "No loaded collection.", "sources": []}


# ===== Chunking estrutural real (prompt-mestre §13, 3ª rodada) =====


def test_structure_metadata_is_absent_by_default_same_as_before_this_round():
    """Uma coleção sem structure_metadata (ex.: raspada por URL, que nunca
    passa isso) continua com chapter/section/page_start/page_end = None em
    todo chunk -- comportamento idêntico a antes desta rodada."""
    service = RAGService()
    service.load_collection(DOCS, "fake-key", source_labels=["intro.md", "arquitetura.md", "precos.md"])

    for chunk in service.retriever.chunks:
        assert chunk.metadata["chapter"] is None
        assert chunk.metadata["section"] is None
        assert chunk.metadata["page_start"] is None
        assert chunk.metadata["page_end"] is None
        # document_id/chunk_id são novos nesta rodada -- sempre presentes,
        # mesmo sem structure_metadata (não dependem dela).
        assert chunk.metadata["document_id"]
        assert chunk.metadata["chunk_id"]


def test_structure_metadata_flows_through_to_every_chunk():
    service = RAGService()
    structure = [
        {"chapter": "Capítulo 1", "section": None, "page_start": 1, "page_end": 1},
        {"chapter": "Capítulo 1", "section": "Arquitetura", "page_start": 2, "page_end": 2},
        {"chapter": "Capítulo 2", "section": None, "page_start": 3, "page_end": 3},
    ]
    service.load_collection(DOCS, "fake-key", structure_metadata=structure)

    metas = [c.metadata for c in service.retriever.chunks]
    assert metas[0]["chapter"] == "Capítulo 1" and metas[0]["section"] is None
    assert metas[1]["chapter"] == "Capítulo 1" and metas[1]["section"] == "Arquitetura"
    assert metas[2]["chapter"] == "Capítulo 2"
    assert metas[0]["page_start"] == 1 and metas[0]["page_end"] == 1
    # document_id é único por documento de origem, não por chunk.
    assert metas[0]["document_id"] != metas[1]["document_id"] != metas[2]["document_id"]


def test_small_document_stays_as_a_single_chunk_not_split_by_size():
    """§13: 'não dividir simplesmente por número fixo de caracteres' --
    um documento que já cabe inteiro num chunk (abaixo de CHUNK_SIZE) não
    deveria virar 2+ chunks só porque um splitter genérico corta tudo."""
    from docksmith.service.rag import CHUNK_SIZE

    small_doc = "Um parágrafo curto que cabe tranquilamente num chunk só."
    assert len(small_doc) < CHUNK_SIZE

    service = RAGService()
    service.load_collection([small_doc], "fake-key")

    assert len(service.retriever.chunks) == 1
    assert service.retriever.chunks[0].page_content == small_doc


def test_oversized_document_is_split_and_every_chunk_inherits_chapter():
    """Documento maior que CHUNK_SIZE precisa ser dividido -- e cada chunk
    resultante herda o chapter/section do documento de origem (o split
    acontece DEPOIS da fronteira estrutural, nunca perde essa informação)."""
    from docksmith.service.rag import CHUNK_SIZE

    paragraph = "Esta é uma frase de teste sobre configuração de sistemas distribuídos. " * 3
    big_doc = "\n\n".join([paragraph] * 20)
    assert len(big_doc) > CHUNK_SIZE * 2

    service = RAGService()
    structure = [{"chapter": "Capítulo 9", "section": "Configuração", "page_start": 90, "page_end": 95}]
    service.load_collection([big_doc], "fake-key", structure_metadata=structure)

    chunks = service.retriever.chunks
    assert len(chunks) > 1  # foi de fato dividido
    for chunk in chunks:
        assert chunk.metadata["chapter"] == "Capítulo 9"
        assert chunk.metadata["section"] == "Configuração"
        assert chunk.metadata["page_start"] == 90
        assert len(chunk.page_content) <= CHUNK_SIZE + 50  # tolerância pequena do splitter
