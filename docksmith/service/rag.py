import logging, traceback
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain.docstore.document import Document

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

class RAGService:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self.llm = ChatGroq(
            groq_api_key=None,  # será setado depois
            model_name="llama-3.3-70b-versatile"
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        self.vector_store = None
        self.qa_chain = None

    def load_collection(self, markdown_list, groq_api_key):
        try:
            logging.info("Loading in-memory collection with %d docs", len(markdown_list))

            self.llm.groq_api_key = groq_api_key

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
                - Quando apropriado, use listas, exemplos em código ou passo a passo.

                📥 Documentação:
                {context}

                ❓ Pergunta:
                {question}

                🧠 Resposta:
            """

            prompt = PromptTemplate(template=template, input_variables=["context", "question"])

            self.qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=self.vector_store.as_retriever(search_kwargs={"k": 3}),
                chain_type_kwargs={"prompt": prompt}
            )

            return True
        except Exception as e:
            logging.error("Error loading collection: %s", e)
            logging.debug(traceback.format_exc())
            return False

    def ask_question(self, question):
        if not self.qa_chain:
            return "No loaded collection."
        try:
            result = self.qa_chain.run(question)
            return result
        except Exception as e:
            logging.error("Error in QA: %s", e)
            logging.debug(traceback.format_exc())
            return f"Error when processing question: {str(e)}"

