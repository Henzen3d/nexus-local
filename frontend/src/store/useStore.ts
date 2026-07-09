import { create } from 'zustand'
import type { Artifact, Conversation, ConversationDetail, Message, Model, CacheStats, CacheSettings, FusionStatusEntry, Attachment, WebSearchSource } from '../types'
import { api } from '../api/client'

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
  view: 'chat' | 'admin' | 'conversations' | 'artifacts'
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
  setSidebarOpen: (v: boolean) => void
  setView: (v: 'chat' | 'admin' | 'conversations' | 'artifacts') => void
  setTheme: (theme: 'light' | 'dark' | 'system') => void
  setChatFont: (font: 'sans' | 'serif' | 'mono') => void
  setLocale: (locale: string) => void
  setModelSortMode: (mode: 'ranking' | 'alphabetical') => void
  setHapticFeedback: (v: boolean) => void
  setProfile: (profile: { displayName?: string; fullName?: string; occupation?: string; customInstructions?: string }) => void
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
    
    const userId = user?.id || ''
    const username = user?.username || ''
    const formattedUsername = username ? username.charAt(0).toUpperCase() + username.slice(1) : ''
    
    const displayName = localStorage.getItem(`nexuslocal_${userId}_display_name`) || 
                        localStorage.getItem('nexuslocal_display_name') || 
                        formattedUsername
                        
    const fullName = localStorage.getItem(`nexuslocal_${userId}_full_name`) || 
                     localStorage.getItem('nexuslocal_full_name') || 
                     formattedUsername
                     
    const occupation = localStorage.getItem(`nexuslocal_${userId}_occupation`) || 
                       localStorage.getItem('nexuslocal_occupation') || 
                       ''
                       
    const customInstructions = localStorage.getItem(`nexuslocal_${userId}_custom_instructions`) || 
                               localStorage.getItem('nexuslocal_custom_instructions') || 
                               ''
                               
    set({ token, user, displayName, fullName, occupation, customInstructions })
  },
  logout: () => {
    localStorage.removeItem('nexuslocal_token')
    localStorage.removeItem('nexuslocal_user')
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
  selectedModelId: null,
  selectedProviderId: null,
  view: 'chat',
  theme: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_theme') as 'light' | 'dark' | 'system' : null) || 'system',
  chatFont: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_chat_font') as 'sans' | 'serif' | 'mono' : null) || 'sans',
  locale: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_locale') : null) || 'pt-BR',
  modelSortMode: (typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_model_sort_mode') as 'ranking' | 'alphabetical' : null) || 'ranking',
  hapticFeedback: typeof window !== 'undefined' ? localStorage.getItem('nexuslocal_haptic_feedback') === 'true' : false,
  displayName: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_display_name`) || 
               localStorage.getItem('nexuslocal_display_name') || 
               (user.username ? user.username.charAt(0).toUpperCase() + user.username.slice(1) : '')
      }
    } catch {}
    return localStorage.getItem('nexuslocal_display_name') || ''
  })() : null) || '',
  fullName: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_full_name`) || 
               localStorage.getItem('nexuslocal_full_name') || 
               (user.username ? user.username.charAt(0).toUpperCase() + user.username.slice(1) : '')
      }
    } catch {}
    return localStorage.getItem('nexuslocal_full_name') || ''
  })() : null) || '',
  occupation: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_occupation`) || 
               localStorage.getItem('nexuslocal_occupation') || 
               ''
      }
    } catch {}
    return localStorage.getItem('nexuslocal_occupation') || ''
  })() : null) || '',
  customInstructions: (typeof window !== 'undefined' ? (() => {
    try {
      const u = localStorage.getItem('nexuslocal_user')
      const user = u ? JSON.parse(u) : null
      if (user) {
        return localStorage.getItem(`nexuslocal_${user.id}_custom_instructions`) || 
               localStorage.getItem('nexuslocal_custom_instructions') || 
               ''
      }
    } catch {}
    return localStorage.getItem('nexuslocal_custom_instructions') || ''
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
    set((s) => ({
      activeConversationId: id,
      conversations: [
        { id, title, message_count: 0, created_at: new Date().toISOString(), updated_at: new Date().toISOString() },
        ...s.conversations,
      ],
    }))
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
    set((s) => ({
      models,
      selectedModelId: s.selectedModelId ?? models[0]?.id ?? null,
      selectedProviderId: s.selectedProviderId ?? models[0]?.provider_id ?? null,
    }))
  },

  selectModel: (modelId: string, providerId: string) => {
    set({ selectedModelId: modelId, selectedProviderId: providerId })
  },

  setSidebarOpen: (v: boolean) => set({ sidebarOpen: v }),
  setView: (v: 'chat' | 'admin' | 'conversations' | 'artifacts') => set({ view: v }),
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