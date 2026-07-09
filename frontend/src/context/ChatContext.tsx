import { createContext, useContext, type ReactNode } from 'react'
import { useChat } from '../hooks/useChat'

interface ChatContextValue {
  sendMessage: (text: string, displayText?: string) => void
}

const ChatContext = createContext<ChatContextValue | null>(null)

/**
 * ChatProvider garante que useChat() seja instanciado uma única vez na árvore.
 * Isso evita que componentes como ArtifactPanel criem conexões WebSocket extras.
 */
export function ChatProvider({ children }: { children: ReactNode }) {
  const { sendMessage } = useChat()
  return (
    <ChatContext.Provider value={{ sendMessage }}>
      {children}
    </ChatContext.Provider>
  )
}

export function useChatContext(): ChatContextValue {
  const ctx = useContext(ChatContext)
  if (!ctx) throw new Error('useChatContext deve ser usado dentro de <ChatProvider>')
  return ctx
}
