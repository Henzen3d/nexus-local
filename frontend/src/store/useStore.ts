import { create } from 'zustand'
import type { Artifact, Conversation, ConversationDetail, Message, Model, CacheStats, CacheSettings, FusionStatusEntry, Attachment, WebSearchSource } from '../types'
import { api } from '../api/client'
import { detectInitialLocale } from '../i18n'

// ── Persistência de provedor/modelo (por usuário quando possível) ───────────

function _scopedKey(suffix: string): string {
  if (typeof window === 'undefined') return `nexuslocal_${suffix}`
  try {
    const u = localStorage.getItem('nexuslocal_user')
    const user = u ? JSON.parse(u) : null
    if (user?.id) return `nexuslocal_${user.id}_${suffix}`
  } catch {
    /* ignore */
  }
  return `nexuslocal_${suffix}`
}

function readPersistedModelSelection(): {
  modelId: string | null
  providerId: string | null
} {
  if (typeof window === 'undefined') return { modelId: null, providerId: null }
  try {
    const modelId = localStorage.getItem(_scopedKey('selected_model_id'))
    const providerId = localStorage.getItem(_scopedKey('selected_provider_id'))
    // fallback legado (global)
    return {
      modelId: modelId || localStorage.getItem('nexuslocal_selected_model_id'),
      providerId: providerId || localStorage.getItem('nexuslocal_selected_provider_id'),
    }
  } catch {
    return { modelId: null, providerId: null }
  }
}

function readLastModelByProvider(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const raw =
      localStorage.getItem(_scopedKey('last_model_by_provider')) ||
      localStorage.getItem('nexuslocal_last_model_by_provider')
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function persistModelSelection(modelId: string, providerId: string) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(_scopedKey('selected_model_id'), modelId)
    localStorage.setItem(_scopedKey('selected_provider_id'), providerId)
    // legado global (compat)
    localStorage.setItem('nexuslocal_selected_model_id', modelId)
    localStorage.setItem('nexuslocal_selected_provider_id', providerId)

    const map = readLastModelByProvider()
    map[providerId] = modelId
    const mapJson = JSON.stringify(map)
    localStorage.setItem(_scopedKey('last_model_by_provider'), mapJson)
    localStorage.setItem('nexuslocal_last_model_by_provider', mapJson)
  } catch {
    /* ignore quota / private mode */
  }
}

/** Resolve model+provider válidos a partir da lista carregada e preferências salvas. */
function resolveModelSelection(
  models: Model[],
  preferredModelId: string | null | undefined,
  preferredProviderId: string | null | undefined
): { modelId: string | null; providerId: string | null } {
  if (!models.length) return { modelId: null, providerId: null }

  const lastByProvider = readLastModelByProvider()

  // 1) modelo persistido/atual ainda existe
  if (preferredModelId) {
    const found = models.find((m) => m.id === preferredModelId)
    if (found) return { modelId: found.id, providerId: found.provider_id }
  }

  // 2) provedor persistido: último modelo daquele provedor, senão o primeiro da lista
  if (preferredProviderId) {
    const lastId = lastByProvider[preferredProviderId]
    if (lastId) {
      const last = models.find((m) => m.id === lastId && m.provider_id === preferredProviderId)
      if (last) return { modelId: last.id, providerId: last.provider_id }
    }
    const firstOfProv = models.find((m) => m.provider_id === preferredProviderId)
    if (firstOfProv) return { modelId: firstOfProv.id, providerId: firstOfProv.provider_id }
  }

  // 3) fallback: primeiro modelo da API (já ordenado por ranking)
  return { modelId: models[0].id, providerId: models[0].provider_id }
}

interface AppState {
  // Sidebar
  conversations: Conversation[]
  activeConversationId: string | null
  activeConversation: ConversationDetail | null
  sidebarOpen: boolean

  // Auth
  token: string | null
  user: { id: string; username: string; email?: string | null; phone?: string | null; role: string } | null
  setAuth: (token: string, user: { id: string; username: string; email?: string | null; phone?: string | null; role: string }) => void
  logout: () => void

  // Current chat
  messages: Message[]
  streamingContent: string
  isStreaming: boolean
  lastCacheHit: { type: string; similarity: number } | null

  // Model selection
  models: Model[]
  selectedModelId: string | null
  selectedProviderId: string | null

  // View
  view: 'chat' | 'admin' | 'conversations' | 'artifacts' | 'projects'
  theme: 'light' | 'dark' | 'system'
  chatFont: 'sans' | 'serif' | 'mono'
  locale: string
  modelSortMode: 'ranking' | 'alphabetical'
  hapticFeedback: boolean
  displayName: string
  fullName: string
  occupation: string
  customInstructions: string

  // Cache state
  cacheStats: CacheStats | null
  cacheSettings: CacheSettings | null

  // Fusion
  fusionMode: boolean
  fusionActive: boolean

  // Web Search
  webSearchActive: boolean
  setWebSearchActive: (v: boolean) => void

  // Artifacts
  activeArtifact: Artifact | null
  artifactPanelOpen: boolean
  artifactHistory: Artifact[]        // todas as versões do artifact ativo (ordenadas por version ASC)
  activeConversationArtifacts: Artifact[] // Todos os artifacts pertencentes à conversa ativa (agrupados/versão mais recente)
  allArtifacts: Artifact[]
  /** ID do último artifact cujo fetch foi disparado — usado para descartar fetches obsoletos */
  _pendingArtifactId: string | null

  // Actions
  loadConversations: (search?: string, filter?: string, page?: number, limit?: number) => Promise<void>
  loadConversation: (id: string) => Promise<void>
  startNewConversation: () => void
  loadActiveConversationArtifacts: () => Promise<void>
  favoriteConversation: (id: string) => Promise<void>
  loadAllArtifacts: (search?: string) => Promise<void>
  appendToken: (token: string) => void
  finalizeStream: (messageId: string, artifactMeta?: { id: string; type: string; title: string }, artifacts?: { id: string; type: string; title: string }[], relayUsed?: boolean, relayModel?: string | null, webSearchUsed?: boolean, webSearchQuery?: string, webSearchSources?: WebSearchSource[]) => void
  setStreaming: (v: boolean) => void
  addUserMessage: (content: string, attachments?: Attachment[]) => void
  setConversationCreated: (id: string, title: string) => void
  setLastCacheHit: (hit: { type: string; similarity: number } | null) => void
  loadModels: () => Promise<void>
  selectModel: (modelId: string, providerId: string) => void
  /** Troca de provedor: restaura o último modelo usado nele (ou o 1º por ranking). */
  selectProvider: (providerId: string) => void
  setSidebarOpen: (v: boolean) => void
  setView: (v: 'chat' | 'admin' | 'conversations' | 'artifacts' | 'projects') => void
  setConversationProjectTag: (id: string, projectTag: string | null) => Promise<void>
  /** Assign conversation to a first-class Project workspace (project_id FK) */
  setConversationProjectId: (id: string, projectId: string | null) => Promise<void>
  /** When set, ProjectsPanel opens assign modal for this conversation id */
  projectAssignConversationId: string | null
  setProjectAssignConversationId: (id: string | null) => void
  /** Active Projects workspace — new chats / WS turns inherit this project_id */
  activeProjectId: string | null
  setActiveProjectId: (id: string | null) => void
  /** Cached project names for breadcrumb (id → name) */
  projectNameById: Record<string, string>
  setProjectName: (id: string, name: string) => void
  setTheme: (theme: 'light' | 'dark' | 'system') => void
  setChatFont: (font: 'sans' | 'serif' | 'mono') => void
  setLocale: (locale: string) => void
  setModelSortMode: (mode: 'ranking' | 'alphabetical') => void
  setHapticFeedback: (v: boolean) => void
  setProfile: (profile: { displayName?: string; fullName?: string; occupation?: string; customInstructions?: string }) => void
  /** Hydrate profile from backend (page reload with existing token). */
  hydrateProfileFromServer: () => Promise<void>
  renameConversation: (id: string, title: string) => Promise<void>
  deleteConversation: (id: string) => Promise<void>
  loadCacheStats: () => Promise<void>
  loadCacheSettings: () => Promise<void>
  updateCacheSettings: (data: Partial<CacheSettings>) => Promise<void>
  setFusionMode: (v: boolean) => void
  setFusionActive: (v: boolean) => void
  setFusionStatuses: (statuses: FusionStatusEntry[]) => void
  updateFusionStatus: (modelId: string, status: FusionStatusEntry['status'], response?: string, confidence?: FusionStatusEntry['confidence'], confidenceReason?: string | null) => void
  setFusionJudgeModelId: (id: string | null) => void
  updateFusionGrounding: (status: 'checking' | 'searching' | 'done', queries?: string[], found?: boolean) => void
  setFusionRefinedPrompt: (prompt: string) => void
  setActiveArtifact: (a: Artifact | null) => void
  setArtifactPanelOpen: (open: boolean) => void
  /**
   * Carrega todas as versões (histórico) de um artifact pelo group_id.
   * Chamado automaticamente por handleArtifactEvent e ao clicar numa versão.
   */
  loadArtifactHistory: (groupId: string) => Promise<void>
  /**
   * Navega entre versões do artifact ativo sem fazer novo fetch (usa o histórico já carregado).
   */
  navigateVersion: (direction: 'prev' | 'next') => void
  /**
   * Chamado quando o WS emite evento `type: "artifact"`.
   * Faz o fetch completo e abre o painel, com proteção contra race conditions:
   * - Descarta se o usuário já trocou de conversa durante o fetch.
   * - Descarta se uma resposta mais recente já iniciou um novo fetch.
   */
  handleArtifactEvent: (event: { id: string; artifact_type: string; title: string; conv_id: string; msg_id: string }) => Promise<void>
  toast: { message: string; type: 'success' | 'error' | 'info' } | null
  showToast: (message: string, type?: 'success' | 'error' | 'info') => void
  hideToast: () => void
  addErrorMessage: (content: string) => void
}

export const useStore = create<AppState>((set, get) => ({
  token: typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_token') : null,
  user: typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      return u ? JSON.parse(u) : null
    } catch {
      return null
    }
  })() : null,
  setAuth: (token, user) => {
    localStorage.setItem('nexuslocal_token', token)
    localStorage.setItem('nexuslocal_user', JSON.stringify(user))

    // Remove legacy GLOBAL profile keys (pre-multi-user). They used to leak
    // occupation/company from user A into a new account B on register/login.
    localStorage.removeItem('nexuslocal_display_name')
    localStorage.removeItem('nexuslocal_full_name')
    localStorage.removeItem('nexuslocal_occupation')
    localStorage.removeItem('nexuslocal_custom_instructions')

    const userId = user?.id || ''
    const username = user?.username || ''
    const formattedUsername = username
      ? username.charAt(0).toUpperCase() + username.slice(1)
      : ''

    // ONLY per-user keys — never fall back to global localStorage.
    const cachedDisplay = localStorage.getItem(`nexuslocal_${userId}_display_name`) || ''
    const cachedFull = localStorage.getItem(`nexuslocal_${userId}_full_name`) || ''
    const cachedOcc = localStorage.getItem(`nexuslocal_${userId}_occupation`) || ''
    const cachedInstr = localStorage.getItem(`nexuslocal_${userId}_custom_instructions`) || ''

    // UI fallback: username only (not occupation / custom instructions)
    const displayName = cachedDisplay || formattedUsername
    const fullName = cachedFull || ''
    const occupation = cachedOcc
    const customInstructions = cachedInstr

    set({ token, user, displayName, fullName, occupation, customInstructions })

    // Hydrate from backend. Migrate localStorage → server only for THIS userId keys.
    api.getUserProfile()
      .then(async (p) => {
        const serverHasData = !!(
          (p.display_name && p.display_name.trim()) ||
          (p.full_name && p.full_name.trim()) ||
          (p.occupation && p.occupation.trim()) ||
          (p.custom_instructions && p.custom_instructions.trim())
        )
        if (serverHasData) {
          const dn = p.display_name || displayName
          const fn = p.full_name || fullName
          const occ = p.occupation || occupation
          const ci = p.custom_instructions || customInstructions
          localStorage.setItem(`nexuslocal_${userId}_display_name`, dn)
          localStorage.setItem(`nexuslocal_${userId}_full_name`, fn)
          localStorage.setItem(`nexuslocal_${userId}_occupation`, occ)
          localStorage.setItem(`nexuslocal_${userId}_custom_instructions`, ci)
          set({ displayName: dn, fullName: fn, occupation: occ, customInstructions: ci })
        } else if (cachedDisplay || cachedFull || cachedOcc || cachedInstr) {
          // Only push keys that already belonged to this userId (re-login same browser)
          await api.saveUserProfile({
            display_name: cachedDisplay || formattedUsername,
            full_name: cachedFull,
            occupation: cachedOcc,
            custom_instructions: cachedInstr,
          })
        }
      })
      .catch((err) => console.warn('[profile] hydrate failed', err))
  },
  logout: () => {
    localStorage.removeItem('nexuslocal_token')
    localStorage.removeItem('nexuslocal_user')
    // Legacy global keys (must not survive for the next account)
    localStorage.removeItem('nexuslocal_display_name')
    localStorage.removeItem('nexuslocal_full_name')
    localStorage.removeItem('nexuslocal_occupation')
    localStorage.removeItem('nexuslocal_custom_instructions')
    set({
      token: null,
      user: null,
      conversations: [],
      activeConversationId: null,
      activeConversation: null,
      messages: [],
      activeArtifact: null,
      artifactPanelOpen: false,
      displayName: '',
      fullName: '',
      occupation: '',
      customInstructions: '',
    })
  },

  conversations: [],
  activeConversationId: null,
  activeConversation: null,
  sidebarOpen: typeof window !== 'undefined' ? window.innerWidth > 768 : true,
  messages: [],
  streamingContent: '',
  isStreaming: false,
  lastCacheHit: null,
  toast: null,
  models: [],
  selectedModelId: typeof window !== 'undefined' ? readPersistedModelSelection().modelId : null,
  selectedProviderId: typeof window !== 'undefined' ? readPersistedModelSelection().providerId : null,
  view: 'chat',
  theme: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_theme') as 'light' | 'dark' | 'system' : null) || 'system',
  chatFont: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_chat_font') as 'sans' | 'serif' | 'mono' : null) || 'sans',
  locale: typeof window !== 'undefined' ? detectInitialLocale() : 'en-US',
  modelSortMode: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_model_sort_mode') as 'ranking' | 'alphabetical' : null) || 'ranking',
  hapticFeedback: typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_haptic_feedback') === 'true' : false,
  displayName: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_display_name`) ||
               (user.username ? user.username.charAt(0).toUpperCase() + user.username.slice(1) : '')
      }
    } catch {}
    return ''
  })() : null) || '',
  fullName: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_full_name`) || ''
      }
    } catch {}
    return ''
  })() : null) || '',
  occupation: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_occupation`) || ''
      }
    } catch {}
    return ''
  })() : null) || '',
  customInstructions: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_custom_instructions`) || ''
      }
    } catch {}
    return ''
  })() : null) || '',
  cacheStats: null,
  cacheSettings: null,
  fusionMode: false,
  fusionActive: false,
  webSearchActive: false,
  activeArtifact: null,
  artifactPanelOpen: false,
  artifactHistory: [],
  activeConversationArtifacts: [],
  allArtifacts: [],
  _pendingArtifactId: null,
  projectAssignConversationId: null,
  activeProjectId: null,
  projectNameById: {},

  loadConversations: async (search?: string, filter?: string, page?: number, limit?: number) => {
    const conversations = await api.getConversations(search, filter, page, limit)
    set({ conversations })
  },

  loadConversation: async (id: string) => {
    const conv = await api.getConversation(id)
    set({
      activeConversationId: id,
      activeConversation: conv,
      messages: conv.messages,
      streamingContent: '',
      activeArtifact: null,
      artifactPanelOpen: false,
      artifactHistory: [],
      activeConversationArtifacts: [],
      _pendingArtifactId: null,
      view: 'chat',
      // Keep RAG context when opening a chat that belongs to a project
      activeProjectId: conv.project_id || null,
    })
    // Puxa a lista de artifacts da conversa em segundo plano
    get().loadActiveConversationArtifacts()
  },

  startNewConversation: () => {
    set({
      activeConversationId: null,
      activeConversation: null,
      messages: [],
      streamingContent: '',
      isStreaming: false,
      activeArtifact: null,
      artifactPanelOpen: false,
      artifactHistory: [],
      activeConversationArtifacts: [],
      _pendingArtifactId: null,
      view: 'chat',
      // Leaving explicit project context unless user opens a project chat again
      activeProjectId: null,
    })
  },

  addUserMessage: (content: string, attachments?: Attachment[]) => {
    const { selectedModelId, models } = get()
    const activeModel = models.find((m) => m.id === selectedModelId)
    const msg: Message = {
      id: `tmp-${Date.now()}`,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
      model_id: selectedModelId ?? undefined,
      model_display_name: activeModel?.display_name,
      provider: activeModel?.provider_name,
      attachments,
    }
    set((s) => ({ messages: [...s.messages, msg] }))
  },

  addErrorMessage: (content: string) => {
    const { selectedModelId } = get()
    const msg: Message = {
      id: `err-${Date.now()}`,
      role: 'error',
      content,
      model_id: selectedModelId ?? undefined,
    }
    set((s) => ({
      messages: [...s.messages, msg],
      isStreaming: false,
    }))
  },

  showToast: (message: string, type: 'success' | 'error' | 'info' = 'info') => {
    set({ toast: { message, type } })
  },

  hideToast: () => {
    set({ toast: null })
  },

  setConversationCreated: (id: string, title: string) => {
    set((s) => {
      const project_id = s.activeProjectId || null
      return {
        activeConversationId: id,
        activeConversation: {
          id,
          title,
          message_count: 0,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          project_id,
          messages: s.messages,
        },
        conversations: [
          {
            id,
            title,
            message_count: 0,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            project_id,
          },
          ...s.conversations,
        ],
      }
    })
  },

  appendToken: (token: string) => {
    set((s) => ({ streamingContent: s.streamingContent + token }))
  },

  finalizeStream: (
    messageId: string,
    artifactMeta?: { id: string; type: string; title: string },
    artifacts?: { id: string; type: string; title: string }[],
    relayUsed?: boolean,
    relayModel?: string | null,
    webSearchUsed?: boolean,
    webSearchQuery?: string,
    webSearchSources?: WebSearchSource[]
  ) => {
    const { streamingContent, selectedModelId, models } = get()
    const activeModel = models.find((m) => m.id === selectedModelId)
    const msg: Message = {
      id: messageId,
      role: 'assistant',
      content: streamingContent,
      model_id: selectedModelId ?? undefined,
      created_at: new Date().toISOString(),
      model_display_name: activeModel?.display_name,
      provider: activeModel?.provider_name,
      relay_used: relayUsed,
      relay_model: relayModel,
      web_search_used: webSearchUsed,
      web_search_query: webSearchQuery,
      web_search_sources: webSearchSources,
      // Popula os metadados do artifact no objeto de mensagem para que o badge seja exibido
      ...(artifactMeta
        ? { artifact_id: artifactMeta.id, artifact_type: artifactMeta.type, artifact_title: artifactMeta.title }
        : {}),
      artifacts: artifacts || (artifactMeta ? [artifactMeta] : []),
    }
    set((s) => ({
      messages: [...s.messages, msg],
      streamingContent: '',
      isStreaming: false,
    }))
  },

  setStreaming: (v: boolean) => set({ isStreaming: v }),

  setLastCacheHit: (hit) => set({ lastCacheHit: hit }),

  loadModels: async () => {
    const models = await api.getModels()
    const s = get()
    // Preferência: seleção em memória → localStorage → primeiro disponível
    const resolved = resolveModelSelection(
      models,
      s.selectedModelId,
      s.selectedProviderId
    )
    set({
      models,
      selectedModelId: resolved.modelId,
      selectedProviderId: resolved.providerId,
    })
    if (resolved.modelId && resolved.providerId) {
      persistModelSelection(resolved.modelId, resolved.providerId)
    }
  },

  selectModel: (modelId: string, providerId: string) => {
    set({ selectedModelId: modelId, selectedProviderId: providerId })
    persistModelSelection(modelId, providerId)
  },

  selectProvider: (providerId: string) => {
    const { models } = get()
    const resolved = resolveModelSelection(models, null, providerId)
    if (resolved.modelId && resolved.providerId) {
      set({
        selectedModelId: resolved.modelId,
        selectedProviderId: resolved.providerId,
      })
      persistModelSelection(resolved.modelId, resolved.providerId)
    }
  },

  setSidebarOpen: (v: boolean) => set({ sidebarOpen: v }),
  setView: (v: 'chat' | 'admin' | 'conversations' | 'artifacts' | 'projects') => set({ view: v }),
  setProjectAssignConversationId: (id) => set({ projectAssignConversationId: id }),
  setActiveProjectId: (id) => {
    // Avoid notify/re-render loops when the same project is set again
    if (get().activeProjectId === id) return
    set({ activeProjectId: id })
  },

  setConversationProjectTag: async (id, projectTag) => {
    const cleaned = projectTag?.trim().toLowerCase().replace(/\s+/g, '-') || null
    await api.updateConversation(id, { project_tag: cleaned })
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, project_tag: cleaned } : c
      ),
      activeConversation:
        s.activeConversation?.id === id
          ? { ...s.activeConversation, project_tag: cleaned }
          : s.activeConversation,
    }))
  },

  setConversationProjectId: async (id, projectId) => {
    const pid = projectId?.trim() || null
    await api.updateConversation(id, { project_id: pid })
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, project_id: pid } : c
      ),
      activeConversation:
        s.activeConversation?.id === id
          ? { ...s.activeConversation, project_id: pid }
          : s.activeConversation,
      // Keep RAG context if assigning the open chat
      activeProjectId:
        s.activeConversationId === id || s.activeConversation?.id === id
          ? pid
          : s.activeProjectId,
    }))
  },

  setProjectName: (id, name) =>
    set((s) => ({
      projectNameById: { ...s.projectNameById, [id]: name },
    })),
  setTheme: (theme) => {
    localStorage.setItem('nexuslocal_theme', theme)
    set({ theme })
  },
  setChatFont: (chatFont) => {
    localStorage.setItem('nexuslocal_chat_font', chatFont)
    set({ chatFont })
  },
  setLocale: (locale) => {
    localStorage.setItem('nexuslocal_locale', locale)
    set({ locale })
  },
  setModelSortMode: (modelSortMode) => {
    localStorage.setItem('nexuslocal_model_sort_mode', modelSortMode)
    set({ modelSortMode })
  },
  setHapticFeedback: (v) => {
    localStorage.setItem('nexuslocal_haptic_feedback', String(v))
    set({ hapticFeedback: v })
    if (v && typeof navigator !== 'undefined' && navigator.vibrate) {
      try {
        navigator.vibrate(15)
      } catch (e) {
        console.warn('Vibration not supported or blocked:', e)
      }
    }
  },
  setProfile: (profile) => {
    const { user } = get()
    const userId = user?.id || ''
    if (profile.displayName !== undefined) localStorage.setItem(`nexuslocal_${userId}_display_name`, profile.displayName)
    if (profile.fullName !== undefined) localStorage.setItem(`nexuslocal_${userId}_full_name`, profile.fullName)
    if (profile.occupation !== undefined) localStorage.setItem(`nexuslocal_${userId}_occupation`, profile.occupation)
    if (profile.customInstructions !== undefined) localStorage.setItem(`nexuslocal_${userId}_custom_instructions`, profile.customInstructions)
    set((s) => ({
      displayName: profile.displayName !== undefined ? profile.displayName : s.displayName,
      fullName: profile.fullName !== undefined ? profile.fullName : s.fullName,
      occupation: profile.occupation !== undefined ? profile.occupation : s.occupation,
      customInstructions: profile.customInstructions !== undefined ? profile.customInstructions : s.customInstructions,
    }))
    // Phase A+: persist to backend (fire-and-forget; local state already updated)
    const payload: Record<string, string> = {}
    if (profile.displayName !== undefined) payload.display_name = profile.displayName
    if (profile.fullName !== undefined) payload.full_name = profile.fullName
    if (profile.occupation !== undefined) payload.occupation = profile.occupation
    if (profile.customInstructions !== undefined) payload.custom_instructions = profile.customInstructions
    if (Object.keys(payload).length > 0) {
      api.saveUserProfile(payload).catch((err) => console.warn('[profile] save failed', err))
    }
  },

  hydrateProfileFromServer: async () => {
    const { token, user } = get()
    if (!token || !user?.id) return
    const userId = user.id
    // Only migrate data already scoped to this userId (never global leftovers)
    const cachedDisplay = localStorage.getItem(`nexuslocal_${userId}_display_name`) || ''
    const cachedFull = localStorage.getItem(`nexuslocal_${userId}_full_name`) || ''
    const cachedOcc = localStorage.getItem(`nexuslocal_${userId}_occupation`) || ''
    const cachedInstr = localStorage.getItem(`nexuslocal_${userId}_custom_instructions`) || ''
    try {
      const p = await api.getUserProfile()
      const serverHasData = !!(
        (p.display_name && p.display_name.trim()) ||
        (p.full_name && p.full_name.trim()) ||
        (p.occupation && p.occupation.trim()) ||
        (p.custom_instructions && p.custom_instructions.trim())
      )
      if (serverHasData) {
        const dn = p.display_name || cachedDisplay
        const fn = p.full_name || cachedFull
        const occ = p.occupation || cachedOcc
        const ci = p.custom_instructions || cachedInstr
        localStorage.setItem(`nexuslocal_${userId}_display_name`, dn)
        localStorage.setItem(`nexuslocal_${userId}_full_name`, fn)
        localStorage.setItem(`nexuslocal_${userId}_occupation`, occ)
        localStorage.setItem(`nexuslocal_${userId}_custom_instructions`, ci)
        set({ displayName: dn, fullName: fn, occupation: occ, customInstructions: ci })
      } else if (cachedDisplay || cachedFull || cachedOcc || cachedInstr) {
        await api.saveUserProfile({
          display_name: cachedDisplay,
          full_name: cachedFull,
          occupation: cachedOcc,
          custom_instructions: cachedInstr,
        })
        set({
          displayName: cachedDisplay,
          fullName: cachedFull,
          occupation: cachedOcc,
          customInstructions: cachedInstr,
        })
      }
    } catch (err) {
      console.warn('[profile] hydrate failed', err)
    }
  },

  renameConversation: async (id: string, title: string) => {
    await api.renameConversation(id, title)
    set((s) => ({
      conversations: s.conversations.map((c) =>
        c.id === id ? { ...c, title } : c
      ),
    }))
  },

  deleteConversation: async (id: string) => {
    await api.deleteConversation(id)
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      ...(s.activeConversationId === id
        ? { activeConversationId: null, messages: [], streamingContent: '', isStreaming: false }
        : {}),
    }))
  },

  loadCacheStats: async () => {
    const stats = await api.getCacheStats()
    set({ cacheStats: stats })
  },

  loadCacheSettings: async () => {
    const settings = await api.getCacheSettings()
    set({ cacheSettings: settings })
  },

  updateCacheSettings: async (data: Partial<CacheSettings>) => {
    await api.updateCacheSettings(data)
    const settings = await api.getCacheSettings()
    const stats = await api.getCacheStats()
    set({ cacheSettings: settings, cacheStats: stats })
  },

  setFusionMode: (v: boolean) => set({ fusionMode: v }),
  setFusionActive: (v: boolean) => set({ fusionActive: v }),
  setWebSearchActive: (v: boolean) => set({ webSearchActive: v }),
  setFusionStatuses: (statuses: FusionStatusEntry[]) => {
    const msg: Message = {
      id: `fusion-${Date.now()}`,
      role: 'fusion_status',
      content: '',
      fusion_statuses: statuses,
      fusion_judge_model_id: null,
    }
    set((s) => ({
      messages: [...s.messages, msg],
    }))
  },
  updateFusionStatus: (modelId: string, status: FusionStatusEntry['status'], response?: string, confidence?: FusionStatusEntry['confidence'], confidenceReason?: string | null) => {
    set((s) => {
      const idx = [...s.messages].reverse().findIndex((m) => m.role === 'fusion_status')
      if (idx === -1) return {}
      const actualIdx = s.messages.length - 1 - idx
      const updatedMessages = [...s.messages]
      const msg = updatedMessages[actualIdx]
      if (msg.fusion_statuses) {
        updatedMessages[actualIdx] = {
          ...msg,
          fusion_statuses: msg.fusion_statuses.map((fs) =>
            fs.model_id === modelId
              ? {
                  ...fs,
                  status,
                  ...(response !== undefined ? { response } : {}),
                  ...(confidence !== undefined ? { confidence } : {}),
                  ...(confidenceReason !== undefined ? { confidence_reason: confidenceReason } : {}),
                }
              : fs
          ),
        }
      }
      return { messages: updatedMessages }
    })
  },
  setFusionJudgeModelId: (id: string | null) => {
    set((s) => {
      const idx = [...s.messages].reverse().findIndex((m) => m.role === 'fusion_status')
      if (idx === -1) return {}
      const actualIdx = s.messages.length - 1 - idx
      const updatedMessages = [...s.messages]
      updatedMessages[actualIdx] = {
        ...updatedMessages[actualIdx],
        fusion_judge_model_id: id,
      }
      return { messages: updatedMessages }
    })
  },
  updateFusionGrounding: (status: 'checking' | 'searching' | 'done', queries?: string[], found?: boolean) => {
    set((s) => {
      const idx = [...s.messages].reverse().findIndex((m) => m.role === 'fusion_status')
      if (idx === -1) return {}
      const actualIdx = s.messages.length - 1 - idx
      const updatedMessages = [...s.messages]
      updatedMessages[actualIdx] = {
        ...updatedMessages[actualIdx],
        fusion_grounding: { status, queries, found },
      }

      return { messages: updatedMessages }
    })
  },
  setFusionRefinedPrompt: (prompt: string) => {
    set((s) => {
      const idx = [...s.messages].reverse().findIndex((m) => m.role === 'fusion_status')
      if (idx === -1) return {}
      const actualIdx = s.messages.length - 1 - idx
      const updatedMessages = [...s.messages]
      updatedMessages[actualIdx] = {
        ...updatedMessages[actualIdx],
        fusion_refined_prompt: prompt,
      }

      return { messages: updatedMessages }
    })
  },

  setActiveArtifact: (a: Artifact | null) => set({ activeArtifact: a }),
  setArtifactPanelOpen: (open: boolean) => set({
    artifactPanelOpen: open,
    sidebarOpen: !open,
  }),

  loadArtifactHistory: async (groupId: string) => {
    try {
      const history = await api.getArtifactHistory(groupId)
      set({ artifactHistory: history })
    } catch (e) {
      console.error('[artifact] falha ao carregar histórico:', e)
    }
  },

  loadActiveConversationArtifacts: async () => {
    const { activeConversationId } = get()
    if (!activeConversationId) {
      set({ activeConversationArtifacts: [] })
      return
    }
    try {
      const artifacts = await api.getArtifacts(activeConversationId)
      // Agrupa pelo artifact_group_id para listar apenas a versão mais recente
      const latestMap: Record<string, Artifact> = {}
      for (const art of artifacts) {
        const existing = latestMap[art.artifact_group_id]
        if (!existing || art.version > existing.version) {
          latestMap[art.artifact_group_id] = art
        }
      }
      // Ordena por data de criação decrescente
      const sorted = Object.values(latestMap).sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      set({ activeConversationArtifacts: sorted })
    } catch (e) {
      console.error('[artifacts] erro ao carregar artifacts da conversa:', e)
    }
  },

  navigateVersion: (direction: 'prev' | 'next') => {
    const { activeArtifact, artifactHistory } = get()
    if (!activeArtifact || artifactHistory.length === 0) return

    const currentIdx = artifactHistory.findIndex((a) => a.id === activeArtifact.id)
    if (currentIdx === -1) return

    const targetIdx = direction === 'prev' ? currentIdx - 1 : currentIdx + 1
    if (targetIdx < 0 || targetIdx >= artifactHistory.length) return

    set({ activeArtifact: artifactHistory[targetIdx] })
  },

  handleArtifactEvent: async (event) => {
    const { activeConversationId } = get()

    // Ignora eventos de outra conversa (pode acontecer se o WS ficar conectado
    // enquanto o usuário navega entre conversas)
    if (event.conv_id !== activeConversationId) return

    // Registra este como o fetch pendente atual.
    // Se uma segunda resposta gerar um artifact antes deste fetch terminar,
    // _pendingArtifactId será atualizado e este fetch será descartado ao resolver.
    set({ _pendingArtifactId: event.id })

    try {
      const artifact = await api.getArtifact(event.id)

      // Double-check após await: descarta se o usuário trocou de conversa
      // ou se um artifact mais recente já foi requisitado
      const state = get()
      if (state.activeConversationId !== event.conv_id) return
      if (state._pendingArtifactId !== event.id) return

      // Carrega o histórico completo de versões
      let history: Artifact[] = [artifact]
      if (artifact.artifact_group_id) {
        try {
          history = await api.getArtifactHistory(artifact.artifact_group_id)
        } catch {
          // Se falhar, segue com array de um elemento (artifact atual)
        }
      }

      // Re-verifica após o segundo await
      const state2 = get()
      if (state2.activeConversationId !== event.conv_id) return
      if (state2._pendingArtifactId !== event.id) return

      set({ activeArtifact: artifact, artifactPanelOpen: true, sidebarOpen: false, artifactHistory: history })
      // Recarrega a lista de artifacts da conversa atualizada
      get().loadActiveConversationArtifacts()
    } catch (e) {
      console.error('[artifact] falha ao buscar artifact:', e)
    }
  },

  favoriteConversation: async (id: string) => {
    const previousConversations = get().conversations
    const updated = previousConversations.map((c) => {
      if (c.id === id) {
        const isFav = !c.is_favorite
        return {
          ...c,
          is_favorite: isFav,
          favorited_at: isFav ? new Date().toISOString() : null,
        }
      }
      return c
    })
    set({ conversations: updated })

    try {
      const res = await api.favoriteConversation(id)
      set((s) => ({
        conversations: s.conversations.map((c) =>
          c.id === id ? { ...c, is_favorite: res.is_favorite, favorited_at: res.is_favorite ? new Date().toISOString() : null } : c
        ),
      }))
    } catch (e) {
      console.error('[conversation] falha ao favoritar:', e)
      set({ conversations: previousConversations })
    }
  },

  loadAllArtifacts: async (search?: string) => {
    try {
      const artifacts = await api.getAllArtifacts(search)
      set({ allArtifacts: artifacts })
    } catch (e) {
      console.error('[artifacts] falha ao carregar galeria de artefatos:', e)
    }
  },
}))