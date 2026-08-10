// Variáveis obrigatórias em produção (build com `vite build`, `import.meta.env.PROD`
// true) falham alto e explícito em vez de cair silenciosamente num fallback de
// localhost — evita o app tentar falar com `localhost` em produção sem avisar.
// Em dev (`vite dev`), o default local é usado normalmente.
// Remove barra(s) finais — todo consumidor concatena `${BASE_URL}${path}` com
// `path` já começando em "/", então uma barra final sobrando produz
// "...com//models" (barra dupla), que o FastAPI/Railway trata como rota
// diferente de "/models" e devolve 404 — foi exatamente essa a causa real de
// "não encontrado" ao raspar/listar modelos em produção (VITE_API_BASE_URL
// configurada na Vercel com barra final).
function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "")
}

function requiredEnv(name: string, value: string | undefined, devDefault: string): string {
  if (value) return stripTrailingSlash(value)
  if (import.meta.env.PROD) {
    throw new Error(
      `Variável de ambiente obrigatória ausente: ${name}. Configure isso nas variáveis de ambiente da Vercel antes do deploy.`,
    )
  }
  return stripTrailingSlash(devDefault)
}

// Base da nova API fina do Docksmith (api/ — FastAPI). Obrigatória em
// produção: sem ela, scrape/chat/models não têm pra onde ir.
export const API_BASE_URL = requiredEnv(
  "VITE_API_BASE_URL",
  import.meta.env.VITE_API_BASE_URL,
  "http://localhost:8787",
)

// Base do subscription_access_api — mesma fonte da verdade que o Hub usa
// para emitir/validar o token de sessão (?token=... na URL). Obrigatória em
// produção: sem ela, nenhuma autenticação funciona.
export const HUB_API_BASE_URL = requiredEnv(
  "VITE_HUB_API_BASE_URL",
  import.meta.env.VITE_HUB_API_BASE_URL,
  "http://localhost:8000",
)

// URL do Hub (Syncron) — para onde mandamos o usuário quando não há sessão
// válida ("Ir para o Hub"). O default já é a URL real de produção (não um
// placeholder de dev), então não precisa ser obrigatória.
export const HUB_URL = import.meta.env.VITE_HUB_URL ?? "https://www.syncron.pro"
