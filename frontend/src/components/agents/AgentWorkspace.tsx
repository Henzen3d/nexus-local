/**
 * AgentWorkspace.tsx — Workspace Multi-Agentes (F8.3.1)
 *
 * Suporte completo a Desktop (3 Colunas) e Mobile (Tabs Responsivas):
 * Coluna 1: Roster de Bots Especialistas e Rotinas
 * Coluna 2: Chat e Canal de Tarefas do Bot Ativo com persistência per-bot
 * Coluna 3: Sandbox do Computador (nexus_computer) com Snapshot real e logs
 */
import React, { useState, useEffect, useRef } from 'react'
import {
  Bot,
  Send,
  Plus,
  Clock,
  Sparkles,
  Shield,
  Activity,
  Play,
  CheckCircle,
  AlertCircle,
  RotateCcw,
  Globe,
  MessageSquare,
  Users,
  ArrowLeft,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BotRosterList } from './BotRosterList'
import { ComputerActionBlock, type ActionLogItem } from './ComputerActionBlock'
import { CreateBotModal } from './CreateBotModal'
import { PetAvatar } from '../mascot/PetAvatar'
import { markdownComponents } from '../markdownComponents'
import { api } from '../../api/client'
import { useStore } from '../../store/useStore'
import type { ProactiveBot, ProactiveRoutine, MascotId } from '../../types'

interface AgentMessage {
  id: string
  sender: 'user' | 'bot'
  text: string
  timestamp: string
}

interface BotChatState {
  messages: AgentMessage[]
  actionLogs: ActionLogItem[]
  currentUrl: string
  pageTitle: string
  screenshotUrl?: string
}

function getStoredBotState(bot: ProactiveBot): BotChatState {
  try {
    const raw = localStorage.getItem(`nexus_agent_bot_state_${bot.id}`)
    if (raw) {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed.messages) && parsed.messages.length > 0) {
        return parsed
      }
    }
  } catch (e) {
    /* ignore */
  }
  return {
    messages: [
      {
        id: `welcome-${bot.id}`,
        sender: 'bot',
        text: `Olá! Sou o **${bot.name}** (${bot.title || 'Especialista'}). Estou pronto para operar no sandbox ou pesquisar tópicos para você. O que vamos executar agora?`,
        timestamp: 'Agora',
      },
    ],
    actionLogs: [
      {
        id: 'log-1',
        action: 'navigate',
        target: 'https://news.ycombinator.com',
        status: 'success',
        latencyMs: 142,
        time: 'Agora há pouco',
      },
      {
        id: 'log-2',
        action: 'extract_dom',
        target: '30 itens de notícias',
        status: 'success',
        latencyMs: 48,
        time: 'Agora há pouco',
      },
    ],
    currentUrl: 'https://news.ycombinator.com',
    pageTitle: '',
    screenshotUrl: undefined,
  }
}

function persistBotState(botId: string, state: Partial<BotChatState>) {
  try {
    const existingRaw = localStorage.getItem(`nexus_agent_bot_state_${botId}`)
    const existing: BotChatState = existingRaw ? JSON.parse(existingRaw) : {
      messages: [],
      actionLogs: [],
      currentUrl: 'https://news.ycombinator.com',
      pageTitle: '',
    }
    const merged = { ...existing, ...state }
    localStorage.setItem(`nexus_agent_bot_state_${botId}`, JSON.stringify(merged))
  } catch (e) {
    /* ignore */
  }
}

export const AgentWorkspace: React.FC = () => {
  const setView = useStore((s) => s.setView)
  const [bots, setBots] = useState<ProactiveBot[]>([])
  const [selectedBot, setSelectedBot] = useState<ProactiveBot | null>(null)
  const [routines, setRoutines] = useState<ProactiveRoutine[]>([])
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [inputMessage, setInputMessage] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [currentUrl, setCurrentUrl] = useState('https://news.ycombinator.com')
  const [pageTitle, setPageTitle] = useState('')
  const [screenshotUrl, setScreenshotUrl] = useState<string | undefined>()
  const [actionLogs, setActionLogs] = useState<ActionLogItem[]>([])
  const [mobileTab, setMobileTab] = useState<'roster' | 'chat' | 'sandbox'>('chat')
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' ? window.innerWidth <= 768 : false)

  const chatBottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Carrega bots e rotinas
  const loadData = async () => {
    setIsLoading(true)
    try {
      const botsRes = await api.getProactiveBots()
      if (botsRes.ok && botsRes.bots.length > 0) {
        setBots(botsRes.bots)
        if (!selectedBot) {
          // Restaura último bot ativo se existir em localStorage
          const lastBotId = localStorage.getItem('nexus_agent_last_selected_bot')
          const found = lastBotId ? botsRes.bots.find((b) => b.id === lastBotId) : null
          setSelectedBot(found || botsRes.bots[0])
        }
      }

      const routinesRes = await api.getProactiveRoutines()
      if (routinesRes.ok) {
        setRoutines(routinesRes.routines)
      }
    } catch (e) {
      console.error('[AgentWorkspace] erro ao carregar bots:', e)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
  }, [])

  // Carrega estado persistido (mensagens, logs, URL) quando o bot selecionado muda
  useEffect(() => {
    if (selectedBot) {
      localStorage.setItem('nexus_agent_last_selected_bot', selectedBot.id)
      const stored = getStoredBotState(selectedBot)
      setMessages(stored.messages)
      setActionLogs(stored.actionLogs)
      setCurrentUrl(stored.currentUrl || 'https://news.ycombinator.com')
      setPageTitle(stored.pageTitle || '')
      setScreenshotUrl(stored.screenshotUrl)
    }
  }, [selectedBot?.id])

  // Auto-scroll para o fim do chat
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isSending])

  const handleUpdateLogs = (newLogs: ActionLogItem[]) => {
    setActionLogs(newLogs)
    if (selectedBot?.id) {
      persistBotState(selectedBot.id, { actionLogs: newLogs })
    }
  }

  const handleUpdateUrl = (newUrl: string) => {
    setCurrentUrl(newUrl)
    if (selectedBot?.id) {
      persistBotState(selectedBot.id, { currentUrl: newUrl })
    }
  }

  const handleUpdateScreenshot = (url: string) => {
    setScreenshotUrl(url)
    if (selectedBot?.id) {
      persistBotState(selectedBot.id, { screenshotUrl: url })
    }
  }

  const handleClearChat = () => {
    if (!selectedBot) return
    const resetWelcome: AgentMessage = {
      id: `welcome-${selectedBot.id}-${Date.now()}`,
      sender: 'bot',
      text: `Olá! Sou o **${selectedBot.name}** (${selectedBot.title || 'Especialista'}). Histórico limpo! O que vamos pesquisar ou executar agora?`,
      timestamp: 'Agora',
    }
    const resetLogs: ActionLogItem[] = []
    setMessages([resetWelcome])
    setActionLogs(resetLogs)
    persistBotState(selectedBot.id, {
      messages: [resetWelcome],
      actionLogs: resetLogs,
    })
  }

  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputMessage.trim() || !selectedBot || isSending) return

    const userText = inputMessage.trim()
    setInputMessage('')

    const userMsg: AgentMessage = {
      id: `usr-${Date.now()}`,
      sender: 'user',
      text: userText,
      timestamp: 'Agora',
    }

    const updated = [...messages, userMsg]
    setMessages(updated)
    persistBotState(selectedBot.id, { messages: updated })
    setIsSending(true)

    try {
      const history = updated
        .slice(0, -1)
        .map((m) => ({ sender: m.sender, text: m.text }))

      const res = await api.chatProactiveBot(selectedBot.id, userText, history)
      if (res.ok) {
        const replyMsg: AgentMessage = {
          id: `bot-${Date.now()}`,
          sender: 'bot',
          text: res.reply,
          timestamp: 'Agora',
        }
        const withReply = [...updated, replyMsg]
        setMessages(withReply)

        let nextLogs = actionLogs
        if (res.actions && res.actions.length > 0) {
          nextLogs = [...(res.actions as ActionLogItem[]), ...actionLogs]
          setActionLogs(nextLogs)
        }
        const nextUrl = res.current_url || currentUrl
        const nextTitle = res.page_title || pageTitle
        if (res.current_url) setCurrentUrl(nextUrl)
        if (res.page_title) setPageTitle(nextTitle)

        persistBotState(selectedBot.id, {
          messages: withReply,
          actionLogs: nextLogs,
          currentUrl: nextUrl,
          pageTitle: nextTitle,
        })
      }
    } catch (err) {
      console.error('[AgentWorkspace] erro ao interagir com o bot:', err)
      const errorMsg: AgentMessage = {
        id: `bot-err-${Date.now()}`,
        sender: 'bot',
        text: 'Desculpe, tive uma oscilação na conexão com o modelo ou com o sandbox de navegação. Por favor, tente novamente.',
        timestamp: 'Agora',
      }
      const withErr = [...updated, errorMsg]
      setMessages(withErr)
      persistBotState(selectedBot.id, { messages: withErr })
    } finally {
      setIsSending(false)
    }
  }

  const handleCreateBot = async (data: Partial<ProactiveBot>) => {
    try {
      const res = await api.createProactiveBot(data)
      if (res.ok && res.bot) {
        setBots((prev) => [...prev, res.bot])
        setSelectedBot(res.bot)
        if (isMobile) setMobileTab('chat')
      }
    } catch (e) {
      console.error('[AgentWorkspace] erro ao criar bot:', e)
    }
  }

  const handleDeleteBot = async (botId: string) => {
    try {
      const res = await api.deleteProactiveBot(botId)
      if (res.ok) {
        setBots((prev) => {
          const next = prev.filter((b) => b.id !== botId)
          if (selectedBot?.id === botId && next.length > 0) {
            setSelectedBot(next[0])
          }
          return next
        })
        localStorage.removeItem(`nexus_agent_bot_state_${botId}`)
      }
    } catch (e) {
      console.error('[AgentWorkspace] erro ao deletar bot:', e)
    }
  }

  // Subcomponente: Coluna 1 (Roster de Bots)
  const renderRosterColumn = () => (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ flex: 1, minHeight: 0 }}>
        <BotRosterList
          bots={bots}
          selectedBotId={selectedBot?.id || null}
          onSelectBot={(bot) => {
            setSelectedBot(bot)
            if (isMobile) setMobileTab('chat')
          }}
          onOpenCreateModal={() => setIsCreateModalOpen(true)}
          onDeleteBot={handleDeleteBot}
        />
      </div>

      {/* Seção de Rotinas Agendadas */}
      <div
        style={{
          height: 180,
          borderTop: '1px solid var(--hairline)',
          borderRight: isMobile ? 'none' : '1px solid var(--hairline)',
          background: 'var(--surface)',
          padding: '0.75rem',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 6,
          }}
        >
          <span style={{ fontSize: '0.8rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6 }}>
            <Clock size={13} color="var(--primary)" />
            Rotinas Agendadas ({routines.length})
          </span>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 4 }}>
          {routines.map((r) => (
            <div
              key={r.id}
              style={{
                padding: '4px 8px',
                borderRadius: 6,
                background: 'var(--surface-soft)',
                fontSize: '0.75rem',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {r.name}
              </span>
              <span
                style={{
                  fontSize: '0.65rem',
                  padding: '1px 4px',
                  borderRadius: 4,
                  background: 'rgba(59, 130, 246, 0.1)',
                  color: '#3B82F6',
                }}
              >
                {r.timing_value}
              </span>
            </div>
          ))}
          {routines.length === 0 && (
            <div style={{ fontSize: '0.72rem', color: 'var(--ink-muted)', textAlign: 'center', marginTop: 16 }}>
              Nenhuma rotina periódica ativa
            </div>
          )}
        </div>
      </div>
    </div>
  )

  // Subcomponente: Coluna 2 (Chat do Bot)
  const renderChatColumn = () => (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        minHeight: 0,
        background: 'var(--surface)',
      }}
    >
      {/* Cabeçalho do Chat */}
      {selectedBot ? (
        <div
          style={{
            padding: '0.85rem 1.25rem',
            borderBottom: '1px solid var(--hairline)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--surface)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 8,
                backgroundColor: `${selectedBot.color_hex}25`,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
              }}
            >
              <PetAvatar
                mascotId={(selectedBot.mascot_id as MascotId) || 'nex'}
                size={32}
                state="idle"
                trackPointer={false}
              />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--ink)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {selectedBot.name}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {selectedBot.title || 'Especialista em Execução Autônoma'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexShrink: 0 }}>
            <button
              type="button"
              onClick={handleClearChat}
              style={{
                fontSize: '0.72rem',
                padding: '3px 8px',
                borderRadius: 8,
                border: '1px solid var(--hairline)',
                background: 'var(--surface-soft)',
                color: 'var(--ink-muted)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
              title="Limpar histórico deste assistente"
            >
              <RotateCcw size={11} />
              <span>Limpar</span>
            </button>
            <span
              style={{
                fontSize: '0.72rem',
                padding: '3px 8px',
                borderRadius: 12,
                background: 'rgba(16, 185, 129, 0.1)',
                color: '#10B981',
                display: 'flex',
                alignItems: 'center',
                gap: 4,
              }}
            >
              <Activity size={12} />
              <span>Pronto</span>
            </span>
          </div>
        </div>
      ) : (
        <div style={{ padding: '1rem', borderBottom: '1px solid var(--hairline)' }}>
          Selecione um bot especialista
        </div>
      )}

      {/* Mensagens do Chat */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '1.25rem',
          display: 'flex',
          flexDirection: 'column',
          gap: '1rem',
        }}
      >
        {messages.map((m) => {
          const isUser = m.sender === 'user'
          return (
            <div
              key={m.id}
              style={{
                display: 'flex',
                justifyContent: isUser ? 'flex-end' : 'flex-start',
              }}
            >
              <div
                style={{
                  maxWidth: isMobile ? '90%' : '80%',
                  padding: '0.75rem 1rem',
                  borderRadius: 12,
                  background: isUser ? 'var(--primary)' : 'var(--surface-soft)',
                  color: isUser ? '#fff' : 'var(--ink)',
                  fontSize: '0.85rem',
                  lineHeight: 1.5,
                  border: isUser ? 'none' : '1px solid var(--hairline)',
                }}
              >
                <div style={{ wordBreak: 'break-word' }}>
                  {isUser ? (
                    <div>{m.text}</div>
                  ) : (
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                      {m.text}
                    </ReactMarkdown>
                  )}
                </div>
                <div
                  style={{
                    fontSize: '0.65rem',
                    opacity: 0.7,
                    textAlign: 'right',
                    marginTop: 4,
                  }}
                >
                  {m.timestamp}
                </div>
              </div>
            </div>
          )
        })}
        {isSending && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.8rem', color: 'var(--ink-muted)' }}>
            <Sparkles size={14} className="spin-slow" />
            <span>{selectedBot?.name} está investigando no computador sandbox...</span>
          </div>
        )}
        <div ref={chatBottomRef} />
      </div>

      {/* Input Bar */}
      <form
        onSubmit={handleSendMessage}
        style={{
          padding: '1rem',
          borderTop: '1px solid var(--hairline)',
          display: 'flex',
          gap: 10,
        }}
      >
        <input
          type="text"
          value={inputMessage}
          onChange={(e) => setInputMessage(e.target.value)}
          placeholder={`Peça uma pesquisa ou ação para ${selectedBot?.name || 'o especialista'}...`}
          style={{
            flex: 1,
            padding: '10px 14px',
            borderRadius: 8,
            border: '1px solid var(--hairline)',
            background: 'var(--surface-soft)',
            color: 'var(--ink)',
            fontSize: '0.88rem',
            outline: 'none',
          }}
        />
        <button
          type="submit"
          className="settings-primary-btn"
          disabled={!inputMessage.trim() || isSending}
          style={{
            padding: '0 16px',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            backgroundColor: selectedBot?.color_hex || 'var(--primary)',
          }}
        >
          <Send size={15} />
          <span>Enviar</span>
        </button>
      </form>
    </div>
  )

  // Subcomponente: Coluna 3 (Sandbox do Computador)
  const renderSandboxColumn = () => (
    <div style={{ height: '100%', minHeight: 0 }}>
      <ComputerActionBlock
        activeBot={selectedBot}
        currentUrl={currentUrl}
        pageTitle={pageTitle}
        screenshotUrl={screenshotUrl}
        logs={actionLogs}
        onLogsChange={handleUpdateLogs}
        onUrlChange={handleUpdateUrl}
        onScreenshotChange={handleUpdateScreenshot}
      />
    </div>
  )

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        width: '100%',
        background: 'var(--surface-soft)',
        overflow: 'hidden',
      }}
    >
      {/* Barra de Abas no Mobile */}
      {isMobile && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            background: 'var(--surface)',
            borderBottom: '1px solid var(--hairline)',
            padding: '4px 8px',
            gap: 6,
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            onClick={() => setView('chat')}
            style={{
              padding: '8px 8px',
              borderRadius: 8,
              border: 'none',
              background: 'transparent',
              color: 'var(--ink-muted)',
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              cursor: 'pointer',
              flexShrink: 0,
            }}
            title="Voltar ao Chat"
            aria-label="Voltar ao Chat"
          >
            <ArrowLeft size={16} />
          </button>
          <button
            type="button"
            onClick={() => setMobileTab('roster')}
            style={{
              flex: 1,
              padding: '8px 4px',
              borderRadius: 8,
              border: 'none',
              background: mobileTab === 'roster' ? 'var(--surface-soft)' : 'transparent',
              color: mobileTab === 'roster' ? 'var(--primary)' : 'var(--ink-muted)',
              fontWeight: mobileTab === 'roster' ? 600 : 400,
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
              cursor: 'pointer',
            }}
          >
            <Users size={13} />
            <span>Bots ({bots.length})</span>
          </button>
          <button
            type="button"
            onClick={() => setMobileTab('chat')}
            style={{
              flex: 1,
              padding: '8px 4px',
              borderRadius: 8,
              border: 'none',
              background: mobileTab === 'chat' ? 'var(--surface-soft)' : 'transparent',
              color: mobileTab === 'chat' ? 'var(--primary)' : 'var(--ink-muted)',
              fontWeight: mobileTab === 'chat' ? 600 : 400,
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
              cursor: 'pointer',
            }}
          >
            <MessageSquare size={13} />
            <span>Chat</span>
          </button>
          <button
            type="button"
            onClick={() => setMobileTab('sandbox')}
            style={{
              flex: 1,
              padding: '8px 4px',
              borderRadius: 8,
              border: 'none',
              background: mobileTab === 'sandbox' ? 'var(--surface-soft)' : 'transparent',
              color: mobileTab === 'sandbox' ? 'var(--primary)' : 'var(--ink-muted)',
              fontWeight: mobileTab === 'sandbox' ? 600 : 400,
              fontSize: '0.78rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 4,
              cursor: 'pointer',
            }}
          >
            <Globe size={13} />
            <span>Sandbox</span>
          </button>
        </div>
      )}

      {/* Conteúdo: Mobile (1 Coluna por aba) ou Desktop (3 Colunas) */}
      <div style={{ flex: 1, minHeight: 0, width: '100%' }}>
        {isMobile ? (
          <div style={{ height: '100%', width: '100%' }}>
            {mobileTab === 'roster' && renderRosterColumn()}
            {mobileTab === 'chat' && renderChatColumn()}
            {mobileTab === 'sandbox' && renderSandboxColumn()}
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '270px 1fr 330px',
              height: '100%',
              width: '100%',
            }}
          >
            {renderRosterColumn()}
            {renderChatColumn()}
            {renderSandboxColumn()}
          </div>
        )}
      </div>

      {/* Modal de Criação de Bot */}
      <CreateBotModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        onSave={handleCreateBot}
      />
    </div>
  )
}
