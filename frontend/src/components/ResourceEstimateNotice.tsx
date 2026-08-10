import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react"
import type { ResourceEstimate } from "@/lib/types"
import { cn } from "@/lib/cn"

const COPY: Record<ResourceEstimate["status"], { title: string; body: string }> = {
  ok: {
    title: "Coleção dentro do limite recomendado",
    body: "A análise pode continuar normalmente.",
  },
  atencao: {
    title: "Coleção grande",
    body: "Esta análise pode exigir mais memória durante a preparação. Recomendamos reduzir a quantidade de conteúdo ou prosseguir sabendo que a operação pode demorar mais.",
  },
  muito_grande: {
    title: "Coleção muito grande",
    body: "O conteúdo selecionado pode exceder a capacidade recomendada desta sessão. Recomendamos reduzir a coleção antes de continuar.",
  },
  bloqueado: {
    title: "Coleção muito grande",
    body: "O conteúdo selecionado pode exceder a capacidade recomendada desta sessão. Recomendamos reduzir a coleção antes de continuar.",
  },
}

const TONE: Record<ResourceEstimate["status"], { border: string; bg: string; text: string; icon: typeof CheckCircle2 }> = {
  ok: { border: "border-success/30", bg: "bg-success/10", text: "text-success", icon: CheckCircle2 },
  atencao: { border: "border-warning/30", bg: "bg-warning/10", text: "text-warning", icon: AlertTriangle },
  muito_grande: { border: "border-danger/30", bg: "bg-danger/10", text: "text-danger", icon: ShieldAlert },
  bloqueado: { border: "border-danger/30", bg: "bg-danger/10", text: "text-danger", icon: ShieldAlert },
}

const STATUS_LABEL: Record<ResourceEstimate["status"], string> = {
  ok: "Dentro do limite",
  atencao: "Atenção",
  muito_grande: "Muito grande",
  bloqueado: "Bloqueado",
}

function formatNumber(n: number): string {
  return n.toLocaleString("pt-BR")
}

function formatMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} GB`
  return `${mb.toLocaleString("pt-BR", { maximumFractionDigits: 1 })} MB`
}

export function ResourceEstimateNotice({
  estimate,
  className,
  children,
}: {
  estimate: ResourceEstimate
  className?: string
  children?: React.ReactNode
}) {
  const copy = COPY[estimate.status]
  const tone = TONE[estimate.status]
  const Icon = tone.icon

  return (
    <div className={cn("rounded-xl border p-4", tone.border, tone.bg, className)}>
      <div className="flex items-start gap-2.5">
        <Icon size={17} className={cn("mt-0.5 shrink-0", tone.text)} />
        <div className="min-w-0 space-y-1">
          <p className={cn("text-sm font-semibold", tone.text)}>{copy.title}</p>
          <p className="text-xs leading-relaxed text-text-secondary">{copy.body}</p>
        </div>
      </div>

      <div className="mt-3 rounded-lg border border-border/60 bg-surface/60 p-3 text-xs text-text-secondary">
        <p className="mb-1.5 font-medium text-text-primary">Estimativa de recursos</p>
        <ul className="space-y-0.5">
          <li>{formatNumber(estimate.document_count)} documento(s)</li>
          <li>~{formatMb(estimate.total_mb)} de conteúdo</li>
          <li>~{formatNumber(estimate.estimated_chunks)} trechos estimados</li>
          <li>Consumo estimado durante preparação: ~{formatMb(estimate.estimated_indexing_mb)}</li>
          <li>Memória disponível: ~{formatMb(estimate.available_memory_mb)}</li>
          <li>
            Status: <span className={cn("font-medium", tone.text)}>{STATUS_LABEL[estimate.status]}</span>
          </li>
        </ul>
      </div>

      {children && <div className="mt-3">{children}</div>}
    </div>
  )
}
