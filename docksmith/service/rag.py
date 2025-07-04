import os
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_community.embedding import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISES
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate



class RAGService:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="all-MiniLM-L6-v2"
        )
        self.llm = ChatGroq(
            groq_api_key=os.getenv("GROQ_API_KEY"),
            model_name="llama-3.1-8b-instant" # llama3-8b-8192
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        self.vector_store = None
        self.qa_chain = None

    def load_collection(self, collection_name):
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
        
        texts = self.text_splitter.split_documents(documents)
        self.vector_store = FAISES.from_documents(texts, self.embeddings)

        template = """
            Você é o Docksmith 🛠️, um assistente treinado para responder apenas com base na documentação abaixo.

            Regras:
            - Use **somente** as informações fornecidas em {context}.
            - Se não encontrar a resposta, diga: "Essa informação não está na documentação."
            - Responda de forma clara, objetiva e em português.
            - Quando útil, use listas ou exemplos em código com formatação Markdown.

            Pergunta:
            {question}

            Resposta:
        """

        prompt = PromptTemplate(
            template=template,
            input_variables=["context", "question"]
        )

        self.qa_chain = RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=self.vector_store.as_retriever(search_kwargs={"k": 3}),
            chain_type_kwargs={"prompt": prompt}
        )

        return True

    def ask_question(self, question):
        """Asks question using rag"""
        if not self.qa_chain:
            return "No loaded collection."
        try:
            result = self.qa_chain.run(question)
            return result
        except Exception as e:
            return f"Error when processing question: {str(e)}"
