import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// Variáveis sem as quais o app não tem como funcionar em produção (ver
// frontend/src/lib/env.ts) — checadas aqui de novo pra falhar o `vite build`
// em si (ex.: no deploy da Vercel) em vez de só falhar depois, quando
// alguém abrir o app publicado e o erro estourar no navegador.
const REQUIRED_IN_PRODUCTION = ['VITE_API_BASE_URL', 'VITE_HUB_API_BASE_URL']

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  if (mode === 'production') {
    const missing = REQUIRED_IN_PRODUCTION.filter((key) => !env[key])
    if (missing.length > 0) {
      throw new Error(
        `Build de produção abortado: variáveis de ambiente obrigatórias ausentes: ${missing.join(', ')}. ` +
          'Configure-as no projeto da Vercel antes do deploy.',
      )
    }
  }

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@': path.resolve(import.meta.dirname, './src'),
      },
    },
    server: {
      // Porta fixa para não colidir com outros frontends do monorepo w-production
      // que também usam o default do Vite (5173) — ex.: agenteos/frontend.
      // O Hub abre o Docksmith via URL_DOCKSMITH_APP (subscription_access_api),
      // que precisa apontar sempre para a mesma porta.
      port: 5174,
      strictPort: true,
    },
  }
})
