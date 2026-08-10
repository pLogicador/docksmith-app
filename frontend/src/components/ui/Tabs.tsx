import * as TabsPrimitive from "@radix-ui/react-tabs"
import { cn } from "@/lib/cn"

export const Tabs = TabsPrimitive.Root

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn(
        "flex gap-1 overflow-x-auto rounded-lg bg-surface-2 p-1 scrollbar-thin",
        className,
      )}
      {...props}
    />
  )
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "shrink-0 rounded-md px-3 py-1.5 text-xs font-medium text-text-secondary transition",
        "data-[state=active]:bg-surface data-[state=active]:text-text-primary data-[state=active]:shadow-sm",
        "hover:text-text-primary",
        className,
      )}
      {...props}
    />
  )
}

export function TabsContent({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={cn("mt-3 outline-none", className)} {...props} />
}
