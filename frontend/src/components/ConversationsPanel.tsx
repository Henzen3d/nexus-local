import { useState, useEffect, useRef } from 'react'
import { MessageSquare, Plus, Search, Trash2, Star, CheckSquare, Square, X, Sliders, ListChecks, Pencil, Menu } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { useHaptic } from '../hooks/useHaptic'
import type { Conversation } from '../types'

export function ConversationsPanel() {
  const { t, i18n } = useTranslation()
  const haptic = useHaptic()
  const conversations = useStore((s) => s.conversations)
  const loadConversations = useStore((s) => s.loadConversations)
  const loadConversation = useStore((s) => s.loadConversation)
  const startNewConversation = useStore((s) => s.startNewConversation)
  const favoriteConversation = useStore((s) => s.favoriteConversation)
  const deleteConversation = useStore((s) => s.deleteConversation)
  const setSidebarOpen = useStore((s) => s.setSidebarOpen)
  const renameConversation = useStore((s) => s.renameConversation)
  const sidebarOpen = useStore((s) => s.sidebarOpen)

  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<'all' | 'favorites'>('all')
  const [isSelectMode, setIsSelectMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [showFilterDropdown, setShowFilterDropdown] = useState(false)

  // Estados para Long Press e Context Menu
  interface MenuState {
    id: string;
    title: string;
    isFavorite: boolean;
    x: number;
    y: number;
  }
  const [menuState, setMenuState] = useState<MenuState | null>(null)

  // Modais customizados para mobile
  const [renameId, setRenameId] = useState<string | null>(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  // Referências para o gesto de toque/clique longo
  const longPressTimeout = useRef<any>(null)
  const isLongPressActive = useRef(false)
  const touchStartPos = useRef({ x: 0, y: 0 })

  // Load conversations when filters change
  useEffect(() => {
    loadConversations(search, filter === 'favorites' ? 'favorites' : undefined)
  }, [search, filter, loadConversations])

  const handleSelectAll = () => {
    if (selectedIds.length === conversations.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(conversations.map((c) => c.id))
    }
  }

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    )
  }

  const handleBulkFavorite = async () => {
    if (selectedIds.length === 0) return
    await Promise.all(selectedIds.map((id) => favoriteConversation(id)))
    setIsSelectMode(false)
    setSelectedIds([])
  }

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return
    const confirm = window.confirm(t('conversations.bulkDeleteConfirm', { count: selectedIds.length }))
    if (!confirm) return
    await Promise.all(selectedIds.map((id) => deleteConversation(id)))
    setIsSelectMode(false)
    setSelectedIds([])
  }

  const handleTouchStart = (e: React.TouchEvent, id: string, title: string, isFavorite: boolean) => {
    if (isSelectMode) return
    const touch = e.touches[0]
    touchStartPos.current = { x: touch.clientX, y: touch.clientY }
    isLongPressActive.current = false

    longPressTimeout.current = setTimeout(() => {
      isLongPressActive.current = true
      haptic(20)
      setMenuState({
        id,
        title,
        isFavorite,
        x: touch.clientX,
        y: touch.clientY
      })
    }, 600)
  }

  const handleTouchMove = (e: React.TouchEvent) => {
    const touch = e.touches[0]
    const diffX = Math.abs(touch.clientX - touchStartPos.current.x)
    const diffY = Math.abs(touch.clientY - touchStartPos.current.y)
    if (diffX > 10 || diffY > 10) {
      if (longPressTimeout.current) {
        clearTimeout(longPressTimeout.current)
      }
    }
  }

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (longPressTimeout.current) {
      clearTimeout(longPressTimeout.current)
    }
    if (isLongPressActive.current) {
      e.preventDefault()
      setTimeout(() => {
        isLongPressActive.current = false
      }, 50)
    }
  }

  const handleMouseDown = (e: React.MouseEvent, id: string, title: string, isFavorite: boolean) => {
    if (isSelectMode || e.button !== 0) return
    isLongPressActive.current = false
    const x = e.clientX
    const y = e.clientY
    touchStartPos.current = { x, y }

    longPressTimeout.current = setTimeout(() => {
      isLongPressActive.current = true
      setMenuState({
        id,
        title,
        isFavorite,
        x,
        y
      })
    }, 600)
  }

  const handleMouseMove = (e: React.MouseEvent) => {
    const diffX = Math.abs(e.clientX - touchStartPos.current.x)
    const diffY = Math.abs(e.clientY - touchStartPos.current.y)
    if (diffX > 10 || diffY > 10) {
      if (longPressTimeout.current) {
        clearTimeout(longPressTimeout.current)
      }
    }
  }

  const handleMouseUp = (e: React.MouseEvent) => {
    if (longPressTimeout.current) {
      clearTimeout(longPressTimeout.current)
    }
    if (isLongPressActive.current) {
      e.preventDefault()
      e.stopPropagation()
      setTimeout(() => {
        isLongPressActive.current = false
      }, 50)
    }
  }

  const handleRename = async () => {
    if (renameId && renameTitle.trim()) {
      await renameConversation(renameId, renameTitle.trim())
      setRenameId(null)
    }
  }

  const handleDelete = async () => {
    if (confirmDeleteId) {
      await deleteConversation(confirmDeleteId)
      setConfirmDeleteId(null)
    }
  }

  return (
    <div className="conversations-panel list-panel">
      <div className="list-panel-inner">
        {/* Header — mesmo padrão de Projetos / Artefatos */}
        <header className="list-panel-header">
          <div className="list-panel-title-row">
            {!sidebarOpen && (
              <button
                type="button"
                className="icon-only-btn touch-target"
                onClick={() => setSidebarOpen(true)}
                title={t("common.openMenu")}
                aria-label={t("common.openMenu")}
              >
                <Menu size={20} />
              </button>
            )}
            <h1>{t("conversations.title")}</h1>
            <div className="list-panel-actions">
              {/* Dropdown de Filtro */}
              <div className="filter-dropdown-container">
                <button
                  type="button"
                  className="icon-only-btn"
                  onClick={() => setShowFilterDropdown(!showFilterDropdown)}
                  title={t('conversations.filterBy', { filter: filter === 'all' ? t('conversations.all') : t('conversations.favorites') })}
                  aria-label={t("conversations.filterConversations")}
                >
                  <Sliders size={18} />
                </button>
                {showFilterDropdown && (
                  <div className="filter-menu-dropdown right-aligned">
                    <button
                      type="button"
                      className={filter === 'all' ? 'active' : ''}
                      onClick={() => {
                        setFilter('all')
                        setShowFilterDropdown(false)
                      }}
                    >
                      {t('conversations.all')}
                    </button>
                    <button
                      type="button"
                      className={filter === 'favorites' ? 'active' : ''}
                      onClick={() => {
                        setFilter('favorites')
                        setShowFilterDropdown(false)
                      }}
                    >
                      {t('conversations.favorites')}
                    </button>
                  </div>
                )}
              </div>

              {/* Selecionar Chats */}
              <button
                type="button"
                className="icon-only-btn"
                onClick={() => {
                  setIsSelectMode(!isSelectMode)
                  setSelectedIds([])
                }}
                title={isSelectMode ? t('conversations.cancelSelection') : t('conversations.selectChats')}
                aria-label={isSelectMode ? t('conversations.cancelSelection') : t('conversations.selectChats')}
              >
                {isSelectMode ? <X size={18} /> : <ListChecks size={18} />}
              </button>

              {!isSelectMode && (
                <button
                  type="button"
                  className="claude-btn-primary"
                  onClick={() => {
                    startNewConversation()
                    if (window.innerWidth <= 768) setSidebarOpen(false)
                  }}
                >
                  <Plus size={16} strokeWidth={2.2} />
                  {t('conversations.newChat', { defaultValue: 'Novo bate-papo' })}
                </button>
              )}
            </div>
          </div>

          <div className="search-bar-container">
            <Search className="search-icon-field" size={15} />
            <input
              type="text"
              className="search-input-field"
              placeholder={t('conversations.searchPlaceholder')}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {search && (
              <button type="button" className="clear-search-btn" onClick={() => setSearch('')}>
                <X size={14} />
              </button>
            )}
          </div>
        </header>

        {/* Bulk Selection Bar */}
        {isSelectMode && (
          <div className="bulk-actions-bar">
            <div className="bulk-info">
              <button type="button" className="icon-btn-select" onClick={handleSelectAll}>
                {selectedIds.length === conversations.length ? (
                  <CheckSquare size={16} className="text-primary" />
                ) : (
                  <Square size={16} />
                )}
              </button>
              <span>{t('conversations.selected', { count: selectedIds.length })}</span>
            </div>
            <div className="bulk-buttons">
              <button
                type="button"
                className="bulk-btn favorite"
                disabled={selectedIds.length === 0}
                onClick={handleBulkFavorite}
              >
                <Star size={14} />
                <span>{t("conversations.toggleFavorites")}</span>
              </button>
              <button
                type="button"
                className="bulk-btn delete danger"
                disabled={selectedIds.length === 0}
                onClick={handleBulkDelete}
              >
                <Trash2 size={14} />
                <span>{t("conversations.delete")}</span>
              </button>
            </div>
          </div>
        )}

        {/* List content */}
        <div className="conversations-content-area">
          {conversations.length === 0 ? (
            <div className="panel-empty-state">
              <MessageSquare size={36} />
              <h3>{t("conversations.emptyTitle")}</h3>
              <p>
                {search
                  ? t('conversations.emptySearch')
                  : t('conversations.emptyHint')}
              </p>
            </div>
          ) : (
            <div className="conversations-rows-wrapper">
              {conversations.map((c) => {
                const isSelected = selectedIds.includes(c.id)
                const timeString = getRelativeTime(c.updated_at)
                const capitalizedTime = timeString.charAt(0).toUpperCase() + timeString.slice(1)
                return (
                  <div
                    key={c.id}
                    className={`conversation-row-item ${
                      isSelectMode ? 'in-select-mode' : ''
                    } ${isSelected ? 'row-selected' : ''}`}
                     onTouchStart={(e) => handleTouchStart(e, c.id, c.title, !!c.is_favorite)}
                     onTouchMove={handleTouchMove}
                     onTouchEnd={handleTouchEnd}
                     onMouseDown={(e) => handleMouseDown(e, c.id, c.title, !!c.is_favorite)}
                    onMouseMove={handleMouseMove}
                    onMouseUp={handleMouseUp}
                    onContextMenu={(e) => e.preventDefault()}
                    onClick={() => {
                      if (isLongPressActive.current) {
                        isLongPressActive.current = false
                        return
                      }
                      if (isSelectMode) {
                        toggleSelect(c.id)
                      } else {
                        loadConversation(c.id)
                        if (window.innerWidth <= 768) setSidebarOpen(false)
                      }
                    }}
                  >
                    {isSelectMode && (
                      <div className="row-checkbox-wrapper">
                        {isSelected ? (
                          <CheckSquare size={16} className="text-primary" />
                        ) : (
                          <Square size={16} />
                        )}
                      </div>
                    )}

                    <div className="row-content-body">
                      <div className="row-title-container">
                        <span className="row-conversation-title" title={c.title}>
                          {c.title}
                        </span>
                        {c.is_favorite && (
                          <Star size={11} className="fill-amber-500 text-amber-500" />
                        )}
                      </div>
                      <span className="row-conversation-meta">
                        {capitalizedTime}
                      </span>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Floating Context Menu */}
      {menuState && (
        <>
          <div 
            className="mobile-context-menu-overlay"
            onClick={() => setMenuState(null)}
            onTouchStart={() => setMenuState(null)}
          />
          <div 
            className="mobile-context-menu"
            style={{
              position: 'fixed',
              top: `${menuState.y}px`,
              left: `${Math.min(window.innerWidth - 190, menuState.x)}px`,
            }}
          >
            <button
              className="mobile-context-menu-item"
              onClick={() => {
                setRenameId(menuState.id)
                setRenameTitle(menuState.title)
                setMenuState(null)
              }}
            >
              <span>Renomear</span>
              <Pencil size={14} />
            </button>
            <button
              className="mobile-context-menu-item"
              onClick={async () => {
                await favoriteConversation(menuState.id)
                setMenuState(null)
              }}
            >
              <span>{menuState.isFavorite ? t('sidebar.unfavorite') : t('sidebar.favorite')}</span>
              <Star size={14} className={menuState.isFavorite ? "fill-amber-500 text-amber-500" : ""} />
            </button>
            <button
              className="mobile-context-menu-item danger"
              onClick={() => {
                setConfirmDeleteId(menuState.id)
                setMenuState(null)
              }}
            >
              <span>{t("conversations.delete")}</span>
              <Trash2 size={14} />
            </button>
          </div>
        </>
      )}

      {/* Modal Customizado de Confirmação de Exclusão */}
      {confirmDeleteId && (
        <div className="confirm-delete-modal-overlay" onClick={() => setConfirmDeleteId(null)}>
          <div className="confirm-delete-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Excluir Conversa</h3>
            <p>Tem certeza? Esta conversa será perdida para sempre.</p>
            <div className="mobile-modal-actions">
              <button className="mobile-modal-btn cancel" onClick={() => setConfirmDeleteId(null)}>
                Cancelar
              </button>
              <button className="mobile-modal-btn danger" onClick={handleDelete}>
                Apagar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Customizado de Renomeação */}
      {renameId && (
        <div className="confirm-delete-modal-overlay" onClick={() => setRenameId(null)}>
          <div className="confirm-delete-modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Renomear conversa</h3>
            <div className="mobile-modal-input-wrapper">
              <input
                autoFocus
                className="mobile-modal-input"
                value={renameTitle}
                onChange={(e) => setRenameTitle(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRename()
                  if (e.key === 'Escape') setRenameId(null)
                }}
              />
            </div>
            <div className="mobile-modal-actions">
              <button className="mobile-modal-btn cancel" onClick={() => setRenameId(null)}>
                Cancelar
              </button>
              <button className="mobile-modal-btn primary" onClick={handleRename}>
                Renomear
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function getRelativeTime(dateString: string) {
  const d = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 60) {
    return diffMins <= 1 ? 'agora há pouco' : `há ${diffMins} min`
  } else if (diffHours < 24) {
    return `há ${diffHours} hora${diffHours > 1 ? 's' : ''}`
  } else if (diffDays === 1) {
    return 'ontem'
  } else if (diffDays < 7) {
    return `há ${diffDays} dias`
  } else {
    return d.toLocaleDateString('pt-BR', { day: 'numeric', month: 'short' })
  }
}
