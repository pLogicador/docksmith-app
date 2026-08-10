# Deploy

**Este documento é só de referência — nenhum deploy foi feito ainda, e nenhuma configuração de produção foi alterada.** Descreve como o deploy deverá ser feito quando o frontend for considerado pronto.

## Visão geral

```
frontend/  →  Vercel (build estático do Vite)
api/       →  host com processo persistente — Railway recomendado (ver justificativa e medição real de RAM em docs/10-preparacao-producao.md)
docksmith/ →  continua no Streamlit Cloud, sem mudanças, como fallback
```

`api/` **não pode** ir para a Vercel: precisa manter FAISS/embeddings e estado de sessão em memória entre requisições, o que exige um processo sempre ativo, não funções serverless. Ver justificativa completa em [Arquitetura](./06-arquitetura.md) e [API / Backend](./04-api-backend.md).

## Frontend → Vercel

1. Conectar o repositório (ou o diretório `frontend/` como raiz do projeto Vercel).
2. Build command: `npm run build` (já é o default detectado para projetos Vite). Output: `dist/`.
3. Variáveis de ambiente na Vercel:
   - `VITE_API_BASE_URL` = URL de produção da API (Railway). **Obrigatória — o build (`vite build`) falha explicitamente se estiver ausente**, em vez de cair num fallback de `localhost`.
   - `VITE_HUB_API_BASE_URL` = URL de produção do `subscription_access_api`. **Obrigatória pelo mesmo motivo.**
   - `VITE_HUB_URL` = `https://www.syncron.pro` (já é o default no código, mas defina explicitamente por clareza).
   - **Não definir** `VITE_DEV_BYPASS_AUTH` em produção.

## API → host com processo persistente

**Railway recomendado** (2GB de RAM, 1 única instância — nunca escalar horizontalmente enquanto sessões/índice FAISS viverem só em memória do processo). Justificativa completa, comparação com Render/Fly.io e medição real de consumo de RAM em [Preparação para produção](./10-preparacao-producao.md). O código (`api/main.py`, FastAPI + uvicorn puro) continua portável entre as três, caso a decisão mude.

Comando de start: `uvicorn api.main:app --host 0.0.0.0 --port $PORT` — já preparado num `Procfile` na raiz do projeto (funciona em Railway/Render/Heroku-style sem alteração).

Variáveis de ambiente a configurar (mesmas já usadas localmente, ver [Executar localmente](./02-executar-localmente.md); tabela completa com finalidade de cada uma em [Preparação para produção](./10-preparacao-producao.md)):

- `ENVIRONMENT=production` — liga o modo estrito: sem isso, uma variável obrigatória ausente cai num default de `localhost`; com isso, o processo falha alto e explícito na inicialização se faltar algo.
- `API_BASE` — URL de produção do `subscription_access_api`. **Obrigatória com `ENVIRONMENT=production`** (processo não inicia sem ela).
- `DOCKSMITH_API_CORS_ORIGINS` — URL de produção do frontend na Vercel. **Obrigatória com `ENVIRONMENT=production`**.
- `GROQ_API_KEY` — chave padrão do Docksmith. Opcional (sem ela, só a recomendação "Groq sem chave" fica indisponível).
- `DOCKSMITH_SESSION_TTL_SECONDS` — opcional, default `3600`.
- `DOCKSMITH_API_DEV_BYPASS_AUTH` — **proibido em produção**: com `ENVIRONMENT=production`, defini-la como `true` derruba o processo na inicialização.

## Configuração do Hub (quando chegar a hora)

Nenhuma mudança de código é necessária em `hub/` ou `subscription_access_api/`. A integração inteira depende de uma variável de ambiente já existente:

- `URL_DOCKSMITH_APP` (lida pelo `subscription_access_api`) — hoje aponta para o Streamlit Cloud. Trocar para a URL de produção da Vercel é o que faz o Hub começar a abrir o frontend novo.
- O CORS do `subscription_access_api` já é montado a partir dessa mesma variável (confirmado no código) — trocar `URL_DOCKSMITH_APP` libera automaticamente o novo domínio para chamar `/validate-agendador-token` direto do navegador, sem nenhuma alteração adicional.
- `hub/js/services.js` já trata qualquer URL sem `streamlit.app`/`8501` pelo caminho padrão (`${serviceUrl}?token=${token}`) — só a URL do Streamlit tem um redirecionamento especial hoje, então a URL da Vercel não precisa de tratamento extra.

## Ordem recomendada do cutover

1. Deploy do `api/` (Railway/Render/Fly) — validar `/health`, `/models`, um `/scrape` e `/chat` reais em produção antes de prosseguir.
2. Deploy do `frontend/` na Vercel, apontando para a API já em produção — validar o fluxo completo com um token real do Hub (não com o bypass de dev).
3. Só depois disso, trocar `URL_DOCKSMITH_APP` no ambiente do `subscription_access_api` para a URL da Vercel.
4. Acompanhar os primeiros acessos reais vindos do Hub antes de considerar o cutover definitivo.

## Rollback

Reverter `URL_DOCKSMITH_APP` para a URL do Streamlit Cloud — o Streamlit continua rodando sem nenhuma alteração durante todo esse processo, então o rollback é imediato e não depende de reverter nenhum deploy do frontend ou da API novos.
