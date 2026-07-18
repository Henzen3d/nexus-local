import { useState, useEffect, useRef, useCallback, useLayoutEffect } from 'react'
import { createPortal } from 'react-dom'
import {
  MessageSquare, Trash2, Pencil, Check, X, ChevronRight,
  Sparkles, Globe, Image, FileText, Atom, FileCode, Download, LogOut,
  MoreVertical, Star, Sun, Moon, Folder, Search, PanelLeftClose, PanelLeftOpen, Plus,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import type { Artifact, Project } from '../types'
import { InstallPWAButton } from './InstallPWAButton'
import { Button } from './ui/Button'
import { NexusLogoIcon } from './NexusLogoIcon'
import { useHaptic } from '../hooks/useHaptic'
import { MOBILE_BREAKPOINT, useIsMobile } from '../hooks/useIsMobile'

type AnchorRect = { top: number; left: number; right: number; bottom: number; width: number; height: number }

function toAnchor(el: DOMRect | HTMLElement): AnchorRect {
  const r = el instanceof DOMRect ? el : el.getBoundingClientRect()
  return { top: r.top, left: r.left, right: r.right, bottom: r.bottom, width: r.width, height: r.height }
}

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
    sidebarOpen,
    setSidebarOpen,
    setView,
    setConversationProjectId,
    setProjectName,
    showToast,
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

  const isMobile = useIsMobile()
  const USER_NAME = displayName || user?.username || t('common.user')
  const USER_INITIAL = USER_NAME.charAt(0).toUpperCase()

  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null)
  const [menuAnchor, setMenuAnchor] = useState<AnchorRect | null>(null)
  const [projectFlyoutOpen, setProjectFlyoutOpen] = useState(false)
  const [flyoutAnchor, setFlyoutAnchor] = useState<AnchorRect | null>(null)
  const [projectList, setProjectList] = useState<Project[]>([])
  const [projectSearch, setProjectSearch] = useState('')
  const [projectsLoading, setProjectsLoading] = useState(false)
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({})
  const [searchOpen, setSearchOpen] = useState(false)
  const [sidebarSearch, setSidebarSearch] = useState('')
  const menuRef = useRef<HTMLDivElement | null>(null)
  const flyoutRef = useRef<HTMLDivElement | null>(null)
  const projectBtnRef = useRef<HTMLButtonElement | null>(null)
  const searchInputRef = useRef<HTMLInputElement | null>(null)

  const closeConvMenu = useCallback(() => {
    setActiveMenuId(null)
    setMenuAnchor(null)
    setProjectFlyoutOpen(false)
    setFlyoutAnchor(null)
    setProjectSearch('')
  }, [])

  const loadProjectsForFlyout = useCallback(async () => {
    setProjectsLoading(true)
    try {
      const list = await api.listProjects('updated')
      setProjectList(list)
      list.forEach((p) => setProjectName(p.id, p.name))
    } catch (e) {
      console.error(e)
    } finally {
      setProjectsLoading(false)
    }
  }, [setProjectName])

  const openProjectFlyout = useCallback(() => {
    const btn = projectBtnRef.current
    if (btn) setFlyoutAnchor(toAnchor(btn))
    setProjectFlyoutOpen(true)
    loadProjectsForFlyout()
  }, [loadProjectsForFlyout])

  // Close on outside click / Escape / scroll
  useEffect(() => {
    if (!activeMenuId) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (menuRef.current?.contains(t) || flyoutRef.current?.contains(t)) return
      closeConvMenu()
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeConvMenu()
        return
      }
      // Atalhos visuais do menu Claude (P / R / D)
      if (!activeMenuId) return
      const conv = conversations.find((x) => x.id === activeMenuId)
      if (!conv) return
      const k = e.key.toLowerCase()
      if (k === 'p') {
        e.preventDefault()
        favoriteConversation(conv.id)
        closeConvMenu()
      } else if (k === 'r') {
        e.preventDefault()
        setEditingId(conv.id)
        setEditTitle(conv.title)
        closeConvMenu()
      } else if (k === 'd') {
        e.preventDefault()
        setConfirmDeleteId(conv.id)
        closeConvMenu()
      }
    }
    const onScroll = () => closeConvMenu()
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    // close when scrolling the conversation list (menu would desync)
    document.querySelector('.conv-list')?.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', closeConvMenu)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
      document.querySelector('.conv-list')?.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', closeConvMenu)
    }
  }, [activeMenuId, closeConvMenu, conversations, favoriteConversation])

  // Keep flyout aligned if menu reflows
  useLayoutEffect(() => {
    if (!projectFlyoutOpen || !projectBtnRef.current) return
    setFlyoutAnchor(toAnchor(projectBtnRef.current))
  }, [projectFlyoutOpen, projectList.length])

  const toggleGroup = (label: string) => {
    setCollapsedGroups(prev => ({ ...prev, [label]: !prev[label] }))
  }

  const haptic = useHaptic()

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
      if (window.innerWidth <= MOBILE_BREAKPOINT) {
        setSidebarOpen(false)
      }
    }
  }

  // Toque longo (long press) nas conversas do menu lateral
  const itemLongPressTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isItemLongPressActive = useRef(false)
  const itemTouchStartPos = useRef({ x: 0, y: 0 })

  const handleItemTouchStart = (e: React.TouchEvent, cId: string) => {
    const touch = e.touches[0]
    itemTouchStartPos.current = { x: touch.clientX, y: touch.clientY }
    isItemLongPressActive.current = false

    itemLongPressTimeout.current = setTimeout(() => {
      isItemLongPressActive.current = true
      haptic(20)
      // open portal menu near the row
      const row = (e.target as HTMLElement)?.closest?.('.conv-item') as HTMLElement | null
      if (row) {
        const rect = row.getBoundingClientRect()
        setMenuAnchor({
          top: rect.top,
          left: rect.left,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        })
      }
      setActiveMenuId(cId)
      setProjectFlyoutOpen(false)
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

  const searchQuery = sidebarSearch.trim().toLowerCase()
  const visibleConversations = searchQuery
    ? conversations.filter((c) => (c.title || '').toLowerCase().includes(searchQuery))
    : conversations

  const favorites = visibleConversations
    .filter((c) => c.is_favorite)
    .sort((a, b) => new Date(b.favorited_at || 0).getTime() - new Date(a.favorited_at || 0).getTime())
  
  const grouped = groupByDate(visibleConversations, {
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
            <Button variant="ghost" size="icon" onClick={() => handleRename(c.id)}><Check size={14} /></Button>
            <Button variant="ghost" size="icon" onClick={() => setEditingId(null)}><X size={14} /></Button>
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
                if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
              }}
            >
              <span>{c.title}</span>
            </button>
            <div className="conv-actions-dropdown-container">
              <button
                className="conv-menu-trigger"
                onClick={(e) => {
                  e.stopPropagation()
                  if (isMenuOpen) {
                    closeConvMenu()
                  } else {
                    const anchor = toAnchor(e.currentTarget)
                    setMenuAnchor(anchor)
                    setActiveMenuId(c.id)
                    setProjectFlyoutOpen(false)
                    setProjectSearch('')
                  }
                }}
                title={t('common.actions')}
                aria-label={t('common.actions')}
                aria-expanded={isMenuOpen}
              >
                <MoreVertical size={14} strokeWidth={2} />
              </button>
            </div>
          </>
        )}
      </div>
    )
  }

  // Menu + flyout em portal (fora do overflow da sidebar) — evita scrollbar horizontal
  const menuConv = activeMenuId ? conversations.find((x) => x.id === activeMenuId) : null
  const portalMenu =
    activeMenuId && menuAnchor && menuConv
      ? createPortal(
          <>
            <div
              ref={menuRef}
              className="conversation-context-menu is-portal"
              style={{
                position: 'fixed',
                top: Math.min(menuAnchor.bottom + 4, window.innerHeight - 200),
                left: Math.max(8, Math.min(menuAnchor.right - 196, window.innerWidth - 420)),
                zIndex: 10050,
              }}
              onClick={(e) => e.stopPropagation()}
              role="menu"
            >
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  favoriteConversation(menuConv.id)
                  closeConvMenu()
                }}
              >
                <Star
                  size={14}
                  className={menuConv.is_favorite ? 'text-amber-500 fill-amber-500' : ''}
                />
                <span>
                  {menuConv.is_favorite
                    ? t('sidebar.unfavorite', { defaultValue: 'Remover estrela' })
                    : t('sidebar.favorite', { defaultValue: 'Favoritar' })}
                </span>
                <kbd className="conv-menu-kbd">P</kbd>
              </button>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setEditingId(menuConv.id)
                  setEditTitle(menuConv.title)
                  closeConvMenu()
                }}
              >
                <Pencil size={14} />
                <span>{t('sidebar.rename', { defaultValue: 'Mudar o nome' })}</span>
                <kbd className="conv-menu-kbd">R</kbd>
              </button>

              <button
                type="button"
                role="menuitem"
                ref={projectBtnRef}
                className={`conv-menu-project-trigger ${projectFlyoutOpen ? 'is-open' : ''}`}
                onMouseEnter={() => {
                  if (window.innerWidth > MOBILE_BREAKPOINT) openProjectFlyout()
                }}
                onClick={() => {
                  if (projectFlyoutOpen) {
                    setProjectFlyoutOpen(false)
                    setFlyoutAnchor(null)
                  } else {
                    openProjectFlyout()
                  }
                }}
              >
                <Folder size={14} />
                <span>
                  {menuConv.project_id
                    ? t('sidebar.changeProject', { defaultValue: 'Mover de projeto' })
                    : t('sidebar.addToProject', { defaultValue: 'Adicionar ao projeto' })}
                </span>
                <ChevronRight size={14} className="conv-menu-chevron" />
              </button>

              <button
                type="button"
                role="menuitem"
                className="danger"
                onClick={() => {
                  setConfirmDeleteId(menuConv.id)
                  closeConvMenu()
                }}
              >
                <Trash2 size={14} />
                <span>{t('sidebar.delete', { defaultValue: 'Apagar' })}</span>
                <kbd className="conv-menu-kbd">D</kbd>
              </button>
            </div>

            {projectFlyoutOpen && flyoutAnchor && (
              <div
                ref={flyoutRef}
                className="conv-project-flyout is-portal"
                style={{
                  position: 'fixed',
                  top: Math.min(flyoutAnchor.top - 4, window.innerHeight - 280),
                  left: Math.min(flyoutAnchor.right + 6, window.innerWidth - 228),
                  zIndex: 10051,
                }}
                onClick={(e) => e.stopPropagation()}
                onMouseLeave={() => {
                  // keep open; close only via outside click
                }}
              >
                <div className="conv-project-flyout-search">
                  <Search size={13} />
                  <input
                    type="search"
                    autoFocus
                    value={projectSearch}
                    onChange={(e) => setProjectSearch(e.target.value)}
                    placeholder={t('sidebar.searchProjects', {
                      defaultValue: 'Pesquisar projetos',
                    })}
                  />
                </div>
                <div className="conv-project-flyout-list">
                  {projectsLoading && (
                    <div className="conv-project-flyout-empty">
                      {t('common.loading', { defaultValue: 'Carregando…' })}
                    </div>
                  )}
                  {!projectsLoading &&
                    projectList
                      .filter((p) =>
                        !projectSearch.trim()
                          ? true
                          : p.name.toLowerCase().includes(projectSearch.trim().toLowerCase())
                      )
                      .map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className={`conv-project-flyout-item ${
                            menuConv.project_id === p.id ? 'is-current' : ''
                          }`}
                          onClick={async () => {
                            try {
                              await setConversationProjectId(menuConv.id, p.id)
                              setProjectName(p.id, p.name)
                              showToast(
                                t('sidebar.addedToProject', {
                                  defaultValue: `Adicionado a «${p.name}»`,
                                  name: p.name,
                                }),
                                'success'
                              )
                            } catch (err) {
                              console.error(err)
                              showToast(
                                t('sidebar.addToProjectError', {
                                  defaultValue: 'Erro ao adicionar ao projeto',
                                }),
                                'error'
                              )
                            }
                            closeConvMenu()
                          }}
                        >
                          <Folder size={13} />
                          <span>{p.name}</span>
                        </button>
                      ))}
                  {!projectsLoading && projectList.length === 0 && (
                    <div className="conv-project-flyout-empty">
                      {t('sidebar.noProjectsYet', { defaultValue: 'Nenhum projeto ainda' })}
                      <button
                        type="button"
                        className="conv-project-flyout-create"
                        onClick={() => {
                          closeConvMenu()
                          setView('projects')
                          if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
                        }}
                      >
                        {t('projects.new', { defaultValue: 'Novo projeto' })}
                      </button>
                    </div>
                  )}
                </div>
                {menuConv.project_id && (
                  <button
                    type="button"
                    className="conv-project-flyout-remove"
                    onClick={async () => {
                      try {
                        await setConversationProjectId(menuConv.id, null)
                        showToast(
                          t('sidebar.removedFromProject', {
                            defaultValue: 'Removido do projeto',
                          }),
                          'info'
                        )
                      } catch (err) {
                        console.error(err)
                      }
                      closeConvMenu()
                    }}
                  >
                    {t('sidebar.removeFromProject', { defaultValue: 'Remover do projeto' })}
                  </button>
                )}
              </div>
            )}
          </>,
          document.body
        )
      : null

  return (
    <aside
      className="sidebar"
      aria-hidden={!sidebarOpen && isMobile}
      aria-expanded={sidebarOpen}
      data-open={sidebarOpen ? 'true' : 'false'}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {portalMenu}
      {/* Header: expandido = brand+busca+recolher | rail = só expandir */}
      <div className="sidebar-header">
        {/* Só no rail (sidebar colapsada no desktop) — não montar quando aberta */}
        {!sidebarOpen && !isMobile && (
          <Button
            variant="ghost"
            size="icon"
            className="sidebar-rail-expand"
            tooltip={t('chat.openSidebar', { defaultValue: 'Abrir menu' })}
            aria-label={t('chat.openSidebar', { defaultValue: 'Abrir menu' })}
            onClick={() => setSidebarOpen(true)}
          >
            <PanelLeftOpen size={18} strokeWidth={1.75} />
          </Button>
        )}

        {sidebarOpen && (
          <>
            <button
              type="button"
              className="sidebar-brand custom-tooltip-trigger"
              onClick={() => {
                startNewConversation()
                if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
              }}
              data-tooltip={t('sidebar.goHome', { defaultValue: 'Início' })}
              aria-label={t('sidebar.goHome', { defaultValue: 'Início' })}
            >
              <NexusLogoIcon className="brand-logo" />
              <span className="brand-name">NexusLocal</span>
            </button>
            <div className="sidebar-header-actions">
              <Button
                variant="ghost"
                size="icon"
                className="sidebar-action-search"
                tooltip={t('sidebar.searchConversations', { defaultValue: 'Buscar conversas' })}
                aria-label={t('sidebar.searchConversations', { defaultValue: 'Buscar conversas' })}
                aria-pressed={searchOpen}
                onClick={() => {
                  setSearchOpen((v) => {
                    const next = !v
                    if (!next) setSidebarSearch('')
                    else {
                      requestAnimationFrame(() => searchInputRef.current?.focus())
                    }
                    return next
                  })
                }}
              >
                <Search size={17} strokeWidth={1.75} />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                tooltip={t('sidebar.closeSidebar')}
                aria-label={t('sidebar.closeSidebar')}
                onClick={() => setSidebarOpen(false)}
              >
                <PanelLeftClose size={17} strokeWidth={1.75} />
              </Button>
            </div>
          </>
        )}
      </div>

      {searchOpen && sidebarOpen && (
        <div className="sidebar-search-row">
          <Search size={14} aria-hidden />
          <input
            ref={searchInputRef}
            type="search"
            value={sidebarSearch}
            onChange={(e) => setSidebarSearch(e.target.value)}
            placeholder={t('sidebar.searchPlaceholder', { defaultValue: 'Buscar conversas…' })}
            aria-label={t('sidebar.searchConversations', { defaultValue: 'Buscar conversas' })}
          />
          {sidebarSearch && (
            <button
              type="button"
              className="custom-tooltip-trigger"
              data-tooltip={t('common.clear', { defaultValue: 'Limpar' })}
              aria-label={t('common.clear', { defaultValue: 'Limpar' })}
              onClick={() => {
                setSidebarSearch('')
                searchInputRef.current?.focus()
              }}
              style={{ display: 'inline-flex', padding: 2, color: 'var(--on-dark-soft)' }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      )}

      <button
        type="button"
        className="new-chat-btn custom-tooltip-trigger"
        data-tooltip={t('sidebar.newChat')}
        aria-label={t('sidebar.newChat')}
        onClick={() => {
          startNewConversation()
          setView('chat')
          if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
        }}
      >
        <span className="new-chat-btn-icon" aria-hidden>
          <Plus size={12} strokeWidth={2.5} />
        </span>
        <span className="new-chat-btn-label">{t('sidebar.newChat')}</span>
      </button>

      <nav className="conv-list">
        <div className="sidebar-fixed-nav">
          <button
            type="button"
            className={`sidebar-fixed-nav-item custom-tooltip-trigger ${view === 'conversations' ? 'selected' : ''}`}
            data-tooltip={t('sidebar.conversations')}
            aria-label={t('sidebar.conversations')}
            onClick={() => {
              setView('conversations')
              if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
            }}
          >
            <MessageSquare size={20} />
            <span>{t('sidebar.conversations')}</span>
          </button>
          <button
            type="button"
            className={`sidebar-fixed-nav-item custom-tooltip-trigger ${view === 'projects' ? 'selected' : ''}`}
            data-tooltip={t('sidebar.projects', { defaultValue: 'Projetos' })}
            aria-label={t('sidebar.projects', { defaultValue: 'Projetos' })}
            onClick={() => {
              setView('projects')
              if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
            }}
          >
            <Folder size={20} />
            <span>{t('sidebar.projects', { defaultValue: 'Projetos' })}</span>
          </button>
          <button
            type="button"
            className={`sidebar-fixed-nav-item custom-tooltip-trigger ${view === 'artifacts' ? 'selected' : ''}`}
            data-tooltip={t('sidebar.artifacts')}
            aria-label={t('sidebar.artifacts')}
            onClick={() => {
              setView('artifacts')
              if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
            }}
          >
            <Sparkles size={20} />
            <span>{t('sidebar.artifacts')}</span>
          </button>
        </div>

        {favorites.length > 0 && (
          <div className="conv-group">
            <span 
              className="conv-group-label hover:text-text-300 transition-colors" 
              onClick={() => toggleGroup('favorites')}
              style={{ cursor: 'pointer' }}
            >
              {t('sidebar.favorites')}
            </span>
            {!collapsedGroups['favorites'] && favorites.map((c) => renderConversationRow(c))}
          </div>
        )}

        {Object.entries(grouped).map(([label, convs]) => (
          <div key={label} className="conv-group">
            <span 
              className="conv-group-label hover:text-text-300 transition-colors"
              onClick={() => toggleGroup(label)}
              style={{ cursor: 'pointer' }}
            >
              {label}
            </span>
            {!collapsedGroups[label] && convs.map((c) => renderConversationRow(c))}
          </div>
        ))}

        {visibleConversations.length === 0 && (
          <div className="empty-state">
            <MessageSquare size={28} />
            <p>
              {searchQuery
                ? t('sidebar.noSearchResults', { defaultValue: 'Nenhuma conversa encontrada.' })
                : t('sidebar.empty')}
            </p>
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
        <div className="sidebar-pwa-slot">
          <InstallPWAButton />
        </div>
        {/* User card → Configurações */}
        <div
          className={`user-card custom-tooltip-trigger ${view === 'admin' ? 'active' : ''}`}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', cursor: 'pointer' }}
          data-tooltip={t('sidebar.settings')}
          role="button"
          tabIndex={0}
          onClick={() => {
            if (view === 'admin') {
              setView('chat')
            } else {
              setView('admin')
              if (window.innerWidth <= MOBILE_BREAKPOINT) setSidebarOpen(false)
            }
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault()
              ;(e.currentTarget as HTMLDivElement).click()
            }
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <div className="user-avatar">{USER_INITIAL}</div>
            <div className="user-info">
              <span className="user-name">{USER_NAME}</span>
              <span className="user-plan" style={{ fontSize: '13px', color: 'var(--muted)', display: 'block' }}>{t('sidebar.settings')}</span>
            </div>
          </div>
          <div className="user-card-actions" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Button
              variant="ghost"
              size="icon"
              onClick={(e) => {
                e.stopPropagation()
                setTheme(theme === 'dark' ? 'light' : 'dark')
              }}
              title={theme === 'dark' ? t('sidebar.themeToLight') : t('sidebar.themeToDark')}
            >
              {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={(e) => {
                e.stopPropagation()
                logout()
              }}
              title={t('sidebar.logout')}
            >
              <LogOut size={14} />
            </Button>
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
