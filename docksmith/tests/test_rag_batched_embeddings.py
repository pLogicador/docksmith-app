"""Fase G (2026-09-10, "PROMPT DE EVOLUÇÃO" -- embeddings em lote): índice
FAISS construído aos poucos (`embedding_batch_size`) precisa ser
EQUIVALENTE ao construído de uma vez só -- mesmo nº de vetores, mesmo
conjunto de chunks recuperável, mesma resposta de busca -- não só "não
quebrou". Usa o modelo real de embeddings (sentence-transformers), mesmo
padrão já estabelecido em test_rag_hybrid_retriever.py -- zero mock,
zero chamada de rede (embeddings rodam localmente, LLM nunca é
invocado por `load_collection`/`similarity_search`).
"""

from __future__ import annotations

from docksmith.service.rag import RAGService

# 7 documentos distintos, cada um com um termo exclusivo -- permite
# confirmar que TODO chunk continua recuperável depois do lote, não só a
# contagem total bater.
DOCS = [
    f"Documento número {i}. Este trecho fala especificamente sobre o "
    f"assunto-único-{i}, que não aparece em nenhum outro documento desta "
    f"coleção de teste."
    for i in range(7)
]


def test_batched_index_has_the_same_chunk_count_as_a_single_shot_index():
    single = RAGService()
    single.load_collection(DOCS, "fake-key")

    batched = RAGService()
    batched.load_collection(DOCS, "fake-key", embedding_batch_size=2)

    assert single.vector_store.index.ntotal == batched.vector_store.index.ntotal
    assert batched.vector_store.index.ntotal == len(DOCS)  # 7 docs pequenos = 7 chunks, nenhum dividido


def test_batched_index_still_finds_every_chunk_by_its_unique_term():
    batched = RAGService()
    batched.load_collection(DOCS, "fake-key", embedding_batch_size=3)  # lotes de 3, 3, 1 -- 3 lotes reais

    for i in range(len(DOCS)):
        hits = batched.vector_store.similarity_search(f"assunto-único-{i}", k=1)
        assert len(hits) == 1
        assert f"assunto-único-{i}" in hits[0].page_content


def test_batch_size_of_one_forces_the_maximum_number_of_batches_and_still_works():
    """Caso extremo -- 1 chunk por lote (o mesmo nº de lotes que de
    documentos) -- confirma que `add_documents` incremental realmente
    soma ao índice em vez de substituir."""
    service = RAGService()
    ok = service.load_collection(DOCS, "fake-key", embedding_batch_size=1)

    assert ok is True
    assert service.vector_store.index.ntotal == len(DOCS)
    hits = service.vector_store.similarity_search("assunto-único-4", k=1)
    assert "assunto-único-4" in hits[0].page_content


def test_batch_size_none_preserves_the_exact_previous_single_shot_behavior():
    """`embedding_batch_size` ausente (padrão pro Streamlit, que nunca
    passa esse parâmetro) -- mesmo caminho de código de sempre."""
    service = RAGService()
    ok = service.load_collection(DOCS, "fake-key")  # sem embedding_batch_size

    assert ok is True
    assert service.vector_store.index.ntotal == len(DOCS)


def test_batch_size_larger_than_total_chunks_is_equivalent_to_a_single_shot():
    service = RAGService()
    ok = service.load_collection(DOCS, "fake-key", embedding_batch_size=1000)  # bem maior que len(DOCS)

    assert ok is True
    assert service.vector_store.index.ntotal == len(DOCS)


def test_hybrid_retrieval_ranking_is_identical_regardless_of_batching():
    """Não é só o FAISS que precisa ficar equivalente -- o BM25 (léxico) é
    construído a partir da MESMA lista `texts`, fora do laço de lotes, e o
    HybridRetriever (fusão RRF) usa os 2 juntos. Em vez de assumir qual
    resultado é "o correto" pra uma pergunta (a fixture tem 7 sentenças
    quase idênticas, só o número muda -- a qualidade absoluta do ranking
    já é coberta por test_rag_hybrid_retriever.py, com uma fixture
    desenhada pra isso), este teste confirma a propriedade que realmente
    importa aqui: a MESMA pergunta devolve a MESMA ordem de resultados,
    byte a byte, batendo lote ou não -- batching é só uma otimização de
    memória, nunca deveria mudar o que é devolvido."""
    single = RAGService()
    single.load_collection(DOCS, "fake-key")
    batched = RAGService()
    batched.load_collection(DOCS, "fake-key", embedding_batch_size=2)

    for query in ["assunto-único-5", "documento", "o que fala sobre o assunto-único-0?"]:
        single_results = single.retriever._get_relevant_documents(query, run_manager=None)
        batched_results = batched.retriever._get_relevant_documents(query, run_manager=None)
        assert [d.page_content for d in single_results] == [d.page_content for d in batched_results]
