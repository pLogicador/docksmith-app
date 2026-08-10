import type { HTMLAttributes } from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/cn"

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      neutral: "bg-surface-2 text-text-secondary border border-border",
      temper: "bg-temper/10 text-temper-strong border border-temper/30",
      success: "bg-success/10 text-success border border-success/30",
      warning: "bg-warning/10 text-warning border border-warning/30",
      danger: "bg-danger/10 text-danger border border-danger/30",
    },
  },
  defaultVariants: { variant: "neutral" },
})

type BadgeProps = HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />
}
