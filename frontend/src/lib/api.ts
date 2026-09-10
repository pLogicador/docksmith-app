import { API_BASE_URL } from "./env"
import { getStoredToken } from "./auth"
import type { ChatResponse, ModelRecommendation, ProviderInfo, ScrapeResponse, SplitUploadResponse } from "./types"

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

// Upload de PDF/DOCX (2026-09-02, prompt-mestre "Docksmith" §6/§57):
// multipart, não JSON -- `request()` acima sempre força
// `Content-Type: application/json`, então este não reaproveita aquele
// helper. Omitir `Content-Type` de propósito: o browser define
// `multipart/form-data; boundary=...` sozinho a partir do `FormData`,
// e sobrescrever isso manualmente quebraria o boundary.
export async function uploadDocument(payload: {
  file: File
  collection_name: string
  session_id?: string | null
  // 2026-09-10: quando um upload anterior foi recusado por exceder
  // DOCSMITH_MAX_PAGES (ver PageLimitExceededDetail), o chamador pode
  // pedir pra refazer o MESMO upload processando só as primeiras N
  // páginas em vez do documento inteiro.
  truncate?: boolean
}): Promise<ScrapeResponse> {
  const token = getStoredToken()
  const form = new FormData()
  form.append("file", payload.file)
  form.append("collection_name", payload.collection_name)
  if (payload.session_id) form.append("session_id", payload.session_id)
  if (payload.truncate) form.append("truncate", "true")

  const resp = await fetch(`${API_BASE_URL}/documents/upload`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  })

  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    const detail = body?.detail
    const message = typeof detail === "string" ? detail : (detail?.message ?? `Erro ${resp.status}`)
    throw new ApiError(resp.status, message, detail)
  }

  return resp.json() as Promise<ScrapeResponse>
}

// Divisão inteligente em partes (Fase A, 2026-09-10): alternativa a
// `uploadDocument({ truncate: true })` pra um documento que excedeu
// DOCSMITH_MAX_PAGES -- em vez de descartar o que passa do limite, divide
// o documento inteiro em N coleções consultáveis (uma por parte),
// fechando cada parte ao final de um capítulo sempre que possível. Mesmo
// motivo de não reaproveitar `request()` que `uploadDocument` já tem:
// multipart, não JSON.
export async function splitUploadDocument(payload: {
  file: File
  collection_name: string
  session_id?: string | null
}): Promise<SplitUploadResponse> {
  const token = getStoredToken()
  const form = new FormData()
  form.append("file", payload.file)
  form.append("collection_name", payload.collection_name)
  if (payload.session_id) form.append("session_id", payload.session_id)

  const resp = await fetch(`${API_BASE_URL}/documents/upload/split`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  })

  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    const detail = body?.detail
    const message = typeof detail === "string" ? detail : (detail?.message ?? `Erro ${resp.status}`)
    throw new ApiError(resp.status, message, detail)
  }

  return resp.json() as Promise<SplitUploadResponse>
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
  // Multicontexto (Fase H, 2026-09-10): 1-3 nomes de coleção pra combinar
  // numa pergunta só -- ausente/vazio preserva 100% o modo de sempre (só
  // `collection_name`). Ver api/schemas.py::ChatRequest.collection_names.
  collection_names?: string[]
}): Promise<ChatResponse> {
  return request("/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}
