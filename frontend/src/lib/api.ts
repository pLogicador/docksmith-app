import { API_BASE_URL } from "./env"
import { getStoredToken } from "./auth"
import type { ChatResponse, ModelRecommendation, ProviderInfo, ScrapeResponse } from "./types"

export class ApiError extends Error {
  status: number
  // Corpo bruto de `detail`: string na maioria dos erros, ou um objeto
  // estruturado (ver ChatBlockedDetail) no bloqueio 413 de coleção grande.
  detail: unknown
  constructor(status: number, message: string, detail?: unknown) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getStoredToken()
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })

  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    const detail = body?.detail
    const message = typeof detail === "string" ? detail : (detail?.message ?? `Erro ${resp.status}`)
    throw new ApiError(resp.status, message, detail)
  }

  return resp.json() as Promise<T>
}

export function fetchProviders(): Promise<{ providers: ProviderInfo[]; recommendations: ModelRecommendation[] }> {
  return request("/models")
}

export function testConnection(payload: { provider: string; model?: string | null; api_key?: string | null }) {
  return request<{ ok: boolean; error: string | null }>("/models/test-connection", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function scrapeUrl(payload: {
  url: string
  collection_name: string
  session_id?: string | null
  max_depth?: number
  concurrency?: number
}): Promise<ScrapeResponse> {
  return request("/scrape", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function askQuestion(payload: {
  session_id: string
  collection_name: string
  question: string
  provider?: string
  model?: string | null
  api_key?: string | null
  depth?: string
  confirm_large_collection?: boolean
}): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
