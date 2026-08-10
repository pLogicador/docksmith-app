import { Symbol } from "@/brand/Symbol"
import { cn } from "@/lib/cn"
import { HOW_IT_WORKS_STEPS } from "./steps"
import { ScreenshotFrame } from "./ScreenshotFrame"

export function HowItWorksPage() {
  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-10 px-4 py-8 sm:px-6 sm:py-10 lg:gap-16">
      <header className="flex flex-col items-start gap-3">
        <Symbol size={36} />
        <div>
          <h1 className="text-xl font-semibold text-text-primary sm:text-2xl">Como funciona</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-text-secondary sm:text-base">
            Do link até a resposta: veja o caminho completo de uma extração no Docksmith, passo a passo.
          </p>
        </div>
      </header>

      <div className="flex flex-col gap-12 lg:gap-20">
        {HOW_IT_WORKS_STEPS.map((step, i) => {
          const reversed = i % 2 === 1
          return (
            <section
              key={step.id}
              className="grid grid-cols-1 items-center gap-5 lg:grid-cols-[1fr_1.1fr] lg:gap-10"
            >
              <div className={cn("flex flex-col gap-2.5", reversed && "lg:order-2")}>
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-temper/10 text-xs font-semibold text-temper-strong">
                  {step.number}
                </span>
                <h2 className="text-lg font-semibold text-text-primary sm:text-xl">{step.title}</h2>
                <p className="max-w-[52ch] text-sm leading-relaxed text-text-secondary">{step.description}</p>
              </div>
              <ScreenshotFrame src={step.imageSrc} alt={step.imageAlt} priority={i === 0} />
            </section>
          )
        })}
      </div>
    </div>
  )
}
