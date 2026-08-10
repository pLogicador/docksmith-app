# Troubleshooting

Problemas reais encontrados durante o desenvolvimento (não hipotéticos) e outros esperados pela natureza do projeto.

## API não inicia / não responde

- **Porta em uso**: `uvicorn api.main:app --reload` sem `--port` sobe na porta `8000` por padrão — a mesma que o `subscription_access_api` costuma usar localmente. Sempre rode com `--port 8787` (ou outra porta livre) explicitamente.
- **Windows: porta "presa" mesmo depois de matar o processo.** Em desenvolvimento neste ambiente, `taskkill /F` em um processo `uvicorn --reload` às vezes deixa o socket "fantasma" ainda aparecendo como `LISTENING` em `netstat` para aquela porta, mesmo com o processo já encerrado (confirmável com `Get-Process -Id <pid>` retornando vazio, ou `Get-NetTCPConnection -LocalPort <porta>` no PowerShell mostrando um `OwningProcess` que não existe mais). Sintoma: a API parece subir sem erro, mas todo request se comporta como se estivesse rodando uma versão antiga do código (variáveis de ambiente antigas, CORS desatualizado). **Solução**: use outra porta (`--port 8788`, por exemplo) em vez de insistir na mesma; reiniciar a máquina limpa o estado se o problema persistir.
- **Import falhando**: se `api/bootstrap.py` não conseguir importar `service.scraping`/`service.rag`, confirme que está rodando a partir da raiz do repositório (`docksmith-app/`), não de dentro de `api/` ou `docksmith/`.

## Frontend não conecta com a API

- Confira `VITE_API_BASE_URL` em `frontend/.env` — precisa apontar para a porta real onde a API está rodando.
- Depois de editar `frontend/.env`, o Vite detecta a mudança e reinicia o servidor de dev automaticamente (`[vite] .env changed, restarting server...` no terminal) — mas isso só recarrega o **frontend**; se você mudou algo do lado da API, reinicie o `uvicorn` também.

## Erro de CORS ("Disallowed CORS origin" / preflight falhando)

A API só aceita requests de origens listadas em `DOCKSMITH_API_CORS_ORIGINS` (default cobre `5173`, `5174`, `5175`). Se o Vite subir numa porta fora dessa lista (ele pula para a próxima porta livre quando a padrão está ocupada), configure `DOCKSMITH_API_CORS_ORIGINS` no `.env` da raiz incluindo a porta real usada, e reinicie a API.

## Token inválido / "Faça login pelo Hub"

- Sem `?token=` na URL e sem um token válido salvo, essa tela é o comportamento esperado — o Docksmith não tem login próprio, só existe através do Hub.
- Para testar localmente sem passar pelo Hub de verdade: ative `DOCKSMITH_API_DEV_BYPASS_AUTH=true` (raiz `.env`) e `VITE_DEV_BYPASS_AUTH=true` (`frontend/.env`), reinicie os dois servidores. **Volte ambos para `false` depois** — é um bypass de autenticação, não deve ficar ligado.
- Se um token real do Hub está sendo rejeitado, confira se `API_BASE` (raiz) / `VITE_HUB_API_BASE_URL` (frontend) apontam para uma instância do `subscription_access_api` que realmente reconhece esse token (mesmo banco de usuários/tokens).

## Modelo de IA não responde / erro do provedor

- **Groq**: confirme `GROQ_API_KEY` no `.env` da raiz.
- **OpenAI / Anthropic / Google**: exigem a chave do próprio usuário (campo "Sua chave de API" no painel de Modelo de IA) — sem ela, a API responde `400` explicando que falta a chave.
- Use o botão "Testar conexão" antes de iniciar uma análise — ele chama `POST /models/test-connection`, que tenta um `invoke("ping")` real contra o provedor e mostra o erro exato retornado por ele (chave inválida, modelo inexistente, limite de uso, etc.).

## FAISS / embeddings lentos ou travando

- Na primeira execução, `sentence-transformers` baixa o modelo `all-MiniLM-L6-v2` — pode demorar alguns segundos a mais na primeira chamada de scraping/chat. Depois fica em cache local.
- Indexar uma coleção com várias páginas (`k` documentos) é síncrono e pode levar de 10 a 30 segundos dependendo do tamanho do conteúdo e da máquina — o frontend mostra "Pensando…" enquanto isso acontece; não é um travamento.
- Trocar de provedor/modelo/profundidade dentro do mesmo chat força reindexação completa da coleção (ver `loaded_signature` em [API / Backend](./04-api-backend.md)) — é esperado ser mais lento na primeira pergunta depois da troca.

## Dependências

- `poetry install` cobre `docksmith/` e `api/` juntos (um `pyproject.toml` só).
- `npm install` dentro de `frontend/` para o frontend.
- Se `poetry add` falhar de forma estranha em ambiente Windows/Git Bash com mensagens tipo "The system cannot find the file specified" ao usar restrições de versão com `<` (ex: `"pacote>=1,<2"`), é um problema de parsing do shell com o caractere `<` sendo interpretado como redirecionamento — use `pacote==1.2.3` (igualdade exata) para contornar.

## Portas ocupadas (resumo)

| Serviço | Porta padrão | Se estiver ocupada |
|---|---|---|
| Streamlit | `8501` | `streamlit run docksmith/app.py --server.port 8502` |
| API | `8787` | `uvicorn api.main:app --reload --port 8788` (lembre de atualizar `VITE_API_BASE_URL` e `DOCKSMITH_API_CORS_ORIGINS`) |
| Frontend | `5173` | O Vite pula sozinho para a próxima porta livre |

## Variáveis de ambiente

Se algo "simplesmente não funciona" sem erro claro, o primeiro passo é conferir se o `.env` certo existe no lugar certo — são **dois arquivos `.env` separados**: um na raiz (Streamlit + API) e um em `frontend/` (frontend). Ver [Executar localmente](./02-executar-localmente.md) para o conteúdo esperado de cada um.

## Problemas de build (frontend)

- `npm run build` roda `tsc -b && vite build` — um erro de tipo TypeScript quebra o build mesmo que o `npm run dev` pareça funcionar (o dev server não bloqueia em erros de tipo). Rode `npx tsc -b --noEmit` para checar tipos isoladamente.
