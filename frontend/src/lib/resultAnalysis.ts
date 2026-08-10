/**
 * Deriva os níveis "Resumo" e "Insights" a partir do texto da resposta —
 * sem chamada extra ao LLM. Nunca inventa conteúdo: só reorganiza o que o
 * modelo já respondeu (primeiras frases / itens de lista já presentes).
 */

import { splitConclusion } from "./splitConclusion"

const BULLET_PATTERN = /^(\d+[.)]|[-*•])\s+/

export function extractSummary(answer: string): string {
  // Reusa a mesma análise estrutural (mdast) do balão do chat — só cai no
  // corte por frase/parágrafo quando não há uma conclusão claramente
  // separável (ver splitConclusion.ts), já que este painel sempre precisa
  // mostrar algum resumo, mesmo quando o balão não destaca nada.
  const { conclusion } = splitConclusion(answer)
  if (conclusion) return conclusion

  const firstBlock = answer.split(/\n\s*\n/)[0]?.trim()
  if (firstBlock && firstBlock.length > 0 && firstBlock.length < 600) {
    return firstBlock.replace(/^#{1,6}\s*/, "")
  }

  const sentences = answer
    .replace(/\n+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
  if (sentences.length === 0) return answer.slice(0, 220)
  return sentences.slice(0, 2).join(" ")
}

export function extractInsights(answer: string): string[] {
  const lines = answer
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)

  const bulletLines = lines.filter((l) => BULLET_PATTERN.test(l))
  if (bulletLines.length >= 2) {
    // Mantém marcações inline (**negrito**, `código`) — quem renderiza é
    // <Markdown inline />, não faz sentido mais tirar `**` aqui.
    return bulletLines.map((l) => l.replace(BULLET_PATTERN, ""))
  }

  const sentences = answer
    .replace(/\n+/g, " ")
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter((s) => s.length > 25)

  return sentences.slice(0, 5)
}
