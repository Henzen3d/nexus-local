import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Archive,
  ArrowLeft,
  ChevronDown,
  FileText,
  Folder,
  Info,
  Lock,
  Menu,
  Mic,
  MoreVertical,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Star,
  Trash2,
  X,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { ProviderSelector } from './ProviderSelector'
import { ModelSelector } from './ModelSelector'
import { SimpleModeSelector } from './SimpleModeSelector'
import type { Project, ProjectChat, ProjectFile, ProjectCapacity } from '../types'

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
    const d = new Date(iso)
    const now = new Date()
    const isToday = d.toDateString() === now.toDateString()
    if (isToday) return 'Hoje'
    
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (d.toDateString() === yesterday.toDateString()) return 'Ontem'

    return d.toLocaleDateString(locale, { day: 'numeric', month: 'short' })
  } catch {
    return ''
  }
}

function formatBytes(bytes?: number): string {
  if (!bytes || bytes <= 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) {
    const kb = bytes / 1024
    return `${kb.toFixed(1).replace('.', ',')} kB`
  }
  const mb = bytes / (1024 * 1024)
  return `${mb.toFixed(1).replace('.', ',')} MB`
}

function getExtensionBadge(filename: string): string {
  const parts = filename.split('.')
  if (parts.length > 1) {
    const ext = parts.pop()!.toUpperCase()
    return ext.slice(0, 4)
  }
  return 'TXT'
}

function debounce<T extends (...args: any[]) => void>(fn: T, ms: number) {
  let t: ReturnType<typeof setTimeout> | null = null
  return (...args: Parameters<T>) => {
    if (t) clearTimeout(t)
    t = setTimeout(() => fn(...args), ms)
  }
}

/** Ilustração de estado vazio para arquivos do projeto */
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

/** Lista de projetos — Cards em grade estilo Claude */
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
        if (!cancelled) {
          const arr = Array.isArray(list) ? list : (list as any)?.projects || []
          setProjects(arr)
        }
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
                <select
                  value={sort}
                  onChange={(e) => setSort(e.target.value as SortKey)}
                  aria-label={t('projects.sortBy', { defaultValue: 'Ordenar por' })}
                >
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
                    'Projetos guardam instruções, arquivos e memória, e conectam chats do mesmo workspace.',
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
                {p.description && <div className="claude-project-card-desc">{p.description}</div>}
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
            defaultValue: 'Defina o nome e a descrição do seu novo workspace.',
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

/** Detalhe do Projeto — Paridade completa com Claude.ai */
function ProjectDetailPage({
  projectId,
  onBack,
}: {
  projectId: string
  onBack: () => void
}) {
  const { t, i18n } = useTranslation()
  const setSidebarOpen = useStore((s) => s.setSidebarOpen)
  const sidebarOpen = useStore((s) => s.sidebarOpen)
  const showToast = useStore((s) => s.showToast)
  const loadConversation = useStore((s) => s.loadConversation)
  const startNewConversation = useStore((s) => s.startNewConversation)
  const setActiveProjectId = useStore((s) => s.setActiveProjectId)
  const setView = useStore((s) => s.setView)
  const selectedModelId = useStore((s) => s.selectedModelId)
  const loadModels = useStore((s) => s.loadModels)
  const uiLevel = useStore((s) => s.uiLevel)

  const [project, setProject] = useState<Project | null>(null)
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [chats, setChats] = useState<ProjectChat[]>([])
  const [capacity, setCapacity] = useState<ProjectCapacity | null>(null)

  const [menuOpen, setMenuOpen] = useState(false)
  const [editingInstructions, setEditingInstructions] = useState(false)
  const [instructionsDraft, setInstructionsDraft] = useState('')

  const [editingDescription, setEditingDescription] = useState(false)
  const [descDraft, setDescDraft] = useState('')

  const [memoryModalOpen, setMemoryModalOpen] = useState(false)
  const [memoryDraft, setMemoryDraft] = useState('')
  const [synthesizing, setSynthesizing] = useState(false)

  const [fileSearchOpen, setFileSearchOpen] = useState(false)
  const [fileSearchQuery, setFileSearchQuery] = useState('')

  const [composer, setComposer] = useState('')
  const [uploading, setUploading] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [isListening, setIsListening] = useState(false)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const recognitionRef = useRef<any>(null)
  const onBackRef = useRef(onBack)
  onBackRef.current = onBack

  useEffect(() => {
    loadModels()
  }, [loadModels])

  useEffect(() => {
    setActiveProjectId(projectId)
  }, [projectId, setActiveProjectId])

  // Carrega dados iniciais do projeto
  useEffect(() => {
    let cancelled = false
    setProject(null)
    setLoadError(false)
    ;(async () => {
      try {
        const [p, f, c, cap] = await Promise.all([
          api.getProject(projectId),
          api.listProjectFiles(projectId),
          api.listProjectChats(projectId),
          api.getProjectCapacity(projectId),
        ])
        if (cancelled) return
        setProject(p)
        setFiles(f)
        setChats(c)
        setCapacity(cap)
        setInstructionsDraft(p.instructions || '')
        setMemoryDraft(p.memory?.summary_text || '')
        setDescDraft(p.description || '')
      } catch (e) {
        console.error(e)
        if (cancelled) return
        setLoadError(true)
        useStore.getState().showToast('Erro ao carregar projeto', 'error')
        onBackRef.current()
      }
    })()
    return () => {
      cancelled = true
    }
  }, [projectId])

  const refresh = useCallback(async () => {
    try {
      const [p, f, c, cap] = await Promise.all([
        api.getProject(projectId),
        api.listProjectFiles(projectId),
        api.listProjectChats(projectId),
        api.getProjectCapacity(projectId),
      ])
      setProject(p)
      setFiles(f)
      setChats(c)
      setCapacity(cap)
      setInstructionsDraft(p.instructions || '')
      setMemoryDraft(p.memory?.summary_text || '')
      setDescDraft(p.description || '')
    } catch (e) {
      console.error(e)
      showToast(t('projects.loadError', { defaultValue: 'Erro ao carregar projeto' }), 'error')
    }
  }, [projectId, showToast, t])

  // Polling de indexação de arquivos
  const indexingBusy = files.some((f) => f.index_status === 'pending' || f.index_status === 'indexing')
  useEffect(() => {
    if (!indexingBusy) return
    pollRef.current = setInterval(async () => {
      try {
        const updatedFiles = await api.listProjectFiles(projectId)
        setFiles(updatedFiles)
        if (updatedFiles.every((f) => f.index_status !== 'pending' && f.index_status !== 'indexing')) {
          const cap = await api.getProjectCapacity(projectId)
          setCapacity(cap)
        }
      } catch {
        /* ignore */
      }
    }, 2000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [indexingBusy, projectId])

  // Fecha menu de contexto em clique externo
  useEffect(() => {
    if (!menuOpen) return
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setMenuOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [menuOpen])

  const filteredFiles = useMemo(() => {
    if (!fileSearchQuery.trim()) return files
    const q = fileSearchQuery.trim().toLowerCase()
    return files.filter((f) => f.filename.toLowerCase().includes(q))
  }, [files, fileSearchQuery])

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
      const cap = await api.getProjectCapacity(projectId)
      setCapacity(cap)
      showToast(t('projects.instructionsSaved', { defaultValue: 'Instruções salvas' }), 'success')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao salvar' }), 'error')
    }
  }

  const saveDescription = async () => {
    try {
      const p = await api.updateProject(projectId, { description: descDraft.trim() })
      setProject((prev) => (prev ? { ...prev, ...p } : p))
      setEditingDescription(false)
      showToast(t('projects.descSaved', { defaultValue: 'Descrição atualizada' }), 'success')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao salvar' }), 'error')
    }
  }

  const handleSynthesizeMemory = async () => {
    setSynthesizing(true)
    try {
      const res = await api.synthesizeProjectMemory(projectId)
      const newSummary = res.summary_text || ''
      setMemoryDraft(newSummary)
      setProject((prev) =>
        prev
          ? {
              ...prev,
              memory: {
                summary_text: newSummary,
                last_synthesized_at: new Date().toISOString(),
                scope_badge: 'Apenas você',
              },
            }
          : prev
      )
      const cap = await api.getProjectCapacity(projectId)
      setCapacity(cap)
      showToast(
        t('projects.memorySynthesized', { defaultValue: 'Memória sintetizada a partir das conversas do projeto!' }),
        'success'
      )
    } catch (e) {
      console.error(e)
      showToast(t('projects.synthesizeError', { defaultValue: 'Erro ao sintetizar memória' }), 'error')
    } finally {
      setSynthesizing(false)
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
      const cap = await api.getProjectCapacity(projectId)
      setCapacity(cap)
      setMemoryModalOpen(false)
      showToast(t('projects.memorySaved', { defaultValue: 'Memória salva' }), 'success')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao salvar' }), 'error')
    }
  }

  const clearMemory = async () => {
    if (!window.confirm(t('projects.confirmClearMemory', { defaultValue: 'Limpar toda a memória deste projeto?' }))) return
    try {
      await api.patchProjectMemory(projectId, '')
      setMemoryDraft('')
      setProject((prev) =>
        prev
          ? {
              ...prev,
              memory: {
                summary_text: '',
                last_synthesized_at: new Date().toISOString(),
                scope_badge: 'Apenas você',
              },
            }
          : prev
      )
      const cap = await api.getProjectCapacity(projectId)
      setCapacity(cap)
      showToast(t('projects.memoryCleared', { defaultValue: 'Memória limpa' }), 'info')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao limpar memória' }), 'error')
    }
  }

  const onUpload = async (fileList: FileList | null) => {
    if (!fileList?.length) return
    setUploading(true)
    let uploadCount = 0
    try {
      for (const file of Array.from(fileList)) {
        try {
          await api.uploadProjectFile(projectId, file)
          uploadCount++
        } catch (err: any) {
          const msg = err.message || ''
          if (msg.includes('duplicado') || msg.includes('409')) {
            showToast(msg, 'info')
          } else {
            showToast(`${t('projects.uploadError', { defaultValue: 'Falha no upload' })}: ${file.name}`, 'error')
          }
        }
      }
      if (uploadCount > 0) {
        showToast(t('projects.fileUploaded', { defaultValue: 'Arquivo enviado: indexando…' }), 'success')
      }
      await refresh()
    } catch (e) {
      console.error(e)
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const onDeleteFile = async (fileId: string, fileName: string) => {
    if (!window.confirm(t('projects.confirmDeleteFile', {
      defaultValue: `Remover o arquivo "${fileName}" deste projeto?`,
      name: fileName,
    }))) {
      return
    }
    try {
      await api.deleteProjectFile(projectId, fileId)
      setFiles((prev) => prev.filter((x) => x.id !== fileId))
      const cap = await api.getProjectCapacity(projectId)
      setCapacity(cap)
      showToast(t('projects.fileDeleted', { defaultValue: 'Arquivo removido' }), 'info')
    } catch {
      showToast(t('common.error', { defaultValue: 'Erro ao remover arquivo' }), 'error')
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

  const toggleVoice = () => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    if (!SpeechRecognition) {
      showToast(t('chat.micUnsupported', { defaultValue: 'Reconhecimento de voz não suportado pelo navegador' }), 'error')
      return
    }
    if (isListening && recognitionRef.current) {
      recognitionRef.current.stop()
      setIsListening(false)
      return
    }
    try {
      const rec = new SpeechRecognition()
      rec.lang = i18n.language || 'pt-BR'
      rec.continuous = false
      rec.interimResults = true
      rec.onresult = (event: any) => {
        const transcript = Array.from(event.results)
          .map((r: any) => r[0]?.transcript || '')
          .join('')
        setComposer(transcript)
      }
      rec.onerror = () => setIsListening(false)
      rec.onend = () => setIsListening(false)
      recognitionRef.current = rec
      rec.start()
      setIsListening(true)
    } catch {
      setIsListening(false)
    }
  }

  const hasMemory = !!(project.memory?.summary_text || '').trim()
  const hasInstructions = !!(project.instructions || '').trim()

  return (
    <div className="claude-projects claude-project-detail">
      <div className="claude-detail-layout">
        {/* ── Coluna Central ── */}
        <main className="claude-detail-main">
          <div className="claude-detail-main-inner">
            {/* Breadcrumb estilo Claude.ai */}
            <div className="claude-breadcrumb">
              <button type="button" className="claude-breadcrumb-link" onClick={onBack}>
                {t('sidebar.projects', { defaultValue: 'Projetos' })}
              </button>
              <span className="claude-breadcrumb-sep">/</span>
              <span className="claude-breadcrumb-current">{project.name}</span>
            </div>

            {/* Linha de Título com Descrição e Ações */}
            <div className="claude-detail-title-row">
              <div className="claude-title-left">
                <h1 className="claude-detail-title">{project.name}</h1>
                {editingDescription ? (
                  <div className="claude-desc-edit-form">
                    <input
                      autoFocus
                      type="text"
                      value={descDraft}
                      onChange={(e) => setDescDraft(e.target.value)}
                      placeholder={t('projects.descPlaceholder', { defaultValue: 'Descrição do projeto (opcional)' })}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') saveDescription()
                        if (e.key === 'Escape') setEditingDescription(false)
                      }}
                    />
                    <div className="claude-desc-edit-btns">
                      <button type="button" className="claude-btn-primary sm" onClick={saveDescription}>
                        {t('common.save', { defaultValue: 'Salvar' })}
                      </button>
                      <button type="button" className="claude-btn-ghost sm" onClick={() => setEditingDescription(false)}>
                        {t('common.cancel', { defaultValue: 'Cancelar' })}
                      </button>
                    </div>
                  </div>
                ) : (
                  <div
                    className={`claude-detail-desc ${!project.description ? 'is-empty' : ''}`}
                    onClick={() => setEditingDescription(true)}
                    role="button"
                    tabIndex={0}
                  >
                    <span>
                      {project.description || t('projects.addDescPrompt', { defaultValue: 'Adicionar descrição do projeto...' })}
                    </span>
                    <button
                      type="button"
                      className="claude-icon-btn sm desc-edit-btn"
                      onClick={(e) => {
                        e.stopPropagation()
                        setEditingDescription(true)
                      }}
                      title={t('projects.editDesc', { defaultValue: 'Editar descrição' })}
                      aria-label={t('projects.editDesc', { defaultValue: 'Editar descrição' })}
                    >
                      <Pencil size={12} />
                    </button>
                  </div>
                )}
              </div>

              <div className="claude-detail-title-actions" ref={menuRef}>
                <button
                  type="button"
                  className={`claude-icon-btn ${project.is_favorite ? 'is-fav' : ''}`}
                  onClick={toggleFavorite}
                  title={t('projects.favorite', { defaultValue: 'Favoritar' })}
                  aria-label={t('projects.favorite', { defaultValue: 'Favoritar' })}
                >
                  <Star size={18} strokeWidth={1.7} fill={project.is_favorite ? 'currentColor' : 'none'} />
                </button>
                <button
                  type="button"
                  className="claude-icon-btn"
                  onClick={() => setMenuOpen((v) => !v)}
                  aria-label="menu"
                >
                  <MoreVertical size={18} strokeWidth={1.7} />
                </button>
                {menuOpen && (
                  <div className="claude-overflow-menu">
                    <button type="button" onClick={() => { setMenuOpen(false); renameProject() }}>
                      <Pencil size={14} /> {t('projects.rename', { defaultValue: 'Renomear' })}
                    </button>
                    <button type="button" onClick={() => { setMenuOpen(false); setEditingDescription(true) }}>
                      <FileText size={14} /> {t('projects.editDesc', { defaultValue: 'Editar descrição' })}
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

            {/* Composer do Projeto */}
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
                    {/* Seletores respeitando o uiLevel */}
                    <div className="claude-composer-selectors">
                      {uiLevel === 'simple' ? (
                        <SimpleModeSelector compact />
                      ) : (
                        <>
                          <ProviderSelector />
                          <ModelSelector compact />
                        </>
                      )}
                    </div>

                    {/* Botão de voz */}
                    <button
                      type="button"
                      className={`claude-composer-mic-btn ${isListening ? 'listening' : ''}`}
                      onClick={toggleVoice}
                      title={isListening ? t('chat.micStop', { defaultValue: 'Parar gravação' }) : t('chat.mic', { defaultValue: 'Falar' })}
                      aria-label={t('chat.mic', { defaultValue: 'Falar' })}
                    >
                      <Mic size={16} />
                    </button>

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

            {/* Rótulo Recentes */}
            <div className="claude-recents-header">
              <h2>{t('projects.recents', { defaultValue: 'Recentes' })}</h2>
            </div>

            {/* Lista de chats em Linha Única */}
            <ul className="claude-chat-single-list">
              {chats.map((c) => (
                <li key={c.id}>
                  <button type="button" className="claude-chat-single-row" onClick={() => openChat(c.id)}>
                    <span className="claude-chat-title">{c.title}</span>
                    <span className="claude-chat-date">
                      {formatShortDate(c.updated_at, i18n.language) || relativeTime(c.updated_at, i18n.language)}
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

        {/* ── Coluna Direita: Card Unificado Contínuo ── */}
        <aside className="claude-detail-aside">
          <div className="claude-unified-side-card">
            {/* SEÇÃO 1: Instruções */}
            <section className="claude-side-section claude-section-instructions">
              <div className="claude-side-head">
                <h3>{t('projects.instructions', { defaultValue: 'Instruções' })}</h3>
                <button
                  type="button"
                  className="claude-icon-btn sm"
                  onClick={() => setEditingInstructions((v) => !v)}
                  title={t('projects.editInstructions', { defaultValue: 'Editar instruções' })}
                  aria-label={t('projects.editInstructions', { defaultValue: 'Editar instruções' })}
                >
                  <Pencil size={13} strokeWidth={1.8} />
                </button>
              </div>

              {editingInstructions ? (
                <div className="claude-side-edit">
                  <textarea
                    value={instructionsDraft}
                    onChange={(e) => setInstructionsDraft(e.target.value)}
                    rows={5}
                    placeholder={t('projects.instructionsPlaceholder', {
                      defaultValue: 'Adicionar instruções para personalizar as respostas neste projeto...',
                    })}
                    autoFocus
                  />
                  <div className="claude-side-edit-actions">
                    <button type="button" className="claude-btn-ghost sm" onClick={() => setEditingInstructions(false)}>
                      {t('common.cancel', { defaultValue: 'Cancelar' })}
                    </button>
                    <button type="button" className="claude-btn-primary sm" onClick={saveInstructions}>
                      {t('common.save', { defaultValue: 'Salvar' })}
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  className={`claude-instructions-preview ${!hasInstructions ? 'is-placeholder' : ''}`}
                  onClick={() => setEditingInstructions(true)}
                  role="button"
                  tabIndex={0}
                >
                  {hasInstructions ? (
                    <p>{project.instructions}</p>
                  ) : (
                    <p className="placeholder-text">
                      {t('projects.instructionsEmpty', {
                        defaultValue: 'Adicionar instruções para personalizar as respostas',
                      })}
                    </p>
                  )}
                </div>
              )}
            </section>

            <div className="claude-side-divider" />

            {/* SEÇÃO 2: Memória */}
            <section className="claude-side-section claude-section-memory">
              <div className="claude-side-head">
                <div className="head-left-group">
                  <h3>{t('projects.memory', { defaultValue: 'Memória' })}</h3>
                  <span className="claude-scope-badge">
                    <Lock size={11} strokeWidth={2} />
                    {project.memory?.scope_badge || t('projects.onlyYou', { defaultValue: 'Apenas você' })}
                  </span>
                </div>
                <button
                  type="button"
                  className="claude-link-btn"
                  onClick={() => setMemoryModalOpen(true)}
                >
                  {t('projects.viewMemory', { defaultValue: 'Ver memória' })}
                </button>
              </div>

              <div
                className={`claude-memory-preview ${!hasMemory ? 'is-placeholder' : ''}`}
                onClick={() => setMemoryModalOpen(true)}
                role="button"
                tabIndex={0}
              >
                <p>
                  {hasMemory
                    ? project.memory!.summary_text
                    : t('projects.memoryEmpty', { defaultValue: 'Nenhuma memória sintetizada ainda.' })}
                </p>
              </div>
            </section>

            <div className="claude-side-divider" />

            {/* SEÇÃO 3: Contexto (Arquivos + Capacidade) */}
            <section className="claude-side-section claude-section-context">
              <div className="claude-side-head">
                <h3>{t('projects.context', { defaultValue: 'Contexto' })}</h3>
                <div className="context-head-actions">
                  <button
                    type="button"
                    className={`claude-icon-btn sm ${fileSearchOpen ? 'active' : ''}`}
                    onClick={() => {
                      setFileSearchOpen((v) => !v)
                      if (fileSearchOpen) setFileSearchQuery('')
                    }}
                    title={t('common.search', { defaultValue: 'Buscar no contexto' })}
                    aria-label={t('common.search', { defaultValue: 'Buscar no contexto' })}
                  >
                    <Search size={14} />
                  </button>
                  <button
                    type="button"
                    className="claude-icon-btn sm"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={uploading}
                    title={t('projects.addFile', { defaultValue: 'Adicionar arquivo' })}
                    aria-label={t('projects.addFile', { defaultValue: 'Adicionar arquivo' })}
                  >
                    <Plus size={16} strokeWidth={2} />
                  </button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    hidden
                    onChange={(e) => onUpload(e.target.files)}
                  />
                </div>
              </div>

              {/* Barra de Capacidade de Contexto */}
              <div className="claude-capacity-box">
                <div className="claude-capacity-header">
                  <span className="claude-capacity-label">
                    {capacity
                      ? capacity.usage_percent >= 100
                        ? `${t('projects.capacityFull', { defaultValue: '100% da capacidade utilizada' })} (${t('projects.ragActive', { defaultValue: 'Modo RAG ativo' })})`
                        : `${capacity.usage_percent}% ${t('projects.capacityUsed', { defaultValue: 'da capacidade do projeto utilizada' })}`
                      : t('common.loading', { defaultValue: 'Carregando…' })}
                  </span>
                  <div className="claude-capacity-tooltip-trigger" tabIndex={0} role="button" aria-label="Informações sobre capacidade de contexto">
                    <Info size={13} className="claude-info-icon" />
                    <div className="claude-capacity-tooltip-popup">
                      <h4>{t('projects.contextCapacityTitle', { defaultValue: 'Capacidade de Contexto do Projeto' })}</h4>
                      <div className="tooltip-stat-row">
                        <span>{t('projects.instructions', { defaultValue: 'Instruções' })}:</span>
                        <strong>~{capacity?.breakdown?.instructions_tokens ?? 0} tokens</strong>
                      </div>
                      <div className="tooltip-stat-row">
                        <span>{t('projects.memory', { defaultValue: 'Memória' })}:</span>
                        <strong>~{capacity?.breakdown?.memory_tokens ?? 0} tokens</strong>
                      </div>
                      <div className="tooltip-stat-row">
                        <span>{t('projects.files', { defaultValue: 'Arquivos' })} ({capacity?.breakdown?.file_count ?? 0}):</span>
                        <strong>~{capacity?.breakdown?.files_tokens ?? 0} tokens</strong>
                      </div>
                      <div className="tooltip-stat-row total-row">
                        <span>{t('common.total', { defaultValue: 'Total' })}:</span>
                        <strong>{capacity?.total_tokens ?? 0} / {capacity?.capacity_limit ?? 131072} tokens</strong>
                      </div>
                      <p className="tooltip-mode-desc">
                        {capacity?.mode === 'full'
                          ? t('projects.modeFullDesc', { defaultValue: '⚡ Modo Integral: O acervo cabe confortavelmente no contexto e é injetado diretamente no prompt para respostas ricas.' })
                          : t('projects.modeRagDesc', { defaultValue: '🔍 Modo Recuperação (RAG): O acervo excede a injeção direta; trechos relevantes são buscados por similaridade vetorial com citação da fonte [Fonte: arquivo].' })}
                      </p>
                    </div>
                  </div>
                </div>
                <div className="claude-capacity-bar-track">
                  <div
                    className={`claude-capacity-bar-fill ${
                      (capacity?.usage_percent ?? 0) >= 100
                        ? 'fill-rag'
                        : (capacity?.usage_percent ?? 0) >= 70
                        ? 'fill-amber'
                        : 'fill-normal'
                    }`}
                    style={{ width: `${Math.min(100, Math.max(3, capacity?.usage_percent ?? 0))}%` }}
                  />
                </div>
              </div>

              {/* Campo de busca rápida no contexto */}
              {fileSearchOpen && (
                <div className="claude-context-search-row">
                  <Search size={13} />
                  <input
                    autoFocus
                    type="search"
                    value={fileSearchQuery}
                    onChange={(e) => setFileSearchQuery(e.target.value)}
                    placeholder={t('projects.filterFilesPlaceholder', { defaultValue: 'Filtrar arquivos por nome…' })}
                  />
                  {fileSearchQuery && (
                    <button type="button" onClick={() => setFileSearchQuery('')}>
                      <X size={12} />
                    </button>
                  )}
                </div>
              )}

              {/* Grid em 2 colunas estilo Claude.ai */}
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
              ) : filteredFiles.length === 0 ? (
                <p className="claude-files-not-found">
                  {t('projects.noFilesFound', { defaultValue: 'Nenhum arquivo corresponde à busca.' })}
                </p>
              ) : (
                <div className="claude-context-grid">
                  {filteredFiles.map((f) => {
                    const ext = getExtensionBadge(f.filename)
                    return (
                      <div key={f.id} className="claude-context-card" title={f.filename}>
                        <div className="context-card-top">
                          <span className="context-file-name">{f.filename}</span>
                          <button
                            type="button"
                            className="context-file-delete-btn"
                            onClick={(e) => {
                              e.stopPropagation()
                              onDeleteFile(f.id, f.filename)
                            }}
                            title={t('common.delete', { defaultValue: 'Remover arquivo' })}
                            aria-label={t('common.delete', { defaultValue: 'Remover arquivo' })}
                          >
                            <X size={12} />
                          </button>
                        </div>
                        <div className="context-card-sub">
                          <span className="context-file-size">{formatBytes(f.file_size || f.size_bytes)}</span>
                        </div>
                        <div className="context-card-bottom">
                          <span className="context-ext-badge">{ext}</span>
                          {f.index_status === 'pending' || f.index_status === 'indexing' ? (
                            <span className="context-status-pill status-indexing" title="Indexando…">
                              <span className="indexing-dot" />
                            </span>
                          ) : f.index_status === 'error' ? (
                            <span className="context-status-pill status-error" title={f.index_error || 'Erro ao indexar'}>
                              !
                            </span>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </section>
          </div>
        </aside>
      </div>

      {/* Modal / Drawer "Ver memória" */}
      {memoryModalOpen && (
        <div className="claude-modal-overlay" onClick={() => setMemoryModalOpen(false)}>
          <div className="claude-modal claude-memory-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
            <div className="claude-modal-header">
              <div className="claude-modal-title-row">
                <h2>{t('projects.projectMemoryTitle', { defaultValue: 'Memória do Projeto' })}</h2>
                <span className="claude-scope-badge">
                  <Lock size={11} strokeWidth={2} />
                  {project.memory?.scope_badge || t('projects.onlyYou', { defaultValue: 'Apenas você' })}
                </span>
              </div>
              <button type="button" className="claude-icon-btn" onClick={() => setMemoryModalOpen(false)} aria-label={t('common.close')}>
                <X size={18} />
              </button>
            </div>
            <p className="claude-modal-desc">
              {t('projects.memoryDesc', {
                defaultValue: 'Fatos, decisões e preferências aprendidos a partir das conversas deste projeto.',
              })}
            </p>

            <div className="claude-memory-editor">
              <textarea
                rows={9}
                value={memoryDraft}
                onChange={(e) => setMemoryDraft(e.target.value)}
                placeholder={t('projects.memoryEmpty', { defaultValue: 'Nenhuma memória sintetizada ainda.' })}
              />
            </div>

            <div className="claude-memory-modal-footer">
              <div className="footer-left">
                <button
                  type="button"
                  className="claude-btn-synthesize"
                  disabled={synthesizing}
                  onClick={handleSynthesizeMemory}
                  title={t('projects.synthesizeHint', { defaultValue: 'Analisa o histórico de conversas do projeto para gerar ou atualizar a memória' })}
                >
                  <Sparkles size={14} className={synthesizing ? 'spin' : ''} />
                  {synthesizing
                    ? t('projects.synthesizing', { defaultValue: 'Sintetizando…' })
                    : t('projects.synthesizeNow', { defaultValue: 'Sintetizar agora' })}
                </button>
                {memoryDraft.trim() && (
                  <button
                    type="button"
                    className="claude-btn-ghost danger sm"
                    onClick={clearMemory}
                  >
                    {t('projects.clearMemory', { defaultValue: 'Limpar' })}
                  </button>
                )}
              </div>
              <div className="footer-right">
                <button type="button" className="claude-btn-ghost sm" onClick={() => setMemoryModalOpen(false)}>
                  {t('common.cancel', { defaultValue: 'Cancelar' })}
                </button>
                <button type="button" className="claude-btn-primary sm" onClick={saveMemory}>
                  {t('common.save', { defaultValue: 'Salvar' })}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Shell de Projetos (workspaces Claude-style).
 */
export function ProjectsPanel() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [newOpen, setNewOpen] = useState(false)

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
