# Desenvolvimento seguro

Regras que existem para proteger a produção atual (Streamlit em produção, Hub, `subscription_access_api`) enquanto o Docksmith evolui.

## Não criar banco de dados

Nenhuma das três partes usa banco de dados. Estado de sessão (coleções, chat, configuração de modelo) vive em memória — no processo da API (`api/sessions.py`) ou no React (`lib/store.tsx`) — e é descartado quando a sessão expira (TTL) ou a página/processo reinicia. Se uma necessidade futura parecer exigir persistência, isso é uma decisão de produto a ser discutida antes de implementar, não algo a assumir.

## Não persistir chaves de API

Chaves de provedores de IA informadas pelo usuário (`api_key` em `/chat` e `/models/test-connection`) nunca são salvas em disco, banco, log ou variável de ambiente do servidor — vivem só na memória da requisição (backend) e do processo do React (frontend, perdidas ao fechar a aba). Groq é o único provedor com chave própria do Docksmith (`GROQ_API_KEY` do servidor), usada como fallback quando o usuário não informa a sua.

## Não alterar produção diretamente

- `docksmith/` continua sendo a produção real (Streamlit Cloud) durante toda a migração — mudanças nele exigem cuidado extra e devem manter compatibilidade total com o que já está publicado.
- Nenhuma alteração foi feita em `hub/` ou `subscription_access_api/` para viabilizar a API/frontend novos — a integração usa mecanismos que já existiam (token de sessão, `URL_DOCKSMITH_APP`, CORS construído a partir dela).
- Variáveis de ambiente de produção (Streamlit Cloud, e futuramente Vercel/Railway) só devem ser alteradas com confirmação explícita — nunca como efeito colateral de uma mudança de código.

## Testar antes de substituir componentes

O princípio geral do projeto: não trocar uma implementação funcional por outra sem antes ter a nova validada. Foi assim que a API e o frontend novos foram construídos — testados localmente (scraping real, chat real, autenticação real contra o `subscription_access_api`) antes de qualquer conversa sobre deploy.

## Manter o Streamlit como fallback

Enquanto o cutover no Hub não acontece, `URL_DOCKSMITH_APP` continua apontando para o Streamlit Cloud. Isso é intencional: dá a opção de reverter instantaneamente (só trocando a variável de volta) se o frontend novo apresentar problemas depois de publicado.

## Preservar compatibilidade com o Hub

O mecanismo de token (`?token=` na URL, validado contra `POST /validate-agendador-token`) é genérico e já funciona sem modificação para o frontend novo — qualquer mudança nesse fluxo de autenticação, dos dois lados, precisa continuar compatível com o que o Hub já envia.

## `URL_DOCKSMITH_APP` só no momento do cutover

Essa variável de ambiente (lida pelo `subscription_access_api`, fora deste repositório) é o único ponto de corte entre "usuários acessam o Streamlit" e "usuários acessam o frontend novo". Não deve ser alterada em produção antes do frontend novo estar publicado, validado e com a API funcionando de ponta a ponta — ver [Deploy](./09-deploy.md) para a ordem recomendada.

## Bypasses de desenvolvimento

`DOCKSMITH_API_DEV_BYPASS_AUTH` (API) e `VITE_DEV_BYPASS_AUTH` (frontend) existem só para testar a interface localmente sem depender de um token real do Hub. Ambos:

- Tem default `false` no código — precisam ser explicitamente ativados.
- Não são lidos por nenhum ambiente de deploy documentado neste projeto.
- Devem ser conferidos como `false` antes de considerar qualquer ambiente "pronto para produção".
