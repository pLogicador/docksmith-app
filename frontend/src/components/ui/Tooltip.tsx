import * as TooltipPrimitive from "@radix-ui/react-tooltip"
import { cn } from "@/lib/cn"

export const TooltipProvider = TooltipPrimitive.Provider
export const Tooltip = TooltipPrimitive.Root
export const TooltipTrigger = TooltipPrimitive.Trigger

export function TooltipContent({
  className,
  sideOffset = 6,
  ...props
}: React.ComponentProps<typeof TooltipPrimitive.Content>) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Content
        sideOffset={sideOffset}
        className={cn(
          "z-50 max-w-xs rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs leading-relaxed text-text-secondary shadow-lg animate-msg-in",
          className,
        )}
        {...props}
      />
    </TooltipPrimitive.Portal>
  )
}
