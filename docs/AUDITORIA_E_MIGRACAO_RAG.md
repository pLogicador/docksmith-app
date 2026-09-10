# Auditoria e Plano de Migração — Pipeline de RAG do Docksmith

Entrega obrigatória exigida pelo prompt-mestre
`01-docksmith-arquitetura-prompt-mestre.md` (registrado em
`hub/react-app/.claude/project-context/prompts/`) antes de qualquer
código: auditoria da arquitetura atual → problemas → arquitetura proposta
→ plano de migração incremental. Data: 2026-09-02.

---

## 1. Arquitetura atual (evidência real, não presumida)

```
docksmith-app/
  api/            camada HTTP fina (FastAPI) -- main.py, config.py,
                  sessions.py, auth.py, providers.py, bootstrap.py,
                  resource_estimate.py, schemas.py, routers/
  docksmith/      motor de verdade -- COMPARTILHADO ao vivo com o
                  Streamlit legado (via sys.path, não um fork)
    service/rag.py        toda a "RAG" do produto
    service/scraping.py   toda a ingestão do produto
```

`api/bootstrap.py` insere `docksmith/` no `sys.path` e importa
`ScrapingService`/`RAGService`/`build_chat_llm`/`DEFAULT_MODELS`
diretamente — zero duplicação, a API e o Streamlit legado rodam o mesmo
código de verdade hoje.

**Pipeline real, hoje, ponta a ponta:**

1. **Ingestão** — só URL/site (`ScrapingService.scrape_website_async`,
   `aiohttp`+`BeautifulSoup`, HTML→Markdown via `markdownify`, crawl
   recursivo mesmo-domínio limitado por `max_depth`/`concurrency`). Zero
   PDF, zero DOCX, zero upload de arquivo.
2. **Armazenamento** — `api/sessions.py`, puramente `dict` em processo
   (`threading.Lock`), sem persistência de nenhum tipo (zero R2, zero S3,
   zero Redis, zero banco — confirmado por grep, zero dependência dessas
   libs em `pyproject.toml`).
3. **Chunking** — `RecursiveCharacterTextSplitter(chunk_size=1000,
   chunk_overlap=200)` do LangChain, puramente por contagem de caractere,
   sem consciência de capítulo/seção/heading, sem metadado nenhum por
   chunk (nem `document_id`, nem `page`, nem `chunk_index`).
4. **Indexação** — `FAISS.from_documents(...)`, reconstruído do zero a
   cada `load_collection()` (toda troca de coleção/provedor/modelo/
   profundidade). `HuggingFaceEmbeddings("all-MiniLM-L6-v2")`, CPU local.
   **Zero BM25/léxico. Zero híbrido. Zero RRF. Zero reranking.**
5. **Retrieval + geração** — `RetrievalQA.from_chain_type(chain_type=
   "stuff", retriever=vector_store.as_retriever(search_kwargs={"k": k}))`
   — top-k denso puro, `k` fixo por "profundidade" (`DEPTH_K`). Zero
   classificação de intenção, zero atalho determinístico (mesmo "quantas
   páginas tem" vira uma chamada de LLM), zero orçamento de contexto por
   token, zero deduplicação.
6. **Citações** — parcial: `{index, excerpt}` por chunk usado, mas sem
   página/capítulo/seção/nome-de-documento, porque os chunks nunca
   carregaram essa informação.
7. **Provedores de LLM** — Groq (padrão)/OpenAI/Anthropic/Google, já
   funcionando, chave própria do usuário suportada — **mais maduro do que
   o prompt-mestre presume**. Zero fallback automático entre provedores
   (falha do provedor vira erro direto pro usuário, já documentado em
   `docs/04-api-backend.md`).
8. **Sessões/TTL** — real e funcionando (`SESSION_TTL_SECONDS`, limpeza
   reativa + proativa em `main.py::_session_cleanup_loop`, endurecida
   nesta mesma data via commit `a481e81`).
9. **Guarda de recursos** — `api/resource_estimate.py`, estimador real de
   RAM via `psutil`, calibrado, bloqueia indexação grande demais sem
   confirmação explícita — mais do que o prompt-mestre pede, sem custo de
   LLM.
10. **Isolamento por usuário** — real (`api/auth.py` + `sessions.
    get_session(session_id, user_id)`).
11. **Filas/workers** — nenhum. Tudo síncrono via `run_in_threadpool`.

**Endpoints existentes**: `GET /health`, `GET /models`, `POST
/models/test-connection`, `POST /scrape`, `GET /sessions/{id}`, `POST
/chat`.

---

## 2. Problemas concretos (não hipotéticos)

- **Retrieval é 100% denso** — sem BM25/léxico, buscas por termo exato
  (nomes próprios, códigos, números específicos) competem em desvantagem
  contra embeddings semânticos, que generalizam demais pra esse caso.
- **Zero proveniência de chunk** — impossível citar página/seção real,
  só um trecho cru.
- **Zero storage externo** — qualquer coisa maior que cabe em RAM do
  processo (ex.: PDFs grandes) não tem pra onde ir.
- **Zero fila** — indexação pesada bloqueia a requisição inteira.
- **Zero fallback de provedor** — uma falha temporária da Groq vira erro
  visível ao usuário, quando poderia cair pra OpenAI/Anthropic
  automaticamente.
- **Reconstrução total do índice a cada troca de parâmetro** — caro,
  desnecessário se o índice fosse cacheado por assinatura de conteúdo.

---

## 3. Arquitetura proposta (visão, não um redesenho completo de uma vez)

Reaproveitando ao máximo o que já funciona (multi-provedor, sessões,
guarda de recursos, isolamento) — a mudança real é dentro de
`RAGService.load_collection`/`ask_question_with_sources`, sem tocar a
API pública consumida pelo frontend nem o caminho do Streamlit legado:

```
Documento(s) → chunking com metadado real (document_index/chunk_index)
             → índice léxico (BM25) + índice denso (FAISS, já existente)
             → fusão RRF → (fase futura: reranking) → LLM
             → resposta + citações reais (com proveniência)
```

PDF/DOCX, storage R2, filas, e a reorganização em `services/{ingestion,
extraction,...}` ficam para depois — dependem de ter um modelo real de
documento/chunk primeiro (item da Fase 1 abaixo), e são, cada um, do
tamanho de uma rodada própria.

---

## 4. Plano de migração incremental (13 fases do prompt-mestre, reordenadas com realismo)

| # | Fase (prompt-mestre) | Depende de | Status |
|---|---|---|---|
| 1 | Auditoria | — | **Concluída** (este documento) |
| 2 | Abstrações (metadado de chunk, seam de retriever) | 1 | **Implementada nesta rodada** (ver §5) |
| 5 | Chunking (metadado real) | 2 | **Implementada nesta rodada** |
| 6 | Indexação (BM25 + embeddings) | 5 | **Implementada nesta rodada** |
| 7 | Retrieval (RRF) | 6 | **Implementada nesta rodada** |
| 11 (parcial) | Fallback entre provedores LLM | — (independente) | **Implementada nesta rodada** |
| 3 | Documentos (PDF/DOCX) | 2 | **Implementada na 2ª rodada** (ver §6) |
| 48 (parcial) | Rate limiting por usuário | — (independente) | **Implementada na 2ª rodada** (scrape/upload/chat) |
| 4 | Storage (R2) | 3 | Avaliada e adiada — ver §6 ("por que não") |
| 8 | QueryEngine (classificação de intenção determinística) | 7 | Registrada, próxima rodada |
| 9 | Grupos de documentos/comparação | 3, 4 | Registrada, futuro |
| 9 (OCR) | OCR de PDF escaneado | 3 | Detecção implementada (erro claro); OCR em si adiado — depende de fila (item 10) |
| 10 | Fila/workers | 3, 4 | Registrada, futuro (só necessário quando ingestão pesada existir) |
| 12 | Observabilidade formal | — | Registrada, futuro |
| 13 | Testes completos da matriz do prompt-mestre | todas | Parcial (cobertura do que foi implementado nas 2 rodadas); expandir conforme fases futuras avançam |

**Por que essa ordem**: BM25/RRF/metadado de chunk (fases 2/5/6/7) não
dependem de storage nem fila — cabem inteiramente dentro do fluxo síncrono
em memória já existente, então são o "primeiro corte seguro" real, sem
risco de infraestrutura nova. PDF/DOCX + R2 + fila formam um cluster
acoplado (arquivo grande precisa de processamento fora da requisição E de
um lugar pra morar) — fazer um sem o outro é trabalho perdido, então ficam
juntos, na próxima rodada.

---

## 5. O que foi implementado nesta rodada (ver `docksmith/service/rag.py`)

- Metadado real por chunk (`document_index`/`chunk_index`, mais um
  parâmetro novo opcional `source_labels` para nomes/URLs de origem).
- Índice léxico BM25 (`rank_bm25`), construído a partir dos mesmos
  `texts` que o FAISS já usa.
- `HybridRetriever` (implementa `BaseRetriever` do LangChain) — fusão RRF
  (`score = Σ 1/(k+rank_i)`, k=60) entre o ranking BM25 e o ranking FAISS,
  substituindo `vector_store.as_retriever()` dentro do `RetrievalQA`.
- Citações reais (`document_index`/`chunk_index` no retorno de
  `ask_question_with_sources`), sem quebrar o contrato existente de
  `SourceExcerpt` na API.
- Fallback entre provedores de LLM em `api/routers/chat.py`.
- **Restrição inegociável, verificada**: a assinatura posicional antiga
  `load_collection(docs, groq_key)` continua funcionando exatamente como
  antes — é o caminho real do Streamlit legado em produção hoje
  (`docs/05-streamlit-legado.md`), e `docksmith/service/rag.py` é
  compartilhado ao vivo entre os dois, não um fork.

Ver `CLAUDE.md` (novo, este repositório não tinha um) para o relato
completo do que foi feito e como foi validado.

---

## 6. 2ª rodada (2026-09-02): documentos (PDF/DOCX) + rate limiting

Continuação direta da fatia fundacional acima, disparada por um pedido
real do usuário durante teste manual do frontend ("o frontend não tem a
opção de colocar documentos, como já está no backend?") — investigado e
confirmado como um gap real (nem frontend nem backend suportavam
PDF/DOCX antes desta rodada), não um mal-entendido.

**Implementado — Fase 3 (Documentos):**
- `DocumentLoader` (`docksmith/service/document_loader.py`): abstração
  única com `load_pdf`/`load_docx`/`load_document` (dispatch por
  extensão), exatamente a interface que o prompt-mestre §6 pede
  (`URLLoader`/`PDFLoader`/`DOCXLoader`, lógica de formato nunca
  espalhada pelos endpoints).
- **PDF**: PyMuPDF (`fitz`), extração direta de texto por página — zero
  LLM (§8). Detecção de PDF escaneado (nenhuma página com texto
  extraível) levanta um erro claro em vez de indexar uma coleção vazia.
- **DOCX**: python-docx, agrupado por SEÇÃO (o texto entre um heading e o
  próximo — a unidade estrutural real que o formato guarda; DOCX não tem
  "página" no arquivo em si), mais um bloco de tabelas.
- Limites configuráveis por ambiente (§12):
  `DOCSMITH_MAX_FILE_SIZE_MB` (default 20), `DOCSMITH_MAX_PAGES`
  (default 300, também usado como teto de nº de seções pra DOCX).
- Novo endpoint `POST /documents/upload` (`api/routers/documents.py`) —
  multipart, mesmo padrão de sessão/coleção que `/scrape` já usa (uma
  coleção vira consultável do mesmo jeito, `/chat` funciona sem nenhuma
  mudança). Upload pra uma coleção já existente (de URL ou de outro
  upload) ANEXA, não substitui.
- **Achado real, corrigido no processo**: `RAGService.load_collection`
  já aceitava um parâmetro `source_labels` desde a 1ª rodada, mas
  `api/routers/chat.py` nunca o passava — nenhuma citação real
  (`documento_0` genérico sempre) chegava a valer nada em produção. Novo
  `session["collection_labels"]` (paralelo a `session["collections"]`,
  só populado por upload de documento) fecha esse loop.
- **Bug real encontrado e corrigido via teste end-to-end ao vivo (não um
  teste automatizado — só apareceu testando de verdade no navegador)**:
  `api/schemas.py::SourceExcerpt` nunca declarava `document_index`/
  `chunk_index`/`source_label` — Pydantic descartava os 3 campos
  silenciosamente antes da resposta chegar ao cliente, então "citações
  reais" (§37) nunca tinham, de fato, chegado ao frontend, apesar de já
  estarem calculadas internamente desde a 1ª rodada. Corrigido nos 2
  lados: schema da API (backend) + `ResultPanel.tsx` (frontend, que
  mostrava "Trecho N" genérico em vez do rótulo real) — confirmado
  visualmente no navegador mostrando "NIMBUS-X200-GUIA.PDF - PÁGINA 1"/
  "...- PÁGINA 2" depois do fix.
- Frontend: nova aba "Enviar arquivo" em `WorkspacePage.tsx` (ao lado de
  "Endereço do site", reaproveitando o componente `Tabs` já existente),
  `uploadDocument()` em `lib/api.ts` (multipart, `FormData`).
- Testes novos: `docksmith/tests/test_document_loader.py` (12, PDF/DOCX
  reais gerados em memória com as próprias libs de extração, sem
  fixture binária versionada), `api/tests/test_documents_endpoint.py`
  (8), mais 1 teste de regressão em `api/tests/test_endpoints.py`
  (`SourceExcerpt` carrega os 3 campos até o JSON final).

**Implementado — Rate limiting (§48, item independente adiantado desta
rodada por já estar pronto e ser de baixo risco):**
- `api/rate_limit.py`: janela deslizante em memória por (usuário,
  categoria de endpoint) — mesmo princípio arquitetural do resto do
  projeto nesta fase (sem Redis ainda, ver §4 do plano). Aplicado a
  `/scrape`, `/documents/upload`, `/chat` (as 3 categorias que o
  prompt-mestre cita nominalmente: upload/crawling/consultas LLM).
  `DOCSMITH_RATE_LIMIT_{SCRAPE,UPLOAD,CHAT}_PER_MINUTE`, defaults 10/10/30.
  6 testes diretos do módulo + 1 de integração via endpoint real (429 +
  header `Retry-After`).

**Avaliado e adiado (decisão explícita, não esquecimento):**
- **Storage (R2)**: a arquitetura atual (sessão inteira em RAM, TTL
  curto) já satisfaz §59 ("não persistir permanentemente por padrão")
  sem precisar de storage externo — introduzir `LocalDiskStorage` só
  trocaria RAM por disco dentro do MESMO container efêmero (§70 já
  proíbe depender do filesystem do Railway como storage persistente),
  sem ganho real sem credenciais R2 de verdade (não disponíveis nesta
  sessão). Fica registrado: a abstração `StorageService` só vale a pena
  implementar junto com credenciais R2 reais, não como exercício isolado.
- **OCR**: detecção implementada (PDF escaneado recusado com mensagem
  clara), mas a extração em si foi deliberadamente adiada — o próprio
  prompt-mestre (§9) exige que OCR rode em fila/worker, nunca na thread
  principal; implementar OCR síncrono aqui contrariaria essa regra
  diretamente. Fica acoplado ao item "Fila/workers" (fase 10).
- **REFNUM não existe em nenhum campo de OFX aqui** (nota cruzada, mesma
  disciplina "documentar em vez de fingir que não importa": esse é do
  ANZ Finance, não do Docksmith — ver o CLAUDE.md daquele repo).

**Validado**: 60/60 testes (`pytest`, backend completo) + `tsc -b`/
`vite build`/`oxlint` limpos (frontend) + teste end-to-end real
(upload de PDF real via UI de verdade → pergunta real → resposta real
do Groq → citações reais visíveis na UI), não só testes automatizados —
ver CLAUDE.md deste repositório para o relato completo da sessão de
validação ao vivo.
