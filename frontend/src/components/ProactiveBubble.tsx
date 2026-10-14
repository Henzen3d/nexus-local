import { useEffect, useMemo, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sparkles, MessageCircle, Ban, PauseCircle, Loader2, CornerUpLeft } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Message, WebSearchSource } from '../types'
import { useStore } from '../store/useStore'
import { AssistantAvatar } from './Avatars'
import { markdownComponents } from './markdownComponents'
import { SourceShelf } from './SourceShelf'

// ─── ProactiveBubble — bolha do assistente proativo (F2.7.3) ──────────────────
// Mensagem `kind='proactive'`: badge ✦, texto sintetizado, linha de motivo,
// fontes (SourceShelf) e três ações: "Quero saber mais" (pré-preenche o composer),
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
  const setComposerPrefill = useStore((s) => s.setComposerPrefill)
  const loadConversation = useStore((s) => s.loadConversation)
  const activeConversationId = useStore((s) => s.activeConversationId)
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

  const handleKnowMore = () => {
    const followUp = insight?.follow_ups?.[0]
    const prompt = followUp && followUp.trim() ? followUp.trim() : t('proactive.knowMorePrompt', { topic })
    setComposerPrefill(prompt)
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
      <AssistantAvatar />
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
  const label = stage === 'synthesizing' ? t('proactive.synthesizing') : t('proactive.researching')
  return (
    <div className="message assistant proactive-researching" role="status" aria-live="polite">
      <AssistantAvatar />
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
