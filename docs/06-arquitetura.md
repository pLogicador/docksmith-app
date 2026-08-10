# Arquitetura

## Diagrama

```text
Hub (syncron.pro)
      ↓  usuário clica em "Docksmith"
subscription_access_api
      │  gera token curto (POST /generate-agendador-token)
      │  abre <URL_DOCKSMITH_APP>?token=...
      ↓
Frontend (Vercel — hoje ainda o Streamlit Cloud)
      │  lê ?token=, valida contra subscription_access_api
      │  (POST /validate-agendador-token)
      ↓
API Python (api/ — FastAPI, processo persistente)
      │  revalida o mesmo token a cada request
      ↓
Docksmith Engine (docksmith/service/*.py — reaproveitado, não duplicado)
      ├── Scraping   (aiohttp + BeautifulSoup + markdownify)
      ├── Embeddings (sentence-transformers, local, CPU)
      ├── FAISS      (índice vetorial em memória)
      ├── RAG        (LangChain RetrievalQA)
      └── LLM        (Groq / OpenAI / Anthropic / Google — escolha do usuário)
```

## Fluxo em linguagem simples

1. O usuário está logado no Hub e clica para abrir o Docksmith.
2. O Hub pede ao `subscription_access_api` um token de curta duração e abre o Docksmith com esse token na URL.
3. O Docksmith (Streamlit hoje; o frontend novo quando o cutover acontecer) confere esse token direto com o `subscription_access_api` — ele é quem decide se o usuário realmente tem acesso.
4. A partir daí, o frontend fala com a API Python (`api/`), que também confere o token a cada chamada, e delega o trabalho pesado (raspar o site, indexar, responder perguntas) para o mesmo motor Python que o Streamlit sempre usou.
5. Nada é salvo em disco: cada resposta é gerada na hora, usando só o que foi raspado naquela sessão.

## Por que essa forma e não outra

- **A API existe** porque o frontend novo (Vercel) precisa de um jeito de chamar a lógica Python, e o motor de RAG (FAISS + embeddings locais) não roda em funções serverless — precisa de um processo que fique de pé e mantenha estado em memória entre uma pergunta e outra.
- **A lógica não foi duplicada.** `api/bootstrap.py` importa `docksmith/service/scraping.py` e `docksmith/service/rag.py` diretamente — é o mesmo código que o Streamlit usa, não uma cópia.
- **Sem banco de dados.** O padrão de estado em memória com TTL (`api/sessions.py`) espelha o que o próprio `subscription_access_api` já faz para os tokens (`tokens` dict + lock + faxina periódica) — não foi inventada uma solução nova.
- **Hub e `subscription_access_api` não mudam.** A integração é 100% baseada em algo que já existia: `URL_DOCKSMITH_APP` já era uma variável de ambiente, e o CORS do `subscription_access_api` já é montado a partir dela.

Mais detalhes de cada camada: [Frontend](./03-frontend.md), [API / Backend](./04-api-backend.md), [Streamlit legado](./05-streamlit-legado.md).
