/**
 * AgentWorkspace.tsx — Workspace Multi-Agentes de 3 Colunas (F8.3.1)
 *
 * Coluna 1: Roster de Bots Especialistas e Rotinas
 * Coluna 2: Chat e Canal de Tarefas do Bot Ativo
 * Coluna 3: Sandbox do Computador (nexus_computer) e Ações ao Vivo
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
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { BotRosterList } from './BotRosterList'
import { ComputerActionBlock, type ActionLogItem } from './ComputerActionBlock'
import { CreateBotModal } from './CreateBotModal'
import { PetAvatar } from '../mascot/PetAvatar'
import { markdownComponents } from '../markdownComponents'
import { api } from '../../api/client'
import type { ProactiveBot, ProactiveRoutine, MascotId } from '../../types'

interface AgentMessage {
  id: string
  sender: 'user' | 'bot'
  text: string
  timestamp: string
}

export const AgentWorkspace: React.FC = () => {
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
  const [actionLogs, setActionLogs] = useState<ActionLogItem[]>([
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
  ])
  const chatBottomRef = useRef<HTMLDivElement>(null)

  // Carrega bots e rotinas
  const loadData = async () => {
    setIsLoading(true)
    try {
      const botsRes = await api.getProactiveBots()
      if (botsRes.ok && botsRes.bots.length > 0) {
        setBots(botsRes.bots)
        if (!selectedBot) {
          setSelectedBot(botsRes.bots[0])
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

  // Inicializa mensagens de boas-vindas do bot ativo
  useEffect(() => {
    if (selectedBot) {
      setMessages([
        {
          id: 'welcome-1',
          sender: 'bot',
          text: `Olá! Sou o **${selectedBot.name}** (${selectedBot.title || 'Especialista'}). Estou pronto para operar no sandbox ou pesquisar tópicos para você. O que vamos executar agora?`,
          timestamp: 'Agora',
        },
      ])
    }
  }, [selectedBot])

  // Auto-scroll para o fim do chat
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isSending])

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
        setMessages((prev) => [...prev, replyMsg])

        if (res.actions && res.actions.length > 0) {
          setActionLogs((prev) => [...(res.actions as ActionLogItem[]), ...prev])
        }
        if (res.current_url) {
          setCurrentUrl(res.current_url)
        }
        if (res.page_title) {
          setPageTitle(res.page_title)
        }
      }
    } catch (err) {
      console.error('[AgentWorkspace] erro ao interagir com o bot:', err)
      const errorMsg: AgentMessage = {
        id: `bot-err-${Date.now()}`,
        sender: 'bot',
        text: 'Desculpe, tive uma oscilação na conexão com o modelo ou com o sandbox de navegação. Por favor, tente novamente.',
        timestamp: 'Agora',
      }
      setMessages((prev) => [...prev, errorMsg])
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
      }
    } catch (e) {
      console.error('[AgentWorkspace] erro ao deletar bot:', e)
    }
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '270px 1fr 330px',
        height: '100vh',
        width: '100%',
        background: 'var(--surface-soft)',
        overflow: 'hidden',
      }}
    >
      {/* ─── COLUNA 1: ROSTER DE BOTS & ROTINAS ─── */}
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ flex: 1, minHeight: 0 }}>
          <BotRosterList
            bots={bots}
            selectedBotId={selectedBot?.id || null}
            onSelectBot={(bot) => setSelectedBot(bot)}
            onOpenCreateModal={() => setIsCreateModalOpen(true)}
            onDeleteBot={handleDeleteBot}
          />
        </div>

        {/* Seção de Rotinas Agendadas */}
        <div
          style={{
            height: 180,
            borderTop: '1px solid var(--hairline)',
            borderRight: '1px solid var(--hairline)',
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

      {/* ─── COLUNA 2: CHAT DO BOT ESPECIALISTA ─── */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
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
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <div
                style={{
                  width: 36,
                  height: 36,
                  borderRadius: 8,
                  backgroundColor: `${selectedBot.color_hex}25`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <PetAvatar
                  mascotId={(selectedBot.mascot_id as MascotId) || 'nex'}
                  size={32}
                  state="idle"
                  trackPointer={false}
                />
              </div>
              <div>
                <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--ink)' }}>
                  {selectedBot.name}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--ink-muted)' }}>
                  {selectedBot.title || 'Especialista em Execução Autônoma'}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', gap: 6 }}>
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
                Pronto para tarefas
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
                    maxWidth: '80%',
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

      {/* ─── COLUNA 3: SANDBOX DO COMPUTADOR ─── */}
      <div style={{ height: '100%', minHeight: 0 }}>
        <ComputerActionBlock
          activeBot={selectedBot}
          currentUrl={currentUrl}
          pageTitle={pageTitle}
          logs={actionLogs}
          onLogsChange={setActionLogs}
          onUrlChange={setCurrentUrl}
        />
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
