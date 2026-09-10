import logging, traceback, uuid
from typing import Any, List

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

# Força baixar para cache local
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Modelo padrão por provedor. "groq" é o comportamento histórico do Docksmith;
# os demais só são exercitados quando o chamador (api/) informa provider/api_key.
#
# Achado real, ao vivo em produção (2026-08-27): "llama-3.3-70b-versatile"
# passou a exigir tier Enterprise na Groq (confirmado na doc oficial,
# console.groq.com/docs/models) — toda pergunta ao RAG estava falhando com
# 404 "model does not exist or you do not have access to it", mesmo com a
# GROQ_API_KEY do servidor correta. "llama-3.1-8b-instant" e "gemma2-9b-it"
# (usados como alternativas em api/providers.py) sofrem do mesmo problema —
# o segundo nem aparece mais no catálogo da Groq. Substituídos pelos únicos
# modelos confirmados disponíveis no tier padrão hoje: a família GPT-OSS.
DEFAULT_MODELS = {
    "groq": "openai/gpt-oss-120b",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
    "google": "gemini-2.0-flash",
}

# Ordem de fallback quando um provedor falha na hora de gerar a resposta
# (2026-09-02, prompt-mestre "Docksmith" §11 -- achado real, já
# documentado em docs/04-api-backend.md: "sem retry/backoff... falha do
# provedor vira erro direto para o usuário"). Cada provedor cai pro
# próximo da lista (nunca ele mesmo); Groq primeiro por ser o único que
# não exige chave própria do usuário.
PROVIDER_FALLBACK_ORDER = ["groq", "openai", "anthropic", "google"]


def build_chat_llm(provider: str = "groq", model_name: str | None = None, api_key: str | None = None):
    """Fábrica de LLM de chat compartilhada entre o RAGService e a camada de API.

    Mantida como função de módulo (em vez de método) para que api/ possa
    validar uma combinação provider/model/api_key ("testar conexão") sem
    precisar instanciar todo o RAGService (embeddings + FAISS).
    """
    provider = (provider or "groq").lower()
    model_name = model_name or DEFAULT_MODELS.get(provider, DEFAULT_MODELS["groq"])

    if provider == "groq":
        return ChatGroq(groq_api_key=api_key, model_name=model_name)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(api_key=api_key, model=model_name)
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(api_key=api_key, model=model_name)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(google_api_key=api_key, model=model_name)
    raise ValueError(f"Unsupported provider: {provider}")


# Expostos como constantes de módulo (não só argumentos inline) para que
# api/resource_estimate.py consiga estimar o nº de chunks de uma coleção
# usando exatamente a mesma conta que o splitter real vai fazer depois —
# sem duplicar um "número mágico" separado que pode desalinhar com o tempo.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# Constante padrão da técnica RRF (Reciprocal Rank Fusion) -- o valor
# sugerido pelo próprio prompt-mestre "Docksmith" §20/§21. Amortece o peso
# de posições de rank muito altas sem zerar contribuições de rank baixo.
RRF_K = 60


def _tokenize(text: str) -> list[str]:
    """Tokenização simples (minúsculas + split por espaço) para o índice
    BM25 -- suficiente para português/inglês técnico sem precisar de um
    tokenizador com modelo próprio; o denso (embeddings) já cobre a parte
    semântica, o léxico só precisa achar termo exato (nomes, códigos,
    números) de forma barata."""
    return text.lower().split()


class HybridRetriever(BaseRetriever):
    """Fusão RRF (Reciprocal Rank Fusion) entre um índice léxico (BM25) e
    a busca densa (FAISS) já existente -- prompt-mestre "Docksmith" §18-21:
    "Não depender exclusivamente de embeddings."

    ``score(chunk) = Σ 1/(RRF_K + rank_i)`` somado sobre as listas de rank
    do BM25 e do FAISS (rank ausente em uma lista simplesmente não soma
    nada para aquela lista -- não é penalizado como "pior que o último").
    Implementa ``BaseRetriever`` (a forma idiomática do LangChain para
    plugar um retriever customizado num ``RetrievalQA`` já existente),
    substituindo diretamente ``vector_store.as_retriever()``.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    vector_store: Any
    bm25_index: Any
    chunks: List[Document]
    k: int = 3
    fetch_k: int = 20  # candidatos considerados de cada lista antes da fusão

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> List[Document]:
        dense_hits = self.vector_store.similarity_search(query, k=min(self.fetch_k, len(self.chunks)))
        # Mapear de volta pro índice em `self.chunks` -- FAISS devolve os
        # próprios objetos Document, comparados aqui pela mesma identidade
        # de conteúdo+metadado já atribuída em load_collection.
        content_to_index = {id(doc): i for i, doc in enumerate(self.chunks)}
        dense_ranks: dict[int, int] = {}
        for rank, doc in enumerate(dense_hits):
            idx = content_to_index.get(id(doc))
            if idx is None:
                # FAISS às vezes devolve uma cópia, não o mesmo objeto --
                # cai pra correspondência por conteúdo (mais lenta, só no
                # caminho de exceção).
                idx = next((i for i, c in enumerate(self.chunks) if c.page_content == doc.page_content), None)
            if idx is not None:
                dense_ranks[idx] = rank

        bm25_scores = self.bm25_index.get_scores(_tokenize(query))
        lexical_order = sorted(range(len(bm25_scores)), key=lambda i: bm25_scores[i], reverse=True)
        lexical_ranks = {idx: rank for rank, idx in enumerate(lexical_order[: self.fetch_k])}

        fused_scores: dict[int, float] = {}
        for idx, rank in dense_ranks.items():
            fused_scores[idx] = fused_scores.get(idx, 0.0) + 1.0 / (RRF_K + rank)
        for idx, rank in lexical_ranks.items():
            fused_scores[idx] = fused_scores.get(idx, 0.0) + 1.0 / (RRF_K + rank)

        ranked_indices = sorted(fused_scores.keys(), key=lambda i: fused_scores[i], reverse=True)
        return [self.chunks[i] for i in ranked_indices[: self.k]]


class RAGService:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"}  # força usar CPU
        )
        self.llm = None
        # Prioridade real de divisão (prompt-mestre §13, 3ª rodada: "1.
        # capítulo; 2. seção; 3. heading; 4. parágrafo; 5. sentença; 6.
        # tamanho máximo") -- capítulo/seção/heading já são respeitados
        # ANTES deste splitter sequer rodar (cada `LoadedDocument` já é uma
        # unidade estrutural própria: 1 página de PDF ou 1 seção de DOCX,
        # ver document_loader.py e `_split_document_preserving_structure`
        # abaixo, que só invoca este splitter quando essa unidade é grande
        # demais pra virar 1 chunk só). Os separadores abaixo cobrem os 2
        # últimos níveis da prioridade -- parágrafo (`\n\n`/`\n`) antes de
        # sentença (pontuação), tamanho máximo só como último recurso.
        # Antes desta rodada, o splitter usava a lista padrão do LangChain
        # (`["\n\n", "\n", " ", ""]`), que pula direto de parágrafo pra
        # espaço -- nunca tentava quebrar por sentença, então um parágrafo
        # grande sempre ia parar no corte bruto por tamanho.
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", ". ", "! ", "? ", ".\n", "!\n", "?\n", " ", ""],
        )
        self.vector_store = None
        self.qa_chain = None
        self.retriever = None
        self.prompt = None
        self.provider = "groq"
        self.model_name = None
        self.api_key = None

    # Nº de trechos recuperados por profundidade — controla o quanto de
    # contexto o LLM recebe para responder (mais trechos = análise mais
    # profunda, porém mais lenta e mais cara).
    DEPTH_K = {"rapida": 2, "equilibrada": 3, "profunda": 6}

    def load_collection(
        self,
        markdown_list,
        groq_api_key=None,
        provider="groq",
        model_name=None,
        api_key=None,
        depth="equilibrada",
        source_labels=None,
        structure_metadata=None,
        embedding_batch_size=None,
    ):
        """Indexa uma coleção e prepara a QA chain.

        Compatibilidade: chamadas antigas `load_collection(docs, groq_key)` continuam
        funcionando (provider="groq" por padrão, profundidade "equilibrada" = k=3,
        idêntico ao comportamento original). `provider`/`model_name`/`api_key`/`depth`
        são usados pela camada de API para permitir escolha de modelo de IA por sessão.

        `source_labels` (2026-09-02, opcional): lista paralela a
        `markdown_list` com um nome/URL de origem por documento, usada só
        pra enriquecer a citação de fonte (`ask_question_with_sources`) --
        nunca obrigatório, nunca quebra uma chamada que não o informa.

        `structure_metadata` (2026-09-02, 3ª rodada, opcional): lista
        paralela a `markdown_list` de dicts `{"chapter", "section",
        "page_start", "page_end"}` -- vem de `document_loader.py` via
        `api/routers/documents.py`/`api/sessions.py` (`collection_structure`,
        mesmo padrão de `collection_labels`). Ausente/`None`/entrada sem
        alguma chave = aquele campo fica `None` no chunk, exatamente como
        antes desta rodada -- coleções raspadas por URL (que nunca passam
        isso) continuam funcionando idênticas a antes; `query_engine.py`
        trata ausência de estrutura como "essa busca estrutural não se
        aplica aqui", nunca como erro.

        `embedding_batch_size` (Fase G, 2026-09-10, opcional): constrói o
        índice FAISS em lotes de N chunks por vez, em vez de `FAISS.
        from_documents(texts, self.embeddings)` numa chamada só -- ver
        `_build_vector_store_in_batches` abaixo. `None` (o padrão, também
        o que o Streamlit sempre usa -- `docksmith/presentation/chat.py`
        nunca passa esse parâmetro) preserva o comportamento de sempre,
        byte a byte: 1 chamada só, resultado idêntico.
        """
        try:
            logging.info("Loading in-memory collection with %d docs", len(markdown_list))

            resolved_key = api_key or groq_api_key
            self.llm = build_chat_llm(provider, model_name, resolved_key)
            self.provider, self.model_name, self.api_key = provider, model_name, resolved_key
            logging.info("LLM configurado: provider=%s model=%s", provider, model_name or DEFAULT_MODELS.get(provider))

            # Metadado real de proveniência por chunk (prompt-mestre
            # "Docksmith" §9/§13/§55: document_id/chunk_id/document_index/
            # chunk_index/chapter/section/page_start/page_end) -- cada
            # Document de origem carrega isso tudo, e o splitter do
            # LangChain propaga (copia) o metadado para cada chunk
            # resultante -- só falta numerar chunk_index/gerar chunk_id
            # depois do split.
            docs: list[Document] = []
            for i, md in enumerate(markdown_list):
                struct = structure_metadata[i] if structure_metadata and i < len(structure_metadata) else {}
                docs.append(
                    Document(
                        page_content=md,
                        metadata={
                            "document_id": uuid.uuid4().hex,
                            "document_index": i,
                            "source_label": (source_labels[i] if source_labels and i < len(source_labels) else f"documento_{i}"),
                            "chapter": struct.get("chapter") if struct else None,
                            "section": struct.get("section") if struct else None,
                            "page_start": struct.get("page_start") if struct else None,
                            "page_end": struct.get("page_end") if struct else None,
                        },
                    )
                )
            texts = self._split_documents_preserving_structure(docs)
            for chunk_index, chunk in enumerate(texts):
                chunk.metadata["chunk_index"] = chunk_index
                chunk.metadata["chunk_id"] = uuid.uuid4().hex

            self.vector_store = self._build_vector_store_in_batches(texts, embedding_batch_size)
            logging.info("FAISS index created with %d chunks", len(texts))

            # Índice léxico (BM25), ao lado do denso já existente --
            # prompt-mestre §18-21: "Não depender exclusivamente de
            # embeddings." Construído a partir dos MESMOS chunks, então os
            # dois rankings do HybridRetriever sempre indexam a mesma lista.
            bm25_index = BM25Okapi([_tokenize(chunk.page_content) for chunk in texts])
            logging.info("BM25 index created with %d chunks", len(texts))

            template = """
                Você é o Docksmith 🛠️, um assistente técnico especializado em responder perguntas com base **exclusiva** na documentação a seguir.

                🔒 Regras obrigatórias:
                - Use **somente** as informações fornecidas em {context}.
                - Se a informação **não estiver claramente descrita**, diga: "Essa informação não está na documentação."
                - Nunca invente respostas ou adicione conhecimento externo.

                📘 Estilo da Resposta:
                - Responda em **português claro e técnico**, com foco em ensinar de forma didática.
                - Quando apropriado, use:
                    - **Listas numeradas** ou com marcadores para organizar informações.
                    - **Trechos de código formatados em Markdown** para exemplos técnicos.
                    - **Explicações detalhadas** quando o conteúdo permitir.
                    - **Passo a passo** se a pergunta envolver procedimentos.

                🎯 Estrutura da Resposta:
                - Comece com uma **conclusão objetiva** (1-2 frases, respondendo diretamente à pergunta).
                - Em seguida, apresente a **fundamentação**: a evidência e o detalhamento de {context} que sustentam essa conclusão.
                - Essa estrutura (conclusão primeiro, fundamentação depois) vale quando a pergunta permite uma resposta direta; para perguntas puramente exploratórias, mantenha a organização mais natural ao conteúdo.

                📌 Objetivo:
                - Ser preciso, confiável e útil como um verdadeiro engenheiro de software lendo a documentação.
                - Se possível, **contextualize** a informação com base nos arquivos/documentos fornecidos.

                📥 Documentação:
                {context}

                ❓ Pergunta:
                {question}

                🧠 Resposta:
            """

            self.prompt = PromptTemplate(template=template, input_variables=["context", "question"])

            k = self.DEPTH_K.get(depth, self.DEPTH_K["equilibrada"])
            self.retriever = HybridRetriever(vector_store=self.vector_store, bm25_index=bm25_index, chunks=texts, k=k)
            self.qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=self.retriever,
                chain_type_kwargs={"prompt": self.prompt},
                return_source_documents=True,
            )

            return True
        except Exception as e:
            logging.error("Error loading collection: %s", e)
            logging.debug(traceback.format_exc())
            return False

    def _build_vector_store_in_batches(self, texts: list[Document], batch_size: int | None) -> "FAISS":
        """Constrói o índice FAISS em lotes de `batch_size` chunks por vez,
        em vez de `FAISS.from_documents(texts, self.embeddings)` de uma
        tacada só (Fase G, evolução "livros grandes", 2026-09-10).
        `batch_size` ausente/None/<=0/>= `len(texts)` preserva o
        comportamento de sempre -- 1 chamada só, resultado idêntico (não
        muda ordem nem conteúdo do índice, só o RITMO em que os vetores
        entram nele).

        Nota de honestidade técnica (auditoria, não estimativa): o ganho
        real aqui é limitar o PICO de memória de vetores retidos
        simultaneamente antes de entrar no índice -- não elimina o custo
        total (a mesma quantidade de embeddings é calculada de qualquer
        forma). `sentence-transformers` já faz batching interno na hora de
        calcular (`encode(batch_size=32)` por padrão, dentro de
        `HuggingFaceEmbeddings`) -- este lote é uma camada ACIMA disso, no
        nível de "quantos chunks entram no índice de uma vez", não uma
        reimplementação do que a biblioteca já faz por dentro."""
        if not batch_size or batch_size <= 0 or batch_size >= len(texts):
            return FAISS.from_documents(texts, self.embeddings)

        total_batches = -(-len(texts) // batch_size)  # ceil division
        vector_store = None
        for batch_number, start in enumerate(range(0, len(texts), batch_size), start=1):
            batch = texts[start : start + batch_size]
            if vector_store is None:
                vector_store = FAISS.from_documents(batch, self.embeddings)
            else:
                vector_store.add_documents(batch)
            logging.info("Lote de embeddings %d/%d indexado (%d chunks)", batch_number, total_batches, len(batch))
        return vector_store

    def _split_documents_preserving_structure(self, docs: list[Document]) -> list[Document]:
        """Prioridade real de chunking (prompt-mestre §13): capítulo/seção/
        heading já são a fronteira de cada `Document` de entrada (1 página
        de PDF ou 1 seção de DOCX, ver document_loader.py) -- então o
        primeiro passo aqui é NUNCA quebrar uma unidade estrutural que já
        cabe inteira num chunk (`len(text) <= CHUNK_SIZE`), evitando
        "quebra desnecessária de estruturas" que o prompt pede pra evitar.
        Só quando uma unidade estrutural É maior que CHUNK_SIZE é que ela
        passa pelo `self.text_splitter` (parágrafo → sentença → tamanho
        máximo, ver os separadores configurados em `__init__`)."""
        result: list[Document] = []
        for doc in docs:
            if len(doc.page_content) <= CHUNK_SIZE:
                result.append(doc)
            else:
                result.extend(self.text_splitter.split_documents([doc]))
        return result

    def ask_question(self, question):
        """Compatível com o uso atual do Streamlit: retorna só o texto da resposta."""
        return self.ask_question_with_sources(question)["answer"]

    def ask_question_with_sources(self, question):
        """Retorna resposta + trechos-fonte usados (para o painel de evidências da API).

        Fallback entre provedores (2026-09-02, achado real -- ver
        PROVIDER_FALLBACK_ORDER): se a chamada ao provedor configurado
        falhar, tenta uma vez, em sequência, com cada provedor alternativo
        que já tenha uma chave resolvida (server-side ou do próprio
        usuário) -- sem repetir o mesmo provedor, sem retry infinito.

        3ª rodada (2026-09-02, prompt-mestre §15-§23 "leitura dinâmica de
        busca"): a pergunta passa primeiro por `QueryEngine` (classificação
        determinística de intenção, zero LLM) -- só perguntas que não
        casam com nenhum padrão estrutural/lexical/comparação (a maioria
        das perguntas conceituais, ex.: "como o autor explica X") caem no
        caminho semântico de sempre (`_invoke_with_fallback`, RetrievalQA
        + busca híbrida, idêntico a antes desta rodada). Nenhuma mudança
        de comportamento pra quem já usava o Docksmith antes de hoje.
        """
        if not self.qa_chain:
            return {"answer": "No loaded collection.", "sources": []}
        try:
            from .query_engine import QueryEngine

            result = QueryEngine(self).answer(question)
            logging.info(
                "Pergunta respondida (intent=%s fontes=%d)", result.get("intent"), len(result.get("sources", []))
            )
            return result
        except Exception as e:
            logging.error("Error in QA: %s", e)
            logging.debug(traceback.format_exc())
            return {"answer": f"Error when processing question: {str(e)}", "sources": []}

    def _invoke_with_fallback(self, question: str) -> dict:
        try:
            return self.qa_chain.invoke({"query": question})
        except Exception as first_error:
            logging.warning("Provedor %s falhou (%s), tentando fallback", self.provider, first_error)
            for candidate in PROVIDER_FALLBACK_ORDER:
                if candidate == self.provider:
                    continue
                try:
                    fallback_llm = build_chat_llm(candidate, None, self.api_key)
                    # Reaproveita o retriever e o prompt já construídos
                    # (índices/instrução não mudam por provedor) -- só o
                    # LLM da chain é trocado.
                    fallback_chain = RetrievalQA.from_chain_type(
                        llm=fallback_llm,
                        chain_type="stuff",
                        retriever=self.retriever,
                        chain_type_kwargs={"prompt": self.prompt},
                        return_source_documents=True,
                    )
                    result = fallback_chain.invoke({"query": question})
                    logging.info("Fallback para provedor %s funcionou", candidate)
                    return result
                except Exception as fallback_error:  # noqa: BLE001 -- tentar o próximo candidato
                    logging.warning("Fallback %s também falhou (%s)", candidate, fallback_error)
                    continue
            raise first_error
