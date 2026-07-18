import { useState, useEffect } from 'react'
import { Download, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { usePWAStore } from '../store/pwaStore'

const DISMISS_KEY = 'nexuslocal_pwa_banner_dismissed'

export function PwaInstallBanner() {
  const { t } = useTranslation()
  const { deferredPrompt, isInstallable, setIsInstallable, setDeferredPrompt } = usePWAStore()
  const [dismissed, setDismissed] = useState(() => {
    if (typeof window === 'undefined') return true
    return sessionStorage.getItem(DISMISS_KEY) === '1'
  })

  useEffect(() => {
    // Standalone PWA — never show
    if (typeof window === 'undefined') return
    const standalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true
    if (standalone) setDismissed(true)
  }, [])

  if (!isInstallable || dismissed || !deferredPrompt) return null

  const handleInstall = async () => {
    try {
      deferredPrompt.prompt()
      await deferredPrompt.userChoice
    } catch {
      /* ignore */
    }
    setDeferredPrompt(null)
    setIsInstallable(false)
  }

  const handleDismiss = () => {
    sessionStorage.setItem(DISMISS_KEY, '1')
    setDismissed(true)
  }

  return (
    <div className="pwa-install-banner" role="region" aria-label={t('pwa.installApp')}>
      <div className="pwa-install-banner-text">
        <strong>{t('pwa.installApp')}</strong>
        <span>{t('pwa.installBanner')}</span>
      </div>
      <div className="pwa-install-banner-actions">
        <button type="button" className="pwa-install-banner-cta" onClick={handleInstall}>
          <Download size={14} />
          {t('pwa.installApp')}
        </button>
        <button
          type="button"
          className="pwa-install-banner-dismiss"
          onClick={handleDismiss}
          aria-label={t('common.close')}
        >
          <X size={16} />
        </button>
      </div>
    </div>
  )
}
