# 📚 Docksmith — Knowledge Extraction, the Smart Way

Docksmith é um assistente técnico para extração e consulta de conhecimento, combinando Web Scraping e RAG (Retrieval-Augmented Generation) em uma interface interativa.

Ele permite colecionar informações de sites técnicos e fazer perguntas inteligentes com base nesse conteúdo, com escolha do provedor/modelo de IA e análise em múltiplos níveis de profundidade (resumo, insights, evidências, dados e detalhamento técnico).

---

## 📁 Estrutura do projeto

```
docksmith-app/
├── docksmith/   # App Streamlit — produção atual, mantido como fallback
├── api/         # API fina em FastAPI — reaproveita docksmith/service/* para o frontend novo
├── frontend/    # Frontend novo (Vite + React + TypeScript) — vai para a Vercel
└── docs/        # Documentação completa do projeto (comece por docs/README.md)
```

| Parte | O que é |
|---|---|
| `docksmith/` | Interface original em Streamlit, em produção (Streamlit Cloud). Contém a lógica de scraping e RAG. |
| `api/` | Camada HTTP fina que reaproveita a mesma lógica de `docksmith/service/` para servir o frontend novo — sem duplicar código, sem banco de dados. |
| `frontend/` | Interface nova, desacoplada do Streamlit, com identidade visual própria, responsiva, e pensada para a Vercel. |

Nenhuma das três partes usa banco de dados — todo estado vive em memória, pelo tempo da sessão.

---

## 🚀 Como executar localmente

Resumo rápido — passo a passo completo em [`docs/02-executar-localmente.md`](docs/02-executar-localmente.md):

```bash
# Python (Streamlit + API — mesmo ambiente Poetry)
poetry install
poetry run streamlit run docksmith/app.py          # produção atual, porta 8501
poetry run uvicorn api.main:app --reload --port 8787  # API nova

# Frontend
cd frontend
npm install
npm run dev                                          # porta 5173 (ou próxima livre)
```

Cada parte precisa do seu `.env` (raiz para Streamlit/API, `frontend/.env` para o frontend) — ver [`docs/02-executar-localmente.md`](docs/02-executar-localmente.md).

---

## 📖 Documentação

Toda a documentação detalhada está em [`docs/`](docs/README.md):

1. [Visão geral](docs/01-visao-geral.md) — arquitetura, papel de cada parte, fluxo de autenticação e de dados.
2. [Executar localmente](docs/02-executar-localmente.md) — passo a passo completo.
3. [Frontend](docs/03-frontend.md) — instalação, build, estrutura, variáveis de ambiente.
4. [API / Backend](docs/04-api-backend.md) — endpoints, autenticação, provedores de IA, RAG, FAISS, limitações.
5. [Streamlit legado](docs/05-streamlit-legado.md) — por que continua existindo e como usá-lo.
6. [Arquitetura](docs/06-arquitetura.md) — diagrama e fluxo de ponta a ponta.
7. [Troubleshooting](docs/07-troubleshooting.md) — problemas comuns (incluindo os que apareceram de verdade durante o desenvolvimento) e soluções.
8. [Desenvolvimento seguro](docs/08-desenvolvimento-seguro.md) — regras que protegem a produção atual.
9. [Deploy](docs/09-deploy.md) — como o deploy deverá ser feito (documentação — nenhum deploy foi executado ainda).

---

## 🔑 Nota importante

> Todos os dados são armazenados em memória (processo da API / sessão do navegador), garantindo portabilidade e sem necessidade de persistência local ou banco de dados.

---

## 🤖 Modelos de IA

O Docksmith suporta múltiplos provedores — Groq (padrão, usa a chave do servidor), OpenAI, Anthropic e Google Gemini (exigem a chave própria do usuário, nunca persistida). Detalhes em [`docs/04-api-backend.md`](docs/04-api-backend.md).

---

## 📊 Status atual

- **Streamlit**: em produção, inalterado (exceto uma extensão retrocompatível para suportar múltiplos provedores de IA).
- **API**: implementada e testada localmente (scraping, chat e autenticação reais). Ainda não implantada.
- **Frontend**: implementado, com identidade visual própria e testado em desktop/mobile. Ainda não implantado.
- **Hub / `subscription_access_api`**: nenhuma alteração de código — a integração é uma troca de variável de ambiente (`URL_DOCKSMITH_APP`) no momento do cutover.

---

### 🖊️ Autor

Criado por Pedro Miranda (**pLogicador**) ✨
Desenvolvedor Back-end, apaixonado por Clean Code, arquitetura modular e RAG aplicado a soluções reais.
