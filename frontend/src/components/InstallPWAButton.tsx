import { useTranslation } from 'react-i18next'
import { usePWAStore } from '../store/pwaStore'
import { Download } from 'lucide-react'

export function InstallPWAButton() {
  const { t } = useTranslation()
  const { deferredPrompt, isInstallable, setIsInstallable, setDeferredPrompt } = usePWAStore()

  const handleInstallClick = async () => {
    if (!deferredPrompt) return

    deferredPrompt.prompt()

    const { outcome } = await deferredPrompt.userChoice

    if (outcome === 'accepted') {
      console.log('[PWA] User accepted NexusLocal install')
    }

    setDeferredPrompt(null)
    setIsInstallable(false)
  }

  if (!isInstallable) return null

  return (
    <button
      onClick={handleInstallClick}
      className="pwa-install-btn"
      title={t('pwa.installTitle')}
    >
      <Download size={16} />
      <span>{t('pwa.installApp')}</span>
    </button>
  )
}
