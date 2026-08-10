import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { AlertTriangle, ArrowRight, Globe, MessageSquare, MessagesSquare, Search, Sparkles } from "lucide-react"
import { scrapeUrl, ApiError } from "@/lib/api"
import { useStore } from "@/lib/store"
import type { ScrapeResponse } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Button } from "@/components/ui/Button"
import { Spinner } from "@/components/ui/Spinner"
import { ResourceEstimateNotice } from "@/components/ResourceEstimateNotice"
import { Symbol } from "@/brand/Symbol"

const CRAWL_RANGE_OPTIONS = [
  { value: 0, label: "Só esta página" },
  { value: 1, label: "Esta página + links diretos" },
  { value: 2, label: "Explorar mais fundo" },
]

const HOW_IT_WORKS = [
  {
    icon: Search,
    title: "1. Extrair",
    description: "Informe um site técnico. O Docksmith raspa as páginas e transforma tudo em texto estruturado.",
  },
  {
    icon: MessagesSquare,
    title: "2. Perguntar",
    description: "Faça perguntas em linguagem natural. A resposta usa só o conteúdo extraído, sem inventar.",
  },
  {
    icon: Sparkles,
    title: "3. Aprofundar",
    description: "Explore evidências, fontes e detalhes técnicos de cada resposta na análise completa.",
  },
]

export function WorkspacePage() {
  const { state, dispatch } = useStore()
  const navigate = useNavigate()

  const [url, setUrl] = useState("")
  const [collectionName, setCollectionName] = useState("")
  const [maxDepth, setMaxDepth] = useState(1)
  const [formError, setFormError] = useState<string | null>(null)
  const [pendingResult, setPendingResult] = useState<ScrapeResponse | null>(null)

  function commitCollection(data: ScrapeResponse) {
    dispatch({ type: "SET_SESSION", sessionId: data.session_id })
    dispatch({
      type: "ADD_COLLECTION",
      collection: { name: data.collection_name, documentCount: data.document_count, preview: data.preview },
    })
    navigate(`/chat/${encodeURIComponent(data.collection_name)}`)
  }

  const scrapeMutation = useMutation({
    mutationFn: () =>
      scrapeUrl({
        url,
        collection_name: collectionName,
        session_id: state.sessionId,
        max_depth: maxDepth,
      }),
    onSuccess: (data) => {
      // Coleções dentro do limite recomendado seguem direto pro chat; as
      // demais mostram a estimativa de recursos antes de continuar.
      if (data.resource_estimate.status === "ok") {
        commitCollection(data)
      } else {
        setPendingResult(data)
      }
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!url.trim() || !collectionName.trim()) {
      setFormError("Informe o site e o nome da coleção.")
      return
    }
    setPendingResult(null)
    scrapeMutation.mutate()
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <div className="flex flex-col items-start gap-3">
        <Symbol size={36} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary sm:text-2xl">Nova extração</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Informe um site técnico. O Docksmith raspa o conteúdo e monta uma coleção consultável por chat —
            tudo na memória desta sessão, nada é salvo em disco.
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="pt-5">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text-secondary" htmlFor="url">
                Endereço do site
              </label>
              <div className="relative">
                <Globe size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary" />
                <Input
                  id="url"
                  placeholder="https://docs.exemplo.com/guia"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  disabled={scrapeMutation.isPending}
                  className="pl-9"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text-secondary" htmlFor="collection">
                Nome da coleção
              </label>
              <Input
                id="collection"
                placeholder="minha-colecao"
                value={collectionName}
                onChange={(e) => setCollectionName(e.target.value)}
                disabled={scrapeMutation.isPending}
              />
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-text-secondary">Alcance do rastreamento</label>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                {CRAWL_RANGE_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    onClick={() => setMaxDepth(opt.value)}
                    disabled={scrapeMutation.isPending}
                    className={`rounded-lg border px-3 py-2 text-left text-xs font-medium transition disabled:opacity-50 ${
                      maxDepth === opt.value
                        ? "border-temper bg-temper/10 text-temper-strong"
                        : "border-border text-text-secondary hover:bg-surface-2"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-text-tertiary">Sites grandes podem demorar mais para extrair.</p>
            </div>

            {formError && (
              <p className="flex items-center gap-1.5 text-xs text-danger">
                <AlertTriangle size={13} /> {formError}
              </p>
            )}

            {scrapeMutation.isError && (
              <p className="flex items-center gap-1.5 text-xs text-danger">
                <AlertTriangle size={13} />
                {scrapeMutation.error instanceof ApiError
                  ? scrapeMutation.error.message
                  : "Não foi possível concluir a extração."}
              </p>
            )}

            <Button type="submit" disabled={scrapeMutation.isPending} className="self-start">
              {scrapeMutation.isPending ? <Spinner size={15} /> : <ArrowRight size={15} />}
              {scrapeMutation.isPending ? "Extraindo conteúdo…" : "Iniciar extração"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {pendingResult && (
        <ResourceEstimateNotice estimate={pendingResult.resource_estimate}>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" onClick={() => commitCollection(pendingResult)}>
              Continuar para o chat <ArrowRight size={14} />
            </Button>
            <Button size="sm" variant="secondary" onClick={() => setPendingResult(null)}>
              Ajustar extração
            </Button>
          </div>
        </ResourceEstimateNotice>
      )}

      {state.collections.length === 0 && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {HOW_IT_WORKS.map((step) => (
            <div key={step.title} className="rounded-xl border border-border bg-surface p-4">
              <step.icon size={18} className="text-temper-strong" />
              <p className="mt-2.5 text-sm font-semibold text-text-primary">{step.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-text-secondary">{step.description}</p>
            </div>
          ))}
        </div>
      )}

      {state.collections.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-text-tertiary">
            Coleções desta sessão
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {state.collections.map((collection) => (
              <Card
                key={collection.name}
                className="cursor-pointer transition hover:border-temper/50"
                onClick={() => navigate(`/chat/${encodeURIComponent(collection.name)}`)}
              >
                <CardHeader className="flex-row items-center justify-between space-y-0">
                  <div className="min-w-0">
                    <CardTitle className="truncate">{collection.name}</CardTitle>
                    <CardDescription>{collection.documentCount} documento(s)</CardDescription>
                  </div>
                  <MessageSquare size={16} className="shrink-0 text-text-tertiary" />
                </CardHeader>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
