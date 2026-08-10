import { useEffect, useRef, useState } from "react"
import { useParams, useNavigate, Link } from "react-router-dom"
import { useMutation } from "@tanstack/react-query"
import { ArrowLeft, Download, SendHorizonal, Trash2 } from "lucide-react"
import { askQuestion, ApiError } from "@/lib/api"
import { useStore } from "@/lib/store"
import type { ChatBlockedDetail } from "@/lib/types"
import { Symbol } from "@/brand/Symbol"
import { Button } from "@/components/ui/Button"
import { Textarea } from "@/components/ui/Input"
import { Spinner } from "@/components/ui/Spinner"
import { ResourceEstimateNotice } from "@/components/ResourceEstimateNotice"
import { ChatMessageBubble } from "./ChatMessageBubble"
import { ResultPanel } from "./ResultPanel"

function isChatBlockedDetail(detail: unknown): detail is ChatBlockedDetail {
  return typeof detail === "object" && detail !== null && (detail as { requires_confirmation?: unknown }).requires_confirmation === true
}

const SWIPE_DISTANCE_THRESHOLD = 60

// Ignora o gesto se ele começar dentro de algo com scroll horizontal próprio
// (blocos de código / tabelas do markdown) — senão rolar um bloco de código
// trocaria de coleção sem querer.
function hasHorizontalScrollAncestor(el: HTMLElement | null): boolean {
  let node = el
  while (node && node !== document.body) {
    if (node.scrollWidth > node.clientWidth) {
      const overflowX = getComputedStyle(node).overflowX
      if (overflowX === "auto" || overflowX === "scroll") return true
    }
    node = node.parentElement
  }
  return false
}

export function ChatPage() {
  const { collectionName = "" } = useParams()
  const decodedName = decodeURIComponent(collectionName)
  const { state, dispatch } = useStore()
  const navigate = useNavigate()
  const [question, setQuestion] = useState("")
  const [analysisMessageId, setAnalysisMessageId] = useState<string | null>(null)
  const [swipeDirection, setSwipeDirection] = useState<"prev" | "next" | null>(null)
  const [blocked, setBlocked] = useState<{ question: string; detail: ChatBlockedDetail } | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const touchStartRef = useRef<{ x: number; y: number; skip: boolean } | null>(null)

  const collection = state.collections.find((c) => c.name === decodedName)
  const messages = state.messagesByCollection[decodedName] ?? []
  const collectionIndex = state.collections.findIndex((c) => c.name === decodedName)

  function handleTouchStart(e: React.TouchEvent) {
    const touch = e.touches[0]
    touchStartRef.current = {
      x: touch.clientX,
      y: touch.clientY,
      skip: hasHorizontalScrollAncestor(e.target as HTMLElement),
    }
  }

  function handleTouchEnd(e: React.TouchEvent) {
    const start = touchStartRef.current
    touchStartRef.current = null
    if (!start || start.skip || collectionIndex < 0) return

    const touch = e.changedTouches[0]
    const deltaX = touch.clientX - start.x
    const deltaY = touch.clientY - start.y
    if (Math.abs(deltaX) < SWIPE_DISTANCE_THRESHOLD || Math.abs(deltaX) < Math.abs(deltaY) * 1.5) return

    if (deltaX < 0 && collectionIndex < state.collections.length - 1) {
      setSwipeDirection("next")
      navigate(`/chat/${encodeURIComponent(state.collections[collectionIndex + 1].name)}`)
    } else if (deltaX > 0 && collectionIndex > 0) {
      setSwipeDirection("prev")
      navigate(`/chat/${encodeURIComponent(state.collections[collectionIndex - 1].name)}`)
    }
  }

  const askMutation = useMutation({
    mutationFn: ({ question: q, confirm }: { question: string; confirm?: boolean }) =>
      askQuestion({
        session_id: state.sessionId!,
        collection_name: decodedName,
        question: q,
        provider: state.modelConfig.provider,
        model: state.modelConfig.model,
        api_key: state.modelConfig.apiKey,
        depth: state.depth,
        confirm_large_collection: confirm,
      }),
  })

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, askMutation.isPending])

  useEffect(() => {
    if (!swipeDirection) return
    const timeout = setTimeout(() => setSwipeDirection(null), 220)
    return () => clearTimeout(timeout)
  }, [swipeDirection, decodedName])

  if (!collection || !state.sessionId) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 px-6 text-center">
        <Symbol size={36} className="text-text-tertiary" />
        <div className="max-w-xs space-y-1">
          <p className="text-sm font-medium text-text-primary">Coleção não encontrada nesta sessão</p>
          <p className="text-xs text-text-secondary">
            Isso acontece se a página foi recarregada. Faça uma nova extração para continuar.
          </p>
        </div>
        <Link to="/">
          <Button size="sm" variant="secondary">
            <ArrowLeft size={14} /> Nova extração
          </Button>
        </Link>
      </div>
    )
  }

  function askAndHandle(q: string, confirm?: boolean) {
    askMutation.mutate(
      { question: q, confirm },
      {
        onSuccess: (data) => {
          setBlocked(null)
          dispatch({
            type: "ADD_MESSAGE",
            collectionName: decodedName,
            message: {
              id: crypto.randomUUID(),
              role: "assistant",
              content: data.answer,
              sources: data.sources,
              provider: data.provider,
              model: data.model,
              timestamp: new Date().toISOString(),
            },
          })
        },
        onError: (err) => {
          // Coleção grande demais pra indexar com segurança: em vez de um erro
          // genérico, mostra a estimativa e deixa o usuário confirmar (ou não).
          if (err instanceof ApiError && err.status === 413 && isChatBlockedDetail(err.detail)) {
            setBlocked({ question: q, detail: err.detail })
            return
          }
          dispatch({
            type: "ADD_MESSAGE",
            collectionName: decodedName,
            message: {
              id: crypto.randomUUID(),
              role: "assistant",
              content: err instanceof ApiError ? err.message : "Não foi possível responder agora. Tente novamente.",
              timestamp: new Date().toISOString(),
            },
          })
        },
      },
    )
  }

  function handleSend() {
    const trimmed = question.trim()
    if (!trimmed || askMutation.isPending) return
    const now = new Date().toISOString()
    dispatch({
      type: "ADD_MESSAGE",
      collectionName: decodedName,
      message: { id: crypto.randomUUID(), role: "user", content: trimmed, timestamp: now },
    })
    setQuestion("")
    setBlocked(null)
    askAndHandle(trimmed)
  }

  const analysisIndex = messages.findIndex((m) => m.id === analysisMessageId)
  const analysisMessage = analysisIndex >= 0 ? messages[analysisIndex] : null
  const analysisQuestion = analysisIndex > 0 ? messages[analysisIndex - 1]?.content ?? null : null

  function handleDownload() {
    const lines = messages.map((m) => `[${m.timestamp}] ${m.role === "user" ? "Usuário" : "Docksmith"}: ${m.content}`)
    const blob = new Blob([lines.join("\n\n")], { type: "text/plain" })
    const link = document.createElement("a")
    link.href = URL.createObjectURL(blob)
    link.download = `chat_${decodedName}.txt`
    link.click()
    URL.revokeObjectURL(link.href)
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-col gap-2 border-b border-border px-4 py-3 sm:px-6">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-text-primary">{decodedName}</p>
            <p className="text-xs text-text-tertiary">{collection.documentCount} documento(s) indexado(s)</p>
          </div>
          <div className="flex shrink-0 gap-1.5">
            <Button variant="ghost" size="icon" onClick={handleDownload} disabled={!messages.length} aria-label="Baixar histórico">
              <Download size={15} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => dispatch({ type: "CLEAR_MESSAGES", collectionName: decodedName })}
              disabled={!messages.length}
              aria-label="Limpar chat"
            >
              <Trash2 size={15} />
            </Button>
          </div>
        </div>

        {state.collections.length > 1 && (
          <div className="flex items-center gap-1.5 lg:hidden" aria-label="Posição entre coleções (arraste para os lados para trocar)">
            {state.collections.map((c, i) => (
              <span
                key={c.name}
                className={`h-1.5 rounded-full transition-all ${
                  i === collectionIndex ? "w-4 bg-temper-strong" : "w-1.5 bg-border"
                }`}
              />
            ))}
          </div>
        )}
      </div>

      <div
        ref={scrollRef}
        onTouchStart={handleTouchStart}
        onTouchEnd={handleTouchEnd}
        className={`flex-1 overflow-y-auto scrollbar-thin px-4 py-5 sm:px-6 ${
          swipeDirection === "next"
            ? "[animation:panel-in-right_200ms_ease-out]"
            : swipeDirection === "prev"
              ? "[animation:panel-in-left_200ms_ease-out]"
              : ""
        }`}
      >
        {state.collections.length > 1 && (
          <p className="mb-3 text-center text-[11px] text-text-tertiary lg:hidden">
            Arraste para os lados para trocar de coleção
          </p>
        )}
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-2 text-center">
            <Symbol size={32} className="text-text-tertiary" />
            <p className="text-sm text-text-secondary">Faça uma pergunta sobre os documentos extraídos.</p>
          </div>
        ) : (
          <div className="mx-auto flex max-w-2xl flex-col gap-5">
            {messages.map((m) => (
              <ChatMessageBubble
                key={m.id}
                message={m}
                onOpenAnalysis={() => setAnalysisMessageId(m.id)}
              />
            ))}
            {askMutation.isPending && (
              <div className="flex items-center gap-2 text-xs text-text-tertiary">
                <Spinner size={13} /> Pensando…
              </div>
            )}
          </div>
        )}
      </div>

      {blocked && (
        <div className="shrink-0 border-t border-border px-4 py-3 sm:px-6">
          <ResourceEstimateNotice estimate={blocked.detail.resource_estimate} className="mx-auto max-w-2xl">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="destructive"
                onClick={() => askAndHandle(blocked.question, true)}
                disabled={askMutation.isPending}
              >
                {askMutation.isPending ? <Spinner size={13} /> : null}
                Perguntar mesmo assim
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setBlocked(null)}>
                Cancelar
              </Button>
            </div>
          </ResourceEstimateNotice>
        </div>
      )}

      <div className="shrink-0 border-t border-border p-3 sm:p-4">
        <div className="mx-auto flex max-w-2xl items-end gap-2">
          <Textarea
            rows={1}
            placeholder="Faça uma pergunta sobre os documentos…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            className="max-h-32 min-h-[42px]"
          />
          <Button size="icon" onClick={handleSend} disabled={!question.trim() || askMutation.isPending} aria-label="Enviar">
            <SendHorizonal size={16} />
          </Button>
        </div>
      </div>

      <ResultPanel
        message={analysisMessage}
        onOpenChange={(open) => !open && setAnalysisMessageId(null)}
        question={analysisQuestion}
        collectionDocumentCount={collection.documentCount}
        depth={state.depth}
      />
    </div>
  )
}
