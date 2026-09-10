# Armazenamento durável sem cartão de crédito (Backblaze B2) — e o que falta configurar

**Resolve a mesma coisa que [`CONFIGURAR_R2.md`](./CONFIGURAR_R2.md) já resolvia** ("documentos ainda somem a cada reinício do servidor"), mas por um caminho que **não exige cadastrar cartão de crédito** — pedido explícito do usuário (2026-09-03), depois de `CONFIGURAR_R2.md` ter deixado claro que a Cloudflare pede cartão pra ativar o R2, mesmo no nível gratuito.

Este documento cobre 4 coisas, na ordem pedida:
1. A pesquisa (R2 exige cartão mesmo? existe alternativa gratuita sem cartão?).
2. O que falta configurar no **Docksmith** (a única das 3 partes do ecossistema — Docksmith, Maestro, frontend — que de fato lida com arquivos).
3. Por que o **Maestro** (Syncron Core) não precisa de nada disso.
4. O que testar pelo **frontend**, e como cada peça funciona por baixo dos panos.

---

## 1. A pesquisa

**Cloudflare R2 continua exigindo cartão de crédito para ativar, mesmo no nível gratuito.** Confirmado agora (2026-09-03), não só presumido a partir da rodada anterior — a própria Cloudflare anuncia "no credit card required" na página de marketing, mas o passo real de ativação do produto R2 pede o cartão mesmo assim (é uma exigência conhecida, discutida na própria comunidade oficial da Cloudflare). Ninguém é cobrado ficando dentro do nível gratuito — mas o cartão precisa estar cadastrado.

**Backblaze B2 é uma alternativa real, não um substituto inferior**, pesquisada e comparada ponto a ponto:

| | Cloudflare R2 | Backblaze B2 |
|---|---|---|
| Armazenamento grátis | 10GB/mês, permanente | 10GB, permanente |
| Egress (download) grátis | Ilimitado, sempre | Até 3x a média mensal armazenada — folgado o bastante pro uso deste projeto (ver seção 4) |
| Operações de escrita/leitura grátis | 1M escrita / 10M leitura por mês | Upload, listagem e leitura grátis para contas pay-as-you-go |
| **Cartão de crédito no cadastro** | **Sim, obrigatório** | **Não** — a própria página de cadastro do Backblaze diz "no credit card required" |
| API | S3-compatível | S3-compatível (mesma biblioteca `boto3` já usada no código) |

**Conclusão: Backblaze B2 é o caminho recomendado** — mesmo nível gratuito generoso e permanente, sem exigir cartão, e o código do Docksmith já fala a API S3-compatível que os dois provedores expõem, então **não foi preciso reescrever a lógica de armazenamento** — só ensinar o código a apontar pra um endpoint diferente (ver seção 2).

`CONFIGURAR_R2.md` continua válido e documentado à parte, sem nenhuma mudança — para quem já tem cartão cadastrado ou prefere ficar 100% dentro do ecossistema Cloudflare, R2 continua funcionando exatamente como antes.

Fontes consultadas nesta pesquisa: [documentação oficial de preços do Cloudflare R2](https://developers.cloudflare.com/r2/pricing/), [discussão da comunidade Cloudflare sobre a exigência de cartão](https://community.cloudflare.com/t/why-using-r2-free-tier-involves-giving-card-info/945179), [página de cadastro do Backblaze B2](https://www.backblaze.com/cloud-storage), [página de preços do Backblaze B2](https://www.backblaze.com/b2/cloud-storage-pricing.html), [documentação da API S3-compatível do Backblaze](https://www.backblaze.com/docs/cloud-storage-s3-compatible-api).

---

## 2. O que já existe no código, e o que falta configurar (Docksmith)

**O código já está pronto — 100% implementado e testado (`api/r2_storage.py`, 29 testes automatizados, `api/tests/test_r2_storage.py`).** O que faltava era só a parte que exigia cartão. Nesta rodada, o código ganhou a capacidade de apontar para qualquer provedor S3-compatível (não só Cloudflare R2) via 2 variáveis novas, opcionais: `R2_ENDPOINT_URL` e `R2_REGION`. Sem elas, nada muda — o código continua funcionando com Cloudflare R2 exatamente como `CONFIGURAR_R2.md` descreve. Com elas, aponta para Backblaze B2 (ou qualquer outro provedor S3-compatível) sem nenhuma mudança de lógica.

**Hoje, nenhuma das variáveis de nenhum dos 2 caminhos está configurada em lugar nenhum** — nem no `.env` local, nem (até onde este código consegue ver) no ambiente de produção do Railway. `is_configured()` retorna `False`, e o Docksmith continua funcionando exatamente como já funcionava: sem nenhuma cópia de segurança durável, documentos somem se o servidor reiniciar no meio de uma sessão. **Isso não quebra nada** — é o comportamento seguro por padrão, sempre foi.

### Passo a passo — Backblaze B2 (recomendado, sem cartão)

1. **Criar a conta.** Acesse [backblaze.com/cloud-storage](https://www.backblaze.com/cloud-storage) → "Get started for free" → informe e-mail e senha → confirme pelo e-mail de verificação (mesmo navegador usado no cadastro). Nenhum cartão é pedido em nenhuma etapa.
2. **Criar um bucket.** No painel, vá em "Buckets" → "Create a Bucket". Dê um nome único (ex.: `docksmith-documentos-<algo único>` — nomes de bucket no B2 são globais, como no S3). Deixe "Private" (não precisa ser público). Depois de criado, o painel mostra o **Endpoint** do bucket, algo como `s3.us-west-004.backblazeb2.com` — guarde essa informação, ela vira as variáveis `R2_ENDPOINT_URL`/`R2_REGION` abaixo.
3. **Criar uma Application Key (não a Master Key).** Vá em "App Keys" → "Add a New Application Key". Dê um nome (ex.: `docksmith-prod`), restrinja ao bucket criado no passo 2 (mais seguro que uma chave com acesso a todos os buckets), e marque permissão de leitura+escrita. **Importante**: a *Master Application Key* da conta (mostrada por padrão na tela de "App Keys") não é compatível com a API S3 — precisa ser uma chave criada especificamente aqui. Depois de criada, o Backblaze mostra duas informações **uma única vez** — copie antes de sair da tela:
   - **keyID** (equivalente ao "Access Key ID" do R2)
   - **applicationKey** (equivalente ao "Secret Access Key" do R2)
4. **Configurar as 6 variáveis de ambiente** (no `.env` local para testar, e/ou nas variáveis de ambiente do serviço no Railway para produção):
   ```bash
   R2_ACCESS_KEY_ID=o-keyID-que-voce-copiou
   R2_SECRET_ACCESS_KEY=a-applicationKey-que-voce-copiou
   R2_BUCKET_NAME=docksmith-documentos-o-nome-que-voce-escolheu
   R2_ENDPOINT_URL=https://s3.us-west-004.backblazeb2.com
   R2_REGION=us-west-004
   ```
   (O nome das variáveis continua com o prefixo `R2_` por serem conceitos genéricos de credencial S3 — Key ID/Secret/Bucket funcionam do mesmo jeito em qualquer provedor S3-compatível; só o endpoint muda de fato entre Cloudflare R2 e Backblaze B2.) `R2_ACCOUNT_ID` (usada só pelo caminho Cloudflare R2) fica sem definir — não é necessária quando `R2_ENDPOINT_URL` está presente.
5. **Pronto.** Na próxima vez que o Docksmith iniciar, `r2_storage.is_configured()` passa a `True` automaticamente e toda cópia de segurança passa a ir para o Backblaze B2. Nenhuma outra configuração é necessária — as 2 cotas de segurança (`DOCSMITH_R2_MAX_MB_PER_USER`/`DOCSMITH_R2_MAX_MB_TOTAL_BUCKET`, já documentadas em `CONFIGURAR_R2.md`) continuam valendo do mesmo jeito, protegendo o uso independente de qual provedor está por trás.

**Onde configurar em produção**: o Docksmith roda no **Railway** (`https://web-production-27204.up.railway.app/`, confirmado em `api/README.md`) — as variáveis de ambiente ficam no painel do serviço lá (Railway → o projeto → o serviço → aba "Variables"), não neste repositório.

### O que ISSO ainda não resolve (herdado de `CONFIGURAR_R2.md`, vale para os dois provedores)

- Ainda não existe uma fila de processamento real — o upload é processado na hora, só a cópia de segurança é que acontece depois, sem atrasar a resposta.
- A validação de tipo de arquivo continua baseada na extensão do nome, não no conteúdo real.
- Não há métricas formais de uso (nem do armazenamento, nem do resto do Docksmith).

---

## 3. O Maestro (Syncron Core) não precisa de nada disso

Pesquisado antes de assumir qualquer coisa: `syncron_core` (o backend do Maestro) foi checado por completo em busca de qualquer referência a armazenamento de objetos, upload de arquivo, ou dependência de S3/R2/Backblaze — **nenhuma encontrada**. Confirmado lendo o próprio `README.md` do projeto: o Maestro é puramente um orquestrador — interpreta a intenção do usuário e repassa a chamada para o backend do produto certo (Docksmith, Agendador de Lives, etc.) via `ServiceAdapter`; ele nunca guarda arquivo nenhum, nunca reimplementa a lógica do produto que está orquestrando. Se um dia o Maestro precisar devolver um arquivo gerado por uma capability (por exemplo, um PDF do Docksmith), a fonte da verdade desse arquivo continua sendo o backend do produto (que já tem — ou, com este documento, já pode ter — seu próprio armazenamento); o Maestro só precisaria repassar uma URL/referência, não guardar uma cópia própria. Não há, hoje, nenhuma capability que faça isso — então não há nada a configurar no Maestro neste momento.

---

## 4. O que testar pelo frontend, e como cada peça funciona

**Pré-requisito**: as 5 variáveis da seção 2 configuradas (local ou produção) — sem elas, os passos abaixo continuam funcionando normalmente, só que sem a cópia de segurança (o objetivo do teste é justamente confirmar que ela existe).

### Teste 1 — upload normal continua funcionando (baseline, sem envolver o R2/B2 ainda)

1. Abra o Docksmith pelo Hub (login real) → aba "Enviar arquivo".
2. Envie um PDF ou DOCX pequeno.
3. Confirme que a coleção é indexada e que dá pra conversar normalmente com o conteúdo (uma pergunta cuja resposta está no arquivo).

**Como funciona por baixo**: o arquivo enviado nunca precisa do armazenamento durável pra esse teste passar — a extração de texto e a indexação (FAISS + BM25, ver `docksmith/service/rag.py`) acontecem inteiramente na memória do processo, na mesma requisição. A cópia de segurança pro Backblaze/R2 é um efeito colateral que acontece **depois**, sem atrasar essa resposta.

### Teste 2 — a cópia de segurança foi criada de verdade

1. Depois do Teste 1, abra o painel do Backblaze (ou Cloudflare) → o bucket configurado.
2. Deve aparecer um objeto novo lá dentro. O nome do objeto é um código opaco (não o nome do seu arquivo, não o seu e-mail) — isso é proposital, ver "Como isso funciona" em `CONFIGURAR_R2.md`, a mesma lógica de privacidade se aplica aqui.

**Como funciona por baixo**: `api/routers/documents.py` chama `r2_storage.upload_raw_bytes(...)` logo depois de processar o arquivo. A chave do objeto é `docksmith/{hash do seu usuário}/{id da sua sessão}/{código aleatório}` — nunca o seu identificador real, nunca o nome do arquivo (esses vão só como metadado do objeto, não no caminho).

### Teste 3 — o cenário real que tudo isso resolve: reinício do servidor no meio de uma sessão

Esse é o teste que só faz sentido em ambiente **local** (reiniciar o serviço de produção no Railway de propósito, só pra testar, não vale o risco/custo de disponibilidade):

1. Rode o Docksmith localmente (`docs/02-executar-localmente.md`), com as 5 variáveis da seção 2 configuradas no `.env`.
2. Envie um documento, confirme que a conversa funciona (Teste 1).
3. **Pare o processo da API (`Ctrl+C` no terminal onde o `uvicorn` está rodando) e inicie de novo**, sem fechar a aba do navegador nem limpar cookies/sessão.
4. Faça uma pergunta de novo, sobre o mesmo documento, na mesma sessão.

**O que deve acontecer**: a resposta continua funcionando normalmente, como se o servidor nunca tivesse reiniciado — mesmo a memória do processo (onde a sessão vivia) tendo sido apagada de verdade pelo restart. **Como funciona por baixo**: `api/sessions.py`, ao não encontrar a sessão na memória, detecta que existe uma cópia dela no armazenamento durável e chama `r2_storage.list_session_objects(...)` + `download_raw_bytes(...)` pra cada objeto encontrado, reconstruindo a sessão (reprocessando o texto original — a indexação em si não é guardada, só o arquivo bruto) antes de responder à pergunta. Isso é o achado real que motivou todo este trabalho ("documentos ainda somem a cada reinício do servidor") — sem as variáveis configuradas, este passo 4 falha (a sessão realmente sumiu) e é exatamente o comportamento que se espera **sem** o armazenamento durável configurado.

### Teste 4 (opcional, mais avançado) — isolamento entre usuários

Não é um teste de UI simples de reproduzir sozinho (exigiria 2 contas reais diferentes) — já coberto por teste automatizado real (`test_a_different_user_id_never_sees_another_users_session_objects`, `api/tests/test_r2_storage.py`), que confirma que reaproveitar o `session_id` de outra pessoa nunca dá acesso aos documentos dela, mesmo apontando pro mesmo bucket.

---

## Resumo — o que falta, em uma frase

**Só falta criar a conta no Backblaze B2 (sem cartão) e colar as 5 credenciais no `.env`/Railway** — todo o código, toda a lógica de segurança (cotas, isolamento entre usuários, restauração automática, tolerância a falha) já existe, já está testado (29 testes automatizados só pra esse módulo), e já funciona com qualquer um dos 2 provedores sem nenhuma mudança de código. O Maestro não precisa de nenhuma configuração equivalente hoje.
