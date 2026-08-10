import { useMemo, useState } from "react"
import { useQuery, useMutation } from "@tanstack/react-query"
import { CheckCircle2, XCircle, DollarSign, Zap, Target, Microscope, HelpCircle, Info } from "lucide-react"
import { fetchProviders, testConnection } from "@/lib/api"
import { useStore, type Depth } from "@/lib/store"
import type { ModelRecommendation } from "@/lib/types"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select"
import { Input } from "@/components/ui/Input"
import { Button } from "@/components/ui/Button"
import { Badge } from "@/components/ui/Badge"
import { Spinner } from "@/components/ui/Spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip"

const DEPTH_OPTIONS: { value: Depth; label: string; hint: string }[] = [
  { value: "rapida", label: "Rápida", hint: "Respostas diretas, menos trechos de contexto" },
  { value: "equilibrada", label: "Equilibrada", hint: "Bom equilíbrio entre profundidade e velocidade" },
  { value: "profunda", label: "Profunda", hint: "Mais contexto e detalhamento técnico" },
]

const RECOMMENDATION_ICON: Record<string, typeof DollarSign> = {
  "custo-beneficio": DollarSign,
  rapida: Zap,
  precisa: Target,
  profunda: Microscope,
}

export function SettingsPanel() {
  const { state, dispatch } = useStore()
  const [apiKeyInput, setApiKeyInput] = useState(state.modelConfig.apiKey ?? "")
  const [testResult, setTestResult] = useState<{ ok: boolean; error: string | null } | null>(null)

  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: fetchProviders })
  const providers = providersQuery.data?.providers ?? []
  const recommendations = providersQuery.data?.recommendations ?? []
  const activeProvider = useMemo(
    () => providers.find((p) => p.id === state.modelConfig.provider),
    [providers, state.modelConfig.provider],
  )

  const testMutation = useMutation({
    mutationFn: () =>
      testConnection({
        provider: state.modelConfig.provider,
        model: state.modelConfig.model,
        api_key: apiKeyInput || null,
      }),
    onSuccess: (data) => setTestResult(data),
  })

  function handleProviderChange(providerId: string) {
    const provider = providers.find((p) => p.id === providerId)
    dispatch({
      type: "SET_MODEL_CONFIG",
      config: { provider: providerId, model: provider?.defaultModel ?? null, apiKey: null },
    })
    setApiKeyInput("")
    setTestResult(null)
  }

  function handleModelChange(model: string) {
    dispatch({ type: "SET_MODEL_CONFIG", config: { model } })
    setTestResult(null)
  }

  function handleApiKeyBlur() {
    dispatch({ type: "SET_MODEL_CONFIG", config: { apiKey: apiKeyInput || null } })
    setTestResult(null)
  }

  function handleRecommendationSelect(rec: ModelRecommendation) {
    dispatch({
      type: "SET_MODEL_CONFIG",
      config: { provider: rec.provider, model: rec.model, apiKey: null },
    })
    dispatch({ type: "SET_DEPTH", depth: rec.recommendedDepth as Depth })
    setApiKeyInput("")
    setTestResult(null)
  }

  return (
    <div className="flex flex-col gap-6 p-4 sm:p-5">
      <section className="space-y-2.5">
        <label className="text-xs font-medium text-text-secondary">Recomendados</label>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {recommendations.map((rec) => {
            const Icon = RECOMMENDATION_ICON[rec.id] ?? Zap
            const isActive =
              state.modelConfig.provider === rec.provider && (state.modelConfig.model ?? "") === rec.model
            return (
              <div
                key={rec.id}
                className={`flex flex-col gap-1.5 rounded-lg border px-3 py-2.5 text-left transition ${
                  isActive
                    ? "border-temper bg-temper/10"
                    : "border-border hover:bg-surface-2"
                }`}
              >
                <button
                  type="button"
                  onClick={() => handleRecommendationSelect(rec)}
                  className="flex w-full items-center gap-2 text-left"
                >
                  <Icon size={15} className={isActive ? "text-temper-strong" : "text-text-tertiary"} />
                  <span className={`text-xs font-semibold ${isActive ? "text-temper-strong" : "text-text-primary"}`}>
                    {rec.label}
                  </span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span
                        className="ml-auto shrink-0 text-text-tertiary hover:text-text-secondary"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <Info size={13} />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="mb-1.5 font-medium text-text-primary">{rec.bestFor}</p>
                      <p>
                        <span className="font-medium text-text-primary">Quando usar: </span>
                        {rec.whenToUse}
                      </p>
                      <p className="mt-1.5">
                        <span className="font-medium text-text-primary">Limitações: </span>
                        {rec.limitations}
                      </p>
                      <p className="mt-1.5">
                        <span className="font-medium text-text-primary">Dica: </span>
                        {rec.tips}
                      </p>
                    </TooltipContent>
                  </Tooltip>
                </button>
                <Badge variant={rec.requiresApiKey ? "warning" : "success"} className="w-fit">
                  {rec.requiresApiKey ? "Requer chave" : "Sem chave"}
                </Badge>
              </div>
            )
          })}
        </div>
      </section>

      <div className="border-t border-border pt-4">
        <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">
          Configuração avançada
        </p>

        <div className="flex flex-col gap-4">
          <section className="space-y-2">
            <label className="text-xs font-medium text-text-secondary">Provedor</label>
            <Select value={state.modelConfig.provider} onValueChange={handleProviderChange}>
              <SelectTrigger>
                <SelectValue placeholder="Selecione um provedor" />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {activeProvider && <p className="text-xs text-text-tertiary">{activeProvider.description}</p>}
          </section>

          {activeProvider && (
            <section className="space-y-2">
              <label className="text-xs font-medium text-text-secondary">Modelo</label>
              <Select value={state.modelConfig.model ?? activeProvider.defaultModel} onValueChange={handleModelChange}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {activeProvider.models.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </section>
          )}

          {activeProvider?.requiresApiKey && (
            <section className="space-y-2">
              <div className="flex items-center gap-1.5">
                <label className="text-xs font-medium text-text-secondary">Sua chave de API</label>
                {activeProvider.apiKeyHelp && (
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-text-tertiary hover:text-text-secondary">
                        <HelpCircle size={13} />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent>
                      <p className="mb-1.5 font-medium text-text-primary">Como obter sua chave</p>
                      <ol className="list-decimal space-y-1 pl-3.5">
                        {activeProvider.apiKeyHelp.steps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                      <a
                        href={activeProvider.apiKeyHelp.url}
                        target="_blank"
                        rel="noreferrer"
                        className="mt-1.5 inline-block text-temper-strong underline underline-offset-2"
                      >
                        Abrir página da chave ↗
                      </a>
                    </TooltipContent>
                  </Tooltip>
                )}
              </div>
              <Input
                type="password"
                placeholder="sk-..."
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
                onBlur={handleApiKeyBlur}
              />
              <p className="text-[11px] text-text-tertiary">
                Usada somente durante esta sessão, nunca é salva permanentemente.
              </p>
            </section>
          )}

          <section className="space-y-2">
            <Button
              variant="secondary"
              size="sm"
              className="w-full"
              disabled={testMutation.isPending}
              onClick={() => testMutation.mutate()}
            >
              {testMutation.isPending ? <Spinner size={14} /> : null}
              Testar conexão
            </Button>
            {testResult && (
              <Badge variant={testResult.ok ? "success" : "danger"} className="w-full justify-center py-1.5">
                {testResult.ok ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                {testResult.ok ? "Conexão validada" : testResult.error ?? "Falha na conexão"}
              </Badge>
            )}
          </section>

          <section className="space-y-2">
            <label className="text-xs font-medium text-text-secondary">Profundidade da análise</label>
            <div className="grid grid-cols-3 gap-2">
              {DEPTH_OPTIONS.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => dispatch({ type: "SET_DEPTH", depth: opt.value })}
                  className={`rounded-lg border px-2 py-2 text-xs font-medium transition ${
                    state.depth === opt.value
                      ? "border-temper bg-temper/10 text-temper-strong"
                      : "border-border text-text-secondary hover:bg-surface-2"
                  }`}
                >
                  {opt.label}
                </button>
              ))}
            </div>
            <p className="text-[11px] text-text-tertiary">
              {DEPTH_OPTIONS.find((o) => o.value === state.depth)?.hint}
            </p>
          </section>
        </div>
      </div>
    </div>
  )
}
