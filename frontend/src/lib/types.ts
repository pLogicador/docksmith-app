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
}

export type ChatBlockedDetail = {
  message: string
  resource_estimate: ResourceEstimate
  requires_confirmation: true
}

export type ChatResponse = {
  answer: string
  sources: SourceExcerpt[]
  collection_name: string
  provider: string
  model: string
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
