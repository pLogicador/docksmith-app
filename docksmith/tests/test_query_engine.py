"""Testes de docksmith/service/query_engine.py (prompt-mestre "Docksmith"
§15-§23, 3ª rodada: "leitura dinâmica de busca" -- classificação de
intenção determinística, busca estrutural sem LLM, resumo hierárquico,
busca léxica sem embeddings, comparação com reranking opcional).

Usa retrieval REAL (BM25/FAISS via RAGService.load_collection, mesma
convenção de test_rag_hybrid_retriever.py) e um LLM FAKE (nunca uma
chamada de rede) -- o que interessa aqui é confirmar QUANTAS vezes e COM
QUE CONTEXTO o LLM é chamado, não a qualidade de uma resposta real.
"""

from __future__ import annotations

from langchain.docstore.document import Document

from docksmith.service.query_engine import QueryEngine, classify_intent
from docksmith.service.rag import RAGService


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeLLM:
    """Registra cada prompt recebido -- os testes verificam CONTAGEM de
    chamadas (prova de resumo hierárquico de verdade, não 1 chamada por
    chunk) e CONTEÚDO do prompt (prova de que só o contexto certo foi
    enviado, não o documento inteiro)."""

    def __init__(self, response: str = "resposta fake do LLM"):
        self.response = response
        self.calls: list[str] = []

    def invoke(self, prompt: str):
        self.calls.append(prompt)
        return _FakeMessage(self.response)


# ===== classify_intent (determinística, zero LLM) =====


class TestClassifyIntent:
    def test_chapter_title_question(self):
        result = classify_intent("Qual é o título do capítulo 7?")
        assert result.intent == "structural_search"
        assert result.chapter == 7
        assert result.wants_title_only is True

    def test_chapter_summary_question(self):
        result = classify_intent("Resuma o capítulo 12.")
        assert result.intent == "structural_search"
        assert result.chapter == 12
        assert result.wants_title_only is False

    def test_page_question(self):
        result = classify_intent("Explique a página 124.")
        assert result.intent == "page_search"
        assert result.page == 124

    def test_quoted_term_is_lexical(self):
        result = classify_intent('Onde aparece a expressão "FITID"?')
        assert result.intent == "lexical_search"
        assert result.term == "FITID"

    def test_contains_term_is_lexical(self):
        result = classify_intent("O documento contém rate-limit?")
        assert result.intent == "lexical_search"
        assert result.term == "rate-limit?" or result.term == "rate-limit"

    def test_compare_extracts_both_chapters(self):
        result = classify_intent("Compare o capítulo 3 e o capítulo 5.")
        assert result.intent == "compare"
        assert result.compare_chapters == [3, 5]

    def test_generic_summarize_without_scope_is_still_summarize(self):
        result = classify_intent("Resuma isso pra mim.")
        assert result.intent == "summarize"

    def test_conceptual_question_falls_back_to_semantic(self):
        result = classify_intent("Como o autor explica o impacto da automação?")
        assert result.intent == "semantic_synthesis"


# ===== QueryEngine -- busca estrutural real =====

_STRUCTURED_DOCS = [
    "Capítulo 1: Introdução\n\nEste capítulo apresenta o produto e seus objetivos gerais.",
    "Capítulo 2: Arquitetura\n\nA arquitetura do sistema é dividida em camada de API e motor de RAG.",
]
_STRUCTURE = [
    {"chapter": "Capítulo 1: Introdução", "section": None, "page_start": 1, "page_end": 1},
    {"chapter": "Capítulo 2: Arquitetura", "section": None, "page_start": 2, "page_end": 2},
]


def _load_structured_service(llm=None) -> RAGService:
    service = RAGService()
    service.load_collection(_STRUCTURED_DOCS, "fake-key", structure_metadata=_STRUCTURE)
    if llm is not None:
        service.llm = llm
    return service


class TestStructuralSearch:
    def test_chapter_title_question_never_calls_the_llm(self):
        """§16, literal: 'Qual é o título do capítulo 7?' -> sem LLM."""
        fake_llm = _FakeLLM()
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)

        result = engine.answer("Qual é o título do capítulo 2?")

        assert result["intent"] == "structural_search"
        assert result["answer"] == "Capítulo 2: Arquitetura"
        assert fake_llm.calls == []  # zero chamadas -- a resposta veio direto do metadado

    def test_chapter_content_question_sends_only_that_chapters_context(self):
        fake_llm = _FakeLLM("Resumo do capítulo 1.")
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)

        result = engine.answer("Resuma o capítulo 1.")

        assert result["intent"] == "structural_search"
        assert result["answer"] == "Resumo do capítulo 1."
        assert len(fake_llm.calls) == 1
        assert "capítulo 1" in fake_llm.calls[0].lower() or "introdução" in fake_llm.calls[0].lower()
        # O prompt não deveria conter o texto do OUTRO capítulo -- prova
        # de que o contexto foi filtrado, não o documento inteiro.
        assert "arquitetura do sistema é dividida" not in fake_llm.calls[0].lower()

    def test_unknown_chapter_falls_back_gracefully_not_a_crash(self):
        """Capítulo que não existe na coleção -- classify_intent ainda
        reconhece a intenção, mas _answer_structural devolve None (sem
        match), e o motor cairia pro caminho semântico (não exercitado
        aqui pra não depender da chain real -- ver nota no arquivo)."""
        from docksmith.service.query_engine import ClassifiedIntent

        service = _load_structured_service()
        engine = QueryEngine(service)
        matched = engine._chunks_for_chapter(999)
        assert matched == []

    def test_page_search_filters_by_page_metadata(self):
        fake_llm = _FakeLLM("Conteúdo da página 2.")
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)

        result = engine.answer("Explique a página 2.")

        assert result["intent"] == "page_search"
        assert len(fake_llm.calls) == 1
        assert "arquitetura" in fake_llm.calls[0].lower()


class TestHierarchicalSummarization:
    def test_large_chapter_triggers_grouped_summarization_not_one_call_per_chunk(self):
        """§22: 30 chunks -> grupos -> resumos -> 1 final. Aqui, um
        capítulo com 12 chunks (acima do limiar de 6) deveria virar
        ceil(12/5)+1 = 3+1 = 4 chamadas ao LLM -- muito menos que 12."""
        many_chunks_doc = "\n\n".join(f"Parágrafo {i} sobre configuração avançada do sistema." for i in range(30))
        # Documento grande o bastante pra ser dividido em bem mais que
        # _HIERARCHICAL_SUMMARY_THRESHOLD (6) chunks pelo splitter
        # (CHUNK_SIZE=1000) -- repete o conteúdo pra garantir volume.
        big_text = "\n\n".join([many_chunks_doc] * 6)

        fake_llm = _FakeLLM("resumo parcial")
        service = RAGService()
        service.load_collection(
            [big_text], "fake-key", structure_metadata=[{"chapter": "Capítulo 9", "section": None}]
        )
        service.llm = fake_llm
        engine = QueryEngine(service)

        matched = engine._chunks_for_chapter(9)
        assert len(matched) > 6  # confirma que o cenário de teste realmente é "grande"

        result = engine.answer("Resuma o capítulo 9.")

        assert result["intent"] == "structural_search"
        num_groups = -(-len(matched) // 5)  # ceil
        assert len(fake_llm.calls) == num_groups + 1  # +1 = chamada de combinação final
        assert len(fake_llm.calls) < len(matched)  # bem menos que 1 chamada por chunk


class TestLexicalSearch:
    def test_finds_exact_term_via_bm25_and_answers_with_only_matching_chunks(self):
        docs = [
            "Este documento fala sobre configuração geral do sistema, sem menção a códigos especiais.",
            "O código FITID é usado para deduplicar transações bancárias no ANZ Finance.",
        ]
        fake_llm = _FakeLLM("FITID é um código de deduplicação.")
        service = RAGService()
        service.load_collection(docs, "fake-key")
        service.llm = fake_llm
        engine = QueryEngine(service)

        result = engine.answer('Onde aparece a expressão "FITID"?')

        assert result["intent"] == "lexical_search"
        assert len(fake_llm.calls) == 1
        assert "fitid" in fake_llm.calls[0].lower()
        assert len(result["sources"]) >= 1


class TestCompare:
    def test_compares_two_chapters_within_the_same_collection(self):
        fake_llm = _FakeLLM("Comparação entre os capítulos.")
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)

        result = engine.answer("Compare o capítulo 1 e o capítulo 2.")

        assert result["intent"] == "compare"
        assert len(fake_llm.calls) == 1  # 1 chamada final de comparação
        assert "introdução" in fake_llm.calls[0].lower()
        assert "arquitetura" in fake_llm.calls[0].lower()

    def test_compare_with_a_nonexistent_chapter_returns_none_from_the_handler(self):
        service = _load_structured_service()
        engine = QueryEngine(service)
        result = engine._answer_compare(classify_intent("Compare o capítulo 1 e o capítulo 999."), "irrelevante")
        assert result is None

    def test_compare_has_no_notice_when_reranking_succeeds(self, monkeypatch):
        """Uso normal (internet disponível, modelo baixado com sucesso):
        nenhum campo extra aparece na resposta -- backward-compatible, não
        polui o caminho feliz de ninguém."""
        fake_llm = _FakeLLM("Comparação entre os capítulos.")
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)
        monkeypatch.setattr(
            QueryEngine, "_rerank", lambda self, question, chunks: (chunks, True)
        )

        result = engine.answer("Compare o capítulo 1 e o capítulo 2.")

        assert "notice" not in result

    def test_compare_tells_the_user_plainly_when_reranking_could_not_run(self, monkeypatch):
        """2026-09-02, 4ª rodada: em vez de degradar em silêncio quando o
        modelo de reranking não pôde ser baixado (sem internet nesse
        instante específico), a resposta explica isso pro usuário -- pra
        não passar a impressão de que a ferramenta "piorou"/"quebrou" sem
        explicação. A resposta continua completa (não é um erro)."""
        fake_llm = _FakeLLM("Comparação entre os capítulos.")
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)
        # Simula exatamente o cenário real: o cross-encoder não pôde ser
        # baixado/carregado agora -- `_rerank` já captura essa falha e
        # devolve reranked=False (ver query_engine.py), então mockar o
        # próprio `_rerank` é a forma mais direta e realista de testar o
        # caminho de aviso, sem depender de rede real no ambiente de teste.
        monkeypatch.setattr(
            QueryEngine, "_rerank", lambda self, question, chunks: (chunks, False)
        )

        result = engine.answer("Compare o capítulo 1 e o capítulo 2.")

        assert result["intent"] == "compare"
        assert "notice" in result
        assert "reranking" in result["notice"].lower() or "reordenar" in result["notice"].lower()
        # A resposta em si continua presente e completa -- não é um erro.
        assert result["answer"] == "Comparação entre os capítulos."

    def test_compare_only_needs_one_side_to_fail_reranking_to_trigger_the_notice(self, monkeypatch):
        fake_llm = _FakeLLM("Comparação entre os capítulos.")
        service = _load_structured_service(fake_llm)
        engine = QueryEngine(service)
        calls = {"n": 0}

        def _half_failing_rerank(self, question, chunks):
            calls["n"] += 1
            return chunks, calls["n"] != 1  # o 1º lado falha, o 2º funciona

        monkeypatch.setattr(QueryEngine, "_rerank", _half_failing_rerank)

        result = engine.answer("Compare o capítulo 1 e o capítulo 2.")
        assert "notice" in result


# ===== _truncate_chunks_to_token_budget (§35/§66 "context budget") =====


class TestTokenBudget:
    def test_keeps_all_chunks_when_well_under_budget(self):
        from docksmith.service.query_engine import _truncate_chunks_to_token_budget

        chunks = [Document(page_content=f"Trecho curto número {i}.") for i in range(5)]
        kept = _truncate_chunks_to_token_budget(chunks, budget=6000)
        assert len(kept) == 5

    def test_cuts_off_chunks_once_the_budget_would_be_exceeded(self):
        from docksmith.service.query_engine import _count_tokens, _truncate_chunks_to_token_budget

        one_chunk_text = "palavra " * 200  # texto real o bastante pra ter um custo de token mensurável
        one_chunk_tokens = _count_tokens(one_chunk_text)
        chunks = [Document(page_content=one_chunk_text) for _ in range(10)]

        budget = one_chunk_tokens * 3 + 1  # cabe exatamente 3 chunks inteiros
        kept = _truncate_chunks_to_token_budget(chunks, budget=budget)

        assert len(kept) == 3
        assert len(kept) < len(chunks)  # prova real de que algo foi cortado

    def test_always_keeps_at_least_one_chunk_even_if_it_alone_exceeds_the_budget(self):
        from docksmith.service.query_engine import _truncate_chunks_to_token_budget

        huge_chunk = Document(page_content="palavra " * 5000)
        kept = _truncate_chunks_to_token_budget([huge_chunk, huge_chunk], budget=10)
        assert len(kept) == 1  # nunca devolve uma lista vazia por causa do orçamento


# ===== RAGService.ask_question_with_sources -- roteamento real =====


def test_ask_question_with_sources_routes_through_query_engine_and_reports_intent():
    fake_llm = _FakeLLM("Capítulo real.")
    service = _load_structured_service(fake_llm)

    result = service.ask_question_with_sources("Qual é o título do capítulo 1?")

    assert result["intent"] == "structural_search"
    assert result["answer"] == "Capítulo 1: Introdução"
    assert fake_llm.calls == []
