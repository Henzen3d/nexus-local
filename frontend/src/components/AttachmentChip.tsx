import { FileText, Image, FileCode, X, Download, Eye, Paperclip } from 'lucide-react'
import type { Attachment } from '../types'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface Props {
  attachment: Attachment
  readonly?: boolean
  onRemove?: () => void
}

export function AttachmentChip({ attachment, readonly = false, onRemove }: Props) {
  const { t } = useTranslation()
  const [lightboxOpen, setLightboxOpen] = useState(false)
  const [docPreviewOpen, setDocPreviewOpen] = useState(false)

  const formatSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  const getIcon = () => {
    if (attachment.file_type === 'image') return <Image size={14} className="text-green-500" />
    if (attachment.mime_type.includes('csv') || attachment.filename.endsWith('.csv')) {
      return <FileCode size={14} className="text-purple-500" />
    }
    return <FileText size={14} className="text-orange-500" />
  }

  const handleDownload = (e: React.MouseEvent) => {
    e.stopPropagation()
    const a = document.createElement('a')
    a.href = attachment.file_url || `/attachments/${attachment.id}_${attachment.filename}`
    a.download = attachment.filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  // Resolve static files local dev server paths
  const backendUrl = import.meta.env.VITE_API_URL || ''
  const cleanBackendUrl = backendUrl.endsWith('/api') ? backendUrl.slice(0, -4) : backendUrl
  const fileUrl = attachment.file_url ? (attachment.file_url.startsWith('http') ? attachment.file_url : cleanBackendUrl + attachment.file_url) : ''
  const thumbnailUrl = attachment.thumbnail_url ? (attachment.thumbnail_url.startsWith('http') ? attachment.thumbnail_url : cleanBackendUrl + attachment.thumbnail_url) : ''

  return (
    <>
      <div 
        className={`attachment-chip ${readonly ? 'readonly' : 'removable'}`}
        onClick={() => {
          if (readonly) {
            if (attachment.file_type === 'image') {
              setLightboxOpen(true)
            } else if (attachment.file_type === 'document') {
              setDocPreviewOpen(true)
            }
          }
        }}
      >
        {attachment.file_type === 'image' && (attachment.thumbnail_url || attachment.file_url) ? (
          <img 
            src={thumbnailUrl || fileUrl} 
            alt={attachment.filename} 
            className="attachment-chip-thumb" 
            onError={(e) => {
              // Fallback to paperclip on load error
              e.currentTarget.style.display = 'none'
            }}
          />
        ) : (
          <span className="attachment-chip-icon">{getIcon()}</span>
        )}

        <div className="attachment-chip-info">
          <span className="attachment-chip-name" title={attachment.filename}>
            {attachment.filename}
          </span>
          {readonly && (
            <span className="attachment-chip-size">
              {formatSize(attachment.size_bytes)}
            </span>
          )}
        </div>

        {readonly ? (
          <div className="attachment-chip-actions">
            <button 
              type="button" 
              className="attachment-chip-action-btn custom-tooltip-trigger tooltip-up"
              onClick={handleDownload}
              data-tooltip={t('artifacts.download')}
            >
              <Download size={12} />
            </button>
          </div>
        ) : (
          <button 
            type="button" 
            className="attachment-chip-remove custom-tooltip-trigger tooltip-up" 
            onClick={(e) => {
              e.stopPropagation()
              onRemove?.()
            }}
            data-tooltip={t('common.remove')}
          >
            <X size={12} />
          </button>
        )}
      </div>

      {/* Lightbox para Imagens */}
      {lightboxOpen && (
        <div className="confirm-delete-modal-overlay" onClick={() => setLightboxOpen(false)}>
          <div className="lightbox-card" onClick={(e) => e.stopPropagation()}>
            <div className="lightbox-header">
              <span className="lightbox-title">{attachment.filename}</span>
              <div className="flex gap-2">
                <button className="icon-btn custom-tooltip-trigger" onClick={handleDownload} data-tooltip={t('artifacts.downloadOriginal')}>
                  <Download size={16} />
                </button>
                <button className="icon-btn custom-tooltip-trigger" onClick={() => setLightboxOpen(false)} data-tooltip={t('common.close')}>
                  <X size={16} />
                </button>
              </div>
            </div>
            <div className="lightbox-body">
              <img src={fileUrl} alt={attachment.filename} className="lightbox-img" />
            </div>
          </div>
        </div>
      )}

      {/* Modal de visualização de texto para Documentos */}
      {docPreviewOpen && (
        <div className="confirm-delete-modal-overlay" onClick={() => setDocPreviewOpen(false)}>
          <div className="confirm-delete-modal-card doc-preview-modal" onClick={(e) => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4 pb-2 border-b border-hairline">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <FileText size={18} className="text-orange-500" />
                {attachment.filename}
              </h3>
              <div className="flex gap-2">
                <button className="icon-btn custom-tooltip-trigger" onClick={handleDownload} data-tooltip={t('artifacts.download')}>
                  <Download size={14} />
                </button>
                <button className="icon-btn custom-tooltip-trigger" onClick={() => setDocPreviewOpen(false)} data-tooltip={t('common.close')}>
                  <X size={14} />
                </button>
              </div>
            </div>
            <div className="doc-preview-content">
              {attachment.extracted_text ? (
                <pre>{attachment.extracted_text}</pre>
              ) : (
                <div className="doc-preview-loading">
                  {t('chat.loadingDocContent')}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
