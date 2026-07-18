import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'

export function WebSearchToggle() {
  const { t } = useTranslation()
  const { webSearchActive, setWebSearchActive } = useStore()

  return (
    <button
      type="button"
      className={`composer-tool-btn web-search-toggle custom-tooltip-trigger tooltip-up ${webSearchActive ? 'active' : ''}`}
      onClick={() => setWebSearchActive(!webSearchActive)}
      data-tooltip={webSearchActive ? t('chat.webSearchOn') : t('chat.webSearchOff')}
      aria-pressed={webSearchActive}
      aria-label={webSearchActive ? t('chat.webSearchOn') : t('chat.webSearchOff')}
    >
      <Globe size={15} strokeWidth={1.75} />
    </button>
  )
}
