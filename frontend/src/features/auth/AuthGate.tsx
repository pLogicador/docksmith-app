import { createContext, useContext, useEffect, useState, type ReactNode } from "react"
import {
  clearToken,
  getStoredToken,
  readTokenFromUrl,
  storeToken,
  stripTokenFromUrl,
  validateToken,
  type HubUser,
} from "@/lib/auth"
import { Symbol } from "@/brand/Symbol"
import { HUB_URL } from "@/lib/env"

type AuthStatus = "checking" | "authenticated" | "unauthenticated" | "expired"

type AuthContextValue = {
  user: HubUser | null
  status: AuthStatus
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function useAuthUser() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuthUser deve ser usado dentro de <AuthGate>")
  return ctx
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("checking")
  const [user, setUser] = useState<HubUser | null>(null)

  useEffect(() => {
    let cancelled = false

    async function run() {
      // Bypass só para desenvolvimento local (QA visual sem precisar de um
      // token real do Hub). Nunca fica true em build de produção/Vercel.
      if (import.meta.env.VITE_DEV_BYPASS_AUTH === "true") {
        storeToken("dev-bypass-token")
        setUser({ id: "dev", email: "dev@docksmith.local" })
        setStatus("authenticated")
        return
      }

      const urlToken = readTokenFromUrl()
      if (urlToken) {
        storeToken(urlToken)
        stripTokenFromUrl()
      }

      const token = urlToken ?? getStoredToken()
      if (!token) {
        if (!cancelled) setStatus("unauthenticated")
        return
      }

      const validated = await validateToken(token)
      if (cancelled) return

      if (!validated) {
        clearToken()
        setStatus("expired")
        return
      }

      setUser(validated)
      setStatus("authenticated")
    }

    run()
    return () => {
      cancelled = true
    }
  }, [])

  if (status === "checking") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-bg text-text-primary">
        <Symbol size={40} className="animate-pulse text-text-secondary" />
        <p className="text-sm text-text-secondary">Verificando acesso…</p>
      </div>
    )
  }

  if (status === "unauthenticated" || status === "expired") {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-bg px-6 text-center text-text-primary">
        <Symbol size={48} />
        <div className="max-w-sm space-y-2">
          <h1 className="text-lg font-semibold">
            {status === "expired" ? "Sessão expirada" : "Faça login pelo Hub"}
          </h1>
          <p className="text-sm text-text-secondary">
            {status === "expired"
              ? "Seu acesso expirou. Volte ao Hub e abra o Docksmith novamente."
              : "O Docksmith é acessado através do Hub Syncron. Entre na sua conta e abra o Docksmith por lá."}
          </p>
        </div>
        <a
          href={HUB_URL}
          className="rounded-lg bg-temper px-5 py-2.5 text-sm font-medium text-temper-foreground transition hover:opacity-90"
        >
          Ir para o Hub
        </a>
      </div>
    )
  }

  return <AuthContext.Provider value={{ user, status }}>{children}</AuthContext.Provider>
}
