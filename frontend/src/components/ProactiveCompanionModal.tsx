import React, { useState, useRef, useEffect, useMemo } from 'react'
import { X, Send, Sparkles, FileText, ExternalLink, ArrowRight, CornerDownLeft, Loader2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { ProactiveMascot } from './ProactiveMascot'
import { markdownComponents } from './markdownComponents'

export const ProactiveCompanionModal: React.FC = () => {
  const { t } = useTranslation()
  const isOpen = useStore((s) => s.proactiveCompanionOpen)
  const insight = useStore((s) => s.proactiveCompanionInsight)
  const messages = useStore((s) => s.proactiveCompanionMessages)
  const isSending = useStore((s) => s.isCompanionSending)
  const closeCompanion = useStore((s) => s.closeProactiveCompanion)
  const sendMessage = useStore((s) => s.sendProactiveCompanionMessage)
  const expandProactiveInsight = useStore((s) => s.expandProactiveInsight)
  const setActiveArtifact = useStore((s) => s.setActiveArtifact)
  const setArtifactPanelOpen = useStore((s) => s.setArtifactPanelOpen)
  const loadArtifactHistory = useStore((s) => s.loadArtifactHistory)
  const proactiveSettings = useStore((s) => s.proactiveSettings)

  const [input, setInput] = useState('')
  const threadEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const personaStyle = proactiveSettings?.persona_style || 'lumi'

  // Auto-scroll para a última mensagem
  useEffect(() => {
    if (isOpen) {
      threadEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, isSending, isOpen])

  // Foco no input ao abrir
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        inputRef.current?.focus()
      }, 100)
      return () => clearTimeout(timer)
    }
  }, [isOpen])

  // Fechar com ESC
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeCompanion()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, closeCompanion])

  if (!isOpen || !insight) return null

  const handleSend = () => {
    const trimmed = input.trim()
    if (!trimmed || isSending) return
    setInput('')
    void sendMessage(trimmed)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleOpenArtifact = async (artifactId?: string | null) => {
    const targetId = artifactId || insight.artifact_id
    if (!targetId) return
    try {
      const art = await api.getArtifact(targetId)
      setActiveArtifact(art)
      setArtifactPanelOpen(true)
      if (art.artifact_group_id) {
        await loadArtifactHistory(art.artifact_group_id)
      }
    } catch (e) {
      console.error('[ProactiveCompanion] erro ao carregar artifact:', e)
    }
  }

  const handleExpandToMainChat = async () => {
    closeCompanion()
    await expandProactiveInsight(insight.id, 'new_chat')
  }

  const followUps = insight.follow_ups || []
  const currentArtifactTitle = insight.artifact_title || insight.topic || t('proactive.artifactFallbackTitle', { defaultValue: 'Guia & Destaques' })

  return (
    <div className="proactive-companion-overlay" onClick={closeCompanion} role="dialog" aria-modal="true">
      <div className="proactive-companion-container" onClick={(e) => e.stopPropagation()}>
        {/* Cabeçalho */}
        <header className="companion-header">
          <div className="companion-header-identity">
            <ProactiveMascot size={32} state={isSending ? 'researching' : 'ready'} style={personaStyle} />
            <div className="companion-header-titles">
              <div className="companion-persona-name">
                <span>{t('proactive.companionPersonaName', { defaultValue: 'Lumi' })}</span>
                <span className="companion-sparkle-pill">✦ {t('proactive.hubTitle', { defaultValue: 'Assistente Proativo' })}</span>
              </div>
              <div className="companion-topic-sub" title={insight.topic}>
                <span className="topic-text">{insight.topic}</span>
                {insight.category && (
                  <span className="topic-category-tag">
                    {t(`proactive.category.${insight.category}`, { defaultValue: insight.category })}
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="companion-header-actions">
            <button
              type="button"
              className="companion-chat-expand-btn"
              onClick={handleExpandToMainChat}
              title={t('proactive.expandToChatTooltip', { defaultValue: 'Continuar em uma conversa normal do NexusLocal' })}
            >
              <ExternalLink size={14} />
              <span>{t('proactive.openInChat', { defaultValue: 'Abrir no chat' })}</span>
            </button>
            <button
              type="button"
              className="companion-close-btn"
              onClick={closeCompanion}
              aria-label={t('common.close', { defaultValue: 'Fechar' })}
            >
              <X size={18} />
            </button>
          </div>
        </header>

        {/* Card do Artefato Anexo */}
        <div className="companion-artifact-bar">
          <div className="companion-artifact-icon">
            <FileText size={18} />
          </div>
          <div className="companion-artifact-info">
            <span className="companion-artifact-title">{currentArtifactTitle}</span>
            <span className="companion-artifact-desc">
              {t('proactive.artifactBannerDesc', { defaultValue: 'Relatório estruturado com dados completos, fontes e tabelas.' })}
            </span>
          </div>
          <button
            type="button"
            className="companion-artifact-open-btn"
            onClick={() => handleOpenArtifact()}
          >
            <Sparkles size={13} />
            <span>{t('proactive.viewArtifactAction', { defaultValue: 'Ver Artefato' })}</span>
          </button>
        </div>

        {/* Corpo de Mensagens */}
        <div className="companion-messages-body">
          {messages.map((msg) => (
            <div key={msg.id} className={`companion-msg-row ${msg.role}`}>
              {msg.role === 'assistant' && (
                <div className="companion-msg-avatar">
                  <ProactiveMascot size={24} state="ready" style={personaStyle} />
                </div>
              )}
              <div className="companion-msg-bubble">
                <div className="companion-msg-text">
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                    {msg.content}
                  </ReactMarkdown>
                </div>
                {msg.artifact && (
                  <div
                    className="companion-msg-artifact-badge"
                    onClick={() => handleOpenArtifact(msg.artifact?.id)}
                  >
                    <FileText size={12} />
                    <span>{t('proactive.artifactUpdatedNotice', { defaultValue: 'Artefato atualizado:' })} {msg.artifact.title}</span>
                    <ArrowRight size={12} />
                  </div>
                )}
              </div>
            </div>
          ))}

          {isSending && (
            <div className="companion-msg-row assistant">
              <div className="companion-msg-avatar">
                <ProactiveMascot size={24} state="researching" style={personaStyle} />
              </div>
              <div className="companion-msg-bubble typing">
                <Loader2 size={14} className="companion-spin-icon" />
                <span>{t('proactive.companionThinking', { defaultValue: 'Lumi pensando e refinando as notas...' })}</span>
              </div>
            </div>
          )}

          <div ref={threadEndRef} />
        </div>

        {/* Sugestões de Perguntas Rápidas (Chips) */}
        {followUps.length > 0 && (
          <div className="companion-chips-container">
            <span className="companion-chips-label">{t('proactive.suggestedChips', { defaultValue: 'Sugestões rápidas:' })}</span>
            <div className="companion-chips-scroll">
              {followUps.slice(0, 3).map((f, i) => (
                <button
                  key={i}
                  type="button"
                  className="companion-suggestion-chip"
                  onClick={() => void sendMessage(f)}
                  disabled={isSending}
                >
                  <Sparkles size={11} />
                  <span>{f}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Rodapé / Input de Envio */}
        <footer className="companion-footer">
          <div className="companion-input-wrapper">
            <textarea
              ref={inputRef}
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={t('proactive.companionInputPlaceholder', { defaultValue: 'Converse com Lumi ou peça para aprofundar...' })}
              disabled={isSending}
            />
            <button
              type="button"
              className="companion-send-btn"
              onClick={handleSend}
              disabled={!input.trim() || isSending}
              aria-label={t('chat.send', { defaultValue: 'Enviar' })}
            >
              {isSending ? <Loader2 size={16} className="companion-spin-icon" /> : <Send size={16} />}
            </button>
          </div>
          <div className="companion-input-hint">
            <span>{t('proactive.companionShortChatHint', { defaultValue: '✦ Conversa rápida entre amigos. Detalhes densos são organizados no Artefato.' })}</span>
          </div>
        </footer>
      </div>
    </div>
  )
}
