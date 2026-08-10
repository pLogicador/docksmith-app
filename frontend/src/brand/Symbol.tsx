/**
 * Símbolo do Docksmith — "faceta": um hexágono (o bloco bruto de conteúdo
 * extraído) lapidado por duas linhas internas em três facetas, com a
 * faceta inferior-direita — a mais "trabalhada" — destacada em cor e
 * preenchimento. Representa o Docksmith transformando material bruto
 * (páginas raspadas) em conhecimento lapidado e preciso (respostas).
 * Poucas formas e traços grossos: continua legível a 16px (favicon).
 *
 * `variant="color"` usa a cor de destaque (--temper) na faceta lapidada;
 * `variant="mono"` usa `currentColor` em tudo, para contextos de uma cor só.
 */
type SymbolProps = {
  size?: number
  variant?: "color" | "mono"
  className?: string
}

export function Symbol({ size = 24, variant = "color", className }: SymbolProps) {
  const accent = variant === "color" ? "var(--temper, #37A6C4)" : "currentColor"
  const accentFill = variant === "color" ? "var(--temper, #37A6C4)" : "currentColor"

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="Docksmith"
    >
      {/* faceta lapidada — destaque */}
      <path d="M16 16 L27 10 L27 22 L16 29 Z" fill={accentFill} opacity="0.16" />
      {/* contorno do hexágono (bloco bruto) */}
      <path
        d="M16 3 L27 10 L27 22 L16 29 L5 22 L5 10 Z"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinejoin="round"
      />
      {/* linhas internas de lapidação */}
      <path d="M5 10 L16 16 L27 10 M16 16 V29" stroke="currentColor" strokeWidth="1.6" opacity="0.5" strokeLinejoin="round" />
      {/* aresta em destaque — o corte final */}
      <path d="M16 16 L27 22" stroke={accent} strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}
