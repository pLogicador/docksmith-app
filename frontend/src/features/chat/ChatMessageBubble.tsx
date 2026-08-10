import { useMemo } from "react"
import { Layers, User } from "lucide-react"
import type { ChatMessage } from "@/lib/types"
import { Symbol } from "@/brand/Symbol"
import { Button } from "@/components/ui/Button"
import { Markdown } from "@/components/markdown/Markdown"
import { ConclusionBlock } from "./ConclusionBlock"
import { splitConclusion } from "@/lib/splitConclusion"

type ChatMessageBubbleProps = {
  message: ChatMessage
  onOpenAnalysis?: () => void
}

export function ChatMessageBubble({ message, onOpenAnalysis }: ChatMessageBubbleProps) {
  const isUser = message.role === "user"
  const hasAnalysis = !isUser && (message.sources?.length || message.provider)
  // Só recalcula quando o conteúdo muda — evita reparsear o markdown a cada
  // re-render do chat (ex.: quando outra mensagem chega).
  const { conclusion, rest } = useMemo(
    () => (isUser ? { conclusion: null, rest: message.content } : splitConclusion(message.content)),
    [isUser, message.content],
  )

  return (
    <div className={`flex animate-msg-in gap-3 ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          isUser ? "bg-surface-2 text-text-secondary" : "bg-temper/10 text-temper-strong"
        }`}
      >
        {isUser ? <User size={13} /> : <Symbol size={14} variant="mono" />}
      </div>

      <div className={`flex min-w-0 max-w-[85%] flex-col gap-1.5 sm:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`min-w-0 max-w-full break-words rounded-2xl px-4 py-2.5 leading-relaxed ${
            isUser
              ? "rounded-tr-sm bg-temper text-temper-foreground"
              : "rounded-tl-sm border border-border bg-surface text-text-primary"
          }`}
        >
          {isUser ? (
            <span className="whitespace-pre-wrap text-sm">{message.content}</span>
          ) : (
            <>
              {conclusion && <ConclusionBlock content={conclusion} />}
              <Markdown content={rest} />
            </>
          )}
        </div>

        {hasAnalysis && (
          <Button variant="ghost" size="sm" onClick={onOpenAnalysis} className="h-7 px-2 text-text-tertiary">
            <Layers size={12} /> Ver análise completa
          </Button>
        )}
      </div>
    </div>
  )
}
