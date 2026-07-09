import { Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'

export function WebSearchToggle() {
  const { t } = useTranslation()
  const { webSearchActive, setWebSearchActive } = useStore()

  return (
    <button
      type="button"
      className={`enhance-btn ${webSearchActive ? 'active' : ''}`}
      onClick={() => setWebSearchActive(!webSearchActive)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '6px',
        borderRadius: 'var(--radius-md)',
        border: '1px solid',
        borderColor: webSearchActive ? 'rgba(93, 184, 166, 0.35)' : 'var(--hairline)',
        background: webSearchActive ? 'rgba(93, 184, 166, 0.12)' : 'transparent',
        color: webSearchActive ? 'var(--cyan)' : 'var(--muted)',
        cursor: 'pointer',
        transition: 'all 0.15s ease-in-out',
      }}
      title={webSearchActive ? t('chat.webSearchOn') : t('chat.webSearchOff')}
    >
      <Globe size={15} />
    </button>
  )
}
