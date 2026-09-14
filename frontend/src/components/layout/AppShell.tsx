import { useState, type ReactNode } from "react"
import { Menu, Settings } from "lucide-react"
import { Symbol } from "@/brand/Symbol"
import { SidebarContent } from "./Sidebar"
import { Drawer, DrawerContent, DrawerTrigger } from "@/components/ui/Drawer"
import { Button } from "@/components/ui/Button"
import { useAuthUser } from "@/features/auth/AuthGate"
import { SettingsPanel } from "@/features/settings/SettingsPanel"
import { HUB_URL } from "@/lib/env"

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
            <span className="font-display text-sm font-semibold">Docksmith</span>
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

        <main className="min-w-0 flex-1 overflow-y-auto scrollbar-thin">
          {children}

          {/* Rodapé padronizado com o Hub (mesma estrutura/lógica de
              navegação já aplicada no Live Scheduler, FlexiPage, AgenteOS e
              ANZ Finance). Vive DENTRO de <main>, depois de {children}, e
              não como uma barra fixa do shell: este layout é
              h-screen/overflow-hidden com <main> como única área rolável,
              então um rodapé fixo comeria espaço útil de tela em toda
              conversa/documento. Aqui ele só aparece ao rolar até o fim do
              conteúdo real, como qualquer rodapé de página normal. */}
          <footer className="border-t border-border">
            <div className="mx-auto flex max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6 md:flex-row md:justify-between">
              <div className="max-w-xs">
                <div className="flex items-center gap-2">
                  <Symbol size={20} />
                  <span className="text-sm font-semibold text-text-primary">Docksmith</span>
                </div>
                <p className="mt-2 text-xs text-text-secondary">
                  Converse com seus documentos, parte do ecossistema Syncron.
                </p>
              </div>

              <div className="flex gap-10 text-xs">
                <div className="flex flex-col gap-2">
                  <span className="font-semibold uppercase tracking-wide text-text-secondary">Ecossistema</span>
                  <a
                    href={`${HUB_URL}/`}
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    Acessar o Syncron
                  </a>
                  <a
                    href={`${HUB_URL}/app/services/`}
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    Minhas ferramentas
                  </a>
                </div>
                <div className="flex flex-col gap-2">
                  <span className="font-semibold uppercase tracking-wide text-text-secondary">Suporte</span>
                  <a
                    href="mailto:pedrologicador@gmail.com"
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    Falar com suporte
                  </a>
                  <a
                    href={`${HUB_URL}/legal/privacy/`}
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    Privacidade
                  </a>
                  <a
                    href={`${HUB_URL}/legal/terms/`}
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    Termos de Uso
                  </a>
                  <a
                    href={`${HUB_URL}/legal/cookies/`}
                    className="text-text-secondary transition-colors hover:text-text-primary"
                  >
                    Cookies
                  </a>
                </div>
              </div>
            </div>
          </footer>
        </main>
      </div>
    </div>
  )
}
