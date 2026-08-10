import { createContext, useContext, useReducer, type ReactNode } from "react"
import type { ChatMessage, Collection, ModelConfig } from "./types"

export type Depth = "rapida" | "equilibrada" | "profunda"

type State = {
  sessionId: string | null
  collections: Collection[]
  activeCollectionName: string | null
  modelConfig: ModelConfig
  depth: Depth
  messagesByCollection: Record<string, ChatMessage[]>
}

type Action =
  | { type: "SET_SESSION"; sessionId: string }
  | { type: "ADD_COLLECTION"; collection: Collection }
  | { type: "SET_ACTIVE_COLLECTION"; name: string }
  | { type: "SET_MODEL_CONFIG"; config: Partial<ModelConfig> }
  | { type: "SET_DEPTH"; depth: Depth }
  | { type: "ADD_MESSAGE"; collectionName: string; message: ChatMessage }
  | { type: "CLEAR_MESSAGES"; collectionName: string }

const initialState: State = {
  sessionId: null,
  collections: [],
  activeCollectionName: null,
  modelConfig: { provider: "groq", model: null, apiKey: null },
  depth: "equilibrada",
  messagesByCollection: {},
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "SET_SESSION":
      return { ...state, sessionId: action.sessionId }
    case "ADD_COLLECTION": {
      const withoutDup = state.collections.filter((c) => c.name !== action.collection.name)
      return {
        ...state,
        collections: [...withoutDup, action.collection],
        activeCollectionName: action.collection.name,
      }
    }
    case "SET_ACTIVE_COLLECTION":
      return { ...state, activeCollectionName: action.name }
    case "SET_MODEL_CONFIG":
      return { ...state, modelConfig: { ...state.modelConfig, ...action.config } }
    case "SET_DEPTH":
      return { ...state, depth: action.depth }
    case "ADD_MESSAGE": {
      const existing = state.messagesByCollection[action.collectionName] ?? []
      return {
        ...state,
        messagesByCollection: {
          ...state.messagesByCollection,
          [action.collectionName]: [...existing, action.message],
        },
      }
    }
    case "CLEAR_MESSAGES":
      return {
        ...state,
        messagesByCollection: { ...state.messagesByCollection, [action.collectionName]: [] },
      }
    default:
      return state
  }
}

const StoreContext = createContext<{ state: State; dispatch: React.Dispatch<Action> } | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState)
  return <StoreContext.Provider value={{ state, dispatch }}>{children}</StoreContext.Provider>
}

export function useStore() {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error("useStore deve ser usado dentro de <StoreProvider>")
  return ctx
}
