import os, logging, traceback
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

class RAGService:
    def __init__(self):
        # Define the embeddings model to transform texts into semantic vectors
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2"
        )
        # Define the LLM model to be used via Groq
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.3-70b-versatile" # llama3-8b-8192
        )
        # Splits text into smaller blocks with overlap
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        self.vector_store = None
        self.qa_chain = None

        logging.info("RAGService started with model %s", self.llm.model_name)

    def load_collection(self, collection_name):
        try:
            logging.info("Loading collection: %s", collection_name)

            # Load all Markdown files from the specified collection
            collection_path = f"data/collections/{collection_name}"
            loader = DirectoryLoader(
                collection_path,
                glob="**/*.md",
                loader_cls=TextLoader,
                loader_kwargs={'encoding': 'utf-8'}
            )

            documents = loader.load()
            if not documents:
                return False
            
            # Applies the text division and creates the vector index
            texts = self.text_splitter.split_documents(documents)
            self.vector_store = FAISS.from_documents(texts, self.embeddings)

            logging.info("FAISS index created with %d chunks", len(texts))

            # Detailed and contextualized prompt for the wizard to answer based on the documentation
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

                📌 Objetivo:
                - Ser preciso, confiável e útil como um verdadeiro engenheiro de software lendo a documentação.
                - Se possível, **contextualize** a informação com base nos arquivos/documentos fornecidos.

                📥 Documentação:
                {context}

                ❓ Pergunta:
                {question}

                🧠 Resposta:
            """

            prompt = PromptTemplate(
                template=template,
                input_variables=["context", "question"]
            )

            # Create the RAG chain with recovery and response generation   
            self.qa_chain = RetrievalQA.from_chain_type(
                llm=self.llm,
                chain_type="stuff",
                retriever=self.vector_store.as_retriever(search_kwargs={"k": 3}),
                chain_type_kwargs={"prompt": prompt}
            )

            return True
        except Exception as e:
                logging.error("Error loading collection %s: %s", collection_name, e)
                logging.debug(traceback.format_exc())
                return False

    def ask_question(self, question):
        # Processes the question and returns the answer using RAG
        if not self.qa_chain:
            return "No loaded collection."
        try:
            logging.info("Question received: %s", question[:80])
            result = self.qa_chain.run(question)
            return result
        except Exception as e:
            logging.error("Error in QA: %s", e)
            logging.debug(traceback.format_exc())
            return f"Error when processing question: {str(e)}"
