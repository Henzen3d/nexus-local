import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { Download, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'

type View = { scale: number; tx: number; ty: number }

function clampScale(value: number) {
  return Math.min(4, Math.max(1, value))
}

function clampView(next: View, img: HTMLImageElement | null): View {
  const scale = clampScale(next.scale)
  if (!img || scale <= 1.01) return { scale: 1, tx: 0, ty: 0 }
  const maxX = (img.offsetWidth * (scale - 1)) / 2
  const maxY = (img.offsetHeight * (scale - 1)) / 2
  return {
    scale,
    tx: Math.min(maxX, Math.max(-maxX, next.tx)),
    ty: Math.min(maxY, Math.max(-maxY, next.ty)),
  }
}

function touchDistance(touches: TouchList) {
  const [a, b] = [touches[0], touches[1]]
  return Math.hypot(a.clientX - b.clientX, a.clientY - b.clientY)
}

function touchMidpoint(touches: TouchList) {
  const [a, b] = [touches[0], touches[1]]
  return { x: (a.clientX + b.clientX) / 2, y: (a.clientY + b.clientY) / 2 }
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
  const [view, setView] = useState<View>({ scale: 1, tx: 0, ty: 0 })
  const viewRef = useRef(view)
  const imgRef = useRef<HTMLImageElement>(null)
  const stageRef = useRef<HTMLDivElement>(null)
  const gesture = useRef<
    | { kind: 'pinch'; dist: number; scale: number; mx: number; my: number; tx: number; ty: number }
    | { kind: 'pan'; x: number; y: number; tx: number; ty: number }
    | null
  >(null)

  const apply = (next: View) => {
    const clamped = clampView(next, imgRef.current)
    viewRef.current = clamped
    setView(clamped)
  }

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
      const current = viewRef.current
      apply({
        ...current,
        scale: current.scale + (event.deltaY < 0 ? 0.25 : -0.25),
      })
    }

    const onTouchStart = (event: TouchEvent) => {
      const current = viewRef.current
      if (event.touches.length === 2) {
        const mid = touchMidpoint(event.touches)
        gesture.current = {
          kind: 'pinch',
          dist: touchDistance(event.touches),
          scale: current.scale,
          mx: mid.x,
          my: mid.y,
          tx: current.tx,
          ty: current.ty,
        }
      } else if (event.touches.length === 1 && current.scale > 1) {
        const touch = event.touches[0]
        gesture.current = {
          kind: 'pan',
          x: touch.clientX,
          y: touch.clientY,
          tx: current.tx,
          ty: current.ty,
        }
      }
    }

    const onTouchMove = (event: TouchEvent) => {
      const active = gesture.current
      if (!active) return
      event.preventDefault()
      if (active.kind === 'pan' && event.touches.length === 1) {
        const touch = event.touches[0]
        apply({
          scale: viewRef.current.scale,
          tx: active.tx + (touch.clientX - active.x),
          ty: active.ty + (touch.clientY - active.y),
        })
      } else if (active.kind === 'pinch' && event.touches.length === 2) {
        const mid = touchMidpoint(event.touches)
        apply({
          scale: active.scale * (touchDistance(event.touches) / active.dist),
          tx: active.tx + (mid.x - active.mx),
          ty: active.ty + (mid.y - active.my),
        })
      }
    }

    const onTouchEnd = (event: TouchEvent) => {
      if (event.touches.length === 1 && viewRef.current.scale > 1) {
        const touch = event.touches[0]
        gesture.current = {
          kind: 'pan',
          x: touch.clientX,
          y: touch.clientY,
          tx: viewRef.current.tx,
          ty: viewRef.current.ty,
        }
        return
      }
      gesture.current = null
    }

    stage.addEventListener('wheel', onWheel, { passive: false })
    stage.addEventListener('touchstart', onTouchStart, { passive: true })
    stage.addEventListener('touchmove', onTouchMove, { passive: false })
    stage.addEventListener('touchend', onTouchEnd)
    stage.addEventListener('touchcancel', onTouchEnd)
    return () => {
      stage.removeEventListener('wheel', onWheel)
      stage.removeEventListener('touchstart', onTouchStart)
      stage.removeEventListener('touchmove', onTouchMove)
      stage.removeEventListener('touchend', onTouchEnd)
      stage.removeEventListener('touchcancel', onTouchEnd)
    }
  }, [])

  return createPortal(
    <div className="image-viewer-overlay" onClick={onClose} role="dialog" aria-modal="true">
      <div className="image-viewer" onClick={(event) => event.stopPropagation()}>
        <div className="image-viewer-bar">
          <span className="image-viewer-title">{alt}</span>
          <div className="image-viewer-actions">
            <button type="button" onClick={() => apply({ ...viewRef.current, scale: viewRef.current.scale - 0.5 })} aria-label={t('chat.zoomOut', { defaultValue: 'Diminuir' })}>
              −
            </button>
            <button type="button" onClick={() => apply({ scale: 1, tx: 0, ty: 0 })} aria-label={t('chat.zoomReset', { defaultValue: 'Tamanho original' })}>
              {Math.round(view.scale * 100)}%
            </button>
            <button type="button" onClick={() => apply({ ...viewRef.current, scale: viewRef.current.scale + 0.5 })} aria-label={t('chat.zoomIn', { defaultValue: 'Aumentar' })}>
              +
            </button>
            <button type="button" onClick={onClose} aria-label={t('common.close', { defaultValue: 'Fechar' })}>
              <X size={18} />
            </button>
          </div>
        </div>
        <div
          ref={stageRef}
          className={`image-viewer-stage${view.scale > 1 ? ' is-zoomed' : ''}`}
          onPointerDown={(event) => {
            if (event.pointerType === 'touch' || view.scale <= 1) return
            const current = viewRef.current
            gesture.current = {
              kind: 'pan',
              x: event.clientX,
              y: event.clientY,
              tx: current.tx,
              ty: current.ty,
            }
            event.currentTarget.setPointerCapture(event.pointerId)
          }}
          onPointerMove={(event) => {
            const active = gesture.current
            if (!active || active.kind !== 'pan' || event.pointerType === 'touch') return
            apply({
              scale: viewRef.current.scale,
              tx: active.tx + (event.clientX - active.x),
              ty: active.ty + (event.clientY - active.y),
            })
          }}
          onPointerUp={(event) => {
            if (event.pointerType === 'touch') return
            gesture.current = null
          }}
        >
          <img
            ref={imgRef}
            src={src}
            alt={alt}
            className="image-viewer-img"
            style={{ transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})` }}
            draggable={false}
            onDoubleClick={() => apply(view.scale > 1 ? { scale: 1, tx: 0, ty: 0 } : { scale: 2, tx: 0, ty: 0 })}
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
