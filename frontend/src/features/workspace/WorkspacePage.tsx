import { useRef, useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { useNavigate } from "react-router-dom"
import { AlertTriangle, ArrowRight, FileText, Globe, MessageSquare, MessagesSquare, Search, Sparkles, Upload } from "lucide-react"
import { scrapeUrl, uploadDocument, splitUploadDocument, ApiError } from "@/lib/api"
import { useStore } from "@/lib/store"
import type { PageLimitExceededDetail, ScrapeResponse, SplitUploadResponse } from "@/lib/types"
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/Card"
import { Input } from "@/components/ui/Input"
import { Button } from "@/components/ui/Button"
import { Spinner } from "@/components/ui/Spinner"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/Tabs"
import { ResourceEstimateNotice } from "@/components/ResourceEstimateNotice"
import { Symbol } from "@/brand/Symbol"

// PDF/DOCX (2026-09-02, prompt-mestre "Docksmith" §6): mesmos formatos que
// docksmith/service/document_loader.py aceita no backend -- mantido em
// sincronia manual (não há um endpoint de "formatos suportados" ainda).
const ACCEPTED_DOCUMENT_TYPES = ".pdf,.docx"
const MAX_DOCUMENT_SIZE_MB = 20 // espelha DOCSMITH_MAX_FILE_SIZE_MB (default do backend)

const CRAWL_RANGE_OPTIONS = [
  { value: 0, label: "Só esta página" },
  { value: 1, label: "Esta página + links diretos" },
  { value: 2, label: "Explorar mais fundo" },
]

// 2026-09-10, mesmo padrão de isChatBlockedDetail (ChatPage.tsx) -- em vez
// de checar `err.status === 422` sozinho (outros erros também usam 422),
// confirma pelo campo `error` literal que veio da API.
function isPageLimitExceededDetail(detail: unknown): detail is PageLimitExceededDetail {
  return typeof detail === "object" && detail !== null && (detail as { error?: unknown }).error === "page_limit_exceeded"
}

const HOW_IT_WORKS = [
  {
    icon: Search,
    title: "1. Extrair",
    description: "Informe um site técnico. O Docksmith lê as páginas e organiza tudo em um texto fácil de consultar.",
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

  const [uploadCollectionName, setUploadCollectionName] = useState("")
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [pageLimitBlocked, setPageLimitBlocked] = useState<PageLimitExceededDetail | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

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

  const uploadMutation = useMutation({
    mutationFn: ({ truncate }: { truncate?: boolean } = {}) =>
      uploadDocument({
        file: selectedFile!,
        collection_name: uploadCollectionName,
        session_id: state.sessionId,
        truncate,
      }),
    onSuccess: (data) => {
      setPageLimitBlocked(null)
      if (data.resource_estimate.status === "ok") {
        commitCollection(data)
      } else {
        setPendingResult(data)
      }
    },
    onError: (err) => {
      // Documento acima de DOCSMITH_MAX_PAGES (2026-09-10): em vez de só
      // mostrar o erro genérico abaixo, guarda o detalhe estruturado pra
      // oferecer "processar só as primeiras N páginas" ou dividir tudo.
      if (err instanceof ApiError && err.status === 422 && isPageLimitExceededDetail(err.detail)) {
        setPageLimitBlocked(err.detail)
      }
    },
  })

  // Fase A (2026-09-10): alternativa a "processar só as primeiras N
  // páginas" -- divide o documento inteiro em várias coleções (uma por
  // parte, cada uma fechando ao final de um capítulo sempre que possível)
  // em vez de descartar o que excede o limite.
  const splitMutation = useMutation({
    mutationFn: () =>
      splitUploadDocument({
        file: selectedFile!,
        collection_name: uploadCollectionName,
        session_id: state.sessionId,
      }),
    onSuccess: (data: SplitUploadResponse) => {
      setPageLimitBlocked(null)
      dispatch({ type: "SET_SESSION", sessionId: data.session_id })
      for (const part of data.parts) {
        dispatch({
          type: "ADD_COLLECTION",
          collection: { name: part.collection_name, documentCount: part.document_count, preview: [] },
        })
      }
      // Vai direto pra 1ª parte -- as demais já ficam disponíveis na lista
      // "Coleções desta sessão" abaixo, prontas pra abrir/combinar (Fase H).
      navigate(`/chat/${encodeURIComponent(data.parts[0].collection_name)}`)
    },
  })

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    setUploadError(null)
    setPageLimitBlocked(null)
    const file = e.target.files?.[0] ?? null
    if (file && file.size > MAX_DOCUMENT_SIZE_MB * 1024 * 1024) {
      setUploadError(`Arquivo maior que ${MAX_DOCUMENT_SIZE_MB}MB.`)
      setSelectedFile(null)
      return
    }
    setSelectedFile(file)
  }

  function handleUploadSubmit(e: React.FormEvent) {
    e.preventDefault()
    setUploadError(null)
    setPageLimitBlocked(null)
    if (!selectedFile) {
      setUploadError("Selecione um arquivo PDF ou DOCX.")
      return
    }
    if (!uploadCollectionName.trim()) {
      setUploadError("Informe o nome da coleção.")
      return
    }
    setPendingResult(null)
    uploadMutation.mutate({})
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-8 sm:px-6 sm:py-10">
      <div className="flex flex-col items-start gap-3">
        <Symbol size={36} />
        <div>
          <h1 className="font-display text-xl font-semibold text-text-primary sm:text-2xl">Nova extração</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Informe um site técnico ou envie um PDF/DOCX. O Docksmith extrai o conteúdo e monta uma coleção
            consultável por chat: tudo na memória desta sessão, nada é salvo em disco.
          </p>
        </div>
      </div>

      <Card>
        <CardContent className="pt-5">
          <Tabs defaultValue="url">
            <TabsList>
              <TabsTrigger value="url">
                <Globe size={13} className="mr-1.5 inline" /> Endereço do site
              </TabsTrigger>
              <TabsTrigger value="file">
                <Upload size={13} className="mr-1.5 inline" /> Enviar arquivo
              </TabsTrigger>
            </TabsList>

            <TabsContent value="url">
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
                  <label className="text-xs font-medium text-text-secondary">Quanto explorar do site</label>
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
            </TabsContent>

            <TabsContent value="file">
              <form onSubmit={handleUploadSubmit} className="flex flex-col gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-text-secondary" htmlFor="document-file">
                    Arquivo (PDF ou DOCX)
                  </label>
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploadMutation.isPending}
                    className="flex w-full items-center gap-2.5 rounded-lg border border-dashed border-border px-3 py-3 text-left text-sm text-text-secondary transition hover:bg-surface-2 disabled:opacity-50"
                  >
                    <FileText size={16} className="shrink-0 text-text-tertiary" />
                    <span className="truncate">
                      {selectedFile ? selectedFile.name : "Clique para escolher um arquivo (até 20MB)"}
                    </span>
                  </button>
                  <input
                    ref={fileInputRef}
                    id="document-file"
                    type="file"
                    accept={ACCEPTED_DOCUMENT_TYPES}
                    onChange={handleFileChange}
                    disabled={uploadMutation.isPending}
                    className="hidden"
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-text-secondary" htmlFor="upload-collection">
                    Nome da coleção
                  </label>
                  <Input
                    id="upload-collection"
                    placeholder="minha-colecao"
                    value={uploadCollectionName}
                    onChange={(e) => setUploadCollectionName(e.target.value)}
                    disabled={uploadMutation.isPending}
                  />
                </div>

                {uploadError && (
                  <p className="flex items-center gap-1.5 text-xs text-danger">
                    <AlertTriangle size={13} /> {uploadError}
                  </p>
                )}

                {uploadMutation.isError && !pageLimitBlocked && (
                  <p className="flex items-center gap-1.5 text-xs text-danger">
                    <AlertTriangle size={13} />
                    {uploadMutation.error instanceof ApiError
                      ? uploadMutation.error.message
                      : "Não foi possível concluir o envio."}
                  </p>
                )}

                {/* Documento acima de DOCSMITH_MAX_PAGES (2026-09-10, pedido
                    explícito do usuário): em vez de só recusar, oferece
                    processar uma versão parcial em vez do usuário precisar
                    cortar o próprio arquivo fora da ferramenta. */}
                {pageLimitBlocked && (
                  <div className="flex flex-col gap-2 rounded-lg border border-warning/30 bg-warning/5 px-3 py-2.5 text-xs">
                    <p className="flex items-start gap-1.5 text-text-primary">
                      <AlertTriangle size={13} className="mt-0.5 shrink-0 text-warning" />
                      O documento tem {pageLimitBlocked.actual_count} {pageLimitBlocked.unit}, acima do limite de{" "}
                      {pageLimitBlocked.max_pages} por envio.
                    </p>
                    <p className="text-text-tertiary">
                      Podemos processar só as primeiras {pageLimitBlocked.max_pages} {pageLimitBlocked.unit}
                      (o restante fica de fora), ou dividir o documento inteiro em várias coleções, cada uma dentro
                      do limite, sem perder nenhum conteúdo.
                    </p>
                    <div className="flex flex-wrap items-center gap-2 pt-0.5">
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => splitMutation.mutate()}
                        disabled={uploadMutation.isPending || splitMutation.isPending}
                      >
                        {splitMutation.isPending ? <Spinner size={13} /> : null}
                        Dividir em partes e processar tudo
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => uploadMutation.mutate({ truncate: true })}
                        disabled={uploadMutation.isPending || splitMutation.isPending}
                      >
                        {uploadMutation.isPending ? <Spinner size={13} /> : null}
                        Processar só as primeiras {pageLimitBlocked.max_pages} {pageLimitBlocked.unit}
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        variant="secondary"
                        onClick={() => setPageLimitBlocked(null)}
                        disabled={uploadMutation.isPending || splitMutation.isPending}
                      >
                        Cancelar
                      </Button>
                    </div>
                    {splitMutation.isError && (
                      <p className="flex items-center gap-1.5 text-danger">
                        <AlertTriangle size={13} />
                        {splitMutation.error instanceof ApiError
                          ? splitMutation.error.message
                          : "Não foi possível dividir o documento."}
                      </p>
                    )}
                  </div>
                )}

                <Button type="submit" disabled={uploadMutation.isPending} className="self-start">
                  {uploadMutation.isPending ? <Spinner size={15} /> : <ArrowRight size={15} />}
                  {uploadMutation.isPending ? "Processando arquivo…" : "Enviar e extrair"}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
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
