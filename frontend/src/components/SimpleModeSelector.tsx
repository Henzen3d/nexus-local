import { useState, useRef, useEffect } from 'react'
import { Zap, Brain, ChevronDown, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import './SimpleModeSelector.css'

interface SimpleModeSelectorProps {
  compact?: boolean
  className?: string
}

export function SimpleModeSelector({ compact = false, className = '' }: SimpleModeSelectorProps) {
  const { t } = useTranslation()
  const { simpleSpeed, setSimpleSpeed, isStreaming } = useStore()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  const isFast = simpleSpeed === 'fast'
  const currentLabel = isFast
    ? t('chat.simpleFast', { defaultValue: 'Rápido' })
    : t('chat.simpleThink', { defaultValue: 'Pensativo' })
  const CurrentIcon = isFast ? Zap : Brain

  const handleSelect = (speed: 'fast' | 'think') => {
    setSimpleSpeed(speed)
    setOpen(false)
  }

  return (
    <div className={`simple-mode-container ${className}`} ref={menuRef}>
      <button
        type="button"
        className={`simple-mode-trigger ${compact ? 'compact' : ''} ${open ? 'open' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
        disabled={isStreaming}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={t('chat.modeSelect', { defaultValue: `Modo do modelo: ${currentLabel}` })}
      >
        <span className="simple-mode-trigger-icon" aria-hidden="true">
          <CurrentIcon size={compact ? 13 : 14} />
        </span>
        <span className="simple-mode-trigger-label">{currentLabel}</span>
        <ChevronDown size={13} className={`simple-mode-chevron ${open ? 'open' : ''}`} aria-hidden="true" />
      </button>

      {open && (
        <div
          className="simple-mode-dropdown"
          role="menu"
          aria-orientation="vertical"
        >
          {/* Opção 1: Rápido */}
          <button
            type="button"
            role="menuitem"
            className={`simple-mode-item ${isFast ? 'active' : ''}`}
            onClick={() => handleSelect('fast')}
          >
            <div className="simple-mode-item-icon" aria-hidden="true">
              <Zap size={16} />
            </div>
            <div className="simple-mode-item-content">
              <span className="simple-mode-item-title">
                {t('chat.simpleFast', { defaultValue: 'Rápido' })}
              </span>
              <span className="simple-mode-item-desc">
                {t('chat.simpleFastDesc', { defaultValue: 'Obtenha respostas rápidas' })}
              </span>
            </div>
            {isFast && (
              <span className="simple-mode-item-check" aria-hidden="true">
                <Check size={14} strokeWidth={2.5} />
              </span>
            )}
          </button>

          {/* Opção 2: Pensativo */}
          <button
            type="button"
            role="menuitem"
            className={`simple-mode-item ${!isFast ? 'active' : ''}`}
            onClick={() => handleSelect('think')}
          >
            <div className="simple-mode-item-icon" aria-hidden="true">
              <Brain size={16} />
            </div>
            <div className="simple-mode-item-content">
              <span className="simple-mode-item-title">
                {t('chat.simpleThink', { defaultValue: 'Pensativo' })}
              </span>
              <span className="simple-mode-item-desc">
                {t('chat.simpleThinkDesc', { defaultValue: 'Lide com tarefas complexas' })}
              </span>
            </div>
            {!isFast && (
              <span className="simple-mode-item-check" aria-hidden="true">
                <Check size={14} strokeWidth={2.5} />
              </span>
            )}
          </button>
        </div>
      )}
    </div>
  )
}
