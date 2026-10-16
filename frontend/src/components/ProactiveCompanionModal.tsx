import React, { useState, useRef, useEffect, useMemo, useCallback } from 'react'
import { X, Send, Sparkles, FileText, ExternalLink, ArrowRight, CornerDownLeft, Loader2, Maximize2, Minimize2 } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { ProactiveMascot } from './ProactiveMascot'
import { markdownComponents } from './markdownComponents'

type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

const MIN_MODAL_WIDTH = 460
const MIN_MODAL_HEIGHT = 400

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
  const isInteractingRef = useRef(false)

  // Estados de dimensão e posicionamento tipo janela do Windows
  const [size, setSize] = useState<{ width: number; height: number }>(() => {
    const w = typeof window !== 'undefined' ? Math.min(740, window.innerWidth - 32) : 720
    const h = typeof window !== 'undefined' ? Math.min(680, window.innerHeight - 40) : 680
    return { width: Math.max(MIN_MODAL_WIDTH, w), height: Math.max(MIN_MODAL_HEIGHT, h) }
  })

  const [pos, setPos] = useState<{ x: number; y: number }>(() => {
    const w = typeof window !== 'undefined' ? Math.min(740, window.innerWidth - 32) : 720
    const h = typeof window !== 'undefined' ? Math.min(680, window.innerHeight - 40) : 680
    const x = typeof window !== 'undefined' ? Math.max(16, Math.round((window.innerWidth - w) / 2)) : 40
    const y = typeof window !== 'undefined' ? Math.max(16, Math.round((window.innerHeight - h) / 2)) : 40
    return { x, y }
  })

  const [isMaximized, setIsMaximized] = useState(false)
  const prevBoundsRef = useRef<{ x: number; y: number; width: number; height: number } | null>(null)

  const personaStyle = proactiveSettings?.persona_style || 'lumi'

  // Centraliza janela se for aberta pela primeira vez ou se a viewport mudar muito
  useEffect(() => {
    if (isOpen && !isMaximized) {
      const w = Math.min(size.width, window.innerWidth - 32)
      const h = Math.min(size.height, window.innerHeight - 40)
      const x = Math.max(16, Math.round((window.innerWidth - w) / 2))
      const y = Math.max(16, Math.round((window.innerHeight - h) / 2))
      setPos({ x, y })
      setSize({ width: Math.max(MIN_MODAL_WIDTH, w), height: Math.max(MIN_MODAL_HEIGHT, h) })
    }
  }, [isOpen])

  // Drag da janela pelo cabeçalho (estilo Windows)
  const handleHeaderMouseDown = (e: React.MouseEvent) => {
    if (isMaximized) return
    const target = e.target as HTMLElement
    if (target.closest('button') || target.closest('a') || target.closest('input') || target.closest('textarea')) {
      return
    }

    e.preventDefault()
    isInteractingRef.current = true
    const startX = e.clientX
    const startY = e.clientY
    const startPosX = pos.x
    const startPosY = pos.y

    document.body.style.userSelect = 'none'

    const onMouseMove = (moveEv: MouseEvent) => {
      const deltaX = moveEv.clientX - startX
      const deltaY = moveEv.clientY - startY
      const maxX = Math.max(0, window.innerWidth - size.width)
      const maxY = Math.max(0, window.innerHeight - 60)
      setPos({
        x: Math.max(0, Math.min(startPosX + deltaX, maxX)),
        y: Math.max(0, Math.min(startPosY + deltaY, maxY)),
      })
    }

    const onMouseUp = () => {
      document.body.style.userSelect = ''
      setTimeout(() => {
        isInteractingRef.current = false
      }, 50)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  // Redimensionamento pelas bordas e cantos (8 direções)
  const handleResizeMouseDown = (direction: ResizeDirection, e: React.MouseEvent) => {
    if (isMaximized) return
    e.preventDefault()
    e.stopPropagation()
    isInteractingRef.current = true

    const startX = e.clientX
    const startY = e.clientY
    const startW = size.width
    const startH = size.height
    const startPosX = pos.x
    const startPosY = pos.y

    document.body.style.userSelect = 'none'

    const onMouseMove = (moveEv: MouseEvent) => {
      const deltaX = moveEv.clientX - startX
      const deltaY = moveEv.clientY - startY

      let newW = startW
      let newH = startH
      let newX = startPosX
      let newY = startPosY

      // Leste (Right)
      if (direction.includes('e')) {
        newW = Math.max(MIN_MODAL_WIDTH, Math.min(startW + deltaX, window.innerWidth - startPosX - 16))
      }
      // Sul (Bottom)
      if (direction.includes('s')) {
        newH = Math.max(MIN_MODAL_HEIGHT, Math.min(startH + deltaY, window.innerHeight - startPosY - 16))
      }
      // Oeste (Left)
      if (direction.includes('w')) {
        const maxDeltaX = startW - MIN_MODAL_WIDTH
        const clampedDeltaX = Math.min(deltaX, maxDeltaX)
        newW = startW - clampedDeltaX
        newX = startPosX + clampedDeltaX
        if (newX < 10) {
          newW = startW + startPosX - 10
          newX = 10
        }
      }
      // Norte (Top)
      if (direction.includes('n')) {
        const maxDeltaY = startH - MIN_MODAL_HEIGHT
        const clampedDeltaY = Math.min(deltaY, maxDeltaY)
        newH = startH - clampedDeltaY
        newY = startPosY + clampedDeltaY
        if (newY < 10) {
          newH = startH + startPosY - 10
          newY = 10
        }
      }

      setSize({ width: Math.round(newW), height: Math.round(newH) })
      setPos({ x: Math.round(newX), y: Math.round(newY) })
    }

    const onMouseUp = () => {
      document.body.style.userSelect = ''
      setTimeout(() => {
        isInteractingRef.current = false
      }, 50)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }

  // Alterna maximizar / restaurar tamanho
  const toggleMaximize = useCallback(() => {
    if (isMaximized) {
      if (prevBoundsRef.current) {
        setPos({ x: prevBoundsRef.current.x, y: prevBoundsRef.current.y })
        setSize({ width: prevBoundsRef.current.width, height: prevBoundsRef.current.height })
      }
      setIsMaximized(false)
    } else {
      prevBoundsRef.current = { ...pos, ...size }
      setIsMaximized(true)
    }
  }, [isMaximized, pos, size])

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

  const containerStyle: React.CSSProperties = isMaximized
    ? {
        position: 'fixed',
        top: 10,
        left: 10,
        width: 'calc(100vw - 20px)',
        height: 'calc(100vh - 20px)',
        maxWidth: 'none',
        maxHeight: 'none',
        borderRadius: 14,
        zIndex: 1260,
      }
    : {
        position: 'fixed',
        top: pos.y,
        left: pos.x,
        width: size.width,
        height: size.height,
        maxWidth: 'none',
        maxHeight: 'none',
        zIndex: 1260,
      }

  return (
    <div
      className="proactive-companion-overlay"
      onClick={() => {
        if (!isInteractingRef.current) closeCompanion()
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        className={`proactive-companion-container ${isMaximized ? 'is-maximized' : ''}`}
        style={containerStyle}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Resize Handles (8 direções) */}
        {!isMaximized && (
          <>
            <div className="companion-resize-edge n" onMouseDown={(e) => handleResizeMouseDown('n', e)} />
            <div className="companion-resize-edge s" onMouseDown={(e) => handleResizeMouseDown('s', e)} />
            <div className="companion-resize-edge w" onMouseDown={(e) => handleResizeMouseDown('w', e)} />
            <div className="companion-resize-edge e" onMouseDown={(e) => handleResizeMouseDown('e', e)} />
            <div className="companion-resize-corner nw" onMouseDown={(e) => handleResizeMouseDown('nw', e)} />
            <div className="companion-resize-corner ne" onMouseDown={(e) => handleResizeMouseDown('ne', e)} />
            <div className="companion-resize-corner sw" onMouseDown={(e) => handleResizeMouseDown('sw', e)} />
            <div className="companion-resize-corner se" onMouseDown={(e) => handleResizeMouseDown('se', e)} />
          </>
        )}

        {/* Cabeçalho */}
        <header
          className="companion-header"
          onMouseDown={handleHeaderMouseDown}
          onDoubleClick={toggleMaximize}
          style={{ cursor: isMaximized ? 'default' : 'grab' }}
          title={isMaximized ? undefined : 'Arraste para mover a janela'}
        >
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
              className="companion-maximize-btn"
              onClick={toggleMaximize}
              title={isMaximized ? t('common.restore', { defaultValue: 'Restaurar' }) : t('common.maximize', { defaultValue: 'Maximizar' })}
              aria-label={isMaximized ? 'Restaurar' : 'Maximizar'}
            >
              {isMaximized ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
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
