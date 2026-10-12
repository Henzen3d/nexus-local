import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Download, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

function clampScale(value: number) {
  return Math.min(4, Math.max(1, value))
}

export function ImageLightbox({
  src,
  alt,
  onClose,
}: {
  src: string
  alt: string
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [scale, setScale] = useState(1)
  const pinch = useRef<{ dist: number; scale: number } | null>(null)
  const stageRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [onClose])

  useEffect(() => {
    const stage = stageRef.current
    if (!stage) return
    const onWheel = (event: WheelEvent) => {
      event.preventDefault()
      setScale((current) => clampScale(current + (event.deltaY < 0 ? 0.25 : -0.25)))
    }
    stage.addEventListener('wheel', onWheel, { passive: false })
    return () => stage.removeEventListener('wheel', onWheel)
  }, [])

  const touchDistance = (touches: React.TouchList) => {
    const [a, b] = [touches[0], touches[1]]
    return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
  }

  return createPortal(
    <div className="image-viewer-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="image-viewer" onClick={(event) => event.stopPropagation()}>
        <div className="image-viewer-bar">
          <span className="image-viewer-title">{alt}</span>
          <div className="image-viewer-actions">
            <button type="button" onClick={() => setScale((current) => clampScale(current - 0.5))} aria-label={t('chat.zoomOut', { defaultValue: 'Diminuir' })}>
              −
            </button>
            <button type="button" onClick={() => setScale(1)} aria-label={t('chat.zoomReset', { defaultValue: 'Tamanho original' })}>
              {Math.round(scale * 100)}%
            </button>
            <button type="button" onClick={() => setScale((current) => clampScale(current + 0.5))} aria-label={t('chat.zoomIn', { defaultValue: 'Aumentar' })}>
              +
            </button>
            <button type="button" onClick={onClose} aria-label={t('common.close', { defaultValue: 'Fechar' })}>
              <X size={18} />
            </button>
          </div>
        </div>
        <div
          ref={stageRef}
          className="image-viewer-stage"
          onTouchStart={(event) => {
            if (event.touches.length === 2) {
              pinch.current = { dist: touchDistance(event.touches), scale }
            }
          }}
          onTouchMove={(event) => {
            if (event.touches.length === 2 && pinch.current) {
              const next = pinch.current.scale * (touchDistance(event.touches) / pinch.current.dist)
              setScale(clampScale(next))
            }
          }}
          onTouchEnd={() => {
            pinch.current = null
          }}
        >
          <img
            src={src}
            alt={alt}
            className="image-viewer-img"
            style={{ transform: `scale(${scale})` }}
            draggable={false}
            onDoubleClick={() => setScale((current) => (current > 1 ? 1 : 2))}
          />
        </div>
      </div>
    </div>,
    document.body,
  )
}

export function GeneratedImage({ fileUrl, filename }: { fileUrl: string; filename: string }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  if (!fileUrl) return null

  return (
    <>
      <div className="generated-image-card">
        <button
          type="button"
          className="generated-image-open"
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
            setOpen(true)
          }}
        >
          <img src={fileUrl} alt={filename} />
        </button>
        <div className="generated-image-foot">
          <span>{filename}</span>
          <a
            href={fileUrl}
            download={filename}
            onClick={(event) => event.stopPropagation()}
          >
            <Download size={13} /> {t('chat.download', { defaultValue: 'Baixar' })}
          </a>
        </div>
      </div>
      {open && <ImageLightbox src={fileUrl} alt={filename} onClose={() => setOpen(false)} />}
    </>
  )
}
