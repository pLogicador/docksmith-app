# Streamlit legado

`docksmith/` continua existindo — intacto, exceto uma extensão retrocompatível — e continua sendo a versão em produção.

## Por que ele continua existindo

É o fallback durante toda a migração para o novo frontend: se algo no frontend novo ou na API falhar, o Streamlit é a implementação já validada em produção. A regra do projeto foi não substituir uma implementação funcional antes de ter um substituto validado — ver [Desenvolvimento seguro](./08-desenvolvimento-seguro.md).

## Como executar

```bash
poetry run streamlit run docksmith/app.py
```

Abre em `http://localhost:8501`.

## Funcionalidades

- **Modo Scraping**: informar uma URL + nome de coleção, extrai o conteúdo (`presentation/scraping.py` → `service/scraping.py`) e guarda em `st.session_state.collections` (só na sessão do navegador).
- **Modo Chat**: selecionar uma coleção e conversar sobre ela (`presentation/chat.py` → `service/rag.py`), com histórico baixável em `.txt` e botão para limpar o chat.
- **Login via Hub**: lê `?token=` da URL, valida contra `subscription_access_api`, mostra o e-mail do usuário na sidebar.

## Estrutura

```
docksmith/
├── app.py                    # Entrada Streamlit: auth, layout, sidebar, roteamento entre os dois modos
├── presentation/
│   ├── chat.py                # UI do modo Chat
│   └── scraping.py            # UI do modo Scraping
└── service/
    ├── rag.py                  # RAGService — lógica de RAG (embeddings, FAISS, LLM)
    ├── scraping.py              # ScrapingService — crawler assíncrono (aiohttp + BeautifulSoup + markdownify)
    ├── scraping_legacy.py        # Versão anterior do scraper — não usada pelo app.py atual
    └── scraping_with_firecrawl.py # Versão baseada no Firecrawl — não usada pelo app.py atual (substituída por scraping.py, que faz parsing em memória)
```

`scraping_legacy.py` e `scraping_with_firecrawl.py` não são importados por nenhum caminho ativo (nem Streamlit, nem API) — ficam no repositório como histórico das iterações anteriores do scraper. `A CONFIRMAR`: se devem ser removidos numa limpeza futura.

## O que é compartilhado com a API nova

Só `docksmith/service/scraping.py` e `docksmith/service/rag.py`. `api/bootstrap.py` insere `docksmith/` no `sys.path` do processo da API e importa essas duas classes exatamente como `docksmith/app.py` já faz — **nenhum código é copiado**, é o mesmo arquivo em ambos os casos.

A única mudança feita em `docksmith/service/rag.py` para viabilizar isso foi tornar `RAGService.load_collection()` capaz de aceitar provedor/modelo/chave/profundidade como parâmetros opcionais — a chamada antiga do Streamlit (`load_collection(docs, groq_key)`, dois argumentos posicionais) continua funcionando sem nenhuma alteração no `presentation/chat.py`.

`presentation/`, `app.py` e o restante da experiência Streamlit **não são tocados nem reaproveitados** pela API — são específicos da interface Streamlit.

## Usando como fallback

Enquanto o novo frontend não estiver validado e o cutover no Hub não for feito, o Streamlit continua sendo a URL que o Hub abre (`URL_DOCKSMITH_APP` ainda aponta para o Streamlit Cloud). Rodar localmente serve para comparar respostas com a API nova durante o desenvolvimento — mesma lógica de RAG por baixo, então divergências de resposta indicam um problema real, não uma diferença de comportamento esperada.
