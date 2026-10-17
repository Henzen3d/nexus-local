import { useEffect, useMemo, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sparkles, MessageCircle, Ban, PauseCircle, Loader2, CornerUpLeft, FileText } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Message, WebSearchSource } from '../types'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { AssistantAvatar } from './Avatars'
import { ProactiveMascot } from './ProactiveMascot'
import { markdownComponents } from './markdownComponents'
import { SourceShelf } from './SourceShelf'

// ─── ProactiveBubble — bolha do assistente proativo (F2.7.3) ──────────────────
// Mensagem `kind='proactive'`: badge ✦, texto sintetizado, linha de motivo,
// fontes (SourceShelf) e três ações: "Quero saber mais" (abre o Companion Modal),
// "Não quero sobre isso" (ack blocked) e "Pausar" (settings.enabled=false).
// O ack `seen` é enviado uma única vez quando a bolha entra na viewport.
// F3.3.3: em chat iniciado por "Me conta aqui", mostra "veio de «conversa de origem»".

const formatTime = (isoString?: string) => {
  if (!isoString) return ''
  try {
    const normalized = isoString.includes('T') ? isoString : isoString.replace(' ', 'T') + (isoString.endsWith('Z') ? '' : 'Z')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return ''
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

const formatDateFull = (isoString?: string) => {
  if (!isoString) return ''
  try {
    const normalized = isoString.includes('T') ? isoString : isoString.replace(' ', 'T') + (isoString.endsWith('Z') ? '' : 'Z')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return ''
    return d.toLocaleString([], { dateStyle: 'long', timeStyle: 'short' })
  } catch {
    return ''
  }
}

export function ProactiveBubble({ message }: { message: Message }) {
  const { t } = useTranslation()
  const ackProactiveInsight = useStore((s) => s.ackProactiveInsight)
  const pauseProactive = useStore((s) => s.pauseProactive)
  const loadConversation = useStore((s) => s.loadConversation)
  const activeConversationId = useStore((s) => s.activeConversationId)
  const proactiveSettings = useStore((s) => s.proactiveSettings)
  const openProactiveCompanion = useStore((s) => s.openProactiveCompanion)
  const setActiveArtifact = useStore((s) => s.setActiveArtifact)
  const setArtifactPanelOpen = useStore((s) => s.setArtifactPanelOpen)
  const loadArtifactHistory = useStore((s) => s.loadArtifactHistory)
  const rootRef = useRef<HTMLDivElement>(null)

  const insight = message.insight || null
  const insightId = insight?.id || message.proactive_insight_id || null
  const status = insight?.status || 'delivered'
  const isClosed = status === 'blocked' || status === 'dismissed'
  // Só quando a bolha NÃO está na própria conversa de origem (chat novo via "Me conta aqui")
  const origin = insight?.origin && insight.origin.conversation_id && insight.origin.conversation_id !== activeConversationId
    ? insight.origin
    : null

  const sources = useMemo<WebSearchSource[]>(() => {
    const fromInsight = (insight?.sources || []).map((s) => ({ title: s.title || s.domain || s.url, url: s.url }))
    if (fromInsight.length) return fromInsight
    return message.web_search_sources || []
  }, [insight, message.web_search_sources])

  const artifacts = useMemo(() => {
    if (message.artifacts && message.artifacts.length > 0) return message.artifacts
    if (insight?.artifact_id) {
      return [{
        id: insight.artifact_id,
        type: 'markdown',
        title: insight.artifact_title || insight.topic || t('proactive.artifactFallbackTitle', { defaultValue: 'Guia & Pesquisa' }),
      }]
    }
    return []
  }, [message.artifacts, insight?.artifact_id, insight?.artifact_title, insight?.topic, t])

  const content = (message.content || insight?.text || '').trim()
  const topic = insight?.topic || ''

  // Ack `seen` quando a bolha fica visível (uma vez por insight — o store deduplica)
  useEffect(() => {
    if (!insightId || !rootRef.current) return
    if (status === 'seen' || isClosed) return
    const el = rootRef.current
    if (typeof IntersectionObserver === 'undefined') {
      void ackProactiveInsight(insightId, 'seen', { silent: true })
      return
    }
    const obs = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          void ackProactiveInsight(insightId, 'seen', { silent: true })
          obs.disconnect()
        }
      },
      { threshold: 0.4 }
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [insightId, status, isClosed, ackProactiveInsight])

  const handleCardClick = async (artId: string) => {
    try {
      const artifact = await api.getArtifact(artId)
      setActiveArtifact(artifact)
      setArtifactPanelOpen(true)
      if (artifact.artifact_group_id) {
        await loadArtifactHistory(artifact.artifact_group_id)
      }
    } catch (e) {
      console.error('Falha ao abrir artifact pelo card:', e)
    }
  }

  const handleKnowMore = () => {
    if (insight) {
      openProactiveCompanion(insight)
    } else if (insightId) {
      openProactiveCompanion({
        id: insightId,
        conversation_id: activeConversationId || '',
        message_id: message.id,
        topic: topic || t('proactive.hubTitle', { defaultValue: 'Assistente Proativo' }),
        category: 'other',
        text: content,
        sources: sources.map((s) => ({ title: s.title, url: s.url, domain: '' })),
        follow_ups: [],
      })
    }
  }

  const handleNotThisTopic = () => {
    if (!insightId) return
    void ackProactiveInsight(insightId, 'blocked')
  }

  const handlePause = () => {
    void pauseProactive()
  }

  return (
    <div
      ref={rootRef}
      className={`message assistant proactive ${isClosed ? 'is-closed' : ''}`}
      data-insight-id={insightId || undefined}
      data-testid="proactive-bubble"
    >
      <div className="proactive-avatar-wrap">
        <ProactiveMascot size={28} state="ready" style={proactiveSettings?.persona_style || 'lumi'} />
      </div>
      <div className="message-body-wrapper">
        <div className="message-body proactive-body">
          <div className="proactive-badge" aria-label={t('proactive.bubbleBadge')}>
            <Sparkles size={12} aria-hidden="true" />
            <span>{t('proactive.bubbleBadge')}</span>
            {insight?.category && (
              <span className="proactive-category">{t(`proactive.category.${insight.category}`, { defaultValue: insight.category })}</span>
            )}
          </div>

          <div className="assistant-response proactive-text">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
              {content}
            </ReactMarkdown>
          </div>

          {insight?.reason_line && <div className="proactive-reason">{insight.reason_line}</div>}

          {origin && (
            <button
              type="button"
              className="proactive-origin-link"
              onClick={() => void loadConversation(origin.conversation_id)}
              title={t('proactive.cameFrom', { title: origin.title || '…' })}
            >
              <CornerUpLeft size={12} aria-hidden="true" />
              <span>{t('proactive.cameFrom', { title: origin.title || '…' })}</span>
            </button>
          )}

          {artifacts.length > 0 && (
            <div className="artifact-chat-card-list">
              {artifacts.map((art) => (
                <div
                  key={art.id}
                  className="artifact-chat-card"
                  onClick={() => void handleCardClick(art.id)}
                  title={t('chat.openArtifact', { defaultValue: 'Abrir no painel de artefatos' })}
                >
                  <div className="artifact-chat-card-content">
                    <div className="artifact-chat-card-preview" aria-hidden="true">
                      <div className="artifact-chat-card-sheet">
                        <FileText size={16} />
                      </div>
                    </div>
                    <div className="artifact-chat-card-info">
                      <div className="artifact-chat-card-title">{art.title}</div>
                      <div className="artifact-chat-card-subtitle">{t('proactive.artifactSubtitle', { defaultValue: 'Relatório estruturado' })}</div>
                    </div>
                    <div className="artifact-chat-card-actions">
                      <button
                        type="button"
                        className="artifact-chat-card-download-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          void handleCardClick(art.id)
                        }}
                      >
                        {t('chat.view', { defaultValue: 'Visualizar' })}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {sources.length > 0 && <SourceShelf sources={sources} />}

          {isClosed ? (
            <div className="proactive-closed-note">
              <Ban size={12} aria-hidden="true" />
              <span>{status === 'blocked' ? t('proactive.blockedNote') : t('proactive.dismissedNote')}</span>
            </div>
          ) : (
            <div className="proactive-actions" role="group" aria-label={t('proactive.bubbleBadge')}>
              <button type="button" className="proactive-action primary" onClick={handleKnowMore}>
                <MessageCircle size={14} aria-hidden="true" />
                {t('proactive.knowMore')}
              </button>
              <button type="button" className="proactive-action" onClick={handleNotThisTopic} disabled={!insightId}>
                <Ban size={14} aria-hidden="true" />
                {t('proactive.notThisTopic')}
              </button>
              <button type="button" className="proactive-action subtle" onClick={handlePause}>
                <PauseCircle size={14} aria-hidden="true" />
                {t('proactive.pause')}
              </button>
            </div>
          )}
        </div>

        <div className="message-meta">
          {message.created_at && (
            <span className="timestamp custom-tooltip-trigger" data-tooltip={formatDateFull(message.created_at)}>
              {formatTime(message.created_at)}
            </span>
          )}
          {message.model_display_name && (
            <>
              <span className="meta-sep">·</span>
              <span className="model-badge">{message.model_display_name}</span>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── ProactiveResearching — indicador discreto "✦ pesquisando…" (F2.7.4) ───────
export function ProactiveResearching({ stage }: { stage?: string }) {
  const { t } = useTranslation()
  const proactiveSettings = useStore((s) => s.proactiveSettings)
  const label = stage === 'synthesizing' ? t('proactive.synthesizing') : t('proactive.researching')
  return (
    <div className="message assistant proactive-researching" role="status" aria-live="polite">
      <div className="proactive-avatar-wrap">
        <ProactiveMascot size={28} state="researching" style={proactiveSettings?.persona_style || 'lumi'} />
      </div>
      <div className="message-body-wrapper">
        <div className="proactive-researching-pill">
          <Sparkles size={12} aria-hidden="true" />
          <span>{label}</span>
          <Loader2 size={12} className="proactive-spin" aria-hidden="true" />
        </div>
      </div>
    </div>
  )
}
