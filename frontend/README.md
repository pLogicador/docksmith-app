# Docksmith — frontend

Vite + React + TypeScript + Tailwind. Novo frontend do Docksmith, consumindo a API em `../api`. Sem banco de dados — todo o estado (sessão, coleções, chat) vive em memória do navegador (`sessionStorage` para o token, contexto React para o resto) e é perdido ao recarregar a página, por design.

## Rodando localmente

```bash
npm install
npm run dev
```

Variáveis de ambiente (`.env`, ver `.env.example`):

- `VITE_API_BASE_URL` — URL da API do Docksmith (`../api`), local: `http://localhost:8787`.
- `VITE_HUB_API_BASE_URL` — URL do `subscription_access_api`, usada para validar o token vindo do Hub.
- `VITE_DEV_BYPASS_AUTH` — **deixe `false`**; só para testar sem um token real do Hub (requer o mesmo bypass habilitado na API).

## Fluxo de acesso

Idêntico ao `docksmith/app.py` atual: o Hub abre `<esta-url>?token=...`; o token é validado direto contra o `subscription_access_api` e guardado em `sessionStorage` para as chamadas seguintes à API.

## Deploy (Vercel)

Build padrão do Vite (`npm run build`, output `dist/`). Configurar na Vercel:

- `VITE_API_BASE_URL` = URL de produção da API (Railway/Render/Fly).
- `VITE_HUB_API_BASE_URL` = URL de produção do `subscription_access_api`.

Depois do deploy validado, o corte no Hub é feito trocando a env var `URL_DOCKSMITH_APP` no `subscription_access_api` para a URL da Vercel — nenhuma alteração de código no Hub ou no `subscription_access_api` é necessária (o CORS já é construído a partir dessa mesma variável).
