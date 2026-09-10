# Frontend

Vite + React 19 + TypeScript + Tailwind CSS v4. Vive em `frontend/`, é um projeto independente (seu próprio `package.json`, `node_modules`, build).

## Instalação e execução

```bash
cd frontend
npm install
npm run dev      # servidor de desenvolvimento (Vite)
npm run build    # tsc -b && vite build → gera frontend/dist
npm run preview  # serve o build de produção localmente
npm run lint      # oxlint
```

## Variáveis de ambiente

Definidas em `frontend/.env` (veja `frontend/.env.example`):

| Variável | Uso | Default no código |
|---|---|---|
| `VITE_API_BASE_URL` | Base da API nova (`api/`) | `http://localhost:8787` |
| `VITE_HUB_API_BASE_URL` | Base do `subscription_access_api`, para validar o token do Hub | `http://localhost:8000` |
| `VITE_HUB_URL` | URL do Hub (Syncron) — para onde o botão "Ir para o Hub" leva quando não há sessão válida | `https://www.syncron.pro` (URL de produção — em dev local aponte para o Hub local, ex.: `http://localhost:5100`) |
| `VITE_DEV_BYPASS_AUTH` | `true` pula a validação real do token (só para dev local, nunca em produção) | `false` |

## Estrutura de pastas

```
frontend/src/
├── brand/            # Symbol.tsx — o símbolo/logo do Docksmith (SVG)
├── components/
│   ├── ui/           # Primitivos: Button, Card, Input, Tabs, Accordion, Select, Drawer, Badge, Spinner
│   └── layout/        # AppShell (shell responsivo) e Sidebar
├── features/
│   ├── auth/          # AuthGate — fluxo de token/login
│   ├── workspace/     # WorkspacePage — formulário de extração + lista de coleções
│   ├── chat/           # ChatPage, ChatMessageBubble, ResultPanel (análise em 5 níveis)
│   └── settings/       # SettingsPanel — provedor/modelo de IA, chave, profundidade
├── lib/
│   ├── api.ts          # Cliente HTTP para a API nova (anexa o token, trata erros)
│   ├── auth.ts         # Leitura do token na URL, validação contra o subscription_access_api
│   ├── store.tsx       # Estado global (sessão, coleções, mensagens, config de modelo) via Context + useReducer
│   ├── resultAnalysis.ts # Extração de "resumo" e "insights" a partir do texto da resposta (client-side, sem chamada extra ao LLM)
│   ├── types.ts        # Tipos compartilhados (espelham os schemas Pydantic da API)
│   └── env.ts / cn.ts  # Helpers
├── App.tsx             # Rotas (react-router-dom)
└── main.tsx             # Bootstrap (QueryClientProvider, BrowserRouter)
```

## Comunicação com a API

- Todo request usa `lib/api.ts` (`request<T>`), que injeta `Authorization: Bearer <token>` a partir do `sessionStorage` (chave `docksmith:token`, gerenciada por `lib/auth.ts`) e lança `ApiError` em respostas não-OK.
- `session_id` é obtido do backend na primeira chamada a `/scrape` e guardado no estado em memória (`lib/store.tsx`) — perdido ao recarregar a página, por design (sem persistência).
- TanStack Query (`@tanstack/react-query`) gerencia as chamadas assíncronas (`useMutation` para scrape/chat/test-connection, `useQuery` para `/models`).

## Identidade visual

- Símbolo: `src/brand/Symbol.tsx` — um hexágono "lapidado" (conceito: conteúdo bruto extraído sendo transformado em conhecimento preciso), com uma faceta em destaque na cor de marca. Variantes `color` (usa `--temper`) e `mono` (`currentColor`).
- Paleta: definida em `src/index.css` como variáveis CSS (`--bg`, `--surface`, `--temper`, etc.), com suporte a tema claro/escuro via `prefers-color-scheme` e `[data-theme]`. Paleta fria (azul-aço/teal), deliberadamente distinta de outros produtos da casa que usam tons quentes.
- **Tipografia (2026-09-01)**: `--font-sans`/`--font-mono` citavam "Inter"/"JetBrains Mono" desde sempre no `@theme` de `index.css`, mas `index.html` nunca tinha o `<link>` correspondente — o app inteiro caía silenciosamente em `ui-sans-serif`/`system-ui` (mesmo bug já achado e corrigido em 2 produtos-irmãos do ecossistema Syncron na mesma sessão). Corrigido junto com a adição de um terceiro token, `--font-display: "IBM Plex Sans", var(--font-sans)` — face de destaque pra headings e números-chave, distinta de Inter (corpo/UI aqui) e das faces de destaque já usadas por outros produtos (Space Grotesk no Hub, Sora no ANZ Finance, Unbounded no Live Scheduler). Aplicada via a classe utilitária `font-display` (gerada automaticamente pelo Tailwind v4 a partir do nome do token) só em papéis de título/número-chave — os `<h1>` de `AuthGate`/`WorkspacePage`/`HowItWorksPage`, o `<h2>` de passo do "Como funciona", o wordmark "Docksmith" ao lado do `Symbol` (`Sidebar.tsx`/`AppShell.tsx`), e os 4 números de `ResultPanel.tsx`'s aba "Dados" (também ganharam `tabular-nums`) — nunca em rótulos pequenos/texto de corpo, que continuam em Inter.

## Estado sem persistência

Por design, não há `localStorage` para dados de sessão nem banco de dados no cliente. `sessionStorage` guarda **apenas o token** (para sobreviver a um refresh dentro da mesma aba); coleções, mensagens e configuração de modelo vivem em memória do React (`StoreProvider`) e são perdidas ao recarregar a página — mesmo comportamento de "tudo na memória da sessão" que o Streamlit sempre teve.
