import { useEffect, useState } from 'react'
import { Brain, Shield, Eye, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

const STORAGE_KEY = 'nexuslocal_memory_onboarding_seen'

/**
 * Phase D: one-time local-first memory intro after login.
 */
export function MemoryOnboarding() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        setOpen(true)
      }
    } catch {
      /* ignore */
    }
  }, [])

  const dismiss = () => {
    try {
      localStorage.setItem(STORAGE_KEY, '1')
    } catch {
      /* ignore */
    }
    setOpen(false)
  }

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-onboarding-title"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 1300, /* modal-backdrop layer */
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
      onClick={dismiss}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--canvas)',
          borderRadius: 'var(--radius-xl)',
          padding: '28px 24px',
          width: '100%',
          maxWidth: '440px',
          boxShadow: '0 24px 64px rgba(0,0,0,0.35)',
          border: '1px solid var(--hairline)',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div
            style={{
              width: 48,
              height: 48,
              borderRadius: 'var(--radius-lg)',
              background: 'color-mix(in srgb, var(--primary) 12%, transparent)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Brain size={26} style={{ color: 'var(--primary)' }} />
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label={t('common.close')}
            className="icon-btn"
            style={{ color: 'var(--muted)' }}
          >
            <X size={20} />
          </button>
        </div>

        <h2 id="memory-onboarding-title" style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 600, color: 'var(--ink)', lineHeight: 1.3 }}>
          {t('memory.onboardingTitle')}
        </h2>
        <p style={{ margin: '0 0 18px', fontSize: '14px', color: 'var(--body)', lineHeight: 1.55 }}>
          {t('memory.onboardingBody')}
        </p>

        <ul style={{ listStyle: 'none', margin: '0 0 22px', padding: 0, display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <li style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
            <Shield size={18} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
            <span style={{ fontSize: 'var(--font-thinking)', color: 'var(--body)', lineHeight: 1.4 }}>{t('memory.onboardingLocal')}</span>
          </li>
          <li style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
            <Eye size={18} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
            <span style={{ fontSize: 'var(--font-thinking)', color: 'var(--body)', lineHeight: 1.4 }}>{t('memory.onboardingControl')}</span>
          </li>
          <li style={{ display: 'flex', gap: '10px', alignItems: 'flex-start' }}>
            <Brain size={18} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
            <span style={{ fontSize: 'var(--font-thinking)', color: 'var(--body)', lineHeight: 1.4 }}>{t('memory.onboardingChatToggle')}</span>
          </li>
        </ul>

        <button
          type="button"
          className="btn btn-primary"
          onClick={dismiss}
          style={{ width: '100%', padding: '12px 16px', fontWeight: 600 }}
        >
          {t('memory.onboardingCta')}
        </button>
      </div>
    </div>
  )
}
