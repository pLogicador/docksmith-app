import logging, traceback
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document
from sentence_transformers import SentenceTransformer

# Força baixar para cache local
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", device="cpu")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Modelo padrão por provedor. "groq" é o comportamento histórico do Docksmith;
# os demais só são exercitados quando o chamador (api/) informa provider/api_key.
DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-5",
    "google": "gemini-2.0-flash",
}


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


class RAGService:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2",
            model_kwargs={"device": "cpu"}  # força usar CPU
        )
        self.llm = None
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        self.vector_store = None
        self.qa_chain = None

    # Nº de trechos recuperados por profundidade — controla o quanto de
    # contexto o LLM recebe para responder (mais trechos = análise mais
    # profunda, porém mais lenta e mais cara).
    DEPTH_K = {"rapida": 2, "equilibrada": 3, "profunda": 6}

    def load_collection(
        self, markdown_list, groq_api_key=None, provider="groq", model_name=None, api_key=None, depth="equilibrada"
    ):
        """Indexa uma coleção e prepara a QA chain.

        Compatibilidade: chamadas antigas `load_collection(docs, groq_key)` continuam
        funcionando (provider="groq" por padrão, profundidade "equilibrada" = k=3,
        idêntico ao comportamento original). `provider`/`model_name`/`api_key`/`depth`
        são usados pela camada de API para permitir escolha de modelo de IA por sessão.
        """
        try:
            logging.info("Loading in-memory collection with %d docs", len(markdown_list))

            resolved_key = api_key or groq_api_key
            self.llm = build_chat_llm(provider, model_name, resolved_key)
            logging.info("LLM configurado: provider=%s model=%s", provider, model_name or DEFAULT_MODELS.get(provider))

            docs = [Document(page_content=md) for md in markdown_list]
            texts = self.text_splitter.split_documents(docs)
            self.vector_store = FAISS.from_documents(texts, self.embeddings)

            logging.info("FAISS index created with %d chunks", len(texts))

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

            prompt = PromptTemplate(template=template, input_variables=["context", "question"])

            k = self.DEPTH_K.get(depth, self.DEPTH_K["equilibrada"])
            self.qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=self.vector_store.as_retriever(search_kwargs={"k": k}),
                chain_type_kwargs={"prompt": prompt},
                return_source_documents=True,
            )

            return True
        except Exception as e:
            logging.error("Error loading collection: %s", e)
            logging.debug(traceback.format_exc())
            return False

    def ask_question(self, question):
        """Compatível com o uso atual do Streamlit: retorna só o texto da resposta."""
        return self.ask_question_with_sources(question)["answer"]

    def ask_question_with_sources(self, question):
        """Retorna resposta + trechos-fonte usados (para o painel de evidências da API)."""
        if not self.qa_chain:
            return {"answer": "No loaded collection.", "sources": []}
        try:
            result = self.qa_chain.invoke({"query": question})
            answer = result.get("result", "")
            source_docs = result.get("source_documents") or []
            sources = [
                {"index": i, "excerpt": doc.page_content[:500]}
                for i, doc in enumerate(source_docs)
            ]
            logging.info("Pergunta respondida (fontes=%d)", len(sources))
            return {"answer": answer, "sources": sources}
        except Exception as e:
            logging.error("Error in QA: %s", e)
            logging.debug(traceback.format_exc())
            return {"answer": f"Error when processing question: {str(e)}", "sources": []}

