import { Fragment, type ComponentPropsWithoutRef } from "react"
import ReactMarkdown, { type Components } from "react-markdown"
import remarkGfm from "remark-gfm"
import { cn } from "@/lib/cn"

function buildComponents(inline: boolean): Components {
  return {
    h1: (p) => <h3 className="mt-3 mb-1.5 text-base font-semibold text-text-primary first:mt-0" {...p} />,
    h2: (p) => <h4 className="mt-3 mb-1.5 text-sm font-semibold text-text-primary first:mt-0" {...p} />,
    h3: (p) => <h5 className="mt-2.5 mb-1 text-sm font-semibold text-text-primary first:mt-0" {...p} />,
    p: inline ? (p) => <Fragment>{p.children}</Fragment> : (p) => <p className="mb-2.5 leading-relaxed last:mb-0" {...p} />,
    ul: (p) => <ul className="mb-2.5 ml-4 list-disc space-y-1 last:mb-0" {...p} />,
    ol: (p) => <ol className="mb-2.5 ml-4 list-decimal space-y-1 last:mb-0" {...p} />,
    li: (p) => <li className="leading-relaxed" {...p} />,
    strong: (p) => <strong className="font-semibold text-text-primary" {...p} />,
    em: (p) => <em className="italic" {...p} />,
    a: (p) => (
      <a className="text-temper-strong underline underline-offset-2 hover:opacity-80" target="_blank" rel="noreferrer" {...p} />
    ),
    blockquote: (p) => (
      <blockquote className="mb-2.5 border-l-2 border-temper/50 pl-3 text-text-secondary last:mb-0" {...p} />
    ),
    code: ({ className, children, ...p }: ComponentPropsWithoutRef<"code">) => {
      const isBlock = /language-/.test(className ?? "")
      if (!isBlock) {
        return (
          <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-[0.85em] text-temper-strong" {...p}>
            {children}
          </code>
        )
      }
      return (
        <code className={cn("block font-mono text-xs leading-relaxed", className)} {...p}>
          {children}
        </code>
      )
    },
    pre: (p) => <pre className="mb-2.5 overflow-x-auto rounded-lg border border-border bg-surface-2 p-3 last:mb-0" {...p} />,
    table: (p) => (
      <div className="mb-2.5 overflow-x-auto last:mb-0">
        <table className="w-full border-collapse text-xs" {...p} />
      </div>
    ),
    th: (p) => <th className="border border-border bg-surface-2 px-2 py-1 text-left font-semibold" {...p} />,
    td: (p) => <td className="border border-border px-2 py-1" {...p} />,
    hr: (p) => <hr className="my-3 border-border" {...p} />,
  }
}

type MarkdownProps = {
  content: string
  className?: string
  /** Renderiza sem quebra de parágrafo — para uso dentro de listas/linhas já existentes. */
  inline?: boolean
}

export function Markdown({ content, className, inline = false }: MarkdownProps) {
  return (
    <div className={cn("text-sm", className)}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={buildComponents(inline)}>
        {content}
      </ReactMarkdown>
    </div>
  )
}
