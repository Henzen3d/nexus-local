import { useTranslation } from 'react-i18next'
import { useStore } from '../../store/useStore'
import './UiLevelSelector.css'

const LEVELS = [
  { key: 'simple', label: 'Simples' },
  { key: 'intermediate', label: 'Intermediario' },
  { key: 'advanced', label: 'Avancado' },
] as const

export function UiLevelSelector() {
  const { t } = useTranslation()
  const { uiLevel, setUiLevel } = useStore()

  return (
    <div className="ui-level-selector">
      {LEVELS.map((level) => (
        <button
          key={level.key}
          type="button"
          className={`ui-level-btn ${uiLevel === level.key ? 'active' : ''}`}
          onClick={() => setUiLevel(level.key)}
          aria-label={`${t('ui.level', { defaultValue: '界面级别' })}: ${level.label}`}
          aria-pressed={uiLevel === level.key}
        >
          {level.label}
        </button>
      ))}
    </div>
  )
}
