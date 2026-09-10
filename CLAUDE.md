# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Docksmith — part of the "Syncron" ecosystem — extracts technical knowledge from a URL (and its linked pages) and lets the user chat with that content via RAG (Retrieval-Augmented Generation). Originally a Streamlit app (`docksmith/`, still the live production entry point), now also has a production-ready React frontend (`frontend/`) + FastAPI backend (`api/`) that reuse the exact same engine code as the Streamlit app — `api/bootstrap.py` inserts `docksmith/` into `sys.path` and imports `ScrapingService`/`RAGService`/`build_chat_llm` directly, no fork. Access is gated through the Syncron Hub (`subscription_access_api`), same pattern as sibling products.

## Architecture

```
docksmith-app/
  api/            thin FastAPI layer -- main.py, config.py, sessions.py, auth.py,
                  providers.py, bootstrap.py, resource_estimate.py, schemas.py, rate_limit.py,
                  routers/{health,models,scrape,documents,chat}.py
                  api/tests/ -- pytest, mocks RAGService/ScrapingService, exercises routing/auth/sessions
  docksmith/      the real engine, shared LIVE with the Streamlit app (not duplicated)
    service/scraping.py   ingestion (URL/site -- async aiohttp+BeautifulSoup crawl,
                           HTML->Markdown via markdownify, depth/concurrency bounded)
    service/document_loader.py   ingestion (PDF/DOCX -- PyMuPDF/python-docx, see Fase 15 §2 below)
    service/rag.py         chunking/indexing/retrieval/generation -- see "RAG pipeline" below
    tests/                 real coverage of the RAG engine + document loaders (new, see Fase 15 below)
  frontend/       Vite + React 19 + TS + Tailwind v4 -- see docs/03-frontend.md
  docs/           numbered reader-facing docs (01-visao-geral through 10-preparacao-producao)
                  + AUDITORIA_E_MIGRACAO_RAG.md (Fase 15's required audit-first deliverable)
```

**No persistence *required*** — `api/sessions.py` is a pure in-process `dict` guarded by a `threading.Lock`; by default nothing is written to disk, S3, or a database. **Correction (2026-09-03, this line was stale)**: optional durable backup to any S3-compatible object storage (Cloudflare R2 or Backblaze B2) does exist and is fully implemented (`api/r2_storage.py`) — see "## Fase 15+ — armazenamento durável" below and `docs/CONFIGURAR_ARMAZENAMENTO.md`. It stays a soft dependency by design: unconfigured, the app behaves exactly as this line originally described.

## RAG pipeline (`docksmith/service/rag.py`)

As of Fase 15 (2026-09-02, see below), this is a genuine **hybrid retrieval** pipeline, not dense-only:

1. **Chunking** — `RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)`, LangChain. Each source document gets `document_index`/`source_label` metadata before splitting; each resulting chunk gets a `chunk_index` after — real provenance, used both for citations (`ask_question_with_sources`'s `sources` list) and internally by the retriever.
2. **Indexing** — FAISS (dense, `all-MiniLM-L6-v2` embeddings, CPU) **and** BM25 (`rank_bm25`, lexical), built from the exact same chunk list, so both retrievers always index identically.
3. **Retrieval** — `HybridRetriever` (implements LangChain's `BaseRetriever`), fuses the two rankings via Reciprocal Rank Fusion (`score = Σ 1/(60 + rank_i)`), replacing the old `vector_store.as_retriever()` inside `RetrievalQA`. Confirmed via a real test (`docksmith/tests/test_rag_hybrid_retriever.py::test_lexical_signal_surfaces_exact_term_match_first`) that lexical matches genuinely influence ranking, not just dense similarity.
4. **Generation + fallback** — `RetrievalQA` as before, but `ask_question_with_sources` now retries once, in sequence, against `PROVIDER_FALLBACK_ORDER` (`groq → openai → anthropic → google`, skipping whichever provider just failed) if the configured provider's call raises. Reuses the already-built retriever/prompt, only swaps the LLM.

**Backward compatibility, verified, not assumed**: `RAGService.load_collection(markdown_list, groq_api_key=None, provider="groq", model_name=None, api_key=None, depth="equilibrada", source_labels=None)` — the old positional call `load_collection(docs, groq_key)` (used by the Streamlit app, `legacy_streamlit/`) still works exactly as before; `source_labels` is new, optional, additive.

## Fase 15 — Auditoria + primeira fatia da evolução arquitetural do RAG (2026-09-02)

Executada a pedido do prompt-mestre `01-docksmith-arquitetura-prompt-mestre.md`
(registrado em `hub/react-app/.claude/project-context/prompts/`), que exige
explicitamente uma auditoria + plano de migração incremental **antes** de
qualquer código — entregue em `docs/AUDITORIA_E_MIGRACAO_RAG.md` (leia
esse documento para o relato completo: arquitetura atual, achado real
por achado real, comparação requisito-por-requisito, e a ordem de fases
realista escolhida).

**Resumo do que foi implementado nesta rodada** (a fatia "fundacional" —
não depende de storage/filas, cabe inteiramente dentro do fluxo síncrono
em memória já existente):
- Metadado real de proveniência por chunk (`document_index`/`chunk_index`/`source_label`).
- Índice léxico BM25, ao lado do FAISS já existente.
- `HybridRetriever` com fusão RRF (k=60).
- Citações reais (não só um trecho cru) em `ask_question_with_sources`.
- Fallback entre provedores de LLM quando o configurado falha.
- `rank-bm25` adicionado a `pyproject.toml`/`requirements.txt`.
- **Primeira suíte de testes automatizados pra `docksmith/service/rag.py`**
  (`docksmith/tests/`, novo diretório — antes só a camada de API era
  testada, sempre com `RAGService` mockado). 6 testes novos + os 27
  existentes de `api/tests/` — 33/33 passando, zero regressão.

**Deliberadamente fora do escopo desta rodada** (dependem de
infraestrutura nova, registrado em `docs/AUDITORIA_E_MIGRACAO_RAG.md`
como próxima rodada, não abandonado): ingestão de PDF/DOCX, storage
Cloudflare R2, filas/workers assíncronos, reorganização em
`services/{ingestion,extraction,...}`, OCR, reranking, classificação de
intenção determinística (`QueryEngine`), grupos de documentos/comparação,
observabilidade/métricas formais.

## Fase 15, 2ª rodada — ingestão de documentos (PDF/DOCX) + rate limiting (2026-09-02)

Disparada por um pedido real do usuário testando o frontend ao vivo
("não tem opção de subir documento?") — confirmado como gap real (nem
frontend nem backend suportavam), não mal-entendido. Ver
`docs/AUDITORIA_E_MIGRACAO_RAG.md` §6 para o relato completo.

- **`docksmith/service/document_loader.py`** (novo): `load_pdf`
  (PyMuPDF, uma `LoadedDocument` por página, detecta PDF escaneado e
  recusa com erro claro em vez de OCR), `load_docx` (python-docx,
  agrupado por seção de heading + bloco de tabelas), `load_document`
  (dispatch por extensão). Zero LLM (§8 do prompt-mestre).
- **`POST /documents/upload`** (`api/routers/documents.py`, novo): mesmo
  padrão de sessão/coleção que `/scrape` — upload numa coleção existente
  ANEXA, não substitui. Limites via env:
  `DOCSMITH_MAX_FILE_SIZE_MB`/`DOCSMITH_MAX_PAGES`.
- **Bug real corrigido (achado testando de verdade no navegador, não em
  teste automatizado)**: `api/schemas.py::SourceExcerpt` nunca declarava
  `document_index`/`chunk_index`/`source_label` — esses 3 campos já
  eram calculados por `RAGService.ask_question_with_sources` desde a
  1ª rodada, mas Pydantic os descartava silenciosamente antes da
  resposta chegar ao cliente. "Citações reais" (§37) nunca tinham, de
  fato, chegado até o usuário. Corrigido no schema da API + em
  `frontend/src/features/chat/ResultPanel.tsx` (mostrava "Trecho N"
  genérico em vez do rótulo real) — confirmado visualmente no
  navegador: "NIMBUS-X200-GUIA.PDF - PÁGINA 1"/"...- PÁGINA 2".
- **`session["collection_labels"]`** (novo, paralelo a
  `session["collections"]`): fecha outro loop que já existia mas nunca
  tinha sido conectado — `source_labels` era aceito por
  `load_collection` desde a 1ª rodada, mas `api/routers/chat.py` nunca
  o passava.
- **`api/rate_limit.py`** (novo, §48): janela deslizante em memória por
  (usuário, categoria), aplicada a `/scrape`/`/documents/upload`/`/chat`.
  `DOCSMITH_RATE_LIMIT_{SCRAPE,UPLOAD,CHAT}_PER_MINUTE` (defaults
  10/10/30).
- Frontend: nova aba "Enviar arquivo" em `WorkspacePage.tsx`
  (reaproveita o componente `Tabs` já existente), `uploadDocument()`
  em `lib/api.ts` (multipart `FormData`, não passa pelo helper
  `request()` que força JSON).
- **Storage (R2) avaliado e adiado nesta rodada específica** (não
  esquecido — ver `docs/AUDITORIA_E_MIGRACAO_RAG.md` §6 para o raciocínio
  completo): sem credenciais R2 reais nesta sessão, `LocalDiskStorage` só
  trocaria RAM por disco dentro do mesmo container efêmero, sem ganho
  real. **Correção deste registro (2026-09-03)**: isso NÃO ficou adiado
  pra sempre — foi implementado de verdade numa rodada seguinte no mesmo
  dia (`api/r2_storage.py`, 4ª/5ª rodada conforme o próprio docstring do
  arquivo), só que sem nunca ganhar sua própria seção neste CLAUDE.md até
  agora — ver "## Fase 15+ — armazenamento durável" abaixo pro estado
  real e completo.

**Testes**: 27 novos (`docksmith/tests/test_document_loader.py` ×12,
`api/tests/test_documents_endpoint.py` ×8, `api/tests/test_rate_limit.py`
×7) + 1 regressão em `api/tests/test_endpoints.py` — 60/60 passando.
`tsc -b`/`vite build`/`oxlint` (frontend) limpos.

**Validado ao vivo, ponta a ponta, não só por teste automatizado**:
login real pelo Hub → real Docksmith card → upload de PDF real via UI
real (não mock) → coleção indexada → pergunta real em linguagem natural
→ resposta real do Groq, grounded, citando a página certa → aba
"Evidências" mostrando o rótulo de citação real. Achado à parte, fora do
escopo do Docksmith (registrado, não corrigido aqui): o clique
"Abrir ferramenta" no Hub mostrou uma race condition intermitente entre
a renovação periódica do token do agendador (`localStorage`) e a leitura
usada no redirect (`sessionStorage`) — mesmo gotcha já documentado no
`CLAUDE.md` do Hub ("Auth & token model"), reproduzido aqui mas não
corrigido por ser um problema do Hub, não do Docksmith.

## Fase 15+ — armazenamento durável: card-free (Backblaze B2) e o estado real do que já existe (2026-09-03)

Pedido do usuário: pesquisar se existe alternativa gratuita ao Cloudflare
R2 que não exija cartão de crédito, documentar o que falta configurar no
Docksmith e no Maestro (`syncron_core`), e o que testar pelo frontend.
Documentação completa em `docs/CONFIGURAR_ARMAZENAMENTO.md` (leia esse
arquivo pro passo a passo real) — resumo técnico aqui:

**Achado, confirmado antes de assumir**: `api/r2_storage.py` já existia,
100% implementado (upload/list/download/delete, 2 cotas de segurança,
isolamento entre usuários via hash, tolerância total a falha) e testado
(25 testes, `api/tests/test_r2_storage.py`) — contrariando a nota de
"storage avaliado e adiado" registrada mais acima neste arquivo, que
descrevia uma rodada anterior no mesmo dia (2026-09-02) e nunca foi
atualizada quando o storage de fato foi implementado numa rodada seguinte.
O único motivo de nada estar configurado era 100% de credenciais reais,
não de código faltando.

**Pesquisa real (WebSearch, não presumida)**: Cloudflare R2 continua
exigindo cartão de crédito cadastrado pra ativar o produto, mesmo pra
ficar só no nível gratuito — confirmado de novo em 2026-09-03. Backblaze
B2 pesquisado como alternativa: mesmo nível gratuito permanente (10GB),
egress grátis até 3x a média mensal armazenada, upload/listagem/leitura
grátis para contas pay-as-you-go, API S3-compatível (mesmo `boto3` já
usado aqui) — e a própria página de cadastro do Backblaze confirma "no
credit card required".

**Mudança de código, mínima e aditiva** (zero mudança de comportamento
sem as 2 variáveis novas): `config.py` ganhou `R2_ENDPOINT_URL`/
`R2_REGION` (ambas opcionais, `R2_REGION` default `"auto"` — o valor
certo pro Cloudflare R2, preservando o comportamento anterior byte a
byte quando não definidas). `r2_storage.py`'s `_get_client()` agora usa
`config.R2_ENDPOINT_URL or f"https://{config.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"`
como endpoint — ou seja, o mesmo código, sem nenhuma outra mudança,
passa a falar com Backblaze B2 (ou qualquer outro provedor S3-compatível)
só trocando variável de ambiente. `is_configured()` ajustado pra aceitar
`R2_ENDPOINT_URL` no lugar de `R2_ACCOUNT_ID` (um dos dois é obrigatório,
não os dois). 4 testes novos cobrindo o caminho do endpoint alternativo.

**Maestro (`syncron_core`) — pesquisado, não presumido: não precisa de
nada disso hoje.** Checado por completo (código-fonte, não só grep
superficial) em busca de qualquer referência a armazenamento de
objeto/upload — nenhuma encontrada. O `README.md` do próprio projeto
confirma: é um orquestrador puro (`ServiceAdapter` repassa pro backend do
produto certo), nunca guarda arquivo, nunca reimplementa lógica de
negócio de um produto. Se uma capability futura precisar devolver um
arquivo gerado, a fonte da verdade continua sendo o backend do produto
(que já pode ter armazenamento próprio, como o Docksmith agora tem) — o
Maestro só repassaria uma referência/URL, nunca guardaria cópia própria.

**Validação**: `python -m pytest -q` (repo inteiro) → 137/137, zero
regressão. `docs/CONFIGURAR_ARMAZENAMENTO.md` (novo) documenta o passo a
passo completo do Backblaze B2 + o que testar pelo frontend (upload
normal, confirmação visual do objeto no bucket, e o teste que realmente
importa: reiniciar o processo local no meio de uma sessão e confirmar que
a conversa continua funcionando via restauração automática) +
explicação de "como cada peça funciona" pra cada teste.
`docs/CONFIGURAR_R2.md` ganhou uma nota no topo cross-linkando pro novo
documento, sem nenhuma outra mudança — continua válido pra quem já tem
cartão/prefere Cloudflare.

## Fase 16 — Documentos grandes: vazamento de config corrigido, bug real de capítulo corrigido, truncamento sob demanda, divisão inteligente por capítulo (2026-09-10)

Sessão de teste real ao vivo pelo Hub (Backblaze B2 configurado com
credenciais reais de produção pelo usuário, upload de um livro real de
446 páginas) encontrou 2 problemas reais e motivou uma evolução
arquitetural — nenhum dos dois presumido, os dois confirmados testando
de verdade, não só lendo código.

**1. Vazamento de informação corrigido**: mensagens de erro de `/documents/
upload` mostravam o nome literal da env var interna pro usuário final
("...acima do limite de 300 (DOCSMITH_MAX_PAGES)."). Corrigido em
`document_loader.py` (`load_pdf`/`load_docx`) e `api/routers/documents.py`
(limite de tamanho de arquivo) — mensagens agora só citam o número, nunca
o nome da variável. Regressão travada em teste (`"DOCSMITH_MAX_PAGES"
not in detail`/idem pra `DOCSMITH_MAX_FILE_SIZE_MB`).

**2. Bug real de detecção de capítulo em PDF, achado testando o livro real
(não hipotético)**: perguntar "qual o título do capítulo 7?" contra um
livro real de 446 páginas devolvia "não está na documentação" — a busca
estrutural rápida (`query_engine.py::classify_intent`) nunca encontrava
o capítulo certo. Causa raiz, em `document_loader.py`: a heurística de
"qual tamanho de fonte é capítulo" escolhia o MAIOR tamanho do documento
inteiro — quebra em qualquer livro com capa (a capa tem a fonte maior de
todo o PDF, mas só aparece 1x; `current_chapter` ficava travado no texto
da capa pras ~280 páginas seguintes). Uma 1ª correção (mais frequente
entre páginas) também errou, na direção oposta: subtítulos de CONTEÚDO
(ex. "Data Engineering Defined") são mais frequentes que o próprio
"CHAPTER N" real, porque cada capítulo tem várias subseções. Fix real:
`_CHAPTER_HEADING_LABEL_RE` (`^(chapter|cap[íi]tulo|cap\.?)\s*\d+\.?\s*$`)
exige que o TEXTO INTEIRO da linha seja um rótulo de capítulo de verdade
(não "contém um dígito", que também capturava "Principle 1: Choose
Common Components Wisely"), presente em 2+ páginas distintas — extraído
como `_numbered_chapter_candidates()`/`_has_reliable_chapter_labels()`,
reaproveitado depois pela Fase A abaixo. Validado ao vivo: a mesma
pergunta, depois do fix, responde "CHAPTER 7" via `structural_search`
(sem chamada de LLM), confirmado no log do backend.

**3. Truncamento sob demanda** (`truncate: bool`, `PageLimitExceededError`
com `actual_count`/`max_pages`/`unit`): documento acima de
`DOCSMITH_MAX_PAGES` recusa por padrão com um 422 estruturado
(`{"error":"page_limit_exceeded",...}`) — o frontend (`WorkspacePage.tsx`)
usa isso pra oferecer processar só as primeiras N páginas, reenviando o
mesmo upload com `truncate=true`.

**4. Fase A do plano "livros grandes" — divisão inteligente consciente de
capítulo, novo endpoint `POST /documents/upload/split`**: alternativa ao
truncamento — em vez de descartar o que excede `DOCSMITH_MAX_PAGES`,
divide o documento inteiro em N coleções, cada uma dentro do limite,
fechando ao final de um capítulo sempre que possível (nunca corta um
capítulo no meio a menos que ele sozinho já exceda o limite, caso em que
só ELE cai pra janela de página fixa — os demais capítulos continuam
intactos). Núcleo do algoritmo:
`document_loader.py::_group_documents_by_chapter_within_limit()` — função
única, reaproveitada por `split_pdf_into_parts()` (unidade = página,
usa `_has_reliable_chapter_labels()` do item 2 acima pra nunca dividir
por um capítulo "adivinhado", só por rótulo confirmado) e
`split_docx_into_parts()` (unidade = seção real do Word, sem a mesma
ambiguidade do PDF). `PdfPart`/`DocxPart` carregam `page_count`/
`total_chars` como properties. Dispatcher `split_document_into_parts()`
ao lado do `load_document()` já existente, mesmo padrão.

API: `POST /documents/upload/split` (endpoint próprio, não reaproveita
`/documents/upload` — a resposta é genuinamente outro formato, N coleções
com metadado cada, não 1 só) devolve `SplitUploadResponse` (`session_id`,
`base_collection_name`, `parts: DocumentPartInfo[]` — `collection_name`,
`unit` ("páginas"/"seções"), `position_start`/`position_end`, `chapters`,
`page_count`, `document_count`, `estimated_chunks`/`estimated_size_mb`
via `resource_estimate.estimate_chunk_count`, reaproveitado sem duplicar
a fórmula). Cada parte vira uma coleção própria em
`session["collections"]`/`collection_labels`/`collection_structure`,
consultável em `/chat` exatamente como qualquer outra coleção — nenhum
caso especial no resto do sistema. **1 backup só no R2** do arquivo
original inteiro (nunca N backups por parte).

Frontend: `WorkspacePage.tsx`'s banner de "página acima do limite" ganhou
um 3º botão, "Dividir em partes e processar tudo" (`splitUploadDocument`,
`lib/api.ts`), ao lado de "Processar só as primeiras N páginas"/
"Cancelar" — ao concluir, adiciona todas as N coleções ao estado local e
navega pra 1ª parte; as demais já aparecem em "Coleções da sessão".

**Validado**: `python -m pytest -q` (repo inteiro) → 166/166 (148
baseline + 18 de `document_loader.py`, incluindo 2 fixtures sintéticas
com capa+capítulos desiguais + capítulo sozinho maior que o limite; 8 de
`test_documents_endpoint.py::TestSplitUpload*`). `npx tsc -b` + `npx
oxlint` limpos (zero warning novo nos arquivos tocados). Ao vivo, pelo
Hub local (bypass de dev — `VITE_DEV_BYPASS_AUTH`/`DOCKSMITH_API_DEV_
BYPASS_AUTH`, só local, nunca em produção, `IS_PRODUCTION and
DEV_BYPASS_AUTH` já levanta erro se alguém tentar): upload real do livro
de 446 páginas → banner 422 sem vazar nome de env var → "Dividir em
partes e processar tudo" → 2 coleções reais criadas (parte 1: páginas
1-295, 289 docs, capítulos 1-7; parte 2: páginas 297-446, 148 docs,
capítulos 8-11 + apêndices A/B — nenhum capítulo cortado ao meio, a
fronteira das partes cai exatamente entre capítulo 7 e 8) → 1 backup só
no R2 (confirmado no log, mesmo tamanho do arquivo original) → pergunta
"qual o título do capítulo 1?" na parte 1 responde "CHAPTER 1" via
`structural_search` → pergunta "qual o título do capítulo 7?" na parte 2
(onde ele NÃO está) responde honestamente "essa informação não está na
documentação", citando o que de fato existe ali (Capítulo 9) — confirma
zero alucinação mesmo caindo no caminho semântico (LLM) em vez do
estrutural → mesma pergunta sobre capítulo 7 na parte 1 (onde ele
realmente está) responde "CHAPTER 7" via `structural_search`. Console do
navegador sem erro de aplicação (só ruído padrão de extensão do Chrome).

**Achado ao vivo, confirma por que a Fase E do plano é necessária**:
alternar entre as 2 partes no mesmo teste forçou reindexação completa a
cada troca (`session["rag_service"]` é hoje 1 slot só por sessão, sem
cache) — confirmado no log (`Indexando coleção '...'` repetido a cada
troca de coleção, mesmo já tendo indexado antes). Não é regressão desta
fase; é a limitação real que a próxima fase (teto de RAM + cache LRU)
resolve.

**Atualização**: as fases E-I do mesmo plano (teto de RAM + cache LRU,
checkpoints de processamento, embeddings em lote, multicontexto, fachada
de storage) foram concluídas na mesma sessão de trabalho -- ver "Fase 17"
abaixo.

## Fase 17 — Cache LRU (2 tetos independentes), checkpoints observáveis, embeddings em lote, multicontexto (até 3 coleções), fachada de storage (2026-09-10)

Continuação direta da Fase 16 -- fases E a I do plano "livros grandes"
(as fases A-D já estavam cobertas pelo trabalho da Fase 16: divisão por
capítulo, metadados, PDF/DOCX separados, 1 backup só). Escopo pedido
pelo usuário: "finalize todas as fases e teste tudo".

**Fase E -- cache LRU por sessão, 2 tetos independentes + orçamento
cumulativo de chunks.** Antes desta fase, `session["rag_service"]`/
`session["loaded_signature"]` eram um slot ÚNICO por sessão -- trocar de
coleção sempre forçava reindexação completa, mesmo de algo já indexado
minutos antes (confirmado ao vivo na Fase 16: "alternar entre as 2
partes... forçou reindexação completa a cada troca"). Substituído por
`session["loaded_indices"]: dict[signature, {"rag_service",
"estimated_mb", "chunk_count", "last_used"}]`, com evicção LRU em
`api/index_cache.py` (módulo novo, puro, testável isolado --
`total_indexed_mb`/`total_indexed_chunks`/`evict_to_fit`/
`invalidate_collection`). **2 tetos independentes** (pedido explícito do
usuário, "não só por memória"): `DOCSMITH_MAX_SESSION_INDEX_MB` (default
800) e `DOCSMITH_MAX_CACHED_COLLECTIONS` (default 3) -- a evicção
dispara quando QUALQUER um dos dois é ultrapassado, testado
isoladamente (1 teste força evicção só por quantidade com memória de
sobra, outro só por memória com quantidade de sobra). **Orçamento
cumulativo de chunks por sessão** (pedido explícito do usuário,
diferente do bloqueio de coleção grande ISOLADA que já existia):
`DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION` (default 20000) -- soma tudo
que já está residente no cache + a coleção nova, bloqueia com o mesmo
padrão 413 + `requires_confirmation` já usado (reaproveitado, não
duplicado), mensagem exata pedida pelo usuário: "O documento ultrapassa
o limite de processamento desta sessão. Deseja continuar?". `ChatResponse`
ganhou `was_cached: bool`. Frontend (`ChatPage.tsx`): como `was_cached`
só chega DEPOIS da resposta (tarde demais pra escolher o texto do
carregamento desde o início), a transparência pedida ("Preparando
novamente este contexto...") foi implementada por TEMPO de espera (troca
de "Pensando…" depois de 4s) em vez de um palpite de estado client-side
-- mais honesto, reage ao que está genuinamente acontecendo.

**Validado AO VIVO** (não só por teste automatizado): reaberto o mesmo
livro de 446 páginas dividido em 2 partes (Fase 16), perguntado na parte
1, depois na parte 2, depois de volta na parte 1 -- confirmado no log:
`POST /chat -> 200 (0ms)` e `cache=True`, ou seja, voltar pra uma
coleção já vista antes não reindexa mais (antes desta fase, reindexava
sempre).

**Fase F -- checkpoints de processamento observáveis.**
`session["collection_status"]: dict[nome, CollectionStatus]` (novo enum
em `api/schemas.py`: `"uploaded"|"extracting"|"chunking"|"embedding"|
"indexed"|"ready"|"failed"`), exposto via `GET /sessions/{id}`
(`SessionCollectionInfo.status`, campo novo). Transições reais: `/scrape`
e `/documents/upload`(`/split`) gravam `"uploaded"` após extração bem-
sucedida; `/chat` grava `"embedding"` antes de indexar, `"indexed"` →
`"ready"` depois; qualquer falha (`ok=False` OU exceção capturada) grava
`"failed"`, que fica visível até a PRÓXIMA pergunta real tentar de novo
-- nunca reescrito sozinho, nunca escondido, sem loop de retry
automático.

**Achado real corrigido no caminho, não hipotético**: antes desta fase,
`/documents/upload` extraía o documento ANTES de criar/recuperar a
sessão -- se a extração falhasse (ex.: página acima do limite), NENHUMA
sessão existia ainda, então "failed" nunca teria como ficar observável
via `GET /sessions/{id}` (a coleção nunca apareceria lá, mesmo com o
status gravado internamente). Corrigido reordenando (sessão primeiro,
extração depois, agora em `run_in_threadpool` -- mesmo padrão que
`restore_session` já usava, no mesmo arquivo, só nunca tinha sido
aplicado ao caminho principal de upload) e fazendo `GET /sessions/{id}`
unir os nomes de `collections` E `collection_status` (uma coleção que só
existe no 2º dict, porque a extração falhou, aparece com
`document_count: 0` e `status: "failed"`).

**Confirmado AO VIVO, achado genuíno do próprio teste (não fabricado)**:
durante a validação manual desta fase, o 1º clique em "Enviar e extrair"
(antes de escolher "Dividir em partes") tentou o upload normal primeiro
e falhou (446 > 300 páginas) -- `GET /sessions/{id}` dessa sessão
mostrou exatamente `{"name": "livro-fases-e-h", "document_count": 0,
"status": "failed"}`, confirmando ao vivo, sem simulação, que o achado
acima e sua correção são reais.

**Fase G -- embeddings em lote.** Achado da auditoria (confirmado lendo
o código, não suposto): `rag.py:260` fazia `FAISS.from_documents(texts,
self.embeddings)` numa chamada só, pra QUALQUER tamanho de coleção.
Novo `RAGService._build_vector_store_in_batches(texts, batch_size)` --
`FAISS.from_documents` só no 1º lote, `vector_store.add_documents(...)`
incremental nos seguintes; `batch_size` ausente/`None`/`<=0`/`>=
len(texts)` preserva o comportamento de sempre, 1 chamada só (nunca
muda o resultado do índice, só o RITMO em que os vetores entram nele).
Novo parâmetro `embedding_batch_size` em `load_collection` (Streamlit
nunca passa isso, comportamento idêntico a sempre); `api/config.py`
ganhou `DOCSMITH_EMBEDDING_BATCH_SIZE` (default 100), resolvido em
`api/routers/chat.py` e passado como parâmetro -- `docksmith/service/
rag.py` continua sem nenhuma dependência de `api/`, mesmo princípio já
usado por `DOCSMITH_MAX_PAGES`/`document_loader.py`. Nota de honestidade
técnica (não escondida): o ganho real é limitar o PICO de memória de
vetores retidos simultaneamente antes de entrar no índice, não reduzir o
custo total -- `sentence-transformers` já faz seu próprio batching
interno (`encode(batch_size=32)`) por baixo, isto é uma camada acima
disso.

**Validado com equivalência real** (`docksmith/tests/
test_rag_batched_embeddings.py`): mesma contagem de vetores construindo
em lote vs. de uma vez só; toda chunk continua recuperável por termo
exclusivo; ranking do `HybridRetriever` (FAISS+BM25+RRF) idêntico, byte
a byte, batendo lote ou não, pra 3 perguntas diferentes. **Confirmado AO
VIVO**: indexar a parte 1 do livro (941 chunks) gerou 10 lotes reais no
log (`Lote de embeddings 1/10`...`10/10`), a parte 2 (466 chunks) gerou
5, e a combinação das duas via multicontexto (1407 chunks) gerou 15 --
sempre terminando em `FAISS index created with N chunks` com N batendo
exatamente a soma esperada.

**Fase H -- multicontexto (até 3 coleções por pergunta).** `ChatRequest`
ganhou `collection_names: list[str] | None = Field(default=None,
max_length=3)` -- ausente/vazio preserva 100% o modo de sempre
(`collection_name` sozinho); quando presente (1-3 nomes), tem
precedência sobre `collection_name` pra decidir quais coleções combinar.
Concatena docs/labels/estrutura das N coleções ANTES de `load_collection`
-- em modo multi, rótulos sem fonte própria (raspagem por URL) ganham
prefixo do nome de origem (`"{nome} - documento_{i}"`, evita 2 coleções
sem rótulo colidirem em citações idênticas e ambíguas); modo single
continua 100% intocado (mesmo código de antes, mesmo default
`documento_{i}` de dentro do `RAGService`). Signature-key vira uma TUPLA
ordenada de nomes em modo multi (`api/index_cache.invalidate_collection`
já sabia procurar dentro de tuplas desde a Fase E, pensado exatamente
pra isso). `resource_estimate`/bloqueio de coleção grande/orçamento
cumulativo/cache LRU -- tudo reaproveitado sem lógica nova, já que
operam sobre a lista de docs já concatenada. Frontend (`ChatPage.tsx`):
chips "Combinar com: {nome}" acima do campo de pergunta, um por outra
coleção da sessão, capados em 2 selecionados (a atual + 2 = teto de 3);
zera a seleção ao trocar de coleção.

**Validado AO VIVO**: com as chips de "Combinar com" ativadas nas 2
partes do mesmo livro, perguntado "qual o título do capítulo 9?" (que
só existe na parte 2) estando na tela da parte 1 -- respondido
corretamente "CHAPTER 9" via `structural_search`, confirmado no log:
`Chat respondido: coleções=livro-fases-e-h - parte 1 + livro-fases-e-h -
parte 2 ... cache=False`, `FAISS index created with 1407 chunks` (941 +
466, a soma exata dos 2 índices individuais).

**Fase I -- fachada de storage: decisão + entregável de baixo risco.**
Confirmado (mesma auditoria da Fase 16): a substância já estava pronta
(`api/r2_storage.py` já é genérico nos nomes, já funciona com R2 ou
Backblaze B2). Decisão registrada: não renomear nada existente (tocaria
toda a superfície de testes/`.env` já configurado em produção por um
ganho puramente de nome). Implementado o módulo fino opcional --
`api/storage_service.py::StorageService`, repasse 1:1 pras funções
reais de `r2_storage.py`, zero lógica própria, zero duplicação -- pra
quem preferir programar contra um nome neutro.

**Validado**: `python -m pytest -q` (repo inteiro) → 206/206 (166 no
fim da Fase 16 + 40 novos: 10 de `test_index_cache.py`, 9 de
`test_collection_status.py`, 6 de `test_rag_batched_embeddings.py`, 5 de
`test_multicontext.py`, 4 de `test_storage_service.py`, + 6 novos em
`test_endpoints.py` cobrindo `was_cached`/evicção/orçamento cumulativo).
`npx tsc -b`/`npx oxlint` limpos (zero warning novo). Varredura de
vazamento (mesmo processo da Fase 16): nenhum nome de env var nova
(`DOCSMITH_MAX_SESSION_INDEX_MB`/`DOCSMITH_MAX_CACHED_COLLECTIONS`/
`DOCSMITH_MAX_EMBEDDING_CHUNKS_PER_SESSION`/`DOCSMITH_EMBEDDING_BATCH_SIZE`)
aparece em texto voltado pro usuário; exceções internas (`except
Exception as exc`) nunca vazam pro `detail` da resposta HTTP, só pro log
do servidor; frontend sem nenhum `console.log`/`console.error` que
pudesse expor dado sensível.

## Running locally, testing

See `docs/02-executar-localmente.md` for the reader-facing version.
Backend tests: `python -m pytest api/tests/ docksmith/tests/ -q` (from
the repo root — both directories need to run together for full coverage,
`api/tests/` mocks the RAG engine, `docksmith/tests/` exercises it for
real). Frontend: see `docs/03-frontend.md`.
