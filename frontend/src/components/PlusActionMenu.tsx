import { useState, useRef, useEffect } from 'react'
import { Plus, Paperclip, Sparkles, Loader2, Globe, Dna, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { useIsMobile } from '../hooks/useIsMobile'
import { BottomSheet } from './ui/BottomSheet'

interface PlusActionMenuProps {
  onOpenFilePicker: () => void
  onEnhance: () => void
  enhancing: boolean
  hasText: boolean
  enhancerReady: boolean
  disabled?: boolean
}

export function PlusActionMenu({
  onOpenFilePicker,
  onEnhance,
  enhancing,
  hasText,
  enhancerReady,
  disabled = false,
}: PlusActionMenuProps) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()

  const {
    fusionMode,
    setFusionMode,
    webSearchActive,
    setWebSearchActive,
  } = useStore()

  useEffect(() => {
    if (!open || isMobile) return
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open, isMobile])

  useEffect(() => {
    if (!open || isMobile) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, isMobile])

  const handleToggleFusion = (e: React.MouseEvent) => {
    e.stopPropagation()
    setFusionMode(!fusionMode)
  }

  const handleToggleWebSearch = (e: React.MouseEvent) => {
    e.stopPropagation()
    setWebSearchActive(!webSearchActive)
  }

  const handleAttachClick = () => {
    setOpen(false)
    onOpenFilePicker()
  }

  const handleEnhanceClick = () => {
    if (!hasText || !enhancerReady || enhancing) return
    setOpen(false)
    onEnhance()
  }

  const renderMenuItems = () => (
    <>
      {/* 1. Anexar arquivos ou fotos */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleAttachClick}
        role="menuitem"
      >
        <span className="plus-menu-item-icon">
          <Paperclip size={16} />
        </span>
        <div className="plus-menu-item-content">
          <span className="plus-menu-item-label">
            {t('chat.addFiles', { defaultValue: 'Adicionar arquivos ou fotos' })}
          </span>
        </div>
      </button>

      {/* 2. Melhorar prompt atual */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleEnhanceClick}
        disabled={!hasText || !enhancerReady || enhancing}
        role="menuitem"
      >
        <span className="plus-menu-item-icon">
          {enhancing ? <Loader2 size={16} className="spin" /> : <Sparkles size={16} />}
        </span>
        <div className="plus-menu-item-content">
          <span className="plus-menu-item-label">
            {t('chat.enhanceTitle', { defaultValue: 'Melhorar prompt atual' })}
          </span>
          <span className="plus-menu-item-sub">
            {!enhancerReady
              ? t('chat.enhanceNotConfigured', { defaultValue: 'Não configurado' })
              : !hasText
              ? t('chat.enhanceDisabledEmpty', { defaultValue: 'Digite algo primeiro' })
              : t('chat.enhanceDesc', { defaultValue: 'Reescreve e enriquece sua mensagem' })}
          </span>
        </div>
      </button>

      <div className="plus-menu-divider" />

      {/* 3. Busca na web */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleToggleWebSearch}
        role="menuitemcheckbox"
        aria-checked={webSearchActive}
      >
        <span className="plus-menu-item-icon">
          <Globe size={16} />
        </span>
        <div className="plus-menu-item-content">
          <span className="plus-menu-item-label">
            {t('chat.webSearch', { defaultValue: 'Busca na web' })}
          </span>
          <span className="plus-menu-item-sub">
            {t('chat.webSearchDesc', { defaultValue: 'Consulta a web durante a resposta' })}
          </span>
        </div>
        <div className="plus-menu-item-right">
          {webSearchActive && <Check size={16} className="plus-menu-check" strokeWidth={2.5} />}
        </div>
      </button>

      {/* 4. Modo Fusion (Toggle estilo trogle-conectores.jpg) */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleToggleFusion}
        role="menuitemcheckbox"
        aria-checked={fusionMode}
      >
        <span className="plus-menu-item-icon">
          <Dna size={16} />
        </span>
        <div className="plus-menu-item-content">
          <span className="plus-menu-item-label">
            {t('chat.fusionMode', { defaultValue: 'Modo Fusion' })}
          </span>
          <span className="plus-menu-item-sub">
            {t('chat.fusionModeSub', { defaultValue: 'Combina respostas de múltiplos modelos' })}
          </span>
        </div>
        <div className="plus-menu-item-right">
          <span
            className={`nexus-toggle-switch ${fusionMode ? 'active' : ''}`}
            aria-hidden="true"
          >
            <span className="nexus-toggle-thumb" />
          </span>
        </div>
      </button>
    </>
  )

  return (
    <div className="plus-menu-container" ref={menuRef}>
      <button
        type="button"
        className={`composer-plus-btn touch-target ${open ? 'active' : ''}`}
        onClick={() => setOpen((prev) => !prev)}
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup={isMobile ? 'dialog' : 'menu'}
        aria-label={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
        data-tooltip={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
      >
        <Plus size={16} strokeWidth={2.2} />
      </button>

      {open && !isMobile && (
        <div className="plus-menu-popover" role="menu">
          {renderMenuItems()}
        </div>
      )}

      {isMobile && (
        <BottomSheet
          open={open}
          onClose={() => setOpen(false)}
          title={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
        >
          <div className="composer-tools-sheet" style={{ padding: '8px 12px 20px' }}>
            {renderMenuItems()}
          </div>
        </BottomSheet>
      )}
    </div>
  )
}
