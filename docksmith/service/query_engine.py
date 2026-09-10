"""QueryEngine (prompt-mestre "Docksmith" §15-§23, 3ª rodada) -- a camada
que decide COMO ler/buscar antes de decidir mandar qualquer coisa pro LLM,
em vez do padrão anterior de "toda pergunta vira uma busca híbrida
genérica + o livro inteiro relevante pro LLM decidir".

Regra central (§15, "NÃO MANDAR DOCUMENTO INTEIRO AO LLM" / §17,
"CLASSIFICAÇÃO DE INTENÇÃO"): classificação de intenção é 100%
determinística (regex, zero LLM) -- só quando a pergunta não casa com
nenhum padrão estrutural/lexical/comparação é que a pergunta cai no
caminho semântico de sempre (busca híbrida BM25+denso já existente em
rag.py, inalterado).

Compatibilidade: este módulo nunca substitui `RAGService` -- ele é
construído A PARTIR de um `RAGService` já carregado (`RAGService.
load_collection` já rodou) e delega pro caminho semântico antigo
(`RAGService._invoke_with_fallback`) sempre que a intenção detectada é
`semantic_synthesis` (o caso mais comum, ex.: "como o autor explica X").
Nenhuma pergunta que já funcionava antes desta rodada passa a se
comportar diferente -- só as que batem num padrão estrutural/lexical/
comparação real ganham um caminho novo, mais barato e mais preciso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from langchain.docstore.document import Document

Intent = Literal[
    "structural_search",
    "page_search",
    "lexical_search",
    "summarize",
    "compare",
    "semantic_synthesis",
]

# Nº de chunks acima do qual uma consulta estrutural (capítulo/página)
# aciona resumo hierárquico (§22/§23) em vez de mandar tudo de uma vez pro
# LLM -- "se pequeno: contexto normal / se grande: resumo hierárquico".
# Calibrado para o mesmo CHUNK_SIZE de rag.py: 6 chunks de ~1000 chars é
# ~6000 chars de contexto, ainda confortável pra 1 chamada só; acima
# disso, agrupar e resumir em 2 passos fica mais barato e mais preciso
# que despejar tudo.
_HIERARCHICAL_SUMMARY_THRESHOLD = 6
# Tamanho de cada grupo na 1ª passada do resumo hierárquico (§22, exemplo:
# "30 chunks → 6 grupos → 6 resumos → 1 resumo final").
_SUMMARY_GROUP_SIZE = 5

# Orçamento de contexto (§35/§66 "context budget") em tokens reais, não um
# proxy de nº de chunks -- achado real da auditoria desta sessão: `tiktoken`
# já era uma dependência instalada do projeto, mas nunca era chamada em
# lugar nenhum (confirmado por grep antes desta rodada). Calibrado folgado
# o bastante pra caber os chunks de um capítulo inteiro na maioria dos
# casos reais -- o corte por Nº de chunks (_HIERARCHICAL_SUMMARY_THRESHOLD)
# já evita volumes grandes ANTES de chegar aqui; isto é a 2ª camada de
# proteção, medida de verdade (tokens), não estimada por contagem de chunks.
_TOKEN_BUDGET = 6000

_encoding = None
_encoding_load_failed = False


def _count_tokens(text: str) -> int:
    """Conta tokens reais via tiktoken quando disponível; cai para uma
    aproximação conservadora (~4 caracteres por token, média real de
    texto em português/inglês tokenizado em BPE) se a codificação não
    puder ser carregada -- ex.: sem acesso à internet na 1ª chamada (o
    arquivo BPE do tiktoken precisa ser baixado uma vez, sem cache
    local pré-existente). Uma métrica auxiliar de orçamento nunca deveria
    travar a resposta real por causa disso."""
    global _encoding, _encoding_load_failed
    if _encoding is None and not _encoding_load_failed:
        try:
            import tiktoken

            _encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:  # noqa: BLE001 -- offline/sem cache -- degrada pro fallback abaixo
            _encoding_load_failed = True
    if _encoding is not None:
        return len(_encoding.encode(text))
    return max(1, len(text) // 4)


def _truncate_chunks_to_token_budget(chunks: list[Document], budget: int = _TOKEN_BUDGET) -> list[Document]:
    """§35/§66: nunca manda mais que um orçamento real de tokens pro LLM
    numa chamada só. Corta pela LISTA de chunks (nunca o texto de dentro
    de um chunk), pra não quebrar uma frase no meio -- sempre mantém pelo
    menos 1 chunk, mesmo que ele sozinho já exceda o orçamento (melhor
    responder com um pouco mais de contexto do que se recusar a
    responder)."""
    kept: list[Document] = []
    used = 0
    for chunk in chunks:
        chunk_tokens = _count_tokens(chunk.page_content)
        if kept and used + chunk_tokens > budget:
            break
        kept.append(chunk)
        used += chunk_tokens
    return kept

_CHAPTER_RE = re.compile(r"cap[íi]tulo\s+(\d+)", re.IGNORECASE)
_PAGE_RE = re.compile(r"p[áa]gina\s+(\d+)", re.IGNORECASE)
_TITLE_RE = re.compile(r"\bt[íi]tulo\b", re.IGNORECASE)
_SUMMARIZE_RE = re.compile(r"\bresum[ao]\b|\bresumir\b|\bresumo\b", re.IGNORECASE)
_COMPARE_RE = re.compile(r"\bcompare\b|\bcomparar\b|\bcompara[çc][ãa]o\b", re.IGNORECASE)
_QUOTED_TERM_RE = re.compile(r'"([^"]+)"')
_CONTAINS_RE = re.compile(r"cont[ée]m\s+(\S+)", re.IGNORECASE)
_WHERE_APPEARS_RE = re.compile(r"onde\s+aparece\s+(?:a\s+)?(?:express[ãa]o\s+)?(\S+)", re.IGNORECASE)


@dataclass
class ClassifiedIntent:
    """Resultado de `classify_intent` -- a intenção mais os parâmetros já
    extraídos dela (nº do capítulo, nº da página, termo léxico), pra
    `QueryEngine.answer` não precisar re-parsear a pergunta."""

    intent: Intent
    chapter: int | None = None
    page: int | None = None
    term: str | None = None
    wants_title_only: bool = False
    compare_chapters: list[int] = field(default_factory=list)


def classify_intent(question: str) -> ClassifiedIntent:
    """Classificação determinística (§17: "Não utilizar LLM obrigatoriamente
    para classificar todas as perguntas. Começar com regras determinísticas.")
    -- zero chamada de IA. `QueryEngine` só recorreria a um classificador
    LLM se as regras não bastassem, e como o fallback já cai pro caminho
    semântico de sempre (que resolve QUALQUER pergunta), essa camada extra
    nunca ficou necessária nesta rodada -- registrado como possível
    próxima etapa, não implementado às cegas sem uma lacuna real."""
    text = question.strip()

    compare_match = _COMPARE_RE.search(text)
    if compare_match:
        chapters = [int(n) for n in _CHAPTER_RE.findall(text)]
        return ClassifiedIntent(intent="compare", compare_chapters=chapters)

    chapter_match = _CHAPTER_RE.search(text)
    if chapter_match:
        chapter_num = int(chapter_match.group(1))
        wants_title = bool(_TITLE_RE.search(text))
        return ClassifiedIntent(intent="structural_search", chapter=chapter_num, wants_title_only=wants_title)

    page_match = _PAGE_RE.search(text)
    if page_match:
        return ClassifiedIntent(intent="page_search", page=int(page_match.group(1)))

    quoted = _QUOTED_TERM_RE.search(text)
    contains = _CONTAINS_RE.search(text)
    where = _WHERE_APPEARS_RE.search(text)
    term_match = quoted or contains or where
    if term_match:
        return ClassifiedIntent(intent="lexical_search", term=term_match.group(1))

    if _SUMMARIZE_RE.search(text):
        return ClassifiedIntent(intent="summarize")

    return ClassifiedIntent(intent="semantic_synthesis")


def _chapter_number(chapter_label: str | None) -> int | None:
    """Extrai o número de dentro do texto real do heading detectado
    (ex.: "Capítulo 7: Segurança" -> 7) -- o metadado `chapter` de cada
    chunk é o TEXTO real do heading (§13 pede o texto real, não um índice
    sintético), então filtrar por número exige achar o número dentro dele."""
    if not chapter_label:
        return None
    match = re.search(r"\d+", chapter_label)
    return int(match.group()) if match else None


def _tokenize(text: str) -> list[str]:
    return text.lower().split()


def _format_chunks_as_context(chunks: list[Document]) -> str:
    return "\n\n---\n\n".join(chunk.page_content for chunk in chunks)


def _to_source_dicts(chunks: list[Document]) -> list[dict[str, Any]]:
    return [
        {
            "index": i,
            "excerpt": chunk.page_content[:500],
            "document_index": chunk.metadata.get("document_index"),
            "chunk_index": chunk.metadata.get("chunk_index"),
            "source_label": chunk.metadata.get("source_label"),
            "chapter": chunk.metadata.get("chapter"),
            "section": chunk.metadata.get("section"),
            "page_start": chunk.metadata.get("page_start"),
            "page_end": chunk.metadata.get("page_end"),
        }
        for i, chunk in enumerate(chunks)
    ]


_SUMMARY_PROMPT = (
    "Resuma o trecho de documentação abaixo em português, de forma objetiva e fiel ao conteúdo. "
    "Não invente informação que não esteja no texto.\n\n{context}\n\nResumo:"
)

_FINAL_SUMMARY_PROMPT = (
    "Você recebeu resumos parciais de diferentes partes do mesmo capítulo/seção de um documento. "
    "Combine-os em um único resumo coeso, em português, sem repetir informação e sem inventar nada "
    "que não esteja nos resumos abaixo.\n\n{summaries}\n\nResumo final:"
)

_DIRECT_ANSWER_PROMPT = (
    "Você é o Docksmith, um assistente técnico. Responda a pergunta abaixo usando SOMENTE o contexto "
    "fornecido. Se a informação não estiver no contexto, diga isso claramente. Responda em português.\n\n"
    "Contexto:\n{context}\n\nPergunta: {question}\n\nResposta:"
)

_COMPARE_PROMPT = (
    "Compare os dois trechos de documentação abaixo, em português, destacando semelhanças e diferenças "
    "relevantes. Use somente o que está nos textos, sem inventar.\n\n"
    "Trecho A ({label_a}):\n{text_a}\n\nTrecho B ({label_b}):\n{text_b}\n\nComparação:"
)


class QueryEngine:
    """Construído a partir de um `RAGService` já carregado (`rag_service.
    retriever` precisa existir). `answer(question)` é o único método
    público -- devolve o mesmo shape que `RAGService.ask_question_with_
    sources` já devolve (`{"answer", "sources"}`), com um campo `intent`
    a mais (qual caminho respondeu, útil pra transparência/depuração --
    `api/schemas.py::ChatResponse` expõe isso opcionalmente)."""

    def __init__(self, rag_service):
        self._rag = rag_service
        self._chunks: list[Document] = rag_service.retriever.chunks
        self._bm25 = rag_service.retriever.bm25_index

    def answer(self, question: str) -> dict[str, Any]:
        classified = classify_intent(question)

        if classified.intent == "structural_search":
            result = self._answer_structural(classified, question)
            if result is not None:
                return result
            # Nenhum chunk bateu com o capítulo pedido (documento sem essa
            # estrutura, ou número inexistente) -- cai pro caminho
            # semântico de sempre em vez de responder "não encontrei" sem
            # nem tentar a busca de verdade.
        elif classified.intent == "page_search":
            result = self._answer_page(classified, question)
            if result is not None:
                return result
        elif classified.intent == "lexical_search":
            result = self._answer_lexical(classified, question)
            if result is not None:
                return result
        elif classified.intent == "compare":
            result = self._answer_compare(classified, question)
            if result is not None:
                return result
        # "summarize" sem capítulo/página explícito (ex.: "resuma isso")
        # não tem um escopo estrutural pra filtrar -- cai pro caminho
        # semântico de sempre, que já teria os chunks mais relevantes via
        # busca híbrida.

        return self._answer_semantic(question)

    # ───────────────── structural_search / page_search (§16/§23) ─────────────────

    def _chunks_for_chapter(self, chapter_num: int) -> list[Document]:
        return [c for c in self._chunks if _chapter_number(c.metadata.get("chapter")) == chapter_num]

    def _chunks_for_page(self, page_num: int) -> list[Document]:
        return [
            c
            for c in self._chunks
            if c.metadata.get("page_start") is not None
            and c.metadata.get("page_end") is not None
            and c.metadata["page_start"] <= page_num <= c.metadata["page_end"]
        ]

    def _answer_structural(self, classified: ClassifiedIntent, question: str) -> dict[str, Any] | None:
        matched = self._chunks_for_chapter(classified.chapter)
        if not matched:
            return None

        if classified.wants_title_only:
            # §16, literal: "Qual é o título do capítulo 7?" -> chapter=7,
            # SEM LLM -- o próprio texto do heading já É a resposta.
            title = matched[0].metadata.get("chapter")
            return {
                "answer": title or "Não foi possível determinar o título deste capítulo.",
                "sources": _to_source_dicts(matched[:1]),
                "intent": "structural_search",
            }

        return self._answer_from_matched_chunks(matched, question, intent="structural_search")

    def _answer_page(self, classified: ClassifiedIntent, question: str) -> dict[str, Any] | None:
        matched = self._chunks_for_page(classified.page)
        if not matched:
            return None
        return self._answer_from_matched_chunks(matched, question, intent="page_search")

    def _answer_from_matched_chunks(self, matched: list[Document], question: str, *, intent: Intent) -> dict[str, Any]:
        """§23: "se pequeno: enviar contexto adequado ao LLM / se grande:
        resumo hierárquico" -- o tamanho é medido primeiro em Nº DE CHUNKS
        (proxy barato, decide qual dos dois caminhos usar) e, dentro do
        caminho direto, reforçado por um orçamento real de tokens
        (§35/§66, `_truncate_chunks_to_token_budget`) antes de montar o
        prompt -- nunca manda mais chunks do que o LLM confortavelmente
        processa numa única chamada."""
        if len(matched) <= _HIERARCHICAL_SUMMARY_THRESHOLD:
            budgeted = _truncate_chunks_to_token_budget(matched)
            context = _format_chunks_as_context(budgeted)
            answer = self._invoke_llm(_DIRECT_ANSWER_PROMPT.format(context=context, question=question))
        else:
            answer = self._hierarchical_summarize(matched)
        return {"answer": answer, "sources": _to_source_dicts(matched), "intent": intent}

    def _hierarchical_summarize(self, chunks: list[Document]) -> str:
        """§22, implementado ao pé da letra: chunks -> grupos -> resumos
        intermediários -> resumo final. Nº de chamadas ao LLM é
        `ceil(len(chunks)/_SUMMARY_GROUP_SIZE) + 1` -- muito menor que
        "1 chamada por chunk", e menor contexto por chamada que "tudo de
        uma vez", que é exatamente o que §15/§22 pedem pra evitar."""
        groups = [chunks[i : i + _SUMMARY_GROUP_SIZE] for i in range(0, len(chunks), _SUMMARY_GROUP_SIZE)]
        partial_summaries = [
            self._invoke_llm(_SUMMARY_PROMPT.format(context=_format_chunks_as_context(group))) for group in groups
        ]
        if len(partial_summaries) == 1:
            return partial_summaries[0]
        combined = "\n\n---\n\n".join(f"Resumo {i + 1}:\n{s}" for i, s in enumerate(partial_summaries))
        return self._invoke_llm(_FINAL_SUMMARY_PROMPT.format(summaries=combined))

    # ───────────────── lexical_search (§18) ─────────────────

    def _answer_lexical(self, classified: ClassifiedIntent, question: str) -> dict[str, Any] | None:
        """§18: "É útil para nomes, termos exatos, números... Não utilizar
        LLM para isso" -- a BUSCA em si é só BM25, sem embeddings e sem
        LLM na recuperação; o LLM só entra depois, pra fraseiar a resposta
        a partir dos poucos trechos já encontrados.

        Achado real (2026-09-02, confirmado lendo o código-fonte de
        `rank_bm25`, não só supondo): a fórmula de IDF que `BM25Okapi` usa
        (`log(N - freq + 0.5) - log(freq + 0.5)`) dá EXATAMENTE zero
        sempre que um termo aparece em precisamente metade dos documentos
        de uma coleção pequena (ex.: 1 de 2 documentos -- `log(1.5) -
        log(1.5) = 0`) -- não é um caso raro/artificial, é uma propriedade
        matemática real da fórmula que qualquer coleção pequena pode
        atingir. Como o score dessa palavra vira 0 em TODO documento (o
        IDF multiplica o score inteiro), o filtro antigo (`scores[i] > 0`)
        descartava um documento que genuinamente contém o termo procurado.
        Corrigido com um fallback determinístico (nenhum LLM/embedding
        envolvido, ainda 100% "busca lexical"): se o BM25 não achou nada,
        confere presença literal do termo nos tokens de cada chunk antes
        de desistir -- só then retorna None de verdade (nenhum chunk
        contém o termo, nem por BM25 nem por correspondência direta).
        """
        term_tokens = _tokenize(classified.term)
        scores = self._bm25.get_scores(term_tokens)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        matched = [self._chunks[i] for i in ranked[:5] if scores[i] > 0]

        if not matched:
            matched = [
                chunk for chunk in self._chunks if any(token in _tokenize(chunk.page_content) for token in term_tokens)
            ][:5]

        if not matched:
            return None
        context = _format_chunks_as_context(matched)
        answer = self._invoke_llm(_DIRECT_ANSWER_PROMPT.format(context=context, question=question))
        return {"answer": answer, "sources": _to_source_dicts(matched), "intent": "lexical_search"}

    # ───────────────── compare (§21 reranking + §31-33 comparação) ─────────────────

    def _answer_compare(self, classified: ClassifiedIntent, question: str) -> dict[str, Any] | None:
        """Comparação DENTRO da mesma coleção (ex.: "compare o capítulo 3 e
        o capítulo 5"). Comparação entre múltiplos DOCUMENTOS/grupos
        (prompt-mestre §31-33, "Livro A -> capítulo 3 / Livro B -> capítulo
        3") depende do conceito de "grupos de documentos", que não existe
        neste backend (confirmado ausente na auditoria desta sessão) --
        implementar isso exigiria construir esse recurso primeiro, fora do
        escopo desta rodada (que é sobre chunking/leitura dinâmica de
        busca, não sobre gestão de múltiplos documentos). Fica registrado,
        não implementado às cegas.
        """
        if len(classified.compare_chapters) < 2:
            return None
        chapter_a, chapter_b = classified.compare_chapters[0], classified.compare_chapters[1]
        chunks_a = self._chunks_for_chapter(chapter_a)
        chunks_b = self._chunks_for_chapter(chapter_b)
        if not chunks_a or not chunks_b:
            return None

        # Reranking (§21): "usar quando... comparação". Reordena cada lado
        # pelos trechos mais relevantes à PERGUNTA (não só ordem de
        # aparição no documento) antes de montar o contexto de comparação.
        chunks_a, reranked_a = self._rerank(question, chunks_a)
        chunks_b, reranked_b = self._rerank(question, chunks_b)
        chunks_a, chunks_b = chunks_a[:3], chunks_b[:3]

        label_a = chunks_a[0].metadata.get("chapter") or f"capítulo {chapter_a}"
        label_b = chunks_b[0].metadata.get("chapter") or f"capítulo {chapter_b}"
        answer = self._invoke_llm(
            _COMPARE_PROMPT.format(
                label_a=label_a,
                text_a=_format_chunks_as_context(chunks_a),
                label_b=label_b,
                text_b=_format_chunks_as_context(chunks_b),
            )
        )
        result: dict[str, Any] = {
            "answer": answer,
            "sources": _to_source_dicts(chunks_a + chunks_b),
            "intent": "compare",
        }
        # Transparência com o usuário (não desvalorizar a ferramenta
        # escondendo o degradê): se o modelo de reranking não pôde ser
        # baixado agora (sem internet nesse instante específico -- ele só
        # é baixado na primeira vez que é usado, não vem embutido no
        # projeto), a resposta continua completa e correta, só não passou
        # pelo refinamento extra de ordenação. Isso é dito explicitamente
        # em vez de silenciosamente degradar sem avisar.
        if not (reranked_a and reranked_b):
            result["notice"] = (
                "Comparação concluída normalmente. O passo extra de reordenar os trechos "
                "por relevância (reranking) não pôde ser aplicado agora — o modelo usado "
                "nesse refinamento só é baixado na primeira vez que é necessário, e isso "
                "exige internet no momento exato da pergunta. A resposta abaixo é completa "
                "e real, só sem esse ajuste fino extra."
            )
        return result

    def _rerank(self, question: str, chunks: list[Document]) -> tuple[list[Document], bool]:
        """Camada OPCIONAL (§21: "Reranking não deve acontecer em todas as
        consultas... Criar camada opcional") -- só é chamada pelos
        caminhos que o próprio prompt lista como gatilho real (comparação;
        ver `_answer_compare` acima). Usa um cross-encoder real
        (sentence-transformers, já uma dependência existente do projeto --
        nenhuma biblioteca nova) em vez de reordenar por um proxy
        qualquer.

        Devolve (chunks, reranked) -- o booleano permite que o chamador
        avise o usuário quando a ordenação não pôde ser aplicada (modelo
        não baixado por falta de internet nesse instante), em vez de
        degradar silenciosamente sem explicar por quê."""
        if len(chunks) <= 1:
            return chunks, True
        try:
            from sentence_transformers import CrossEncoder

            reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            pairs = [(question, chunk.page_content) for chunk in chunks]
            scores = reranker.predict(pairs)
            order = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)
            return [chunks[i] for i in order], True
        except Exception:  # noqa: BLE001 -- reranking é um refinamento, nunca deveria quebrar a resposta
            return chunks, False

    # ───────────────── semantic_synthesis (caminho de sempre, inalterado) ─────────────────

    def _answer_semantic(self, question: str) -> dict[str, Any]:
        result = self._rag._invoke_with_fallback(question)
        answer = result.get("result", "")
        source_docs = result.get("source_documents") or []
        return {"answer": answer, "sources": _to_source_dicts(source_docs), "intent": "semantic_synthesis"}

    # ───────────────── LLM direto (fora da chain RetrievalQA) ─────────────────

    def _invoke_llm(self, prompt: str) -> str:
        """Mesmo padrão de fallback entre provedores que `RAGService.
        _invoke_with_fallback` já usa pro caminho semântico -- reaproveitado
        aqui pra chamada direta ao LLM (sem passar pela chain RetrievalQA,
        já que os prompts deste módulo não usam retrieval genérico, o
        contexto já foi filtrado estruturalmente antes)."""
        from .rag import PROVIDER_FALLBACK_ORDER, build_chat_llm

        try:
            return self._rag.llm.invoke(prompt).content
        except Exception:  # noqa: BLE001 -- tenta os provedores de fallback, mesma lista/ordem de rag.py
            for candidate in PROVIDER_FALLBACK_ORDER:
                if candidate == self._rag.provider:
                    continue
                try:
                    fallback_llm = build_chat_llm(candidate, None, self._rag.api_key)
                    return fallback_llm.invoke(prompt).content
                except Exception:  # noqa: BLE001 -- tenta o próximo candidato
                    continue
            raise
