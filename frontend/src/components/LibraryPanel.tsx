import React, { useState, useEffect } from 'react'
import {
  Search, Plus, Eye, Image as ImageIcon, FileText, Download, Trash2,
  Menu, X, Sparkles, LayoutGrid, List, MessageSquare, Loader2, ArrowUpRight
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import type { LibraryItem } from '../types'
import { ImageLightbox } from './ImageLightbox'

export function LibraryPanel() {
  const { t, i18n } = useTranslation()
  const {
    libraryItems,
    libraryLoading,
    libraryFilter,
    librarySearch,
    setLibraryFilter,
    setLibrarySearch,
    loadLibrary,
    deleteLibraryItem,
    loadConversation,
    setView,
    setSidebarOpen,
    sidebarOpen,
    startNewConversation,
  } = useStore()

  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid')
  const [lightboxItem, setLightboxItem] = useState<LibraryItem | null>(null)
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null)

  useEffect(() => {
    loadLibrary()
  }, [])

  const backendUrl = import.meta.env.VITE_API_URL || ''
  const cleanBackendUrl = backendUrl.endsWith('/api') ? backendUrl.slice(0, -4) : backendUrl

  const resolveUrl = (path?: string | null) => {
    if (!path) return ''
    if (path.startsWith('http')) return path
    return cleanBackendUrl + path
  }

  const formatSize = (bytes: number) => {
    if (!bytes || bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  const getRelativeTime = (dateString: string) => {
    if (!dateString) return ''
    const d = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 60) {
      return diffMins <= 1 ? t('time.justNow', { defaultValue: 'agora há pouco' }) : t('time.minutesAgo', { count: diffMins, defaultValue: `há ${diffMins} min` })
    } else if (diffHours < 24) {
      return t(diffHours === 1 ? 'time.hoursAgo_one' : 'time.hoursAgo_other', { count: diffHours, defaultValue: `há ${diffHours} h` })
    } else if (diffDays === 1) {
      return t('time.yesterday', { defaultValue: 'ontem' })
    } else if (diffDays < 7) {
      return t('time.daysAgo', { count: diffDays, defaultValue: `há ${diffDays} dias` })
    } else {
      return d.toLocaleDateString(i18n.language, { day: 'numeric', month: 'short' })
    }
  }

  const handleOpenConversation = async (convId?: string | null) => {
    if (!convId) return
    await loadConversation(convId)
    setView('chat')
    if (window.innerWidth <= 768) setSidebarOpen(false)
  }

  const handleDownload = (e: React.MouseEvent, item: LibraryItem) => {
    e.stopPropagation()
    const a = document.createElement('a')
    a.href = resolveUrl(item.file_url)
    a.download = item.filename || 'download'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }

  const handleDelete = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    await deleteLibraryItem(id)
    setDeleteConfirmId(null)
  }

  const handleNewImagePrompt = (promptText?: string) => {
    startNewConversation()
    setView('chat')
    if (window.innerWidth <= 768) setSidebarOpen(false)
    if (promptText) {
      setTimeout(() => {
        const textarea = document.querySelector('.composer-textarea') as HTMLTextAreaElement
        if (textarea) {
          textarea.value = promptText
          textarea.dispatchEvent(new Event('input', { bubbles: true }))
          textarea.focus()
        }
      }, 100)
    }
  }

  return (
    <div className="library-panel list-panel">
      <div className="library-container list-panel-inner">
        {/* Header */}
        <header className="list-panel-header library-header">
          <div className="list-panel-title-row">
            {!sidebarOpen && (
              <button
                type="button"
                className="icon-only-btn touch-target"
                onClick={() => setSidebarOpen(true)}
                title={t('common.openMenu', { defaultValue: 'Abrir menu' })}
                aria-label={t('common.openMenu', { defaultValue: 'Abrir menu' })}
              >
                <Menu size={20} />
              </button>
            )}
            <div className="library-title-group">
              <h1>{t('library.title', { defaultValue: 'Biblioteca' })}</h1>
              <span className="library-count-badge">{libraryItems.length}</span>
            </div>

            <div className="list-panel-actions">
              <div className="library-view-toggle">
                <button
                  type="button"
                  className={`library-toggle-btn ${viewMode === 'grid' ? 'active' : ''}`}
                  onClick={() => setViewMode('grid')}
                  title={t('library.gridView', { defaultValue: 'Grade' })}
                  aria-label={t('library.gridView', { defaultValue: 'Grade' })}
                >
                  <LayoutGrid size={16} />
                </button>
                <button
                  type="button"
                  className={`library-toggle-btn ${viewMode === 'list' ? 'active' : ''}`}
                  onClick={() => setViewMode('list')}
                  title={t('library.listView', { defaultValue: 'Lista' })}
                  aria-label={t('library.listView', { defaultValue: 'Lista' })}
                >
                  <List size={16} />
                </button>
              </div>

              <button
                type="button"
                className="claude-btn-primary"
                onClick={() => handleNewImagePrompt('Crie uma imagem ')}
              >
                <Plus size={16} strokeWidth={2.2} />
                <span>{t('library.newImage', { defaultValue: 'Nova Imagem' })}</span>
              </button>
            </div>
          </div>

          {/* Barra de busca padronizada idêntica a Projetos, Conversas e Artefatos */}
          <div className="search-bar-container">
            <Search className="search-icon-field" size={15} />
            <input
              type="search"
              placeholder={t('library.searchPlaceholder', { defaultValue: 'Buscar por nome, prompt ou conversa…' })}
              value={librarySearch}
              onChange={(e) => setLibrarySearch(e.target.value)}
              className="search-input-field"
            />
            {librarySearch && (
              <button
                type="button"
                className="clear-search-btn"
                onClick={() => setLibrarySearch('')}
                aria-label={t('common.clear', { defaultValue: 'Limpar' })}
              >
                <X size={14} />
              </button>
            )}
          </div>

          {/* Filtros de categoria em pills */}
          <div className="library-filter-pills">
            <button
              type="button"
              className={`library-filter-pill ${libraryFilter === 'all' ? 'active' : ''}`}
              onClick={() => setLibraryFilter('all')}
            >
              {t('library.all', { defaultValue: 'Tudo' })}
            </button>
            <button
              type="button"
              className={`library-filter-pill ${libraryFilter === 'generated' ? 'active' : ''}`}
              onClick={() => setLibraryFilter('generated')}
            >
              <Sparkles size={13} className="text-amber-400" />
              {t('library.generated', { defaultValue: 'Geradas por IA' })}
            </button>
            <button
              type="button"
              className={`library-filter-pill ${libraryFilter === 'image' ? 'active' : ''}`}
              onClick={() => setLibraryFilter('image')}
            >
              <ImageIcon size={13} />
              {t('library.images', { defaultValue: 'Imagens' })}
            </button>
            <button
              type="button"
              className={`library-filter-pill ${libraryFilter === 'document' ? 'active' : ''}`}
              onClick={() => setLibraryFilter('document')}
            >
              <FileText size={13} />
              {t('library.documents', { defaultValue: 'Documentos' })}
            </button>
          </div>
        </header>

        {/* Body / Content */}
        <div className="library-body custom-scrollbar">
          {libraryLoading ? (
            <div className="library-loading-state">
              <Loader2 size={28} className="spinner" />
              <span>{t('common.loading', { defaultValue: 'Carregando…' })}</span>
            </div>
          ) : libraryItems.length === 0 ? (
            <div className="library-empty-state">
              <div className="library-empty-icon-wrap">
                <Sparkles size={36} />
              </div>
              <h3>{t('library.emptyTitle', { defaultValue: 'Nenhum arquivo na biblioteca' })}</h3>
              <p>{t('library.emptyDesc', { defaultValue: 'Gere imagens com IA no chat ou anexe arquivos nas conversas para acessá-los aqui.' })}</p>

              <div className="library-suggestions-box">
                <span className="library-suggestions-title">{t('library.suggestionsLabel', { defaultValue: 'Sugestões para experimentar:' })}</span>
                <div className="library-suggestions-grid">
                  <button
                    type="button"
                    className="library-suggestion-chip"
                    onClick={() => handleNewImagePrompt('Crie uma imagem fotográfica hiper-realista de um gato com iluminação cinematográfica e lente 85mm')}
                  >
                    <Sparkles size={14} />
                    <span>Fotografia cinematográfica de animal</span>
                    <ArrowUpRight size={13} />
                  </button>
                  <button
                    type="button"
                    className="library-suggestion-chip"
                    onClick={() => handleNewImagePrompt('Crie uma ilustração futurista de uma cidade cyberpunk à noite com luzes neon e chuva')}
                  >
                    <Sparkles size={14} />
                    <span>Metrópole cyberpunk neon</span>
                    <ArrowUpRight size={13} />
                  </button>
                  <button
                    type="button"
                    className="library-suggestion-chip"
                    onClick={() => handleNewImagePrompt('Crie uma pintura artística em aquarela de montanhas ao pôr do sol')}
                  >
                    <Sparkles size={14} />
                    <span>Aquarela artística ao pôr do sol</span>
                    <ArrowUpRight size={13} />
                  </button>
                </div>
              </div>
            </div>
          ) : viewMode === 'grid' ? (
            <div className="library-grid">
              {libraryItems.map((item) => {
                const imgUrl = resolveUrl(item.thumbnail_url || item.file_url)
                const isImage = item.file_type === 'image'

                return (
                  <div
                    key={item.id}
                    className="library-card"
                    onClick={() => {
                      if (isImage) {
                        setLightboxItem(item)
                      } else {
                        handleOpenConversation(item.conversation_id)
                      }
                    }}
                  >
                    <div className="library-card-media-wrap">
                      {isImage ? (
                        <img
                          src={imgUrl}
                          alt={item.prompt || item.filename}
                          className="library-card-img"
                          loading="lazy"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none'
                          }}
                        />
                      ) : (
                        <div className="library-card-doc-placeholder">
                          <FileText size={38} className="text-accent" />
                          <span className="library-card-ext">
                            {item.filename.split('.').pop()?.toUpperCase() || 'DOC'}
                          </span>
                        </div>
                      )}

                      {/* AI Generated Badge */}
                      {item.is_generated && (
                        <div className="library-badge-ai" title={item.model_id || 'FLUX.1'}>
                          <Sparkles size={11} />
                          <span>FLUX.1</span>
                        </div>
                      )}

                      {/* Size Badge */}
                      <div className="library-badge-size">
                        {formatSize(item.size_bytes)}
                      </div>

                      {/* Hover action overlay */}
                      <div className="library-card-overlay">
                        {isImage && (
                          <button
                            type="button"
                            className="library-action-btn"
                            title={t('common.view', { defaultValue: 'Visualizar' })}
                            onClick={(e) => {
                              e.stopPropagation()
                              setLightboxItem(item)
                            }}
                          >
                            <Eye size={15} />
                          </button>
                        )}
                        {item.conversation_id && (
                          <button
                            type="button"
                            className="library-action-btn"
                            title={t('library.openInChat', { defaultValue: 'Ver na conversa' })}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleOpenConversation(item.conversation_id)
                            }}
                          >
                            <MessageSquare size={15} />
                          </button>
                        )}
                        <button
                          type="button"
                          className="library-action-btn"
                          title={t('library.download', { defaultValue: 'Baixar' })}
                          onClick={(e) => handleDownload(e, item)}
                        >
                          <Download size={15} />
                        </button>
                        <button
                          type="button"
                          className="library-action-btn danger"
                          title={t('library.delete', { defaultValue: 'Excluir arquivo' })}
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteConfirmId(item.id)
                          }}
                        >
                          <Trash2 size={15} />
                        </button>
                      </div>
                    </div>

                    {/* Card Footer */}
                    <div className="library-card-info">
                      <div className="library-card-title-row">
                        <span className="library-card-filename" title={item.filename}>
                          {item.filename}
                        </span>
                        <span className="library-card-date">{getRelativeTime(item.created_at)}</span>
                      </div>

                      {item.prompt && (
                        <p className="library-card-prompt" title={item.prompt}>
                          "{item.prompt}"
                        </p>
                      )}

                      {item.conversation_title && (
                        <div
                          className="library-card-conv"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleOpenConversation(item.conversation_id)
                          }}
                          title={item.conversation_title}
                        >
                          <MessageSquare size={12} />
                          <span>{item.conversation_title}</span>
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          ) : (
            <div className="library-list-table-wrapper">
              <table className="library-list-table">
                <thead>
                  <tr>
                    <th>{t('library.preview', { defaultValue: 'Prévia' })}</th>
                    <th>{t('library.name', { defaultValue: 'Nome' })}</th>
                    <th>{t('library.type', { defaultValue: 'Tipo' })}</th>
                    <th>{t('library.conversation', { defaultValue: 'Conversa' })}</th>
                    <th>{t('library.size', { defaultValue: 'Tamanho' })}</th>
                    <th>{t('library.date', { defaultValue: 'Data' })}</th>
                    <th style={{ textAlign: 'right' }}>{t('common.actions', { defaultValue: 'Ações' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {libraryItems.map((item) => {
                    const isImage = item.file_type === 'image'
                    const imgUrl = resolveUrl(item.thumbnail_url || item.file_url)

                    return (
                      <tr key={item.id} onClick={() => isImage ? setLightboxItem(item) : handleOpenConversation(item.conversation_id)}>
                        <td style={{ width: '48px' }}>
                          {isImage ? (
                            <img src={imgUrl} alt={item.filename} className="library-table-thumb" />
                          ) : (
                            <div className="library-table-doc-thumb">
                              <FileText size={18} />
                            </div>
                          )}
                        </td>
                        <td>
                          <div className="library-table-name-wrap">
                            <span className="library-table-filename">{item.filename}</span>
                            {item.prompt && (
                              <span className="library-table-prompt" title={item.prompt}>
                                {item.prompt}
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          {item.is_generated ? (
                            <span className="library-pill-tag ai">
                              <Sparkles size={10} /> IA (FLUX.1)
                            </span>
                          ) : (
                            <span className="library-pill-tag">
                              {item.file_type === 'image' ? 'Imagem' : 'Documento'}
                            </span>
                          )}
                        </td>
                        <td>
                          {item.conversation_title ? (
                            <button
                              type="button"
                              className="library-table-conv-link"
                              onClick={(e) => {
                                e.stopPropagation()
                                handleOpenConversation(item.conversation_id)
                              }}
                            >
                              {item.conversation_title}
                            </button>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>
                        <td>{formatSize(item.size_bytes)}</td>
                        <td>{getRelativeTime(item.created_at)}</td>
                        <td style={{ textAlign: 'right' }}>
                          <div className="library-table-actions">
                            {isImage && (
                              <button
                                type="button"
                                className="icon-btn-subtle"
                                title={t('common.view', { defaultValue: 'Visualizar' })}
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setLightboxItem(item)
                                }}
                              >
                                <Eye size={14} />
                              </button>
                            )}
                            <button
                              type="button"
                              className="icon-btn-subtle"
                              title={t('library.download', { defaultValue: 'Baixar' })}
                              onClick={(e) => handleDownload(e, item)}
                            >
                              <Download size={14} />
                            </button>
                            <button
                              type="button"
                              className="icon-btn-subtle danger"
                              title={t('library.delete', { defaultValue: 'Excluir arquivo' })}
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeleteConfirmId(item.id)
                              }}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Delete confirmation modal */}
      {deleteConfirmId && (
        <div className="modal-backdrop" onClick={() => setDeleteConfirmId(null)}>
          <div className="modal-content-compact" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>{t('library.deleteConfirmTitle', { defaultValue: 'Excluir arquivo?' })}</h3>
              <button
                type="button"
                className="modal-close-btn"
                onClick={() => setDeleteConfirmId(null)}
              >
                <X size={16} />
              </button>
            </div>
            <p className="modal-body-text">
              {t('library.deleteConfirm', { defaultValue: 'Tem certeza que deseja excluir este arquivo da sua biblioteca? Esta ação não pode ser desfeita.' })}
            </p>
            <div className="modal-footer">
              <button
                type="button"
                className="modal-btn-cancel"
                onClick={() => setDeleteConfirmId(null)}
              >
                {t('common.cancel', { defaultValue: 'Cancelar' })}
              </button>
              <button
                type="button"
                className="modal-btn-danger"
                onClick={(e) => handleDelete(e, deleteConfirmId)}
              >
                <Trash2 size={14} />
                <span>{t('common.delete', { defaultValue: 'Apagar' })}</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Lightbox */}
      {lightboxItem && (
        <ImageLightbox
          src={resolveUrl(lightboxItem.file_url)}
          alt={lightboxItem.prompt || lightboxItem.filename}
          onClose={() => setLightboxItem(null)}
        />
      )}
    </div>
  )
}
