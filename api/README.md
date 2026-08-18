# Docksmith API

Camada de API fina em FastAPI. Reaproveita `docksmith/service/*.py` (scraping e RAG) sem duplicar código — ver `api/bootstrap.py`. Não usa banco de dados; estado de sessão vive em memória do processo com TTL (`api/sessions.py`), mesmo padrão do dicionário `tokens` do `subscription_access_api`.

## Rodando localmente

```bash
poetry install
poetry run uvicorn api.main:app --reload --port 8787
```

Variáveis de ambiente (lidas do `.env` na raiz do repo, mesmo arquivo do Streamlit):

- `API_BASE` — URL do `subscription_access_api` (validação de token).
- `GROQ_API_KEY` — chave padrão usada quando o usuário não informa a própria (provedor Groq).
- `DOCKSMITH_API_CORS_ORIGINS` — origens liberadas para o frontend (default cobre as portas comuns do Vite em dev).
- `DOCKSMITH_SESSION_TTL_SECONDS` — TTL da sessão em memória (default 3600).
- `DOCKSMITH_API_DEV_BYPASS_AUTH` — **deixe `false`**; só para testar o frontend localmente sem um token real do Hub (aceita `Authorization: Bearer dev-bypass-token`).

## Ambiente real de produção (confirmado 2026-08-18)

- **URL**: `https://web-production-27204.up.railway.app/` — **Railway**, confirmado ao vivo (`GET /health` e `GET /models` respondendo 200, `GET /openapi.json` com `"title": "Docksmith API"`) durante a integração com o Syncron Core.
- Isso contraria uma auditoria anterior que classificava esta API como "implementada e testada localmente, nunca implantada" — parece ter sido implantada depois daquela auditoria, sem deixar rastro no repositório (nenhum `railway.json`/`Procfile` commitado, nenhuma env var de produção documentada aqui apontando pra essa URL). Registrado aqui pra não se repetir essa confusão — se o serviço mudar de URL, atualize esta seção.

## Deploy

Streamlit Cloud não hospeda esta API (não é um app Streamlit), então ela precisa de um host próprio com processo persistente — Railway, Render ou Fly.io servem igualmente bem, o código é FastAPI + uvicorn puro. Sugestão (Railway):

1. Novo serviço apontando para este repositório, comando de start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`.
2. Configurar as variáveis de ambiente acima (iguais às já usadas pelo Streamlit hoje, mais `DOCKSMITH_API_CORS_ORIGINS` com a URL da Vercel do novo frontend).
3. **Não** definir `DOCKSMITH_API_DEV_BYPASS_AUTH` em produção.
