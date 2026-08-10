import * as DialogPrimitive from "@radix-ui/react-dialog"
import { X } from "lucide-react"
import { cn } from "@/lib/cn"

export const Drawer = DialogPrimitive.Root
export const DrawerTrigger = DialogPrimitive.Trigger

type DrawerContentProps = React.ComponentProps<typeof DialogPrimitive.Content> & {
  side?: "left" | "right" | "bottom"
  title: string
}

const sideClasses: Record<NonNullable<DrawerContentProps["side"]>, string> = {
  left: "inset-y-0 left-0 h-full w-[85vw] max-w-xs data-[state=open]:[animation:panel-in-left_180ms_ease-out]",
  right: "inset-y-0 right-0 h-full w-[92vw] max-w-md data-[state=open]:[animation:panel-in-right_180ms_ease-out]",
  bottom: "inset-x-0 bottom-0 max-h-[85vh] w-full rounded-t-2xl data-[state=open]:[animation:panel-in-bottom_180ms_ease-out]",
}

export function DrawerContent({ className, children, side = "right", title, ...props }: DrawerContentProps) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-black/50 data-[state=open]:[animation:overlay-in_150ms_ease-out]" />
      <DialogPrimitive.Content
        className={cn(
          "fixed z-50 flex flex-col bg-surface shadow-xl focus:outline-none",
          sideClasses[side],
          className,
        )}
        {...props}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
          <DialogPrimitive.Title className="text-sm font-semibold text-text-primary">{title}</DialogPrimitive.Title>
          <DialogPrimitive.Close className="rounded-md p-1.5 text-text-secondary hover:bg-surface-2 hover:text-text-primary">
            <X size={16} />
          </DialogPrimitive.Close>
        </div>
        <div className="flex-1 overflow-y-auto scrollbar-thin">{children}</div>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}
