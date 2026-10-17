import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { WifiOff, Wifi } from 'lucide-react'

/**
 * Banner discreto no topo da página quando offline.
 * Some automaticamente ao reconectar.
 */
export function OfflineBanner() {
  const { t } = useTranslation()
  const isOnline = useStore((s) => s.isOnline)

  if (isOnline) return null

  return (
    <div
      className="offline-banner"
      role="alert"
      aria-live="polite"
      aria-label={t('offline.bannerLabel', { defaultValue: 'Sem conexão com a internet' })}
    >
      <WifiOff size={14} />
      <span>{t('offline.bannerText', { defaultValue: 'Você está offline. As mensagens serão enviadas quando a conexão retornar.' })}</span>
    </div>
  )
}

export function OnlineIndicator() {
  const { t } = useTranslation()
  const isOnline = useStore((s) => s.isOnline)

  if (isOnline) return null

  return (
    <div
      className="online-indicator"
      role="status"
      aria-live="polite"
      aria-label={t('offline.onlineLabel', { defaultValue: 'Conexão restaurada' })}
    >
      <Wifi size={14} />
      <span>{t('offline.onlineText', { defaultValue: 'Conexão restaurada' })}</span>
    </div>
  )
}
