import { NavLink } from "react-router-dom"
import { FolderOpen, HelpCircle, Plus } from "lucide-react"
import { useStore } from "@/lib/store"
import { cn } from "@/lib/cn"
import { Symbol } from "@/brand/Symbol"

export function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { state } = useStore()

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2.5 px-4 py-5">
        <Symbol size={26} />
        <div>
          <p className="text-sm font-semibold leading-none text-text-primary">Docksmith</p>
          <p className="mt-1 text-[11px] leading-none text-text-tertiary">Extração de conhecimento</p>
        </div>
      </div>

      <nav className="flex flex-col gap-1 px-3">
        <NavLink
          to="/"
          onClick={onNavigate}
          end
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
              isActive ? "bg-surface-2 text-text-primary" : "text-text-secondary hover:bg-surface-2 hover:text-text-primary",
            )
          }
        >
          <Plus size={16} />
          Nova extração
        </NavLink>

        <NavLink
          to="/como-funciona"
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition",
              isActive ? "bg-surface-2 text-text-primary" : "text-text-secondary hover:bg-surface-2 hover:text-text-primary",
            )
          }
        >
          <HelpCircle size={16} />
          Como funciona
        </NavLink>
      </nav>

      <div className="mt-5 flex-1 overflow-y-auto scrollbar-thin px-3">
        <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wide text-text-tertiary">
          Coleções da sessão
        </p>
        {state.collections.length === 0 ? (
          <p className="px-3 py-2 text-xs text-text-tertiary">
            Nenhuma coleção ainda. Faça uma extração para começar.
          </p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {state.collections.map((collection) => (
              <li key={collection.name}>
                <NavLink
                  to={`/chat/${encodeURIComponent(collection.name)}`}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
                      isActive
                        ? "bg-surface-2 text-text-primary"
                        : "text-text-secondary hover:bg-surface-2 hover:text-text-primary",
                    )
                  }
                >
                  <FolderOpen size={15} className="shrink-0 text-text-tertiary" />
                  <span className="truncate">{collection.name}</span>
                  <span className="ml-auto shrink-0 text-[11px] text-text-tertiary">
                    {collection.documentCount}
                  </span>
                </NavLink>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-border px-4 py-3">
        <p className="text-[11px] text-text-tertiary">
          Coleções ficam apenas na memória desta sessão — nada é salvo em disco.
        </p>
      </div>
    </div>
  )
}
