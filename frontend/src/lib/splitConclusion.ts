import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkStringify from "remark-stringify"
import remarkGfm from "remark-gfm"
import { toString as mdastToString } from "mdast-util-to-string"
import type { Root, RootContent, Heading } from "mdast"

/**
 * Separa a "conclusão" da "fundamentação" de uma resposta em Markdown —
 * usando a árvore real do documento (mdast), não regex/corte por frase.
 * Isso evita o problema da regra frágil anterior (extractSummary cortando
 * por parágrafo/frase às cegas, arriscando quebrar tabelas/listas/código).
 *
 * Duas estratégias, nessa ordem, cada uma só age quando o resultado é
 * inequívoco — sem match seguro, devolve a resposta inteira sem split
 * (nunca força uma divisão errada nem duplica conteúdo):
 *
 * 1. Heading explícito de conclusão ("## Conclusão", "## Resumo"...) — se o
 *    modelo já organizou a resposta assim, usamos essa seção como conclusão
 *    e removemos ela do restante.
 * 2. Primeiro bloco é um parágrafo curto E existe conteúdo depois dele — o
 *    padrão comum pedido no prompt do RAG (conclusão objetiva de 1-2 frases
 *    antes da fundamentação). Só dispara com blocks.length > 1, i.e. nunca
 *    quando a resposta inteira É a conclusão.
 *
 * Não depende de nenhum marcador/sintaxe exclusiva do LLM: funciona com
 * texto puro, com ou sem heading, e simplesmente não separa nada quando a
 * estrutura real da resposta não sustenta uma divisão segura (respostas
 * curtas, começando com lista/tabela/código, etc.).
 */

const CONCLUSION_HEADING_PATTERN = /^(conclus[aã]o|resumo|resposta( direta)?|tl;dr|em resumo)\s*:?\s*$/i

// Alinhado ao que o prompt do RAG pede ("conclusão objetiva, 1-2 frases") —
// um parágrafo explicativo comum já passa de ~300 caracteres, então limites
// generosos demais classificariam parágrafos longos como "conclusão".
const SHORT_PARAGRAPH_MAX_CHARS = 280
const SHORT_PARAGRAPH_MAX_WORDS = 45

const parser = unified().use(remarkParse).use(remarkGfm)
const serializer = unified().use(remarkStringify).use(remarkGfm)

function stringifyBlocks(blocks: RootContent[]): string {
  const root: Root = { type: "root", children: blocks }
  return serializer.stringify(root).trim()
}

function isConclusionHeading(node: RootContent): node is Heading {
  return node.type === "heading" && node.depth <= 3 && CONCLUSION_HEADING_PATTERN.test(mdastToString(node).trim())
}

export type ConclusionSplit = {
  conclusion: string | null
  rest: string
}

export function splitConclusion(markdown: string): ConclusionSplit {
  const trimmed = markdown.trim()
  if (!trimmed) return { conclusion: null, rest: markdown }

  let blocks: RootContent[]
  try {
    blocks = (parser.parse(trimmed) as Root).children
  } catch {
    return { conclusion: null, rest: markdown }
  }

  if (blocks.length === 0) return { conclusion: null, rest: markdown }

  // Estratégia 1 — heading explícito de conclusão.
  const headingIdx = blocks.findIndex(isConclusionHeading)
  if (headingIdx !== -1) {
    const nextHeadingIdx = blocks.findIndex((b, i) => i > headingIdx && b.type === "heading")
    const sectionEnd = nextHeadingIdx === -1 ? blocks.length : nextHeadingIdx
    const conclusionBlocks = blocks.slice(headingIdx + 1, sectionEnd)
    const restBlocks = [...blocks.slice(0, headingIdx), ...blocks.slice(sectionEnd)]
    if (conclusionBlocks.length > 0 && restBlocks.length > 0) {
      try {
        return { conclusion: stringifyBlocks(conclusionBlocks), rest: stringifyBlocks(restBlocks) }
      } catch {
        // segue para a próxima estratégia se a re-serialização falhar
      }
    }
  }

  // Estratégia 2 — primeiro bloco é um parágrafo curto, com mais conteúdo depois.
  const [first, ...remaining] = blocks
  if (first.type === "paragraph" && remaining.length > 0) {
    const text = mdastToString(first).trim()
    const wordCount = text.split(/\s+/).filter(Boolean).length
    if (text.length > 0 && text.length <= SHORT_PARAGRAPH_MAX_CHARS && wordCount <= SHORT_PARAGRAPH_MAX_WORDS) {
      try {
        return { conclusion: stringifyBlocks([first]), rest: stringifyBlocks(remaining) }
      } catch {
        // sem split seguro — cai no retorno abaixo
      }
    }
  }

  return { conclusion: null, rest: markdown }
}
