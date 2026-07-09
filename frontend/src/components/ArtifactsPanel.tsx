import { useState, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Search, Plus, Eye, Globe, Image, FileText, Atom, FileCode, Clock, Lock, Unlock, Menu } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import type { Artifact } from '../types'

export function ArtifactsPanel() {
  const { t, i18n } = useTranslation()
  const {
    allArtifacts,
    loadAllArtifacts,
    loadConversation,
    setActiveArtifact,
    setArtifactPanelOpen,
    loadArtifactHistory,
    setSidebarOpen,
    sidebarOpen
  } = useStore()

  const [search, setSearch] = useState('')

  useEffect(() => {
    loadAllArtifacts(search)
  }, [search, loadAllArtifacts])

  const handleOpenArtifact = async (art: Artifact) => {
    // Carrega a conversa associada ao artefato
    await loadConversation(art.conv_id)
    // Define o artefato como ativo e abre o painel lateral
    setActiveArtifact(art)
    setArtifactPanelOpen(true)
    if (art.artifact_group_id) {
      await loadArtifactHistory(art.artifact_group_id)
    }
  }

  const renderArtifactPreview = (art: Artifact) => {
    return (
      <div className="artifact-card-preview">
        {/* Eye counter badge */}
        {art.view_count !== undefined && (
          <div className="artifact-views-badge" title={t('common.views', { count: art.view_count })}>
            <Eye size={11} />
            <span>{art.view_count}</span>
          </div>
        )}

        {art.type === 'markdown' ? (
          <ReactMarkdown className="artifact-markdown-preview-render">
            {art.content}
          </ReactMarkdown>
        ) : art.type === 'code' || art.type === 'jsx' ? (
          <div className="artifact-text-preview-code">
            {art.content}
          </div>
        ) : (
          <div className="preview-placeholder-wrapper">
            <div className="placeholder-wireframe">
              {art.type === 'html' && <Globe size={24} />}
              {art.type === 'svg' && <Image size={24} />}
            </div>
          </div>
        )}

        {/* Version badge */}
        {art.version !== undefined && (
          <div className="artifact-version-badge" title={t('common.version', { version: art.version })}>
            <FileText size={10} />
            <span>{art.version}</span>
          </div>
        )}
      </div>
    )
  }

  const getRelativeTime = (dateString: string) => {
    const d = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - d.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 60) {
      return diffMins <= 1 ? t('time.justNow') : t('time.minutesAgo', { count: diffMins })
    } else if (diffHours < 24) {
      return t(diffHours === 1 ? 'time.hoursAgo_one' : 'time.hoursAgo_other', { count: diffHours })
    } else if (diffDays === 1) {
      return t('time.yesterday')
    } else if (diffDays < 7) {
      return t('time.daysAgo', { count: diffDays })
    } else {
      return d.toLocaleDateString(i18n.language, { day: 'numeric', month: 'short' })
    }
  }

  return (
    <div className="artifacts-panel">
      <div className="artifacts-container">
        {/* Header */}
        <header className="artifacts-header">
          <div className="panel-top-bar">
            <div className="panel-top-bar-left">
              {!sidebarOpen && (
                <button
                  className="icon-only-btn"
                  onClick={() => setSidebarOpen(true)}
                  title={t("common.openMenu")}
                  aria-label={t("common.openMenu")}
                >
                  <Menu size={20} />
                </button>
              )}
            </div>
            <div className="panel-top-bar-right">
              <button
                className="btn-primary-new"
                onClick={() => {
                  // Inicia um novo chat para o usuário solicitar criação de artefatos
                  const check = window.confirm(t('artifacts.newChatConfirm'))
                  if (check) {
                    const { startNewConversation } = useStore.getState()
                    startNewConversation()
                    if (window.innerWidth <= 768) setSidebarOpen(false)
                  }
                }}
              >
                <Plus size={14} />
                <span>{t("artifacts.newArtifact")}</span>
              </button>
            </div>
          </div>
          <h1>{t("artifacts.title")}</h1>
        </header>

        {/* Search Input */}
        <div className="search-bar-container">
          <Search className="search-icon-field" size={15} />
          <input
            type="text"
            className="search-input-field"
            placeholder={t('artifacts.searchPlaceholder')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button className="clear-search-btn" onClick={() => setSearch('')}>
              X
            </button>
          )}
        </div>

        {/* Grid content */}
        <div className="artifacts-content-area">
          {allArtifacts.length === 0 ? (
            <div className="panel-empty-state">
              <FileCode size={36} />
              <h3>{t("artifacts.emptyTitle")}</h3>
              <p>
                {search
                  ? t('artifacts.emptySearch')
                  : t('artifacts.emptyHint')}
              </p>
            </div>
          ) : (
            <div className="artifacts-grid">
              {allArtifacts.map((art) => (
                <div
                  key={art.id}
                  className="artifact-card-item"
                  onClick={() => handleOpenArtifact(art)}
                >
                  {renderArtifactPreview(art)}

                  <div className="artifact-card-details">
                    <h4 className="artifact-card-title" title={art.title}>
                      {art.title}
                    </h4>
                    
                    <div className="artifact-card-meta">
                      <div className="meta-time">
                        <Clock size={11} />
                        <span>{t('artifacts.edited', { time: getRelativeTime(art.created_at) })}</span>
                      </div>

                      <div className={`meta-visibility ${art.visibility === 'Publicado' ? 'published' : 'private'}`}>
                        {art.visibility === 'Publicado' ? <Unlock size={10} /> : <Lock size={10} />}
                        <span>{art.visibility === 'Publicado' ? t('artifacts.published') : t('artifacts.private')}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
