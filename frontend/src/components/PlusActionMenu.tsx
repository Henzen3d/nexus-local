import { useState, useRef, useEffect } from 'react'
import {
  Plus,
  Paperclip,
  Sparkles,
  Loader2,
  Globe,
  Dna,
  Check,
  Camera,
  Image as ImageIcon,
  FolderOpen,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { useIsMobile } from '../hooks/useIsMobile'

interface PlusActionMenuProps {
  onOpenFilePicker: () => void
  onOpenPhotoPicker?: () => void
  onOpenCameraPicker?: () => void
  onOpenLibrary?: () => void
  onEnhance: () => void
  enhancing: boolean
  hasText: boolean
  enhancerReady: boolean
  disabled?: boolean
}

export function PlusActionMenu({
  onOpenFilePicker,
  onOpenPhotoPicker,
  onOpenCameraPicker,
  onOpenLibrary,
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
    uiLevel,
  } = useStore()

  // Fechar ao clicar fora (desktop e mobile)
  useEffect(() => {
    if (!open) return
    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('touchstart', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('touchstart', handleClickOutside)
    }
  }, [open])

  // Fechar ao pressionar Escape
  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open])

  const handleToggleFusion = (e: React.MouseEvent) => {
    e.stopPropagation()
    setFusionMode(!fusionMode)
  }

  const handleToggleWebSearch = (e: React.MouseEvent) => {
    e.stopPropagation()
    setWebSearchActive(!webSearchActive)
  }

  const handleFileClick = () => {
    setOpen(false)
    onOpenFilePicker()
  }

  const handlePhotoClick = () => {
    setOpen(false)
    if (onOpenPhotoPicker) {
      onOpenPhotoPicker()
    } else {
      onOpenFilePicker()
    }
  }

  const handleCameraClick = () => {
    setOpen(false)
    if (onOpenCameraPicker) {
      onOpenCameraPicker()
    } else {
      onOpenFilePicker()
    }
  }

  const handleLibraryClick = () => {
    setOpen(false)
    if (onOpenLibrary) {
      onOpenLibrary()
    } else {
      useStore.getState().setView('library')
    }
  }

  const handleEnhanceClick = () => {
    if (!hasText || !enhancerReady || enhancing) return
    setOpen(false)
    onEnhance()
  }

  /* ────────── Desktop Render ────────── */
  const renderDesktopMenu = () => (
    <div
      className="plus-menu-popover"
      role="menu"
      aria-label={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
    >
      {/* 1. Adicionar fotos e arquivos */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleFileClick}
        role="menuitem"
        aria-label={t('chat.addFiles', { defaultValue: 'Adicionar fotos e arquivos' })}
      >
        <span className="plus-menu-item-icon">
          <Paperclip size={18} strokeWidth={1.8} />
        </span>
        <div className="plus-menu-item-content">
          <span className="plus-menu-item-label">
            {t('chat.addFiles', { defaultValue: 'Adicionar fotos e arquivos' })}
          </span>
          <span className="plus-menu-item-sub">
            {t('chat.addFilesSub', { defaultValue: 'Enviar do computador' })}
          </span>
        </div>
      </button>

      {/* 2. Adicionar da biblioteca */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleLibraryClick}
        role="menuitem"
        aria-label={t('chat.fromLibrary', { defaultValue: 'Adicionar da biblioteca' })}
      >
        <span className="plus-menu-item-icon">
          <FolderOpen size={18} strokeWidth={1.8} />
        </span>
        <div className="plus-menu-item-content">
          <span className="plus-menu-item-label">
            {t('chat.fromLibrary', { defaultValue: 'Adicionar da biblioteca' })}
          </span>
          <span className="plus-menu-item-sub">
            {t('chat.fromLibrarySub', { defaultValue: 'Explore e pesquise seus arquivos' })}
          </span>
        </div>
      </button>

      {/* 3. Melhorar prompt atual */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleEnhanceClick}
        disabled={!hasText || !enhancerReady || enhancing}
        role="menuitem"
        aria-label={t('chat.enhanceTitle', { defaultValue: 'Melhorar prompt atual' })}
      >
        <span className="plus-menu-item-icon">
          {enhancing ? (
            <Loader2 size={18} className="spin" />
          ) : (
            <Sparkles size={18} strokeWidth={1.8} />
          )}
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

      {/* 4. Busca na web */}
      <button
        type="button"
        className="plus-menu-item touch-target"
        onClick={handleToggleWebSearch}
        role="menuitemcheckbox"
        aria-checked={webSearchActive}
        aria-label={t('chat.webSearch', { defaultValue: 'Busca na web' })}
      >
        <span className="plus-menu-item-icon">
          <Globe size={18} strokeWidth={1.8} />
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
          {webSearchActive && (
            <Check size={16} className="plus-menu-check" strokeWidth={2.5} />
          )}
        </div>
      </button>

      {/* 5. Modo Fusion (Intermediário / Avançado) */}
      {uiLevel !== 'simple' && (
        <button
          type="button"
          className="plus-menu-item touch-target"
          onClick={handleToggleFusion}
          role="menuitemcheckbox"
          aria-checked={fusionMode}
          aria-label={t('chat.fusionMode', { defaultValue: 'Modo Fusion' })}
        >
          <span className="plus-menu-item-icon">
            <Dna size={18} strokeWidth={1.8} />
          </span>
          <div className="plus-menu-item-content">
            <span className="plus-menu-item-label">
              {t('chat.fusionMode', { defaultValue: 'Modo Fusion' })}
            </span>
            <span className="plus-menu-item-sub">
              {t('chat.fusionModeSub', {
                defaultValue: 'Combina respostas de múltiplos modelos',
              })}
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
      )}
    </div>
  )

  /* ────────── Mobile Render (Floating Island Pill) ────────── */
  const renderMobileMenu = () => (
    <>
      <div
        className="plus-menu-backdrop"
        onClick={() => setOpen(false)}
        aria-hidden="true"
      />
      <div
        className="plus-mobile-menu"
        role="menu"
        aria-label={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
      >
        {/* 1. Câmera */}
        <button
          type="button"
          className="plus-mobile-item touch-target"
          onClick={handleCameraClick}
          role="menuitem"
          aria-label={t('chat.camera', { defaultValue: 'Câmera' })}
        >
          <div className="plus-mobile-item-icon-badge">
            <Camera size={19} strokeWidth={1.9} />
          </div>
          <span className="plus-mobile-item-label">
            {t('chat.camera', { defaultValue: 'Câmera' })}
          </span>
        </button>

        {/* 2. Fotos */}
        <button
          type="button"
          className="plus-mobile-item touch-target"
          onClick={handlePhotoClick}
          role="menuitem"
          aria-label={t('chat.photos', { defaultValue: 'Fotos' })}
        >
          <div className="plus-mobile-item-icon-badge">
            <ImageIcon size={19} strokeWidth={1.9} />
          </div>
          <span className="plus-mobile-item-label">
            {t('chat.photos', { defaultValue: 'Fotos' })}
          </span>
        </button>

        {/* 3. Arquivos */}
        <button
          type="button"
          className="plus-mobile-item touch-target"
          onClick={handleFileClick}
          role="menuitem"
          aria-label={t('chat.files', { defaultValue: 'Arquivos' })}
        >
          <div className="plus-mobile-item-icon-badge">
            <Paperclip size={19} strokeWidth={1.9} />
          </div>
          <span className="plus-mobile-item-label">
            {t('chat.files', { defaultValue: 'Arquivos' })}
          </span>
        </button>

        {/* 4. Biblioteca */}
        <button
          type="button"
          className="plus-mobile-item touch-target"
          onClick={handleLibraryClick}
          role="menuitem"
          aria-label={t('chat.library', { defaultValue: 'Biblioteca' })}
        >
          <div className="plus-mobile-item-icon-badge">
            <FolderOpen size={19} strokeWidth={1.9} />
          </div>
          <span className="plus-mobile-item-label">
            {t('chat.library', { defaultValue: 'Biblioteca' })}
          </span>
        </button>

        {/* 5. Busca na web */}
        <button
          type="button"
          className="plus-mobile-item touch-target"
          onClick={handleToggleWebSearch}
          role="menuitemcheckbox"
          aria-checked={webSearchActive}
          aria-label={t('chat.webSearch', { defaultValue: 'Busca na web' })}
        >
          <div
            className={`plus-mobile-item-icon-badge ${
              webSearchActive ? 'active-web' : ''
            }`}
          >
            <Globe size={19} strokeWidth={1.9} />
          </div>
          <span className="plus-mobile-item-label">
            {t('chat.webSearch', { defaultValue: 'Busca na web' })}
          </span>
          {webSearchActive && (
            <div className="plus-mobile-item-right">
              <Check size={16} className="plus-menu-check" strokeWidth={2.5} />
            </div>
          )}
        </button>

        {/* 6. Modo Fusion (se intermediário/avançado) */}
        {uiLevel !== 'simple' && (
          <button
            type="button"
            className="plus-mobile-item touch-target"
            onClick={handleToggleFusion}
            role="menuitemcheckbox"
            aria-checked={fusionMode}
            aria-label={t('chat.fusionMode', { defaultValue: 'Modo Fusion' })}
          >
            <div
              className={`plus-mobile-item-icon-badge ${
                fusionMode ? 'active-fusion' : ''
              }`}
            >
              <Dna size={19} strokeWidth={1.9} />
            </div>
            <span className="plus-mobile-item-label">
              {t('chat.fusionMode', { defaultValue: 'Modo Fusion' })}
            </span>
            {fusionMode && (
              <div className="plus-mobile-item-right">
                <Check size={16} className="plus-menu-check" strokeWidth={2.5} />
              </div>
            )}
          </button>
        )}

        {/* 7. Melhorar prompt */}
        <button
          type="button"
          className="plus-mobile-item touch-target"
          onClick={handleEnhanceClick}
          disabled={!hasText || !enhancerReady || enhancing}
          role="menuitem"
          aria-label={t('chat.enhanceTitle', { defaultValue: 'Melhorar prompt atual' })}
        >
          <div className="plus-mobile-item-icon-badge">
            {enhancing ? (
              <Loader2 size={19} className="spin" />
            ) : (
              <Sparkles size={19} strokeWidth={1.9} />
            )}
          </div>
          <span className="plus-mobile-item-label">
            {t('chat.enhanceShort', { defaultValue: 'Melhorar prompt' })}
          </span>
        </button>
      </div>
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
        aria-haspopup="menu"
        aria-label={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
        data-tooltip={t('chat.plusMenu', { defaultValue: 'Ações e ferramentas' })}
      >
        <Plus size={18} strokeWidth={2.2} />
      </button>

      {open && (isMobile ? renderMobileMenu() : renderDesktopMenu())}
    </div>
  )
}
