# Preparação para produção

**Nenhum cutover foi feito.** Este documento é o resultado de duas auditorias completas do que já foi construído (`api/`, `docksmith/`, `frontend/`) e da preparação da infraestrutura necessária para o deploy — sem tocar em `hub/`, `subscription_access_api/`, `URL_DOCKSMITH_APP`, sem criar banco de dados/Redis/persistência nova, e sem desativar o Streamlit atual.

## Arquitetura de produção recomendada (confirmada, sem mudanças)

```
frontend/  →  Vercel (build estático do Vite + vercel.json com rewrite SPA)
api/       →  Railway (processo persistente único, sempre ativo)
docksmith/ →  continua no Streamlit Cloud, sem mudanças, como fallback/rollback
```

Sem banco de dados, sem Redis, sem persistência permanente — o estado (coleções raspadas, índice FAISS, RAG carregado) continua 100% em memória do processo, exatamente como hoje. Nada muda no `hub/` ou `subscription_access_api/` além de, no momento do cutover, trocar o valor de `URL_DOCKSMITH_APP` — igual já documentado em [09-deploy.md](./09-deploy.md).

## Decisão de hospedagem do backend — por quê Railway

`api/` carrega `sentence-transformers` (que traz `torch` como dependência transitiva), `faiss-cpu` e todo o ecossistema `langchain`. Isso descarta serverless e exige um processo persistente único (ver raciocínio completo na primeira versão desta seção, inalterado). Comparação Railway/Render/Fly.io também inalterada — **recomendação continua Railway**.

**Preparado (não executado):** `Procfile` na raiz (`web: uvicorn api.main:app --host 0.0.0.0 --port $PORT`).

### RAM do backend — medição real (não estimativa)

Medido ao vivo no processo real rodando localmente (Windows, Python 3.12, CPU-only), usando `Get-Process`/`Get-CimInstance` no processo worker do uvicorn, em cada etapa:

| Etapa | RSS (memória residente) | Memória committed |
|---|---|---|
| Baseline pós-startup (modelo de embeddings já carregado, 0 requisições) | **~448 MB** | ~997 MB |
| Após 1 scraping (1 documento) | ~453 MB (+5MB) | ~1002 MB |
| **1ª consulta RAG** (indexação FAISS + 1ª inferência) | **~633 MB (+180MB)** | **~2086 MB (+1084MB)** |
| 2ª consulta, mesma sessão (índice reaproveitado) | ~633 MB (sem mudança) | ~2086 MB (sem mudança) |
| +1 sessão concorrente (2ª coleção pequena) | ~735 MB (+102MB) | ~2253 MB |
| +1 sessão com coleção maior (13 docs), **pico durante indexação** | **~832 MB (transitório)** | ~2383 MB |
| Mesma coleção, em repouso após indexar | ~762 MB | ~2289 MB |

**Achados-chave:**
- A **primeira consulta real** depois do startup é o maior salto isolado (+180MB RSS, +1GB committed) — é o custo de aquecimento do `torch` fazendo inferência pela primeira vez (alocação de buffers internos), não algo que se repete depois.
- Consultas subsequentes na mesma sessão têm **custo adicional zero** — o índice e a máquina de inferência já estão quentes.
- Cada sessão simultânea adicional custa entre ~100-170MB RSS pra coleções pequenas/médias, escalando com o número de chunks indexados.
- Colecões maiores geram um **pico transitório durante a indexação** (computação dos embeddings) notavelmente acima do estado de repouso — a memória cai depois que a indexação termina, mas o pico precisa ser suportado pelo container sem OOM.
- A métrica "committed"/private do Windows é bem mais alta que a RSS (comportamento específico do alocador do PyTorch nesse SO) — em Linux (destino real: Railway), o comportamento tende a ser mais parecido com a RSS; recomendo **remedir no primeiro deploy real** pra confirmar.

**Conclusões para dimensionamento:**
- **RAM mínima tecnicamente viável:** 1GB — sobrevive a 2-3 sessões leves simultâneas, mas sem margem nenhuma pra picos de indexação maiores ou para overhead do container/SO.
- **RAM recomendada: 2GB** — cobre confortavelmente o baseline (~450-650MB) + várias sessões concorrentes + picos de indexação de coleções maiores, com folga real.
- **Margem de segurança:** não operar sustentado acima de ~70-75% do limite do container (com 2GB, isso deixa ~500-600MB de headroom acima do observado com 3 sessões ativas).
- **Comportamento esperado no cold start:** o modelo de embeddings carrega na importação do módulo — todo boot do processo (não cada request) paga esse custo. Recomendo cache do modelo HuggingFace num volume persistente se a plataforma suportar, pra não rebaixar da internet a cada deploy.
- **1GB é suficiente?** Tecnicamente sobrevive no teste feito (pico de ~832MB com 3 sessões/15 documentos), mas é **desconfortavelmente justo** — sem margem pra tráfego real, uma coleção grande, ou múltiplos usuários simultâneos. **Não recomendo rodar produção em 1GB.**
- **Configuração inicial mais segura para Railway:** serviço com **2GB de RAM**, 1 única instância (sem réplicas horizontais — ver justificativa arquitetural), monitorar uso real nos primeiros dias e ajustar.

### Calibração da estimativa de memória de indexação (implementado nesta auditoria)

Para evitar que uma coleção raspada seja grande demais para a memória disponível da instância (e derrube o processo durante a indexação), `api/resource_estimate.py` estima, **antes** de criar o índice FAISS, quanta RAM a indexação de uma coleção vai consumir — sem persistir nada, puramente informativo/defensivo.

**Como os números são calculados (nenhum limite inventado):**
- **Nº de chunks estimado:** usa exatamente `CHUNK_SIZE`/`CHUNK_OVERLAP` de `docksmith/service/rag.py` (os mesmos do splitter real), não um valor duplicado.
- **Custo por chunk e overhead fixo:** calibrados por medição real (não teórica). Indexar uma coleção real de 875 chunks (`docs.python.org/collections.html`, `max_depth=1`) custou **+133.8MB de RSS** no processo. Resolvendo `custo_fixo + 875 × custo_por_chunk = 133.8MB` com um overhead fixo conservador de 60MB (nova instância de `RAGService`/`HuggingFaceEmbeddings`/índice FAISS vazio) dá **~85KB por chunk** — a conta de volta (`60MB + 875×85KB ≈ 132.9MB`) bate com o medido, erro <1%.
  - Ressalva documentada no código: a **primeira** indexação depois do processo subir paga também um "aquecimento" do `torch` (~180-200MB, ver seção anterior) que é por-processo, não por-coleção — a calibração acima isola e não tenta prever esse custo único.
- **Memória disponível/em uso:** lida em tempo real via `psutil` (`Process.memory_info().rss` do processo atual + `virtual_memory().available` do host), nunca um valor fixo — os limiares abaixo são uma **fração** dessa memória real, então se adaptam sozinhos a qualquer tamanho de instância (1GB, 2GB, etc.).

**Limiares (fração da memória disponível no momento):**

| Status | Limiar (estimativa ÷ memória disponível) | Mensagem exibida |
|---|---|---|
| `ok` | < 25% | "Coleção dentro do limite recomendado" |
| `atencao` | 25%–55% | "Coleção grande" |
| `muito_grande` | 55%–85% | "Coleção muito grande" (recomenda reduzir, mas não bloqueia) |
| `bloqueado` | ≥ 85% | Mesma mensagem, **mas o backend recusa indexar** (HTTP 413) até o usuário confirmar explicitamente (`confirm_large_collection: true`) |

**Onde entra no fluxo:** `POST /scrape` já retorna `resource_estimate` na resposta (o frontend mostra o aviso certo antes de ir pro chat); `POST /chat` recalcula a estimativa no momento de indexar de fato e bloqueia com 413 se `bloqueado` e não confirmado — o ponto de bloqueio real é o mesmo lugar onde a indexação (FAISS + embeddings) de fato aconteceria.

**Validação:** testado com 4 coleções (sintéticas, dimensionadas a partir da fórmula acima e da memória real disponível na máquina de teste — replicar isso com raspagem real exigiria dezenas de milhares de páginas) via `TestClient` contra o app real (`api/main.py`, sem nenhuma alteração de código para o teste): 253 chunks → `ok`; 4.556 chunks (429MB estimado) → `atencao`; 8.521 chunks (751MB estimado) → `muito_grande`; 12.053 chunks (1037MB estimado) → `bloqueado`, com `/chat` retornando 413 sem confirmação e 200 ao reenviar com `confirm_large_collection: true`. Todos os 4 tiers dispararam nos limiares esperados.

## Logging estruturado (implementado nesta auditoria)

`api/logging_config.py` (novo) reaproveita o mesmo `logging` stdlib que `docksmith/service/*.py` já usava — nenhuma biblioteca nova. Cobertura adicionada:

| Evento | Onde |
|---|---|
| Inicialização/encerramento da API | `api/main.py` (lifespan) |
| Requisições (método, rota, status, duração) | `api/main.py` (middleware; `/health` fica de fora pra não gerar ruído) |
| Autenticação aceita/rejeitada | `api/auth.py` |
| Criação/expiração de sessão | `api/sessions.py` |
| Scraping iniciado/concluído/falhou | `api/routers/scrape.py` |
| Indexação de coleção + resposta do chat | `api/routers/chat.py` |
| Teste de conexão com provedor (sucesso/falha) | `api/providers.py` |
| LLM configurado + pergunta respondida | `docksmith/service/rag.py` (compartilhado com Streamlit, mudança puramente aditiva) |

**Nunca logado:** API keys, tokens (mesmo parciais), senhas, ou o texto de perguntas/respostas do usuário — só metadados (contagens, nomes de provedor/modelo, IDs de sessão, URLs raspadas, status HTTP). Confirmado por busca automatizada em todos os arquivos alterados.

## Variáveis de ambiente — fallback silencioso removido (implementado nesta auditoria)

Antes, uma variável obrigatória ausente fazia o app tentar falar com `localhost` silenciosamente em produção. Agora:

- **Frontend**: `frontend/src/lib/env.ts` lança erro explícito em runtime se faltar `VITE_API_BASE_URL`/`VITE_HUB_API_BASE_URL` em build de produção (`import.meta.env.PROD`). Além disso, `frontend/vite.config.ts` agora **falha o próprio `vite build`** (não só em runtime no navegador) se essas variáveis não estiverem definidas — testado nos dois sentidos (falha sem elas, passa com elas).
- **Backend**: `api/config.py` ganhou `ENVIRONMENT` (default `"development"`; definir `ENVIRONMENT=production` no Railway). Com `ENVIRONMENT=production`, `API_BASE` e `DOCKSMITH_API_CORS_ORIGINS` ausentes derrubam o processo na inicialização com um erro claro, e `DOCKSMITH_API_DEV_BYPASS_AUTH=true` é **proibido** (erro na inicialização) — defesa extra contra deixar o bypass ligado sem querer. Testado isoladamente nos 3 cenários (vars ausentes falha, vars presentes passa, bypass proibido falha).
- Defaults locais continuam existindo normalmente em dev (`ENVIRONMENT` não definido = comportamento de sempre, sem quebrar nada).
- `HUB_URL`/`VITE_HUB_URL` não precisou virar obrigatória: seu default já é a URL real de produção (`https://www.syncron.pro`), não um placeholder de dev.

### Variáveis de ambiente completas

#### Frontend (Vercel)
| Variável | Finalidade | Onde é usada | Obrigatória em produção? | Default local |
|---|---|---|---|---|
| `VITE_API_BASE_URL` | Base da API do Docksmith (`api/`) | `frontend/src/lib/api.ts` (todas as chamadas) | **Sim — build falha sem ela** | `http://localhost:8787` |
| `VITE_HUB_API_BASE_URL` | Base do `subscription_access_api` (validação de token) | `frontend/src/lib/auth.ts` | **Sim — build falha sem ela** | `http://localhost:8000` |
| `VITE_HUB_URL` | Link "Ir para o Hub" quando sem sessão válida | `frontend/src/features/auth/AuthGate.tsx` | Não (default já é produção) | `https://www.syncron.pro` |
| `VITE_DEV_BYPASS_AUTH` | Pular autenticação real (QA local) | `frontend/src/features/auth/AuthGate.tsx` | **Não definir em produção** | `false` |

#### Backend (Railway)
| Variável | Finalidade | Onde é usada | Obrigatória em produção? | Default local |
|---|---|---|---|---|
| `ENVIRONMENT` | Liga o modo estrito (falha alto em vez de fallback silencioso) | `api/config.py` | Recomendada (`production`) | `development` |
| `API_BASE` | Base do `subscription_access_api` (revalidação de token a cada request) | `api/auth.py` | **Sim — processo não inicia sem ela** (com `ENVIRONMENT=production`) | `http://localhost:8000` |
| `DOCKSMITH_API_CORS_ORIGINS` | Origens liberadas a chamar a API | `api/main.py` (CORS) | **Sim — processo não inicia sem ela** (com `ENVIRONMENT=production`) | `localhost:5173,5174,5175` |
| `GROQ_API_KEY` | Chave padrão do Docksmith (provedor Groq sem custo pro usuário) | `api/config.py`/`docksmith/service/rag.py` | Não obrigatória — sem ela, só a opção "Groq sem chave" some | não definida |
| `DOCKSMITH_SESSION_TTL_SECONDS` | TTL da sessão em memória | `api/sessions.py` | Não | `3600` |
| `DOCKSMITH_API_DEV_BYPASS_AUTH` | Pular autenticação real (QA local) | `api/auth.py` | **Proibido em produção — processo não inicia se `true`** | `false` |
| `PORT` | Porta HTTP | `Procfile` | Definida automaticamente pela plataforma | — |

Nenhum valor real de nenhuma variável foi colocado nesta documentação.

## Testes automatizados (criados nesta auditoria)

`api/tests/` — pytest, focado só nos fluxos críticos pré-deploy (nada de suíte de cobertura ampla):

| Arquivo | Cobre |
|---|---|
| `test_auth.py` (6 testes) | token ausente, inválido, válido, bypass de dev aceito/rejeitado, `subscription_access_api` fora do ar |
| `test_sessions.py` (4 testes) | isolamento entre usuários, reuso de sessão, sessão de outro usuário ignorada, expiração por TTL |
| `test_providers.py` (5 testes) | recomendações batem com o catálogo real de provedores/modelos (regressão), toda recomendação com chave obrigatória tem `apiKeyHelp`, chave do usuário nunca vaza numa mensagem de erro |
| `test_endpoints.py` (8 testes) | scrape (sucesso/falha/sem auth), chat (sessão/coleção inexistente, provedor sem chave, resposta com fontes, falha de indexação) |

**23/23 passando, offline (scraping e chamadas de LLM mockados), ~1.6s.** `pytest` adicionado como dependência de desenvolvimento (`poetry add --group dev pytest`).

**Frontend:** decidi **não** adicionar um framework de testes (nenhum existe hoje) só para cobrir uma função. A lógica mais delicada e nova (`splitConclusion.ts`) já foi validada manualmente com 7 casos representativos (conclusão curta, resposta de uma frase, tabela/lista/código como primeiro bloco, parágrafo longo) durante o desenvolvimento. Configurar Vitest/Jest do zero pra um arquivo não pareceu ter necessidade clara o suficiente — sinalizando aqui caso você discorde.

## Frontend — Vercel

- Build de produção validado, agora com verificação ativa de env vars obrigatórias (ver acima).
- `frontend/vercel.json` — rewrite de SPA (sem ele, `/como-funciona`/`/chat/:nome` dariam 404 num refresh direto).
- Favicon, `<title>`, meta description e `theme-color` corretos em `index.html`.
- Zero URLs `localhost` hardcoded — tudo via `import.meta.env.VITE_*`.
- Responsividade validada em 320-2304px (dark e light) em fases anteriores; balão de chat com bug de overflow horizontal encontrado e corrigido nesta rodada (`min-w-0 max-w-full` — respostas com lista+código aninhados não estouravam mais a largura do balão).

## Alterações necessárias no Hub / subscription_access_api

**Nenhuma mudança de código, reconfirmado nesta auditoria.** Fluxo revalidado ponta a ponta sem tocar em nenhum dos dois serviços:

```
Hub → subscription_access_api (POST /generate-agendador-token)
    → abre URL_DOCKSMITH_APP?token=...
    → frontend (AuthGate lê ?token=, chama POST /validate-agendador-token)
    → token guardado em sessionStorage
    → cada chamada a api/ manda o token como Bearer
    → api/auth.py revalida contra subscription_access_api a cada request
```

`URL_DOCKSMITH_APP` só muda no momento do cutover, não agora.

## Segurança — auditoria final

| Item verificado | Resultado |
|---|---|
| API keys/secrets expostos em código | Nenhum encontrado (busca automatizada em todos os arquivos alterados) |
| `.env` versionado | Não |
| Credenciais hardcoded | Nenhuma |
| CORS aberto demais | Não — allowlist explícita, `allow_credentials=False`, inalterado nesta rodada |
| Endpoints sem autenticação indevida | Só `/health` e `GET /models` são públicos (sem dado sensível); resto exige token |
| Isolamento entre usuários | Confirmado por teste automatizado (`test_sessions.py`) |
| API key do usuário persistida? | Não — recalculada a cada request |
| Segredo vazando pro frontend | `GROQ_API_KEY` nunca aparece em nenhuma resposta |
| Logs com dado sensível | Nenhum — auditado em todos os `logger.*`/`logging.*` novos |
| Erro de provedor vaza a chave do usuário? | Não — confirmado por teste automatizado (`test_providers.py`) |

### Corrigido nesta rodada (aditivo, seguro)
- Logging estruturado adicionado (ver seção acima).
- Fallback silencioso pra `localhost` removido, com erro explícito em produção.
- `frontend/vercel.json` e `Procfile` criados.
- Testes automatizados criados pra auth/isolamento/endpoints/provedores.

### Riscos remanescentes (decisão de produto/infra, não bugs)
1. `test_connection` (`api/providers.py`) retorna `str(e)[:300]` direto pro frontend — é erro do próprio provedor configurado pelo usuário (não vaza dado de terceiros), mas pode expor texto cru de SDK. Baixa severidade, não corrigido.
2. Bundle do frontend > 500KB (aviso do Vite) — funciona normalmente, code-splitting deixaria o carregamento inicial mais rápido. Não bloqueante.
3. Estado em memória impede escalonamento horizontal — decisão arquitetural conhecida, não um bug; documentado explicitamente pra não ser esquecido ao configurar o Railway.
4. Medições de RAM foram feitas em Windows local — recomendo remedir no ambiente Linux real do Railway assim que o primeiro deploy acontecer, já que o comportamento de memória do `torch` pode diferir por SO.

## Checklist de deploy

- [ ] Confirmar plano no Railway (recomendado: 2GB RAM, 1 instância)
- [ ] Configurar `ENVIRONMENT=production` + demais env vars da tabela acima no Railway
- [ ] Deploy do `api/` no Railway
- [ ] Validar `/health` e `/models` em produção
- [ ] Validar um `/scrape` e `/chat` reais em produção
- [ ] Remedir RAM real no ambiente Linux do Railway (ver seção acima)
- [ ] Configurar env vars obrigatórias na Vercel (build falha alto se faltar alguma — ver tabela)
- [ ] Deploy do `frontend/` na Vercel
- [ ] Validar fluxo completo com token real do Hub (não com bypass de dev)
- [ ] Rodar `poetry run pytest api/tests/` uma última vez antes do deploy
- [ ] Só depois disso, trocar `URL_DOCKSMITH_APP` no `subscription_access_api`
- [ ] Acompanhar os primeiros acessos reais antes de considerar definitivo

## Checklist de validação (plano de testes de produção)

| Teste | O que confirma | Automatizado? |
|---|---|---|
| Token ausente/inválido/válido | Autenticação correta | ✅ `test_auth.py` |
| Isolamento entre usuários | Sem vazamento de sessão | ✅ `test_sessions.py` |
| Recomendações de modelo batem com catálogo real | Sem capacidade inventada | ✅ `test_providers.py` |
| Erro de provedor não vaza chave | Segurança da chave do usuário | ✅ `test_providers.py` |
| Scrape/chat happy path + erros | Endpoints principais | ✅ `test_endpoints.py` |
| Abertura do frontend sem token | "Faça login pelo Hub" | Manual |
| Frontend → API (CORS) | Sem erro de CORS no console | Manual |
| Scraping real, indexação, chat/RAG reais | Fim a fim com provedor real | Manual |
| Resposta em Markdown + conclusão destacada | Renderização correta | Manual |
| Evidências (accordion) | Trechos batem com a fonte | Manual |
| Página "Como funciona" | Screenshots corretos, zig-zag | Manual |
| Mobile (dark/light) | Sem overflow, menu funciona | Manual |
| Erros de API (ex.: chave inválida) | Mensagem clara, UI não trava | Manual |

## Estratégia de rollback

Idêntica à documentada em [09-deploy.md](./09-deploy.md): reverter `URL_DOCKSMITH_APP` de volta pra URL do Streamlit Cloud. Rollback imediato, não depende de reverter nenhum deploy novo.

## Riscos identificados (resumo executivo)

1. Estado em memória impede escalonamento horizontal do `api/` — manter sempre 1 instância, em qualquer plataforma.
2. RAM medida em Windows local — remedir no Linux do Railway no primeiro deploy.
3. `test_connection` pode expor texto cru de erro de SDK (baixa severidade).
4. Bundle do frontend > 500KB — otimização futura, não bloqueante.
5. Sem teste automatizado de UI/E2E — validação de frontend continua manual (justificado: sem necessidade clara de suíte nova agora).

---

**Nada foi implantado.** Este documento é o entregável das duas auditorias — as próximas ações (criar conta na plataforma escolhida, configurar env vars reais, apontar domínio) dependem da sua autorização explícita.
