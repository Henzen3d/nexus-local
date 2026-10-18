import { useTranslation } from 'react-i18next'
import { Sparkles, SlidersHorizontal, Terminal } from 'lucide-react'
import { useStore } from '../../store/useStore'
import './UiLevelSelector.css'

export function UiLevelSelector() {
  const { t } = useTranslation()
  const { uiLevel, setUiLevel, selectModel } = useStore()

  const handleSelect = (level: 'simple' | 'intermediate' | 'advanced') => {
    setUiLevel(level)
    if (level === 'simple') {
      selectModel('auto', 'auto')
    }
  }

  const levels = [
    {
      key: 'simple' as const,
      icon: Sparkles,
      title: t('settings.uiLevelSimpleTitle', { defaultValue: 'Simples' }),
      desc: t('settings.uiLevelSimpleDesc', {
        defaultValue: 'Chat direto com modo Rápido ou Pensativo. Roteamento inteligente automático sem nomes técnicos de modelos.',
      }),
    },
    {
      key: 'intermediate' as const,
      icon: SlidersHorizontal,
      title: t('settings.uiLevelIntermediateTitle', { defaultValue: 'Intermediário' }),
      desc: t('settings.uiLevelIntermediateDesc', {
        defaultValue: 'Equilibrado. Exibe o seletor compacto de modelos no chat para escolha rápida.',
      }),
    },
    {
      key: 'advanced' as const,
      icon: Terminal,
      title: t('settings.uiLevelAdvancedTitle', { defaultValue: 'Avançado' }),
      desc: t('settings.uiLevelAdvancedDesc', {
        defaultValue: 'Controle técnico completo. Seleção de provedores, controle de raciocínio e ferramentas avançadas.',
      }),
    },
  ]

  return (
    <div
      className="ui-level-selector"
      role="radiogroup"
      aria-label={t('settings.uiLevelTitle', { defaultValue: 'Nível da Interface' })}
    >
      {levels.map((lvl) => {
        const Icon = lvl.icon
        const isSelected = uiLevel === lvl.key

        return (
          <button
            key={lvl.key}
            type="button"
            role="radio"
            aria-checked={isSelected}
            className={`ui-level-btn ui-level-card ${isSelected ? 'active' : ''}`}
            onClick={() => handleSelect(lvl.key)}
          >
            <div className="ui-level-card-header">
              <div className="ui-level-icon-wrapper" aria-hidden="true">
                <Icon size={16} />
              </div>
              <span className="ui-level-card-title">{lvl.title}</span>
              <span className={`ui-level-radio ${isSelected ? 'checked' : ''}`} aria-hidden="true" />
            </div>
            <p className="ui-level-card-desc">{lvl.desc}</p>
          </button>
        )
      })}
    </div>
  )
}
