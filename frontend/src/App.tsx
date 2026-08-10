import { Routes, Route } from "react-router-dom"
import { AuthGate } from "@/features/auth/AuthGate"
import { StoreProvider } from "@/lib/store"
import { AppShell } from "@/components/layout/AppShell"
import { WorkspacePage } from "@/features/workspace/WorkspacePage"
import { ChatPage } from "@/features/chat/ChatPage"
import { HowItWorksPage } from "@/features/how-it-works/HowItWorksPage"

function App() {
  return (
    <AuthGate>
      <StoreProvider>
        <AppShell>
          <Routes>
            <Route path="/" element={<WorkspacePage />} />
            <Route path="/chat/:collectionName" element={<ChatPage />} />
            <Route path="/como-funciona" element={<HowItWorksPage />} />
          </Routes>
        </AppShell>
      </StoreProvider>
    </AuthGate>
  )
}

export default App
