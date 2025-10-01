# 📚 Docksmith - Knowledge Extraction, the Smart Way

Docksmith é um assistente técnico para extração e consulta de conhecimento, combinando Web Scraping e RAG (Retrieval-Augmented Generation) em uma interface interativa.

Ele permite que você colecione informações de sites técnicos e faça perguntas inteligentes com base nesses conteúdos, em um ambiente simples e confiável.

---

## 🧩 Principais Funcionalidades

- ✅ Web Scraping automático de sites técnicos
- ✅ Armazenamento em sessão do navegador (sem necessidade de arquivos locais)
- ✅ Busca inteligente baseada em IA (RAG)
- ✅ Chat interativo em Streamlit
- ✅ Logs estruturados para depuração

---

## 📁 Estrutura do Projeto

```
docksmith-app/
├── docksmith/
│   ├── app.py             # Ponto de entrada (Streamlit)
│   ├── presentation/      # Camada de apresentação (UI)
│   │   ├── chat.py        # Página de chat
│   │   └── scraping.py    # Página de scraping
│   └── service/           # Serviços internos
│       ├── rag.py         # Serviço de IA (RAG + Groq)
│       └── scraping.py    # Serviço de scraping (Firecrawl)
├── pyproject.toml         # Dependências (Poetry)
└── README.md
```

## 🔑 Nota importante:

> Todos os dados são armazenados na sessão do navegador (em memória), garantindo portabilidade e sem necessidade de persistência local.

---

## ⚙️ Requisitos

- Python 3.12+
- [Poetry](https://python-poetry.org/) para dependências
- Docker para rodar o Firecrawl

---

## 📦 Instalação e Setup

```bash
# Clonar o projeto
git clone https://github.com/seu-usuario/docksmith-app.git
cd docksmith-app

# Instalar dependências
poetry install

# Ativar ambiente virtual
poetry shell
```

---

## 🚀 Executando a aplicação

```bash
streamlit run docksmith/app.py
```

Acesse: [http://localhost:8501](http://localhost:8501)

---

## 🌐 Firecrawl (Scraping Service)

O Docksmith usa o Firecrawl como serviço de scraping. Para rodar localmente:

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

## 🤖 Modelos de IA

O Docksmith utiliza modelos da Groq API:

```python
self.llm = ChatGroq(
    groq_api_key=os.getenv("GROQ_API_KEY"),
    model_name="llama-3.1-8b-instant"
)
```

Modelos recomendados:

- `llama-3.1-8b-instant`
- `gemma2-9b-it`
- `llama-3.3-70b-versatile`

---

## 🛠️ Logs e Debugs

O projeto gera logs estratégicos para acompanhar o fluxo e facilitar a depuração de erros.

### 🖊️ Autor

---

Criado por Pedro Miranda (**pLogicador**) ✨
Desenvolvedor Back-end, apaixonado por Clean Code, arquitetura modular e RAG aplicado a soluções reais.
