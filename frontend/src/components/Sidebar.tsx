import { useState, useEffect, useRef } from 'react'
import { MessageSquare, Plus, Trash2, Pencil, Check, X, ChevronLeft, Sparkles, Globe, Image, FileText, Atom, FileCode, Download, LogOut, MoreHorizontal, Star, Sun, Moon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import type { Artifact } from '../types'
import { InstallPWAButton } from './InstallPWAButton'

export function Sidebar() {
  const { t } = useTranslation()
  const {
    conversations,
    activeConversationId,
    loadConversations,
    loadConversation,
    startNewConversation,
    renameConversation,
    deleteConversation,
    favoriteConversation,
    setSidebarOpen,
    setView,
    view,
    activeConversationArtifacts,
    setActiveArtifact,
    setArtifactPanelOpen,
    loadArtifactHistory,
    user,
    displayName,
    logout,
    theme,
    setTheme
  } = useStore()

  const USER_NAME = displayName || user?.username || t('common.user')
  const USER_INITIAL = USER_NAME.charAt(0).toUpperCase()

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  // Gestos de toque no mobile
  const touchRef = useRef({ startX: 0, startY: 0, endX: 0, endY: 0 })

  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    touchRef.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      endX: touch.clientX,
      endY: touch.clientY
    }
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    touchRef.current.endX = touch.clientX
    touchRef.current.endY = touch.clientY
  }

  const handleTouchEnd = () => {
    const { startX, startY, endX, endY } = touchRef.current
    const diffX = startX - endX
    const diffY = startY - endY

    // Verifica se deslizou para a esquerda (gesto de fechar) com limite horizontal preponderante
    if (diffX > 50 && Math.abs(diffX) > Math.abs(diffY) * 1.5) {
      if (window.innerWidth <= 768) {
        setSidebarOpen(false)
      }
    }
  }

  // Toque longo (long press) nas conversas do menu lateral
  const itemLongPressTimeout = useRef<any>(null)
  const isItemLongPressActive = useRef(false)
  const itemTouchStartPos = useRef({ x: 0, y: 0 })

  const handleItemTouchStart = (e: React.TouchEvent, cId: string) => {
    const touch = e.touches[0]
    itemTouchStartPos.current = { x: touch.clientX, y: touch.clientY }
    isItemLongPressActive.current = false

    itemLongPressTimeout.current = setTimeout(() => {
      isItemLongPressActive.current = true
      if (navigator.vibrate) {
        try { navigator.vibrate(20) } catch {}
      }
      setActiveMenuId(cId)
    }, 600)
  }

  const handleItemTouchMove = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    const diffX = Math.abs(touch.clientX - itemTouchStartPos.current.x)
    const diffY = Math.abs(touch.clientY - itemTouchStartPos.current.y)
    if (diffX > 10 || diffY > 10) {
      if (itemLongPressTimeout.current) {
        clearTimeout(itemLongPressTimeout.current)
      }
    }
  }

  const handleItemTouchEnd = (e: React.TouchEvent) => {
    if (itemLongPressTimeout.current) {
      clearTimeout(itemLongPressTimeout.current)
    }
    if (isItemLongPressActive.current) {
      e.preventDefault()
      setTimeout(() => {
        isItemLongPressActive.current = false
      }, 50)
    }
  }

  const handleItemMouseDown = (e: React.MouseEvent, cId: string) => {
    if (e.button !== 0) return
    isItemLongPressActive.current = false
    const x = e.clientX
    const y = e.clientY
    itemTouchStartPos.current = { x, y }

    itemLongPressTimeout.current = setTimeout(() => {
      isItemLongPressActive.current = true
      setActiveMenuId(cId)
    }, 600)
  }

  const handleItemMouseMove = (e: React.MouseEvent) => {
    const diffX = Math.abs(e.clientX - itemTouchStartPos.current.x)
    const diffY = Math.abs(e.clientY - itemTouchStartPos.current.y)
    if (diffX > 10 || diffY > 10) {
      if (itemLongPressTimeout.current) {
        clearTimeout(itemLongPressTimeout.current)
      }
    }
  }

  const handleItemMouseUp = (e: React.MouseEvent) => {
    if (itemLongPressTimeout.current) {
      clearTimeout(itemLongPressTimeout.current)
    }
    if (isItemLongPressActive.current) {
      e.preventDefault()
      e.stopPropagation()
      setTimeout(() => {
        isItemLongPressActive.current = false
      }, 50)
    }
  }

  useEffect(() => {
    loadConversations()
  }, [loadConversations])

  useEffect(() => {
    const handleClose = () => setActiveMenuId(null)
    window.addEventListener('click', handleClose)
    return () => window.removeEventListener('click', handleClose)
  }, [])

  const handleRename = async (id: string) => {
    if (editTitle.trim()) await renameConversation(id, editTitle.trim())
    setEditingId(null)
  }

  const getFileExtension = (type: string) => {
    switch (type) {
      case 'html': return 'html'
      case 'markdown': return 'md'
      case 'svg': return 'svg'
      case 'jsx': return 'jsx'
      default: return 'txt'
    }
  }

  const getMimeType = (type: string) => {
    switch (type) {
      case 'html': return 'text/html'
      case 'markdown': return 'text/markdown'
      case 'svg': return 'image/svg+xml'
      default: return 'text/plain'
    }
  }

  const handleDownloadArtifact = (art: Artifact, e: React.MouseEvent) => {
    e.stopPropagation()
    const mime = getMimeType(art.type)
    const blob = new Blob([art.content], { type: mime })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const safeTitle = art.title.replace(/[^a-z0-9\s-_.]/gi, '')
    const ext = getFileExtension(art.type)
    a.download = safeTitle.toLowerCase().endsWith(`.${ext}`) ? safeTitle : `${safeTitle}.${ext}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const renderArtifactIcon = (type: string) => {
    switch (type) {
      case 'html': return <Globe size={13} className="text-blue-500" />
      case 'svg': return <Image size={13} className="text-green-500" />
      case 'markdown': return <FileText size={13} className="text-orange-500" />
      case 'jsx': return <Atom size={13} className="text-cyan-500" />
      default: return <FileCode size={13} className="text-purple-500" />
    }
  }

  const handleArtifactClick = async (art: Artifact) => {
    setActiveArtifact(art)
    setArtifactPanelOpen(true)
    if (art.artifact_group_id) {
      await loadArtifactHistory(art.artifact_group_id)
    }
  }

  const favorites = conversations
    .filter((c) => c.is_favorite)
    .sort((a, b) => new Date(b.favorited_at || 0).getTime() - new Date(a.favorited_at || 0).getTime())
  
  const grouped = groupByDate(conversations, {
    today: t('time.today'),
    yesterday: t('time.yesterday').replace(/^./, (c) => c.toUpperCase()),
    last7Days: t('time.last7Days'),
    older: t('time.older'),
  })

  const renderConversationRow = (c: typeof conversations[0]) => {
    const isMenuOpen = activeMenuId === c.id

    return (
      <div
        key={c.id}
        className={`conv-item ${c.id === activeConversationId ? 'active' : ''}`}
      >
        {editingId === c.id ? (
          <div className="conv-edit">
            <input
              autoFocus
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRename(c.id)
                if (e.key === 'Escape') setEditingId(null)
              }}
            />
            <button onClick={() => handleRename(c.id)}><Check size={14} /></button>
            <button onClick={() => setEditingId(null)}><X size={14} /></button>
          </div>
        ) : (
          <>
            <button
              className="conv-title"
              onTouchStart={(e) => handleItemTouchStart(e, c.id)}
              onTouchMove={handleItemTouchMove}
              onTouchEnd={handleItemTouchEnd}
              onMouseDown={(e) => handleItemMouseDown(e, c.id)}
              onMouseMove={handleItemMouseMove}
              onMouseUp={handleItemMouseUp}
              onContextMenu={(e) => e.preventDefault()}
              onClick={() => {
                if (isItemLongPressActive.current) {
                  isItemLongPressActive.current = false
                  return
                }
                loadConversation(c.id)
                if (window.innerWidth <= 768) setSidebarOpen(false)
              }}
            >
              <span>{c.title}</span>
            </button>
            <div className="conv-actions-dropdown-container">
              <button
                className="conv-menu-trigger"
                onClick={(e) => {
                  e.stopPropagation()
                  setActiveMenuId(isMenuOpen ? null : c.id)
                }}
                title={t('common.actions')}
              >
                <MoreHorizontal size={13} />
              </button>
              
              {isMenuOpen && (
                <div className="conversation-context-menu" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => {
                      favoriteConversation(c.id)
                      setActiveMenuId(null)
                    }}
                  >
                    <Star
                      size={13}
                      className={c.is_favorite ? "text-amber-500 fill-amber-500" : ""}
                    />
                    <span>{c.is_favorite ? t('sidebar.unfavorite') : t('sidebar.favorite')}</span>
                  </button>
                  <button
                    onClick={() => {
                      setEditingId(c.id)
                      setEditTitle(c.title)
                      setActiveMenuId(null)
                    }}
                  >
                    <Pencil size={13} />
                    <span>{t('sidebar.rename')}</span>
                  </button>
                  <button
                    className="danger"
                    onClick={() => {
                      setConfirmDeleteId(c.id)
                      setActiveMenuId(null)
                    }}
                  >
                    <Trash2 size={13} />
                    <span>{t('sidebar.delete')}</span>
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <aside
      className="sidebar"
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-brand">
          <span className="brand-icon">⬡</span>
          <span className="brand-name">NexusLocal</span>
        </div>
        <button className="icon-btn" onClick={() => setSidebarOpen(false)} title={t('sidebar.closeSidebar')}>
          <ChevronLeft size={18} />
        </button>
      </div>

      <button
        className="new-chat-btn"
        onClick={() => {
          startNewConversation()
          if (window.innerWidth <= 768) setSidebarOpen(false)
        }}
      >
        <Plus size={15} />
        {t('sidebar.newChat')}
      </button>

      <nav className="conv-list">
        <div className="sidebar-fixed-nav">
          <button
            className={`sidebar-fixed-nav-item ${view === 'conversations' ? 'selected' : ''}`}
            onClick={() => {
              setView('conversations')
              if (window.innerWidth <= 768) setSidebarOpen(false)
            }}
          >
            <MessageSquare size={13} />
            <span>{t('sidebar.conversations')}</span>
          </button>
          <button
            className={`sidebar-fixed-nav-item ${view === 'artifacts' ? 'selected' : ''}`}
            onClick={() => {
              setView('artifacts')
              if (window.innerWidth <= 768) setSidebarOpen(false)
            }}
          >
            <Sparkles size={13} />
            <span>{t('sidebar.artifacts')}</span>
          </button>
        </div>

        {favorites.length > 0 && (
          <div className="conv-group">
            <span className="conv-group-label" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Star size={11} className="fill-amber-500 text-amber-500" />
              {t('sidebar.favorites')}
            </span>
            {favorites.map((c) => renderConversationRow(c))}
          </div>
        )}

        {Object.entries(grouped).map(([label, convs]) => (
          <div key={label} className="conv-group">
            <span className="conv-group-label">{label}</span>
            {convs.map((c) => renderConversationRow(c))}
          </div>
        ))}

        {conversations.length === 0 && (
          <div className="empty-state">
            <MessageSquare size={28} />
            <p>{t('sidebar.empty')}</p>
          </div>
        )}
      </nav>

      {activeConversationId && activeConversationArtifacts.length > 0 && (
        <div className="sidebar-artifacts-section">
          <div className="sidebar-artifacts-header">
            <Sparkles size={12} className="text-primary" />
            <span>{t('sidebar.artifacts')}</span>
          </div>
          <div className="sidebar-artifacts-list">
            {activeConversationArtifacts.map((art) => (
              <div key={art.id} className="sidebar-artifact-item">
                <button
                  className="sidebar-artifact-btn"
                  onClick={() => handleArtifactClick(art)}
                  title={art.title}
                >
                  {renderArtifactIcon(art.type)}
                  <span className="sidebar-artifact-title">{art.title}</span>
                  <span className="sidebar-artifact-version">v{art.version}</span>
                </button>
                <button
                  className="sidebar-artifact-download-btn"
                  onClick={(e) => handleDownloadArtifact(art, e)}
                  title={t('sidebar.exportFile')}
                >
                  <Download size={12} />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Footer */}
      <div className="sidebar-footer">
        <InstallPWAButton />
        {/* User card */}
        <div 
          className={`user-card ${view === 'admin' ? 'active' : ''}`} 
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', cursor: 'pointer' }}
          onClick={() => {
            if (view === 'admin') {
              setView('chat')
            } else {
              setView('admin')
              if (window.innerWidth <= 768) setSidebarOpen(false)
            }
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="user-avatar">{USER_INITIAL}</div>
            <div className="user-info">
              <span className="user-name">{USER_NAME}</span>
              <span className="user-plan" style={{ fontSize: '11px', color: 'var(--muted)', display: 'block' }}>{t('sidebar.settings')}</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              className="icon-btn theme-toggle-btn-sidebar"
              onClick={(e) => {
                e.stopPropagation()
                setTheme(theme === 'dark' ? 'light' : 'dark')
              }}
              title={theme === 'dark' ? t('sidebar.themeToLight') : t('sidebar.themeToDark')}
              style={{ color: 'var(--muted)', padding: '6px', borderRadius: 'var(--radius-sm)', transition: 'color 0.15s' }}
              onMouseEnter={(e) => e.currentTarget.style.color = 'var(--primary)'}
              onMouseLeave={(e) => e.currentTarget.style.color = 'var(--muted)'}
            >
              {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </button>
            <button 
              className="icon-btn logout-btn" 
              onClick={(e) => {
                e.stopPropagation()
                logout()
              }} 
              title={t('sidebar.logout')} 
            style={{ color: 'var(--muted)', padding: '6px', borderRadius: 'var(--radius-sm)', transition: 'color 0.15s' }}
            onMouseEnter={(e) => e.currentTarget.style.color = '#ff6b6b'}
            onMouseLeave={(e) => e.currentTarget.style.color = 'var(--muted)'}
          >
            <LogOut size={14} />
          </button>
          </div>
        </div>
      </div>

      {/* Modal de confirmação de exclusão */}
      {confirmDeleteId && (
        <div className="confirm-delete-modal-overlay" onClick={() => setConfirmDeleteId(null)}>
          <div className="confirm-delete-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>{t('sidebar.deleteTitle')}</h3>
            <p>{t('sidebar.deleteBody')}</p>
            <div className="confirm-delete-modal-actions">
              <button className="confirm-delete-btn cancel" onClick={() => setConfirmDeleteId(null)}>
                {t('common.cancel')}
              </button>
              <button
                className="confirm-delete-btn delete"
                onClick={async () => {
                  await deleteConversation(confirmDeleteId)
                  setConfirmDeleteId(null)
                }}
              >
                {t('sidebar.delete')}
              </button>
            </div>
          </div>
        </div>
      )}
    </aside>
  )
}

function groupByDate(
  convs: { id: string; title: string; updated_at: string; message_count: number; created_at: string }[],
  labels: { today: string; yesterday: string; last7Days: string; older: string }
) {
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const yesterday = new Date(today.getTime() - 86400000)
  const week = new Date(today.getTime() - 7 * 86400000)

  const groups: Record<string, typeof convs> = {
    [labels.today]: [],
    [labels.yesterday]: [],
    [labels.last7Days]: [],
    [labels.older]: [],
  }

  for (const c of convs) {
    const d = new Date(c.updated_at)
    if (d >= today) groups[labels.today].push(c)
    else if (d >= yesterday) groups[labels.yesterday].push(c)
    else if (d >= week) groups[labels.last7Days].push(c)
    else groups[labels.older].push(c)
  }

  return Object.fromEntries(Object.entries(groups).filter(([, v]) => v.length > 0))
}
