# Visão geral

## O que é o Docksmith

Um assistente técnico que raspa (scraping) sites de documentação e permite fazer perguntas em linguagem natural sobre o conteúdo extraído, usando RAG (Retrieval-Augmented Generation): busca vetorial (FAISS) sobre o texto extraído + um modelo de IA para gerar a resposta a partir apenas dos trechos recuperados.

Não há banco de dados nem persistência em disco em nenhuma das três partes do projeto — tudo vive em memória, pelo tempo da sessão.

## As três partes do projeto

```
docksmith-app/
├── docksmith/   # App Streamlit original — produção atual / fallback
├── api/         # API fina em FastAPI — novo backend para o frontend
└── frontend/    # Novo frontend em React — vai para a Vercel
```

| Parte | Tecnologia | Papel |
|---|---|---|
| `docksmith/` | Streamlit | Interface original, ainda em produção. Contém a lógica de negócio real em `docksmith/service/`. |
| `api/` | FastAPI | Camada HTTP fina que **reaproveita** `docksmith/service/*.py` (não duplica) para servir o novo frontend. |
| `frontend/` | Vite + React + TypeScript + Tailwind | Interface nova, desacoplada do Streamlit, pensada para a Vercel. |

A lógica de negócio (scraping e RAG) mora fisicamente em `docksmith/service/scraping.py` e `docksmith/service/rag.py`. Tanto o Streamlit quanto a API importam essas mesmas duas classes — `api/bootstrap.py` é o único lugar que faz essa ponte (ver [Streamlit legado](./05-streamlit-legado.md)).

## Fluxo de autenticação

O Docksmith não tem sistema de login próprio. O acesso é controlado inteiramente pelo Hub (`subscription_access_api`), do mesmo jeito para o Streamlit e para o novo frontend:

1. O Hub gera um token de curta duração (`POST /generate-agendador-token` no `subscription_access_api`).
2. O Hub abre o Docksmith com esse token na URL: `<url-do-docksmith>?token=<token>`.
3. O Docksmith (Streamlit ou frontend novo) lê o `token` da URL e valida contra `POST /validate-agendador-token` no `subscription_access_api`.
4. Se válido, libera o uso; se não, mostra uma tela pedindo para entrar pelo Hub.

A API nova (`api/`) faz uma revalidação adicional server-to-server em cada request protegido (`api/auth.py`), para não confiar apenas no que o navegador diz. Ver detalhes em [API / Backend](./04-api-backend.md).

## Fluxo de dados (alto nível)

```
1. Usuário informa uma URL          → Workspace (frontend) ou modo Scraping (Streamlit)
2. Scraping                          → ScrapingService (aiohttp + BeautifulSoup + markdownify)
3. Conteúdo vira Markdown em memória → guardado na sessão (frontend: em memória do processo da API; Streamlit: em st.session_state)
4. Usuário faz uma pergunta          → RAGService indexa o Markdown em FAISS (embeddings locais) e monta a QA chain
5. Resposta gerada                   → LLM do provedor escolhido, usando só os trechos recuperados como contexto
6. Resposta exibida                  → com fontes/evidências (novo frontend) e níveis de profundidade
```

Nada disso é salvo em disco ou banco de dados: fechar a sessão ou reiniciar o processo apaga as coleções.

## Estado atual do projeto

- **Streamlit (`docksmith/`)**: em produção (Streamlit Cloud), inalterado exceto uma extensão retrocompatível em `docksmith/service/rag.py` (suporte a múltiplos provedores de IA — o Streamlit continua chamando exatamente como antes).
- **API (`api/`)**: implementada e testada localmente (scraping + chat reais, autenticação real contra o `subscription_access_api`). Ainda não implantada.
- **Frontend (`frontend/`)**: implementado, com identidade visual própria, painel de análise em 5 níveis, seleção de provedor/modelo de IA, e testado em desktop e mobile. Ainda não implantado.
- **Hub / `subscription_access_api`**: nenhuma alteração de código foi feita. A integração é só uma variável de ambiente (`URL_DOCKSMITH_APP`), trocada no momento do cutover — ver [Deploy](./09-deploy.md).
