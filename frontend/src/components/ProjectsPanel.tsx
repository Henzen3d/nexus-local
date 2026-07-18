import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Archive,
  ArrowLeft,
  ChevronDown,
  FileText,
  Folder,
  Lock,
  Menu,
  MoreVertical,
  Pencil,
  Plus,
  Search,
  Star,
  Trash2,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { ProviderSelector } from './ProviderSelector'
import { ModelSelector } from './ModelSelector'
import type { Project, ProjectChat, ProjectFile } from '../types'

type SortKey = 'updated' | 'name' | 'created'

function relativeTime(iso: string, locale: string): string {
  try {
    const d = new Date(iso)
    const diff = Date.now() - d.getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return 'agora'
    if (mins < 60) return `há ${mins} min`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `há ${hours}h`
    const days = Math.floor(hours / 24)
    if (days < 30) return `há ${days}d`
    return d.toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  } catch {
    return ''
  }
}

function formatShortDate(iso: string | null | undefined, locale: string): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  } catch {
    return ''
  }
}

function debounce<T extends (...args: any[]) => void>(fn: T, ms: number) {
  let t: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (t) clearTimeout(t)
    t = setTimeout(() => fn(...args), ms)
  }
}

/** Empty-state illustration for project files (Claude knowledge stack) */
function KnowledgeIllustration() {
  const theme = useStore((s) => s.theme)
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    const resolve = () => {
      if (theme === 'dark') return true
      if (theme === 'light') return false
      return window.matchMedia('(prefers-color-scheme: dark)').matches
    }
    setIsDark(resolve())
    if (theme !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => setIsDark(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [theme])

  return (
    <img
      src={isDark ? '/project-knowledge-dark.svg' : '/project-knowledge-light.svg'}
      alt=""
      className="project-knowledge-illust"
      width={105}
      height={56}
      draggable={false}
    />
  )
}

/** Projects list — Claude-style cards grid */
function ProjectsListPage({
  onOpen,
  onNew,
}: {
  onOpen: (id: string) => void
  onNew: () => void
}) {
  const { t, i18n } = useTranslation()
  const setSidebarOpen = useStore((s) => s.setSidebarOpen)
  const sidebarOpen = useStore((s) => s.sidebarOpen)
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [sort, setSort] = useState<SortKey>('updated')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        const list = await api.listProjects(sort, search || undefined)
        if (!cancelled) setProjects(list)
      } catch (e) {
        console.error(e)
        if (!cancelled) {
          useStore.getState().showToast('Erro ao carregar projetos', 'error')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [sort, search])

  const debouncedSearch = useMemo(
    () =>
      debounce((v: string) => {
        setSearch(v.trim())
      }, 250),
    []
  )

  return (
    <div className="claude-projects claude-projects-list list-panel">
      <div className="claude-projects-inner list-panel-inner">
        <header className="claude-projects-list-header list-panel-header">
          <div className="claude-projects-list-top list-panel-title-row">
            {!sidebarOpen && (
              <button
                type="button"
                className="icon-only-btn touch-target"
                onClick={() => setSidebarOpen(true)}
                aria-label={t('common.openMenu')}
              >
                <Menu size={20} />
              </button>
            )}
            <h1>{t('sidebar.projects', { defaultValue: 'Projetos' })}</h1>
            <div className="claude-projects-list-actions list-panel-actions">
              <div className="claude-sort-pill">
                <span>{t('projects.sortBy', { defaultValue: 'Ordenar por' })}:</span>
                <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
                  <option value="updated">
                    {t('projects.sortUpdated', { defaultValue: 'Última atualização' })}
                  </option>
                  <option value="name">{t('projects.sortName', { defaultValue: 'Nome (A-Z)' })}</option>
                  <option value="created">
                    {t('projects.sortCreated', { defaultValue: 'Data de criação' })}
                  </option>
                </select>
                <ChevronDown size={14} className="claude-sort-chevron" aria-hidden />
              </div>
              <button type="button" className="claude-btn-primary" onClick={onNew}>
                <Plus size={16} strokeWidth={2.2} />
                {t('projects.new', { defaultValue: 'Novo projeto' })}
              </button>
            </div>
          </div>
          <div className="search-bar-container">
            <Search className="search-icon-field" size={15} />
            <input
              type="search"
              className="search-input-field"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value)
                debouncedSearch(e.target.value)
              }}
              placeholder={t('projects.searchProjects', { defaultValue: 'Procurar projetos...' })}
            />
            {searchInput && (
              <button
                type="button"
                className="clear-search-btn"
                onClick={() => {
                  setSearchInput('')
                  setSearch('')
                }}
                aria-label={t('common.clear', { defaultValue: 'Limpar' })}
              >
                <X size={14} />
              </button>
            )}
          </div>
        </header>

        <div className="claude-projects-list-body">
          {loading && (
            <div className="claude-projects-empty-state">
              <p>{t('common.loading', { defaultValue: 'Carregando…' })}</p>
            </div>
          )}

          {!loading && projects.length === 0 && (
            <div className="claude-projects-empty-state">
              <Folder size={40} strokeWidth={1.25} />
              <h3>{t('projects.emptyTitle', { defaultValue: 'Crie seu primeiro projeto' })}</h3>
              <p>
                {t('projects.emptyDescV2', {
                  defaultValue:
                    'Projetos guardam instruções, arquivos e memória — e conectam chats do mesmo workspace.',
                })}
              </p>
              <button type="button" className="claude-btn-primary" onClick={onNew}>
                <Plus size={16} />
                {t('projects.new', { defaultValue: 'Novo projeto' })}
              </button>
            </div>
          )}

          <div className="claude-projects-grid">
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                className="claude-project-card"
                onClick={() => onOpen(p.id)}
                aria-label={t('projects.openProject', {
                  defaultValue: 'Abrir projeto {{name}}',
                  name: p.name,
                })}
              >
                <div className="claude-project-card-row">
                  <span className="claude-project-card-icon">
                    <Folder size={16} strokeWidth={1.8} />
                  </span>
                  {p.is_favorite && <Star size={13} className="claude-project-card-star" fill="currentColor" />}
                </div>
                <div className="claude-project-card-name">{p.name}</div>
                <div className="claude-project-card-meta">
                  {t('projects.updated', {
                    defaultValue: 'Atualizado {{when}}',
                    when: relativeTime(p.updated_at, i18n.language),
                  })}
                  {(p.chat_count ?? 0) > 0 && (
                    <span className="project-card-stat">
                      · {p.chat_count}{' '}
                      {p.chat_count === 1
                        ? t('projects.chatOne', { defaultValue: 'conversa' })
                        : t('projects.chatMany', { defaultValue: 'conversas' })}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

function NewProjectModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: (p: Project) => void
}) {
  const { t } = useTranslation()
  const { showToast } = useStore()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName('')
      setDescription('')
    }
  }, [open])

  if (!open) return null

  const submit = async () => {
    if (!name.trim()) return
    setSaving(true)
    try {
      const p = await api.createProject({ name: name.trim(), description: description.trim() })
      showToast(t('projects.created', { defaultValue: 'Projeto criado' }), 'success')
      onCreated(p)
      onClose()
    } catch (e) {
      console.error(e)
      showToast(t('projects.createError', { defaultValue: 'Erro ao criar projeto' }), 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="claude-modal-overlay" onClick={onClose}>
      <div className="claude-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
        <div className="claude-modal-header">
          <h2>{t('projects.new', { defaultValue: 'Novo projeto' })}</h2>
          <button type="button" className="claude-icon-btn" onClick={onClose} aria-label={t('common.close')}>
            <X size={18} />
          </button>
        </div>
        <p className="claude-modal-desc">
          {t('projects.newDesc', {
            defaultValue: 'Nome obrigatório. A descrição é cosmético e não entra no contexto da IA.',
          })}
        </p>
        <label className="claude-field">
          <span>{t('projects.namePlaceholder', { defaultValue: 'Nome do projeto' })}</span>
          <input
            autoFocus
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault()
                submit()
              }
            }}
          />
        </label>
        <label className="claude-field">
          <span>{t('projects.descPlaceholder', { defaultValue: 'Descrição (opcional)' })}</span>
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <div className="claude-modal-actions">
          <button type="button" className="claude-btn-ghost" onClick={onClose}>
            {t('common.cancel')}
          </button>
          <button type="button" className="claude-btn-primary" disabled={!name.trim() || saving} onClick={submit}>
            {t('common.save')}
          </button>
        </div>
      </div>
    </div>
  )
}

/** Detail — matches Claude projects screenshots (70/30) */
function ProjectDetailPage({
  projectId,
  onBack,
}: {
  projectId: string
  onBack: () => void
}) {
  const { t, i18n } = useTranslation()
  // Selectors estáveis — evita re-render em qualquer mudança da store
  const setSidebarOpen = useStore((s) => s.setSidebarOpen)
  const sidebarOpen = useStore((s) => s.sidebarOpen)
  const showToast = useStore((s) => s.showToast)
  const loadConversation = useStore((s) => s.loadConversation)
  const startNewConversation = useStore((s) => s.startNewConversation)
  const setActiveProjectId = useStore((s) => s.setActiveProjectId)
  const setView = useStore((s) => s.setView)
  const selectedModelId = useStore((s) => s.selectedModelId)
  const loadModels = useStore((s) => s.loadModels)

  const [project, setProject] = useState<Project | null>(null)
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [chats, setChats] = useState<ProjectChat[]>([])
  const [menuOpen, setMenuOpen] = useState(false)
  const [editingInstructions, setEditingInstructions] = useState(false)
  const [instructionsDraft, setInstructionsDraft] = useState('')
  const [editingMemory, setEditingMemory] = useState(false)
  const [memoryDraft, setMemoryDraft] = useState('')
  const [composer, setComposer] = useState('')
  const [uploading, setUploading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const onBackRef = useRef(onBack)
  onBackRef.current = onBack

  // Garante lista de provedores/modelos ao abrir o detalhe do projeto
  useEffect(() => {
    loadModels()
  }, [loadModels])

  // Bind RAG context once per projectId (no unstable deps)
  useEffect(() => {
    setActiveProjectId(projectId)
  }, [projectId, setActiveProjectId])

  // Load project data when id changes
  useEffect(() => {
    let cancelled = false
    setProject(null)
    setLoadError(false)
    ;(async () => {
      try {
        const [p, f, c] = await Promise.all([
          api.getProject(projectId),
          api.listProjectFiles(projectId),
          api.listProjectChats(projectId),
        ])
        if (cancelled) return
        setProject(p)
        setFiles(f)
        setChats(c)
        setInstructionsDraft(p.instructions || '')
        setMemoryDraft(p.memory?.summary_text || '')
      } catch (e) {
        console.error(e)
        if (cancelled) return
        setLoadError(true)
        useStore.getState().showToast(
          // t from closure is fine for one-shot error
          'Erro ao carregar projeto',
          'error'
        )
        onBackRef.current()
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const refresh = useCallback(async () => {
    try {
      const [p, f, c] = await Promise.all([
        api.getProject(projectId),
        api.listProjectFiles(projectId),
        api.listProjectChats(projectId),
      ])
      setProject(p)
      setFiles(f)
      setChats(c)
      setInstructionsDraft(p.instructions || '')
      setMemoryDraft(p.memory?.summary_text || '')
    } catch (e) {
      console.error(e)
      showToast(t('projects.loadError', { defaultValue: 'Erro ao carregar projeto' }), 'error')
    }
  }, [projectId, showToast, t])

  // Poll indexing only while files are busy — depend on a stable boolean, not `files` array
  const indexingBusy = files.some((f) => f.index_status === 'pending' || f.index_status === 'indexing')
  useEffect(() => {
    if (!indexingBusy) return
    pollRef.current = setInterval(async () => {
      try {
        setFiles(await api.listProjectFiles(projectId))
      } catch {
        /* ignore */
      }
    }, 2000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [indexingBusy, projectId])

  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  if (!project) {
    return (
      <div className="claude-projects claude-project-detail">
        <div className="claude-projects-empty-state">
          <p>
            {loadError
              ? t('projects.loadError', { defaultValue: 'Erro ao carregar projeto' })
              : t('common.loading', { defaultValue: 'Carregando…' })}
          </p>
          {loadError && (
            <button type="button" className="claude-btn-primary" onClick={onBack}>
              {t('projects.allProjects', { defaultValue: 'Todos os projetos' })}
            </button>
          )}
        </div>
      </div>
    )
  }

  const openChat = async (chatId: string) => {
    setActiveProjectId(projectId)
    await loadConversation(chatId)
    setView('chat')
    if (window.innerWidth <= 768) setSidebarOpen(false)
  }

  const startProjectChat = (firstMessage?: string) => {
    startNewConversation()
    setActiveProjectId(projectId)
    setView('chat')
    if (firstMessage?.trim()) {
      setTimeout(() => {
        window.dispatchEvent(
          new CustomEvent('nexus:send-project-message', { detail: { text: firstMessage.trim() } })
        )
      }, 120)
    }
  }

  const saveInstructions = async () => {
    try {
      const p = await api.updateProject(projectId, { instructions: instructionsDraft })
      setProject((prev) => (prev ? { ...prev, ...p } : p))
      setEditingInstructions(false)
      showToast(t('projects.instructionsSaved', { defaultValue: 'Instruções salvas' }), 'success')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao salvar' }), 'error')
    }
  }

  const saveMemory = async () => {
    try {
      await api.patchProjectMemory(projectId, memoryDraft)
      setProject((prev) =>
        prev
          ? {
              ...prev,
              memory: {
                summary_text: memoryDraft,
                last_synthesized_at: prev.memory?.last_synthesized_at ?? new Date().toISOString(),
                scope_badge: 'Apenas você',
              },
            }
          : prev
      )
      setEditingMemory(false)
      showToast(t('projects.memorySaved', { defaultValue: 'Memória salva' }), 'success')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao salvar' }), 'error')
    }
  }

  const onUpload = async (fileList: FileList | null) => {
    if (!fileList?.length) return
    setUploading(true)
    try {
      for (const file of Array.from(fileList)) {
        await api.uploadProjectFile(projectId, file)
      }
      await refresh()
      showToast(t('projects.fileUploaded', { defaultValue: 'Arquivo enviado — indexando…' }), 'success')
    } catch (e) {
      console.error(e)
      showToast(t('projects.uploadError', { defaultValue: 'Falha no upload' }), 'error')
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const toggleFavorite = async () => {
    const p = await api.updateProject(projectId, { is_favorite: !project.is_favorite })
    setProject((prev) => (prev ? { ...prev, ...p } : p))
  }

  const renameProject = async () => {
    const name = window.prompt(t('projects.rename', { defaultValue: 'Renomear projeto' }), project.name)
    if (!name?.trim()) return
    const p = await api.updateProject(projectId, { name: name.trim() })
    setProject((prev) => (prev ? { ...prev, ...p } : p))
  }

  const archiveProject = async () => {
    await api.updateProject(projectId, { archived: true })
    showToast(t('projects.archived', { defaultValue: 'Projeto arquivado' }), 'info')
    onBack()
  }

  const deleteProject = async () => {
    if (!window.confirm(t('projects.confirmDelete', { defaultValue: 'Excluir este projeto permanentemente?' })))
      return
    await api.deleteProject(projectId)
    setActiveProjectId(null)
    showToast(t('projects.deleted', { defaultValue: 'Projeto excluído' }), 'success')
    onBack()
  }

  const hasMemory = !!(project.memory?.summary_text || '').trim()
  const hasInstructions = !!(project.instructions || '').trim()
  const memoryUpdated = project.memory?.last_synthesized_at

  return (
    <div className="claude-projects claude-project-detail">
      <div className="claude-detail-layout">
        {/* ── Center column ── */}
        <main className="claude-detail-main">
          <div className="claude-detail-main-inner">
            <header className="claude-detail-header">
              <div className="claude-detail-header-left">
                {!sidebarOpen && (
                  <button
                    type="button"
                    className="icon-only-btn touch-target"
                    onClick={() => setSidebarOpen(true)}
                    aria-label={t('common.openMenu')}
                  >
                    <Menu size={20} />
                  </button>
                )}
                <button type="button" className="claude-back-link" onClick={onBack}>
                  <ArrowLeft size={15} strokeWidth={1.8} />
                  {t('projects.allProjects', { defaultValue: 'Todos os projetos' })}
                </button>
              </div>
            </header>

            <div className="claude-detail-title-row">
              <h1 className="claude-detail-title">{project.name}</h1>
              <div className="claude-detail-title-actions" ref={menuRef}>
                <button
                  type="button"
                  className="claude-icon-btn"
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-label="menu"
                >
                  <MoreVertical size={18} strokeWidth={1.7} />
                </button>
                <button
                  type="button"
                  className={`claude-icon-btn ${project.is_favorite ? 'is-fav' : ''}`}
                  onClick={toggleFavorite}
                  title={t('projects.favorite', { defaultValue: 'Favoritar' })}
                >
                  <Star size={18} strokeWidth={1.7} fill={project.is_favorite ? 'currentColor' : 'none'} />
                </button>
                {menuOpen && (
                  <div className="claude-overflow-menu">
                    <button type="button" onClick={() => { setMenuOpen(false); renameProject() }}>
                      <Pencil size={14} /> {t('projects.rename', { defaultValue: 'Renomear' })}
                    </button>
                    <button type="button" onClick={() => { setMenuOpen(false); archiveProject() }}>
                      <Archive size={14} /> {t('projects.archive', { defaultValue: 'Arquivar' })}
                    </button>
                    <button type="button" className="danger" onClick={() => { setMenuOpen(false); deleteProject() }}>
                      <Trash2 size={14} /> {t('projects.delete', { defaultValue: 'Excluir' })}
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Composer — Claude pill box */}
            <div className="claude-composer">
              <div className="claude-composer-inner">
                <textarea
                  className="claude-composer-input"
                  rows={2}
                  value={composer}
                  onChange={(e) => setComposer(e.target.value)}
                  placeholder={t('projects.composerPlaceholder', {
                    defaultValue: 'Como posso ajudar você hoje?',
                  })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && composer.trim()) {
                      e.preventDefault()
                      const msg = composer
                      setComposer('')
                      startProjectChat(msg)
                    }
                  }}
                />
                <div className="claude-composer-toolbar">
                  <button
                    type="button"
                    className="claude-composer-plus"
                    title={t('projects.attachHint', { defaultValue: 'Anexar (na conversa)' })}
                    onClick={() => startProjectChat()}
                  >
                    <Plus size={18} strokeWidth={1.8} />
                  </button>
                  <div className="claude-composer-right">
                    {/* Mesmos seletores do chat: provedor + modelo (antes só ciclava o modelo) */}
                    <div className="claude-composer-selectors">
                      <ProviderSelector />
                      <ModelSelector />
                    </div>
                    <button
                      type="button"
                      className="claude-send-fab"
                      disabled={!selectedModelId && !composer.trim()}
                      onClick={() => {
                        if (!selectedModelId) {
                          showToast(
                            t('chat.selectModelPlaceholder', {
                              defaultValue: 'Selecione um modelo antes de enviar',
                            }),
                            'error'
                          )
                          return
                        }
                        const msg = composer.trim()
                        setComposer('')
                        startProjectChat(msg || undefined)
                      }}
                      aria-label={t('projects.newChat', { defaultValue: 'Nova conversa' })}
                    >
                      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden>
                        <path
                          d="M8 13V3M8 3L3.5 7.5M8 3L12.5 7.5"
                          stroke="currentColor"
                          strokeWidth="1.6"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Chat list — simple rows like Claude */}
            <ul className="claude-chat-list">
              {chats.map((c) => (
                <li key={c.id}>
                  <button type="button" className="claude-chat-row" onClick={() => openChat(c.id)}>
                    <span className="claude-chat-title">{c.title}</span>
                    <span className="claude-chat-meta">
                      {t('projects.lastMessage', {
                        defaultValue: 'Última mensagem {{when}}',
                        when: formatShortDate(c.updated_at, i18n.language) || relativeTime(c.updated_at, i18n.language),
                      })}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            {chats.length === 0 && (
              <p className="claude-chat-empty">
                {t('projects.noChats', {
                  defaultValue: 'Nenhuma conversa ainda. Envie a primeira mensagem acima.',
                })}
              </p>
            )}
          </div>
        </main>

        {/* ── Right rail ── */}
        <aside className="claude-detail-aside">
          {/* Memory */}
          <section className="claude-side-card">
            <div className="claude-side-card-head">
              <h3>{t('projects.memory', { defaultValue: 'Memória' })}</h3>
              <span className="claude-scope-badge">
                <Lock size={11} strokeWidth={2} />
                {project.memory?.scope_badge || t('projects.onlyYou', { defaultValue: 'Apenas você' })}
              </span>
              <button
                type="button"
                className="claude-icon-btn sm"
                onClick={() => setEditingMemory((v) => !v)}
                title={t('projects.editMemory', { defaultValue: 'Editar memória' })}
              >
                <Pencil size={14} strokeWidth={1.7} />
              </button>
            </div>
            {editingMemory ? (
              <div className="claude-side-edit">
                <textarea value={memoryDraft} onChange={(e) => setMemoryDraft(e.target.value)} rows={5} />
                <div className="claude-side-edit-actions">
                  <button type="button" className="claude-btn-ghost" onClick={() => setEditingMemory(false)}>
                    {t('common.cancel')}
                  </button>
                  <button type="button" className="claude-btn-primary sm" onClick={saveMemory}>
                    {t('common.save')}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <p className={`claude-side-body ${!hasMemory ? 'is-placeholder' : ''}`}>
                  {hasMemory
                    ? project.memory!.summary_text
                    : t('projects.memoryEmpty', { defaultValue: 'Nenhuma memória sintetizada ainda.' })}
                </p>
                {memoryUpdated && (
                  <p className="claude-side-footnote">
                    {t('projects.lastUpdated', {
                      defaultValue: 'Última atualização {{when}}',
                      when: formatShortDate(memoryUpdated, i18n.language),
                    })}
                  </p>
                )}
              </>
            )}
          </section>

          {/* Instructions */}
          <section className="claude-side-card">
            <div className="claude-side-card-head">
              <h3>{t('projects.instructions', { defaultValue: 'Instruções' })}</h3>
              <button
                type="button"
                className="claude-icon-btn sm"
                onClick={() => setEditingInstructions(true)}
                aria-label={t('projects.addInstructions', { defaultValue: 'Adicionar instruções' })}
              >
                <Plus size={16} strokeWidth={1.8} />
              </button>
            </div>
            {editingInstructions ? (
              <div className="claude-side-edit">
                <textarea
                  value={instructionsDraft}
                  onChange={(e) => setInstructionsDraft(e.target.value)}
                  rows={6}
                  placeholder={t('projects.instructionsPlaceholder', {
                    defaultValue: 'Adicionar instruções para personalizar as respostas',
                  })}
                  autoFocus
                />
                <div className="claude-side-edit-actions">
                  <button type="button" className="claude-btn-ghost" onClick={() => setEditingInstructions(false)}>
                    {t('common.cancel')}
                  </button>
                  <button type="button" className="claude-btn-primary sm" onClick={saveInstructions}>
                    {t('common.save')}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                className={`claude-side-body clickable ${!hasInstructions ? 'is-placeholder' : ''}`}
                onClick={() => setEditingInstructions(true)}
              >
                {hasInstructions
                  ? project.instructions
                  : t('projects.instructionsEmpty', {
                      defaultValue: 'Adicionar instruções para personalizar as respostas',
                    })}
              </button>
            )}
          </section>

          {/* Files */}
          <section className="claude-side-card">
            <div className="claude-side-card-head">
              <h3>{t('projects.files', { defaultValue: 'Arquivos' })}</h3>
              <button
                type="button"
                className="claude-icon-btn sm"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploading}
                aria-label={t('projects.addFile', { defaultValue: 'Adicionar arquivo' })}
              >
                <Plus size={16} strokeWidth={1.8} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                hidden
                onChange={(e) => onUpload(e.target.files)}
              />
            </div>

            {files.length === 0 ? (
              <div
                className="claude-files-empty"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  onUpload(e.dataTransfer.files)
                }}
                onClick={() => fileInputRef.current?.click()}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') fileInputRef.current?.click()
                }}
              >
                <KnowledgeIllustration />
                <p>
                  {t('projects.dropzone', {
                    defaultValue:
                      'Adicione PDFs, documentos ou outros textos para usar como referência neste projeto.',
                  })}
                </p>
              </div>
            ) : (
              <ul className="claude-file-list">
                {files.map((f) => (
                  <li key={f.id} className="claude-file-item">
                    <FileText size={15} strokeWidth={1.6} className="claude-file-icon" />
                    <div className="claude-file-meta">
                      <span className="claude-file-name" title={f.filename}>
                        {f.filename}
                      </span>
                      <span className={`claude-file-status status-${f.index_status}`}>
                        {f.index_status === 'ready' && t('projects.indexReady', { defaultValue: 'Indexado' })}
                        {f.index_status === 'indexing' && t('projects.indexIndexing', { defaultValue: 'Indexando…' })}
                        {f.index_status === 'pending' && t('projects.indexPending', { defaultValue: 'Na fila' })}
                        {f.index_status === 'error' && t('projects.indexError', { defaultValue: 'Erro' })}
                      </span>
                      {(f.index_status === 'pending' || f.index_status === 'indexing') && (
                        <span className="claude-index-bar" aria-hidden />
                      )}
                    </div>
                    <button
                      type="button"
                      className="claude-icon-btn sm"
                      onClick={async (e) => {
                        e.stopPropagation()
                        await api.deleteProjectFile(projectId, f.id)
                        setFiles((prev) => prev.filter((x) => x.id !== f.id))
                      }}
                      aria-label={t('common.delete', { defaultValue: 'Excluir' })}
                    >
                      <X size={13} />
                    </button>
                  </li>
                ))}
                <li>
                  <button
                    type="button"
                    className="claude-add-more-files"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                  >
                    <Plus size={14} />
                    {t('projects.addFile', { defaultValue: 'Adicionar arquivo' })}
                  </button>
                </li>
              </ul>
            )}
          </section>
        </aside>
      </div>
    </div>
  )
}

/**
 * Shell de Projetos (workspaces Claude-style).
 * - Lista: cards de projetos (API /projects) — NÃO agrupa por project_tag
 * - Clique no card → tela de detalhe (composer + chats + Memória/Instruções/Arquivos)
 */
export function ProjectsPanel() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [newOpen, setNewOpen] = useState(false)

  // Deep-link opcional: ?project=<id> na URL (só na montagem)
  useEffect(() => {
    try {
      const params = new URLSearchParams(window.location.search)
      const pid = params.get('project')
      if (pid) setSelectedId(pid)
    } catch {
      /* ignore */
    }
  }, [])

  const openProject = useCallback((id: string) => {
    setSelectedId(id)
    try {
      const url = new URL(window.location.href)
      url.searchParams.set('project', id)
      window.history.replaceState({}, '', url.toString())
    } catch {
      /* ignore */
    }
  }, [])

  const backToList = useCallback(() => {
    setSelectedId(null)
    try {
      const url = new URL(window.location.href)
      url.searchParams.delete('project')
      window.history.replaceState({}, '', url.toString())
    } catch {
      /* ignore */
    }
  }, [])

  if (selectedId) {
    return (
      <>
        <ProjectDetailPage projectId={selectedId} onBack={backToList} />
        <NewProjectModal open={newOpen} onClose={() => setNewOpen(false)} onCreated={(p) => openProject(p.id)} />
      </>
    )
  }

  return (
    <>
      <ProjectsListPage onOpen={openProject} onNew={() => setNewOpen(true)} />
      <NewProjectModal
        open={newOpen}
        onClose={() => setNewOpen(false)}
        onCreated={(p) => openProject(p.id)}
      />
    </>
  )
}
