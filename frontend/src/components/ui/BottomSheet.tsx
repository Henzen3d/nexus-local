import { useEffect, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface BottomSheetProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  /** Extra class on the sheet panel */
  className?: string
  /** Accessible name when title is omitted */
  ariaLabel?: string
  showHandle?: boolean
  /** Max height of the sheet (CSS value) */
  maxHeight?: string
}

/**
 * Shared mobile bottom sheet: portal, scroll lock, Escape, overlay dismiss,
 * handle + close + title. Works in light and dark via design tokens.
 */
export function BottomSheet({
  open,
  onClose,
  title,
  children,
  className = '',
  ariaLabel,
  showHandle = true,
  maxHeight,
}: BottomSheetProps) {
  const { t } = useTranslation()

  useEffect(() => {
    if (!open) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, onClose])

  useEffect(() => {
    if (!open) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prev
    }
  }, [open])

  if (!open || typeof document === 'undefined') return null

  return createPortal(
    <div className="nl-sheet-overlay" onClick={onClose} role="presentation">
      <div
        className={`nl-sheet ${className}`.trim()}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel || title}
        style={maxHeight ? { maxHeight } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        {showHandle && <div className="nl-sheet-handle" aria-hidden="true" />}
        <div className="nl-sheet-header">
          <button
            type="button"
            className="nl-sheet-close"
            onClick={onClose}
            aria-label={t('common.close')}
          >
            <X size={18} />
          </button>
          <span className="nl-sheet-title">{title || ''}</span>
          <span className="nl-sheet-header-spacer" aria-hidden="true" />
        </div>
        <div className="nl-sheet-body">{children}</div>
      </div>
    </div>,
    document.body
  )
}
