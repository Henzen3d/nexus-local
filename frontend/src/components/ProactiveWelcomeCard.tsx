import { useEffect, useState } from 'react'
import { Sparkles, ArrowRight, MessageCircle, X, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { isFresh, relativeAge, toastPreview } from '../lib/proactivePending'
import type { ProactiveInsight } from '../types'

// ─── ProactiveWelcomeCard — "Enquanto você esteve fora…" (F3.5.3) ─────────────
// Aparece só na tela inicial (sem conversa aberta) quando há insights prontos
// ainda não entregues. Cada item: ✦ Pesquisei sobre {tópico} · há N min, com
// "Abrir conversa" (vai à origem — a presença faz o backend entregar a bolha),
// "Me conta aqui" (POST /expand new_chat → conversa iniciada pela IA) e
// "Dispensar" (ack dismissed). Nada é marcado como visto automaticamente.

export function ProactiveWelcomeCard() {
  const { t } = useTranslation()
  const pendingInsights = useStore((s) => s.pendingInsights)
  const openPendingInsight = useStore((s) => s.openPendingInsight)
  const dismissPendingInsight = useStore((s) => s.dismissPendingInsight)
  const expandProactiveInsight = useStore((s) => s.expandProactiveInsight)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [, setTick] = useState(0)

  // "há N min" precisa envelhecer sem eventos
  useEffect(() => {
    if (pendingInsights.length === 0) return
    const id = setInterval(() => setTick((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [pendingInsights.length])

  if (pendingInsights.length === 0) return null

  const now = Date.now()
  const title = isFresh(pendingInsights, now) ? t('proactive.cardTitleFresh') : t('proactive.cardTitleAway')

  const ageLabel = (insight: ProactiveInsight) => {
    const age = relativeAge(insight.ready_at || insight.created_at, now)
    switch (age.key) {
      case 'minutes':
        return t('proactive.ageMinutes', { n: age.n })
      case 'hours':
        return t('proactive.ageHours', { n: age.n })
      case 'yesterday':
        return t('proactive.ageYesterday')
      case 'days':
        return t('proactive.ageDays', { n: age.n })
      default:
        return t('proactive.ageJustNow')
    }
  }

  const run = async (id: string, fn: () => Promise<void>) => {
    if (busyId) return
    setBusyId(id)
    try {
      await fn()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <section className="proactive-welcome-card" aria-label={title} data-testid="proactive-welcome-card">
      <header className="proactive-welcome-head">
        <Sparkles size={16} aria-hidden="true" />
        <h2>{title}</h2>
      </header>
      <ul className="proactive-welcome-list">
        {pendingInsights.map((insight) => {
          const busy = busyId === insight.id
          return (
            <li key={insight.id} className="proactive-welcome-item" data-insight-id={insight.id}>
              <div className="proactive-welcome-item-main">
                <div className="proactive-welcome-item-title">
                  <span className="proactive-welcome-spark" aria-hidden="true">✦</span>
                  <span>{t('proactive.cardItem', { topic: insight.topic, age: ageLabel(insight) })}</span>
                </div>
                <p className="proactive-welcome-preview">{toastPreview(insight.text || '', 180)}</p>
                {insight.origin?.title && (
                  <span className="proactive-welcome-origin">{t('proactive.cameFrom', { title: insight.origin.title })}</span>
                )}
              </div>
              <div className="proactive-welcome-actions" role="group" aria-label={insight.topic}>
                <button
                  type="button"
                  className="proactive-action primary"
                  disabled={!!busyId}
                  onClick={() => void run(insight.id, () => openPendingInsight(insight.id))}
                >
                  <ArrowRight size={14} aria-hidden="true" />
                  {t('proactive.openConversation')}
                </button>
                <button
                  type="button"
                  className="proactive-action"
                  disabled={!!busyId}
                  onClick={() => void run(insight.id, () => expandProactiveInsight(insight.id, 'new_chat'))}
                >
                  {busy ? <Loader2 size={14} className="spin" aria-hidden="true" /> : <MessageCircle size={14} aria-hidden="true" />}
                  {t('proactive.tellMeHere')}
                </button>
                <button
                  type="button"
                  className="proactive-action subtle"
                  disabled={!!busyId}
                  onClick={() => void run(insight.id, () => dismissPendingInsight(insight.id))}
                  aria-label={t('proactive.dismiss')}
                  title={t('proactive.dismiss')}
                >
                  <X size={14} aria-hidden="true" />
                  <span className="proactive-dismiss-label">{t('proactive.dismiss')}</span>
                </button>
              </div>
            </li>
          )
        })}
      </ul>
    </section>
  )
}
