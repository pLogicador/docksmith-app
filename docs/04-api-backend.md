# API / Backend

Camada fina em FastAPI (`api/`), pensada para expor `docksmith/service/*.py` por HTTP ao novo frontend. Não reimplementa scraping nem RAG — importa e reaproveita.

## Como iniciar

```bash
poetry run uvicorn api.main:app --reload --port 8787
```

Sempre com `--port` explícito (ver [Troubleshooting](./07-troubleshooting.md) sobre o conflito com a porta `8000` do `subscription_access_api`).

## Estrutura

```
api/
├── main.py       # App FastAPI, CORS, registro das rotas
├── bootstrap.py  # Ponte de reaproveitamento: adiciona docksmith/ ao sys.path e importa
│                 # ScrapingService, RAGService, build_chat_llm, DEFAULT_MODELS
├── config.py     # Leitura de variáveis de ambiente (load_dotenv na raiz do repo)
├── schemas.py    # Modelos Pydantic de request/response
├── auth.py       # Revalidação de token contra o subscription_access_api
├── sessions.py   # Estado de sessão em memória (dict + lock + TTL) — sem banco de dados
├── providers.py  # Catálogo de provedores/modelos de IA + teste de conexão
└── routers/
    ├── health.py
    ├── models.py   # GET /models, POST /models/test-connection
    ├── scrape.py   # POST /scrape, GET /sessions/{id}
    └── chat.py     # POST /chat
```

## Endpoints

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | não | Checagem simples (`{"status":"ok"}`). |
| GET | `/models` | não | Catálogo de provedores/modelos de IA suportados. |
| POST | `/models/test-connection` | sim | Testa se `provider`+`model`+`api_key` conseguem responder (`llm.invoke("ping")`). |
| POST | `/scrape` | sim | Raspa uma URL, cria/reaproveita uma sessão, guarda a coleção resultante em memória. |
| GET | `/sessions/{id}` | sim | Lista as coleções existentes numa sessão. |
| POST | `/chat` | sim | Responde uma pergunta sobre uma coleção (indexa com FAISS na primeira vez, depois reaproveita). |

Todas as rotas com "Auth: sim" exigem `Authorization: Bearer <token>` e usam `Depends(auth.get_current_user)`.

## Autenticação

`api/auth.py` **não reimplementa** nenhuma regra de acesso — a cada request protegido, revalida o token chamando `POST {API_BASE}/validate-agendador-token` no `subscription_access_api` (a mesma fonte da verdade usada pelo Hub e pelo Streamlit). Isso garante que a API nunca confia apenas no que o navegador afirma.

Fluxo:
1. Header ausente/malformado → `401`.
2. Header presente → chamada HTTP ao `subscription_access_api`.
3. `subscription_access_api` indisponível → `502`.
4. Token inválido/expirado (`subscription_access_api` responde != 200) → `401`.
5. Válido → segue com `{"token": ..., "user": {"id": ..., "email": ...}}`.

**Bypass de desenvolvimento**: se `DOCKSMITH_API_DEV_BYPASS_AUTH=true` (env) e o token enviado for literalmente `dev-bypass-token`, pula a chamada real e injeta um usuário fake (`id: "dev"`). Existe só para testar o frontend localmente sem depender do `subscription_access_api`. **Nunca deve estar `true` fora do ambiente local** — não é lido em nenhum ambiente de deploy documentado.

## Integração com o `subscription_access_api`

- `API_BASE` (env, default `http://localhost:8000`) aponta para ele.
- A API nova só faz uma chamada de leitura (`POST /validate-agendador-token`); nunca escreve nada nele.
- Nenhum código do `subscription_access_api` foi alterado para essa integração existir.

## Configuração dos provedores de IA

`docksmith/service/rag.py` expõe `build_chat_llm(provider, model_name, api_key)`, usada tanto pelo `RAGService` quanto por `api/providers.py` (para o teste de conexão, sem precisar montar embeddings/FAISS).

Provedores suportados e modelo padrão (`DEFAULT_MODELS` em `rag.py`):

| Provedor | Requer chave própria | Modelo padrão |
|---|---|---|
| `groq` | Não (usa `GROQ_API_KEY` do servidor se o usuário não informar a própria) | `llama-3.3-70b-versatile` |
| `openai` | Sim | `gpt-4o-mini` |
| `anthropic` | Sim | `claude-sonnet-5` |
| `google` | Sim | `gemini-2.0-flash` |

O catálogo completo (modelos disponíveis por provedor, descrição, se exige chave) fica em `api/providers.py` (`PROVIDER_CATALOG`), consumido pelo frontend via `GET /models`.

A chave do usuário (`api_key` no request de `/chat` ou `/models/test-connection`) **nunca é persistida** — vive só na variável Python da requisição e, no frontend, só na memória do React durante a sessão da aba.

## RAG, FAISS e embeddings

- **Embeddings**: `HuggingFaceEmbeddings` com `all-MiniLM-L6-v2`, rodando em CPU, local (baixado/cacheado na primeira execução).
- **Chunking**: `RecursiveCharacterTextSplitter`, `chunk_size=1000`, `chunk_overlap=200`.
- **Índice**: FAISS em memória (`FAISS.from_documents`), reconstruído a cada chamada de `load_collection` (ou seja, a cada nova coleção ou troca de modelo/profundidade — ver `loaded_signature` em `api/routers/chat.py`).
- **Retrieval**: `RetrievalQA` (LangChain), `chain_type="stuff"`, `k` variável por profundidade (`RAGService.DEPTH_K`): `rapida=2`, `equilibrada=3` (default, igual ao comportamento original do Streamlit), `profunda=6`.
- **Fontes/evidências**: `return_source_documents=True` habilitado na chain; `ask_question_with_sources()` retorna os trechos usados (consumidos pelo painel de análise do frontend). `ask_question()` (usado pelo Streamlit) continua retornando só a string, sem quebrar a interface antiga.

## Estado em memória (sem banco de dados)

`api/sessions.py` guarda um dicionário de sessões no processo:

```python
{session_id: {
    "user_id": ...,
    "collections": {nome: [documentos_markdown, ...]},
    "rag_service": RAGService | None,
    "loaded_signature": (coleção, provider, model, tem_chave_própria, depth) | None,
    "last_seen": timestamp,
}}
```

Protegido por `threading.Lock`, com faxina por TTL (`DOCKSMITH_SESSION_TTL_SECONDS`, default 3600s) — mesmo padrão já usado pelo `subscription_access_api` para o dicionário `tokens`. Isso significa:

- **Um processo só.** Rodar a API em múltiplas réplicas sem sticky sessions perde a consistência (sessão criada numa réplica não existe nas outras). `A CONFIRMAR`: estratégia de deploy para múltiplas réplicas, se necessário no futuro.
- **Reiniciar o processo apaga todas as sessões.** Comportamento intencional (sem persistência), mas o usuário perde a coleção e precisa raspar de novo.
- **Sem limite de memória configurado.** Coleções grandes ficam inteiras em RAM até expirar pelo TTL.

## Limitações importantes

- Só roda como processo persistente — não funciona em funções serverless (Vercel) por causa do FAISS/embeddings e do estado em memória entre requests. Ver [Deploy](./09-deploy.md).
- Sem retry/backoff nas chamadas aos provedores de IA — falha do provedor vira erro direto para o usuário.
- `ScrapingService` (herdado do Streamlit) não respeita `robots.txt` nem tem rate limiting configurável pelo usuário final — só os parâmetros `max_depth`/`concurrency` já existentes.
- `HuggingFaceEmbeddings` está com aviso de depreciação do LangChain (recomenda migrar para o pacote `langchain-huggingface`) — não migrado nesta etapa por não ser uma mudança necessária.
