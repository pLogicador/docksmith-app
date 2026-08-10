# Executar localmente

## Pré-requisitos

- Python 3.12+ e [Poetry](https://python-poetry.org/) (gerencia as dependências de `docksmith/` e `api/` — um único ambiente para as duas).
- Node.js 18+ e npm (para `frontend/`).
- Um arquivo `.env` na raiz do repositório (ver abaixo).

## 1. Configurar o `.env` da raiz

Usado pelo Streamlit **e** pela API (ambos chamam `load_dotenv()` a partir de dentro do repositório). Crie `docksmith-app/.env`:

```env
GROQ_API_KEY=sua_chave_groq
API_BASE=http://localhost:8000

# Legado (não usado pelo ScrapingService atual, que não depende mais do Firecrawl)
FIRECRAWL_API_URL=https://api.firecrawl.dev
FIRECRAWL_API_KEY=sua_chave_firecrawl

# Opcionais (têm default no código, só defina se quiser mudar):
# DOCKSMITH_API_CORS_ORIGINS=http://localhost:5173,http://localhost:5174,http://localhost:5175
# DOCKSMITH_SESSION_TTL_SECONDS=3600
# DOCKSMITH_API_DEV_BYPASS_AUTH=false
```

`API_BASE` é a URL do `subscription_access_api` — sem ele configurado e rodando, tanto o Streamlit quanto a API vão bloquear o acesso (ver [Troubleshooting](./07-troubleshooting.md)).

## 2. Instalar dependências Python

```bash
cd docksmith-app
poetry install
```

Isso instala as dependências de `docksmith/` (Streamlit, LangChain, FAISS, sentence-transformers…) e de `api/` (FastAPI, uvicorn, langchain-openai/anthropic/google-genai, httpx) — é o mesmo `pyproject.toml` para as duas partes.

## 3. Rodar o Streamlit (produção atual / fallback)

```bash
poetry run streamlit run docksmith/app.py
```

Abre em `http://localhost:8501`. Sem `API_BASE` acessível, mostra "Você precisa logar no www.syncron.pro" e para — isso é esperado (mesmo comportamento de produção).

## 4. Rodar a API nova

```bash
poetry run uvicorn api.main:app --reload --port 8787
```

**Importante:** sempre passe `--port` explicitamente. Sem ele, o uvicorn usa a porta `8000` por padrão — a mesma porta que o `subscription_access_api` normalmente usa localmente, causando conflito.

Testar se subiu:

```bash
curl http://localhost:8787/health
# {"status":"ok"}
```

## 5. Rodar o frontend

```bash
cd frontend
npm install
npm run dev
```

Abre em `http://localhost:5173` (ou a próxima porta livre — `5174`, `5175`… o Vite avisa no terminal qual usou). Crie `frontend/.env` a partir de `frontend/.env.example`:

```env
VITE_API_BASE_URL=http://localhost:8787
VITE_HUB_API_BASE_URL=http://localhost:8000
VITE_HUB_URL=http://localhost:5100
VITE_DEV_BYPASS_AUTH=false
```

`VITE_HUB_URL` é para onde o botão "Ir para o Hub" aponta quando não há sessão válida — em produção é `https://www.syncron.pro`; localmente, aponte para onde o Hub estiver rodando na sua máquina (ex.: `http://localhost:5100`).

## 6. Rodar as três partes ao mesmo tempo

Três terminais separados:

```bash
# Terminal 1 — Streamlit (fallback, opcional para testar o frontend novo)
poetry run streamlit run docksmith/app.py

# Terminal 2 — API nova
poetry run uvicorn api.main:app --reload --port 8787

# Terminal 3 — Frontend novo
cd frontend && npm run dev
```

Para o frontend novo funcionar de ponta a ponta (scraping + chat reais), você também precisa do `subscription_access_api` rodando em `API_BASE`/`VITE_HUB_API_BASE_URL` — é ele quem emite e valida o token de acesso. Sem ele, use `DOCKSMITH_API_DEV_BYPASS_AUTH=true` (raiz `.env`) + `VITE_DEV_BYPASS_AUTH=true` (`frontend/.env`) para testar a interface sem um token real — **nunca deixe essas duas flags como `true` fora do seu ambiente local**.

### Testar o fluxo completo a partir do Hub (opcional)

Se você também tem os repositórios `hub` e `subscription_access_api` rodando localmente e quer testar o clique real "abrir Docksmith" a partir do Hub (em vez de acessar o frontend direto), aponte `URL_DOCKSMITH_APP` no `.env` do `subscription_access_api` para a URL do frontend novo (ex.: `http://localhost:5173`) em vez do Streamlit. Isso é o único lugar fora deste repositório que precisa saber onde o Docksmith está — o Hub em si não guarda nenhuma URL própria do Docksmith, ele sempre pergunta ao `subscription_access_api`. Ver [Arquitetura](./06-arquitetura.md) e [Deploy](./09-deploy.md#configuração-do-hub-quando-chegar-a-hora) para o equivalente em produção.

## Portas usadas

| Serviço | Porta padrão | Observação |
|---|---|---|
| Streamlit | `8501` | Padrão do `streamlit run`. |
| API nova | `8787` | Escolha do projeto — não hardcoded, mas é o valor usado em toda a documentação e nos `.env.example`. |
| Frontend (Vite) | `5173` | O Vite pula automaticamente para `5174`, `5175`... se a porta estiver ocupada. |
| `subscription_access_api` | `8000` | Externo a este repositório — ver o projeto `subscription_access_api`. `A CONFIRMAR`: porta em produção. |

## Como saber se cada parte está funcionando

- **Streamlit**: abre em `:8501` e, com `API_BASE` acessível mas sem token na URL, mostra o aviso de login — isso já confirma que subiu e está tentando validar.
- **API**: `curl http://localhost:8787/health` deve responder `{"status":"ok"}`; `curl http://localhost:8787/models` deve listar os 4 provedores.
- **Frontend**: abre no navegador e mostra a tela "Faça login pelo Hub" (sem token) ou a tela "Nova extração" (com um token válido ou bypass ativado).
