import { useState, type ReactNode } from "react"
import { Menu, Settings } from "lucide-react"
import { Symbol } from "@/brand/Symbol"
import { SidebarContent } from "./Sidebar"
import { Drawer, DrawerContent, DrawerTrigger } from "@/components/ui/Drawer"
import { Button } from "@/components/ui/Button"
import { useAuthUser } from "@/features/auth/AuthGate"
import { SettingsPanel } from "@/features/settings/SettingsPanel"

export function AppShell({ children }: { children: ReactNode }) {
  const { user } = useAuthUser()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div className="flex h-screen overflow-hidden bg-bg">
      {/* Sidebar — persistente em telas >= lg */}
      <aside className="hidden w-64 shrink-0 border-r border-border lg:block">
        <SidebarContent />
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-3 sm:px-5">
          <Drawer open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
            <DrawerTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Abrir navegação">
                <Menu size={18} />
              </Button>
            </DrawerTrigger>
            <DrawerContent side="left" title="Docksmith">
              <SidebarContent onNavigate={() => setMobileNavOpen(false)} />
            </DrawerContent>
          </Drawer>

          <div className="flex items-center gap-2 lg:hidden">
            <Symbol size={20} />
            <span className="text-sm font-semibold">Docksmith</span>
          </div>

          <div className="ml-auto flex items-center gap-2 sm:gap-3">
            {user?.email && (
              <span className="hidden max-w-[14rem] truncate text-xs text-text-secondary sm:inline">
                {user.email}
              </span>
            )}
            <Drawer open={settingsOpen} onOpenChange={setSettingsOpen}>
              <DrawerTrigger asChild>
                <Button variant="secondary" size="sm">
                  <Settings size={14} />
                  <span className="hidden sm:inline">Modelo de IA</span>
                </Button>
              </DrawerTrigger>
              <DrawerContent side="right" title="Modelo de IA">
                <SettingsPanel />
              </DrawerContent>
            </Drawer>
          </div>
        </header>

        <main className="min-w-0 flex-1 overflow-y-auto scrollbar-thin">{children}</main>
      </div>
    </div>
  )
}
