import { useEffect, useRef } from 'react'
import { PanelLeftOpen, Code2, BookOpen, Pencil, Lightbulb, Dna } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { MessageBubble, StreamingBubble } from './MessageBubble'
import { MessageInput } from './MessageInput'
import { ProviderSelector } from './ProviderSelector'
import { FusionStatusCard } from './FusionStatusCard'
import { useChatContext } from '../context/ChatContext'

function getGreetingKey() {
  const h = new Date().getHours()
  if (h >= 5 && h < 12) return 'chat.greetingMorning'
  if (h >= 12 && h < 18) return 'chat.greetingAfternoon'
  return 'chat.greetingEvening'
}

export function ChatWindow() {
  const { t } = useTranslation()
  const { messages, streamingContent, isStreaming, sidebarOpen, setSidebarOpen, fusionMode, setFusionMode, fusionActive, displayName } = useStore()
  const { sendMessage } = useChatContext()
  const messagesAreaRef = useRef<HTMLDivElement>(null)
  const bottomSentinelRef = useRef<HTMLDivElement>(null)
  const prevMessagesLength = useRef(messages.length)

  const name = displayName || t('common.user')

  useEffect(() => {
    const container = messagesAreaRef.current
    if (!container) return

    const messageCountChanged = messages.length !== prevMessagesLength.current
    prevMessagesLength.current = messages.length

    if (messageCountChanged) {
      container.scrollTop = container.scrollHeight
      return
    }

    const threshold = 180
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold

    if (isNearBottom && bottomSentinelRef.current) {
      bottomSentinelRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }
  }, [messages, streamingContent])

  const isEmpty = messages.length === 0 && !isStreaming

  const chips = [
    {
      label: t('chat.chipWrite'),
      Icon: Pencil,
      prompt: t('chat.chipWritePrompt'),
    },
    {
      label: t('chat.chipLearn'),
      Icon: BookOpen,
      prompt: t('chat.chipLearnPrompt'),
    },
    {
      label: t('chat.chipCode'),
      Icon: Code2,
      prompt: t('chat.chipCodePrompt'),
    },
    {
      label: t('chat.chipBrainstorm'),
      Icon: Lightbulb,
      prompt: t('chat.chipBrainstormPrompt'),
    },
  ]

  return (
    <main className="chat-window">
      <header className="chat-header">
        {!sidebarOpen && (
          <button className="icon-btn" onClick={() => setSidebarOpen(true)} title={t('chat.openSidebar')}>
            <PanelLeftOpen size={18} />
          </button>
        )}
        <ProviderSelector />
        <button
          className={`fusion-toggle ${fusionMode ? 'active' : ''}`}
          onClick={() => setFusionMode(!fusionMode)}
          disabled={fusionActive}
          title={fusionMode ? t('chat.deactivateFusion') : t('chat.activateFusion')}
        >
          <Dna size={16} />
          {fusionMode && <span className="fusion-toggle-label">Fusion</span>}
        </button>
      </header>

      <div className="messages-area" ref={messagesAreaRef}>
        {isEmpty ? (
          <div className="welcome">
            <div className="welcome-brand">
              <span className="welcome-mark">⬡</span>
              <h1 className="welcome-greeting">
                {t(getGreetingKey())}, <strong>{name}</strong>
              </h1>
            </div>

            <p className="welcome-sub">
              {t('chat.welcomeSub')}
            </p>

            <div className="welcome-chips">
              {chips.map((chip) => (
                <button
                  key={chip.label}
                  className="chip-btn"
                  onClick={() => sendMessage(chip.prompt)}
                  title={chip.prompt}
                >
                  <chip.Icon size={15} />
                  <span>{chip.label}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((m) => {
              if (m.role === 'fusion_status') {
                return (
                  <FusionStatusCard
                    key={m.id}
                    fusionStatuses={m.fusion_statuses || []}
                    fusionJudgeModelId={m.fusion_judge_model_id || null}
                    fusionGrounding={m.fusion_grounding || null}
                    fusionRefinedPrompt={m.fusion_refined_prompt || null}
                  />
                )
              }
              return <MessageBubble key={m.id} message={m} />
            })}
            {isStreaming && <StreamingBubble content={streamingContent} />}
          </>
        )}
        <div ref={bottomSentinelRef} style={{ height: 0, flexShrink: 0 }} aria-hidden="true" />
      </div>

      <MessageInput onSend={sendMessage} />
    </main>
  )
}
