# 📃 Docksmith - Knowledge Extraction, the Smart Way

Docksmith é um assistente técnico com suporte a Web Scraping e RAG (Retrieval-Augmented Generation), permitindo que você extraia e converse com conteúdo técnico de forma inteligente e documentada.

---

## 🧠 Funcionalidades

- ✅ Web Scraping de sites e conversão automática para Markdown
- ✅ Geração vetorial de documentos com embeddings (FAISS + HuggingFace)
- ✅ Chat inteligente com contexto baseado nos seus próprios documentos
- ✅ Interface interativa com Streamlit

---

## 📁 Estrutura do Projeto

```
docksmith-app/
├── docksmith/
│   ├── app.py                     # Arquivo principal do Streamlit
│   ├── presentation/             # Camada de apresentação
│   │   ├── chat.py               # Página de chat com os documentos
│   │   └── scraping.py           # Página de scraping web
│   └── service/                  # Camada de serviços
│       ├── rag.py                # Serviço de IA com RAG + LangChain + Groq
│       └── scraping.py           # Serviço de Web Scraping com Firecrawl
├── data/collections/            # Onde os arquivos markdown extraídos são salvos
├── pyproject.toml               # Gerenciador de dependências com Poetry
└── README.md                    # (Este arquivo)
```

---

## ⚙️ Requisitos

- Python 3.12+
- [Poetry](https://python-poetry.org/) para gerenciamento de dependências
- Docker Desktop (para rodar o Firecrawl localmente)

---

## 📦 Instalação com Poetry

```bash
# Clonar o projeto
git clone https://github.com/seu-usuario/docksmith-app.git
cd docksmith-app

# Ativar ambiente com Poetry
poetry install
poetry shell
```

---

## 🚀 Executando a aplicação

```bash
streamlit run docksmith/app.py
```

Acesse: [http://localhost:8501](http://localhost:8501)

---

## 🌐 Executando o Firecrawl com Docker

Certifique-se de estar na pasta onde o projeto do Firecrawl foi clonado.

```bash
docker compose up
```

A API do Firecrawl ficará disponível em `http://localhost:3002`.

---

## 🧪 Variáveis de Ambiente (.env)

```env
FIRECRAWL_API_KEY=devkey
FIRECRAWL_API_URL=http://localhost:3002
GROQ_API_KEY=sua_chave_groq_aqui
```

---

## 🤖 Trocar o modelo de IA

Edite o arquivo `rag.py` na linha onde é definido o modelo:

```python
self.llm = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model_name="llama-3.1-8b-instant"  # por exemplo
)
```

Modelos suportados:

- `llama-3.1-8b-instant`
- `gemma2-9b-it`
- `llama-3.3-70b-versatile`

❗ **Evite usar modelos como `whisper-*` — são voltados para transcrição de áudio.**

---

## 🧰 Dependências principais

Constam no `pyproject.toml`:

- `streamlit`
- `firecrawl`
- `langchain`, `langchain-community`, `langchain-core`, `langchain-groq`
- `faiss-cpu`
- `sentence-transformers`
- `python-dotenv`

---

## 🛠️ Logs e Debugs

O projeto agora conta com logs estratégicos nos serviços (`rag.py` e `scraping.py`), facilitando a identificação de erros e o fluxo de execução.

</br>
</br>

### ⚙️ Lógica de Funcionamento do Docksmith

---

O **Docksmith** foi criado para permitir a extração inteligente de conhecimento a partir de conteúdos online, combinando **scraping** com **RAG (Retrieval-Augmented Generation)**. A seguir está um resumo do fluxo principal:

---

#### 1. 🕸️ Coleta de Conteúdo com Firecrawl

- O usuário informa uma URL e o nome da coleção.
- O **Firecrawl** (executado via Docker) realiza o mapeamento dos links e faz o scraping do conteúdo.
- Os conteúdos extraídos são convertidos em Markdown (`.md`) e salvos em `data/collections/<nome_da_colecao>`.

---

#### 2. 📁 Gerenciamento de Coleções

- As coleções são listadas automaticamente na barra lateral da interface Streamlit.
- Ao selecionar uma, os documentos `.md` são carregados e divididos em chunks utilizando `RecursiveCharacterTextSplitter`.
- Esses chunks são transformados em **vetores** usando `HuggingFaceEmbeddings` e armazenados no **FAISS**, formando uma base vetorial para busca semântica.

---

#### 3. 💬 Chat com RAG (Retrieval-Augmented Generation)

- Quando o usuário envia uma pergunta, o modelo de linguagem (via **Groq API**) é chamado.
- O sistema busca os documentos mais relevantes na base vetorial (`FAISS`) como contexto.
- A pergunta e o contexto são passados para o modelo que gera uma resposta baseada **somente no que foi carregado da coleção**.

---

#### 4. 📜 Restrições do Assistente

O prompt enviado ao modelo LLM é cuidadosamente elaborado para garantir:

- O assistente responde **apenas com base na documentação carregada**.
- Se a informação **não estiver presente**, o modelo deve dizer: `"Essa informação não está na documentação."`
- O estilo da resposta é claro, técnico e com exemplos quando aplicável (listas, Markdown, trechos de código).

---

Essa abordagem garante respostas confiáveis, contextuais e baseadas em dados reais extraídos da web ou de outras fontes documentais.
