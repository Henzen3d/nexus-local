import { useEffect, useRef, useState } from 'react'
import { Sparkles, ShieldOff, Users, Globe, Clock, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'

const MEMORY_ONBOARDING_KEY = 'nexuslocal_memory_onboarding_seen'

/**
 * F4.2 — Onboarding opt-in do Assistente Proativo (uma vez, fonte da verdade no servidor).
 *
 * Aparece quando `proactiveSettings.onboarding_eligible` é verdadeiro (nunca visto,
 * desligado e ≥ 3 conversas — calculado pelo backend, então funciona em vários
 * dispositivos) e depois do onboarding de memória, para não empilhar modais.
 * "Ativar" ⇒ PUT {enabled:true, onboarding_seen:true}; "Agora não" ⇒ marca como visto.
 */
export function ProactiveOnboarding() {
  const { t } = useTranslation()
  const settings = useStore((s) => s.proactiveSettings)
  const conversationCount = useStore((s) => s.conversations.length)
  const updateProactiveSettings = useStore((s) => s.updateProactiveSettings)
  const loadProactiveSettings = useStore((s) => s.loadProactiveSettings)
  const markSeen = useStore((s) => s.markProactiveOnboardingSeen)
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const recheckedRef = useRef(false)

  // Cruzou as 3 conversas nesta sessão? Reconsulta o servidor uma vez (ele decide a elegibilidade).
  useEffect(() => {
    if (recheckedRef.current || !settings) return
    if (settings.onboarding_eligible || settings.enabled || settings.onboarding_seen_at) return
    if (conversationCount >= 3 && (settings.conversation_count ?? 0) < 3) {
      recheckedRef.current = true
      void loadProactiveSettings()
    }
  }, [conversationCount, settings, loadProactiveSettings])

  useEffect(() => {
    if (!settings?.onboarding_eligible) {
      setOpen(false)
      return
    }
    let memorySeen = true
    try {
      memorySeen = !!localStorage.getItem(MEMORY_ONBOARDING_KEY)
    } catch {
      /* ignore */
    }
    if (!memorySeen) {
      // Espera o onboarding de memória ser dispensado nesta sessão
      const timer = setInterval(() => {
        try {
          if (localStorage.getItem(MEMORY_ONBOARDING_KEY)) {
            setOpen(true)
            clearInterval(timer)
          }
        } catch {
          clearInterval(timer)
        }
      }, 1500)
      return () => clearInterval(timer)
    }
    setOpen(true)
  }, [settings?.onboarding_eligible])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') void later()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const later = async () => {
    if (busy) return
    setBusy(true)
    try {
      await markSeen()
    } finally {
      setBusy(false)
      setOpen(false)
    }
  }

  const enable = async () => {
    if (busy) return
    setBusy(true)
    try {
      const res = await updateProactiveSettings({ enabled: true, onboarding_seen: true })
      if (res) setOpen(false)
    } finally {
      setBusy(false)
    }
  }

  if (!open) return null

  const bullets = [
    { icon: <ShieldOff size={18} aria-hidden="true" />, text: t('proactive.onboardingNot1') },
    { icon: <Users size={18} aria-hidden="true" />, text: t('proactive.onboardingNot2') },
    { icon: <Globe size={18} aria-hidden="true" />, text: t('proactive.onboardingNot3') },
    { icon: <Clock size={18} aria-hidden="true" />, text: t('proactive.onboardingLimits') },
  ]

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="proactive-onboarding-title"
      aria-describedby="proactive-onboarding-body"
      className="proactive-onboarding-backdrop"
      onClick={() => void later()}
      data-testid="proactive-onboarding"
    >
      <div className="proactive-onboarding-card" onClick={(e) => e.stopPropagation()}>
        <div className="proactive-onboarding-head">
          <div className="proactive-onboarding-icon">
            <Sparkles size={26} aria-hidden="true" />
          </div>
          <button type="button" onClick={() => void later()} aria-label={t('common.close')} className="icon-btn" style={{ color: 'var(--muted)' }}>
            <X size={20} />
          </button>
        </div>

        <h2 id="proactive-onboarding-title" className="proactive-onboarding-title">
          {t('proactive.onboardingTitle')}
        </h2>
        <p id="proactive-onboarding-body" className="proactive-onboarding-body">
          {t('proactive.onboardingBody')}
        </p>

        <ul className="proactive-onboarding-list">
          {bullets.map((b, i) => (
            <li key={i}>
              <span className="proactive-onboarding-bullet-icon">{b.icon}</span>
              <span>{b.text}</span>
            </li>
          ))}
        </ul>

        <p className="proactive-onboarding-footnote">{t('proactive.onboardingHowToDisable')}</p>

        <div className="proactive-onboarding-actions">
          <button type="button" className="btn btn-primary" onClick={() => void enable()} disabled={busy}>
            {t('proactive.onboardingEnable')}
          </button>
          <button type="button" className="btn btn-ghost proactive-onboarding-later" onClick={() => void later()} disabled={busy}>
            {t('proactive.onboardingLater')}
          </button>
        </div>
      </div>
    </div>
  )
}
