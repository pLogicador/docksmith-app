export type ApiKeyHelp = {
  steps: string[]
  url: string
}

export type ProviderInfo = {
  id: string
  label: string
  requiresApiKey: boolean
  models: string[]
  defaultModel: string
  speedHint: string
  description: string
  apiKeyHelp: ApiKeyHelp | null
}

export type ModelRecommendation = {
  id: string
  label: string
  provider: string
  model: string
  recommendedDepth: string
  requiresApiKey: boolean
  bestFor: string
  whenToUse: string
  limitations: string
  tips: string
}

export type SourceExcerpt = {
  index: number
  excerpt: string
  // 2026-09-02: proveniência real por trecho (página de PDF, seção de
  // DOCX, ou rótulo genérico de documento raspado por URL) -- já calculada
  // pelo backend desde a 1ª rodada da Fase I, mas só passou a chegar até
  // aqui depois do schema da API (api/schemas.py) declarar os campos.
  document_index?: number | null
  chunk_index?: number | null
  source_label?: string | null
}

export type ResourceEstimateStatus = "ok" | "atencao" | "muito_grande" | "bloqueado"

export type ResourceEstimate = {
  document_count: number
  total_chars: number
  total_mb: number
  estimated_chunks: number
  estimated_indexing_mb: number
  current_process_mb: number
  available_memory_mb: number
  status: ResourceEstimateStatus
}

export type ScrapeResponse = {
  session_id: string
  collection_name: string
  document_count: number
  preview: string[]
  resource_estimate: ResourceEstimate
  // True só quando o upload foi aceito com truncamento (ver
  // PageLimitExceededDetail abaixo) -- 2026-09-10.
  truncated: boolean
}

export type ChatBlockedDetail = {
  message: string
  resource_estimate: ResourceEstimate
  requires_confirmation: true
}

// Detalhe estruturado do 422 "page_limit_exceeded" (2026-09-10, pedido
// explícito do usuário testando um livro real de 446 páginas pelo Hub) --
// mesmo padrão de ChatBlockedDetail acima: em vez de um erro sem saída, dá
// ao frontend os números reais pra oferecer "processar só as primeiras N
// páginas" em vez do documento inteiro ser recusado.
export type PageLimitExceededDetail = {
  error: "page_limit_exceeded"
  message: string
  actual_count: number
  max_pages: number
  unit: string
}

// Fase A (2026-09-10, "PROMPT DE EVOLUÇÃO"/"OBSERVAÇÕES FINAIS" -- divisão
// inteligente consciente de estrutura): metadado de UMA parte devolvida por
// POST /documents/upload/split -- ver api/schemas.py::DocumentPartInfo.
export type DocumentPartInfo = {
  collection_name: string
  part_number: number
  unit: "páginas" | "seções"
  position_start: number | null
  position_end: number | null
  chapters: string[]
  page_count: number
  document_count: number
  estimated_chunks: number
  estimated_size_mb: number
}

export type SplitUploadResponse = {
  session_id: string
  base_collection_name: string
  parts: DocumentPartInfo[]
}

export type ChatResponse = {
  answer: string
  sources: SourceExcerpt[]
  collection_name: string
  provider: string
  model: string
  // Fase E (2026-09-10): false quando esta pergunta precisou (re)indexar a
  // coleção agora, no cache LRU por sessão -- 1ª vez ou evictada por outra
  // coleção ter sido usada nesse meio tempo. Ver api/index_cache.py.
  was_cached?: boolean
}

export type Collection = {
  name: string
  documentCount: number
  preview: string[]
}

export type ModelConfig = {
  provider: string
  model: string | null
  apiKey: string | null
}

export type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  sources?: SourceExcerpt[]
  provider?: string
  model?: string
  timestamp: string
}
