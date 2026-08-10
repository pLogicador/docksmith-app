import { Markdown } from "@/components/markdown/Markdown"

/**
 * Destaque visual da conclusão dentro do próprio balão do chat — só é usado
 * quando splitConclusion() (frontend/src/lib/splitConclusion.ts) identifica
 * com segurança uma conclusão separável da fundamentação. Rótulo pequeno em
 * caixa alta segue o mesmo padrão já usado em "Trecho N" (evidências) e
 * "Configuração avançada" (painel de modelo), para ficar consistente com o
 * resto do app em vez de inventar um estilo novo.
 */
export function ConclusionBlock({ content }: { content: string }) {
  return (
    <div className="mb-2.5 rounded-lg border border-temper/25 bg-temper/5 px-3 py-2.5">
      <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-temper-strong">Conclusão</p>
      <Markdown content={content} className="text-sm font-medium text-text-primary" />
    </div>
  )
}
