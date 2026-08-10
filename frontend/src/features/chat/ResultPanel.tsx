import { Layers, FileText, Sparkles, Database, Cpu } from "lucide-react"
import type { ChatMessage } from "@/lib/types"
import { extractInsights, extractSummary } from "@/lib/resultAnalysis"
import { Drawer, DrawerContent } from "@/components/ui/Drawer"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs"
import { Badge } from "@/components/ui/Badge"
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/Accordion"
import { Markdown } from "@/components/markdown/Markdown"

type ResultPanelProps = {
  message: ChatMessage | null
  onOpenChange: (open: boolean) => void
  question: string | null
  collectionDocumentCount: number
  depth: string
}

const DEPTH_LABEL: Record<string, string> = {
  rapida: "Rápida",
  equilibrada: "Equilibrada",
  profunda: "Profunda",
}

export function ResultPanel({ message, onOpenChange, question, collectionDocumentCount, depth }: ResultPanelProps) {
  const open = !!message
  const summary = message ? extractSummary(message.content) : ""
  const insights = message ? extractInsights(message.content) : []
  const sources = message?.sources ?? []

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent side="right" title="Análise completa" className="max-w-xl">
        {message && (
          <div className="flex flex-col gap-5 overflow-x-hidden break-words p-4 sm:p-5">
            {question && (
              <div className="break-words rounded-lg bg-surface-2 px-3 py-2 text-xs text-text-secondary">
                <span className="font-medium text-text-tertiary">Pergunta: </span>
                {question}
              </div>
            )}

            <Tabs defaultValue="resumo">
              <TabsList>
                <TabsTrigger value="resumo">
                  <Layers size={13} className="mr-1.5 inline" /> Resumo
                </TabsTrigger>
                <TabsTrigger value="insights">
                  <Sparkles size={13} className="mr-1.5 inline" /> Insights
                </TabsTrigger>
                <TabsTrigger value="evidencias">
                  <FileText size={13} className="mr-1.5 inline" /> Evidências
                </TabsTrigger>
                <TabsTrigger value="dados">
                  <Database size={13} className="mr-1.5 inline" /> Dados
                </TabsTrigger>
                <TabsTrigger value="tecnico">
                  <Cpu size={13} className="mr-1.5 inline" /> Técnico
                </TabsTrigger>
              </TabsList>

              <TabsContent value="resumo">
                <Markdown content={summary} className="text-sm text-text-primary" />
                <p className="mt-3 text-xs text-text-tertiary">
                  Conclusão — a essência da resposta, extraída do início dela. Veja a fundamentação completa no chat.
                </p>
              </TabsContent>

              <TabsContent value="insights">
                {insights.length ? (
                  <ul className="flex flex-col gap-2.5">
                    {insights.map((point, i) => (
                      <li key={i} className="flex gap-2.5 text-sm text-text-primary">
                        <span className="mt-0.5 shrink-0 text-temper-strong">{i + 1}.</span>
                        <Markdown content={point} inline className="leading-relaxed" />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-text-tertiary">Sem pontos estruturados identificados nesta resposta.</p>
                )}
              </TabsContent>

              <TabsContent value="evidencias">
                {sources.length ? (
                  <Accordion type="multiple" className="flex flex-col gap-2">
                    {sources.map((s) => (
                      <AccordionItem
                        key={s.index}
                        value={String(s.index)}
                        className="rounded-lg border border-border bg-surface-2 px-3"
                      >
                        <AccordionTrigger className="text-[10px] font-semibold uppercase tracking-wide text-text-tertiary">
                          Trecho {s.index + 1}
                        </AccordionTrigger>
                        <AccordionContent className="break-words text-xs leading-relaxed text-text-secondary">
                          {s.excerpt}
                        </AccordionContent>
                      </AccordionItem>
                    ))}
                  </Accordion>
                ) : (
                  <p className="text-sm text-text-tertiary">Nenhum trecho-fonte retornado para esta resposta.</p>
                )}
              </TabsContent>

              <TabsContent value="dados">
                <dl className="grid grid-cols-2 gap-3">
                  <div className="rounded-lg border border-border bg-surface-2 p-3">
                    <dt className="text-[11px] text-text-tertiary">Documentos na coleção</dt>
                    <dd className="mt-1 text-lg font-semibold text-text-primary">{collectionDocumentCount}</dd>
                  </div>
                  <div className="rounded-lg border border-border bg-surface-2 p-3">
                    <dt className="text-[11px] text-text-tertiary">Trechos usados na resposta</dt>
                    <dd className="mt-1 text-lg font-semibold text-text-primary">{sources.length}</dd>
                  </div>
                  <div className="rounded-lg border border-border bg-surface-2 p-3">
                    <dt className="text-[11px] text-text-tertiary">Profundidade</dt>
                    <dd className="mt-1 text-lg font-semibold text-text-primary">{DEPTH_LABEL[depth] ?? depth}</dd>
                  </div>
                  <div className="rounded-lg border border-border bg-surface-2 p-3">
                    <dt className="text-[11px] text-text-tertiary">Caracteres na resposta</dt>
                    <dd className="mt-1 text-lg font-semibold text-text-primary">{message.content.length}</dd>
                  </div>
                </dl>
              </TabsContent>

              <TabsContent value="tecnico">
                <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap gap-1.5">
                    {message.provider && <Badge variant="temper">{message.provider}</Badge>}
                    {message.model && <Badge variant="neutral">{message.model}</Badge>}
                    <Badge variant="neutral">{new Date(message.timestamp).toLocaleString("pt-BR")}</Badge>
                  </div>
                  <p className="text-xs leading-relaxed text-text-tertiary">
                    A resposta foi gerada por busca vetorial (FAISS + embeddings locais) sobre a coleção, seguida de
                    geração de texto pelo modelo de IA selecionado, usando apenas os trechos recuperados como contexto.
                  </p>
                </div>
              </TabsContent>
            </Tabs>
          </div>
        )}
      </DrawerContent>
    </Drawer>
  )
}
