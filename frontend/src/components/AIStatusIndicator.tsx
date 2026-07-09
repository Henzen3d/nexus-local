import { Check, AlertCircle, RefreshCw, XSquare, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export type AIStatus = 'thinking' | 'completed' | 'regenerating' | 'error' | 'cancelled'

interface Props {
  status: AIStatus
  label?: string
}

export function AIStatusIndicator({ status, label }: Props) {
  const { t } = useTranslation()

  switch (status) {
    case 'thinking':
      return (
        <span className="ai-status ai-status-thinking">
          <Loader2 size={13} className="spin" />
          <span>{label || t('chat.thinking')}</span>
        </span>
      )
    case 'completed':
      return (
        <span className="ai-status ai-status-completed">
          <Check size={13} />
          <span>{label || t('chat.done')}</span>
        </span>
      )
    case 'regenerating':
      return (
        <span className="ai-status ai-status-regenerating">
          <RefreshCw size={13} className="spin" />
          <span>{label || t('chat.regenerating')}</span>
        </span>
      )
    case 'error':
      return (
        <span className="ai-status ai-status-error">
          <AlertCircle size={13} />
          <span>{label || t('common.error')}</span>
        </span>
      )
    case 'cancelled':
      return (
        <span className="ai-status ai-status-cancelled">
          <XSquare size={13} />
          <span>{label || t('chat.cancelled')}</span>
        </span>
      )
    default:
      return null
  }
}
