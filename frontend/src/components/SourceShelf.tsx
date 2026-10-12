import { useState } from 'react'
import { createPortal } from 'react-dom'
import { ExternalLink, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { WebSearchSource } from '../types'
import { useIsMobile } from '../hooks/useIsMobile'
import { BottomSheet } from './ui/BottomSheet'
import { faviconUrl, pageCountKey, sourceHost } from '../lib/sourceCards'

function Favicon({ url, size = 18 }: { url: string; size?: number }) {
  const [failed, setFailed] = useState(false)
  const host = sourceHost(url)
  if (failed) {
    return (
      <span className="source-favicon source-favicon-fallback" style={{ width: size, height: size }} aria-hidden="true">
        {(host[0] || '?').toUpperCase()}
      </span>
    )
  }
  return (
    <img
      className="source-favicon"
      src={faviconUrl(url)}
      alt=""
      width={size}
      height={size}
      style={{ width: size, height: size }}
      onError={() => setFailed(true)}
    />
  )
}

function SourceCards({ sources }: { sources: WebSearchSource[] }) {
  return (
    <div className="source-card-list">
      {sources.map((source) => (
        <a
          key={source.url}
          className="source-card"
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
        >
          <div className="source-card-title">{source.title || sourceHost(source.url)}</div>
          {source.snippet && <p className="source-card-snippet">{source.snippet}</p>}
          <div className="source-card-foot">
            <Favicon url={source.url} size={16} />
            <span className="source-card-host">{sourceHost(source.url)}</span>
            <ExternalLink size={14} className="source-card-open" aria-hidden="true" />
          </div>
        </a>
      ))}
    </div>
  )
}

function SourceSidePanel({ title, onClose, sources }: { title: string; onClose: () => void; sources: WebSearchSource[] }) {
  const { t } = useTranslation()
  if (typeof document === 'undefined') return null
  return createPortal(
    <div className="source-panel-overlay" onClick={onClose} role="presentation">
      <aside
        className="source-panel"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="source-panel-header">
          <h2>{title}</h2>
          <button type="button" className="source-panel-close" onClick={onClose} aria-label={t('common.close')}>
            <X size={18} />
          </button>
        </header>
        <div className="source-panel-body">
          <SourceCards sources={sources} />
        </div>
      </aside>
    </div>,
    document.body,
  )
}

export function SourceShelf({ sources }: { sources: WebSearchSource[] }) {
  const { t } = useTranslation()
  const isMobile = useIsMobile()
  const [open, setOpen] = useState(false)
  if (!sources.length) return null

  const preview = sources.slice(0, 4)
  const title = t('chat.webResults', { defaultValue: 'Resultados da web' })
  const countLabel = t(pageCountKey(sources.length), { count: sources.length, defaultValue: `${sources.length} páginas` })

  return (
    <>
      <button type="button" className="source-chip" onClick={() => setOpen(true)} aria-expanded={open}>
        <span className="source-chip-favs" aria-hidden="true">
          {preview.map((source) => <Favicon key={source.url} url={source.url} />)}
        </span>
        <span>{countLabel}</span>
      </button>
      {isMobile ? (
        <BottomSheet open={open} onClose={() => setOpen(false)} title={title} maxHeight="88vh">
          <SourceCards sources={sources} />
        </BottomSheet>
      ) : (
        open && <SourceSidePanel title={title} onClose={() => setOpen(false)} sources={sources} />
      )}
    </>
  )
}
