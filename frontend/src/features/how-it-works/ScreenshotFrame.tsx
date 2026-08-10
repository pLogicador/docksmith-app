import { cn } from "@/lib/cn"

type ScreenshotFrameProps = {
  src: string
  alt: string
  className?: string
  priority?: boolean
}

/**
 * Moldura simples (borda + sombra) para screenshots reais do Docksmith —
 * sem chrome de navegador falso: como as imagens já são o produto de
 * verdade, a moldura só precisa dar acabamento, não vender ilusão de app.
 */
export function ScreenshotFrame({ src, alt, className, priority }: ScreenshotFrameProps) {
  return (
    <div className={cn("overflow-hidden rounded-2xl border border-border bg-surface shadow-lg", className)}>
      <img src={src} alt={alt} loading={priority ? "eager" : "lazy"} className="block h-auto w-full" />
    </div>
  )
}
