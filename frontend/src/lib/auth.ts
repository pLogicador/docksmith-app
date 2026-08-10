import { HUB_API_BASE_URL } from "./env"

const TOKEN_STORAGE_KEY = "docksmith:token"

export type HubUser = {
  id: string | number
  email: string
}

export function readTokenFromUrl(): string | null {
  const params = new URLSearchParams(window.location.search)
  const raw = params.get("token")
  if (!raw) return null
  const trimmed = raw.trim()
  return trimmed.toLowerCase().startsWith("bearer ") ? trimmed.slice(7).trim() : trimmed
}

export function stripTokenFromUrl(): void {
  const url = new URL(window.location.href)
  if (!url.searchParams.has("token")) return
  url.searchParams.delete("token")
  window.history.replaceState({}, "", url.toString())
}

export function getStoredToken(): string | null {
  return sessionStorage.getItem(TOKEN_STORAGE_KEY)
}

export function storeToken(token: string): void {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, token)
}

export function clearToken(): void {
  sessionStorage.removeItem(TOKEN_STORAGE_KEY)
}

/**
 * Valida o token direto contra o subscription_access_api — a mesma fonte
 * da verdade que o Hub já usa. Não reimplementa nenhuma regra de acesso.
 */
export async function validateToken(token: string): Promise<HubUser | null> {
  try {
    const resp = await fetch(`${HUB_API_BASE_URL}/validate-agendador-token`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    })
    if (!resp.ok) return null
    const data = await resp.json()
    return data?.user ?? null
  } catch {
    return null
  }
}
