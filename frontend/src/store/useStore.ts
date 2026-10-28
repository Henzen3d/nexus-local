import type { UiError } from '../lib/nexusUi'
import { create } from 'zustand'
import type { Artifact, Conversation, ConversationDetail, Message, Model, CacheStats, CacheSettings, FusionStatusEntry, Attachment, LibraryItem, WebSearchSource, AutoRouteDecisionInfo, UiEnvelope, ProgressBlock, IntelligentUiConfig, ProcessStep, ProactiveInsight, ProactiveAckAction, ProactiveChannelHint, ProactiveExpandMode, ProactiveSettings, ToastItem, CompanionMessage } from '../types'
import { api } from '../api/client'
import i18n, { detectInitialLocale } from '../i18n'
import { effectivePreferredModel } from '../lib/modelSelection'
import { MAX_BLOCKS, mergeUiEnvelopes } from '../lib/nexusUi'
import { bubbleContent, mergePending, newIds, pruneExpired, toastPreview } from '../lib/proactivePending'

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

function isAutoOptIn(): boolean {
  if (typeof window === 'undefined') return false
  try {
    return localStorage.getItem(_scopedKey('auto_opt_in')) === '1'
  } catch {
    return false
  }
}

function setAutoOptIn(on: boolean) {
  if (typeof window === 'undefined') return
  try {
    const key = _scopedKey('auto_opt_in')
    if (on) localStorage.setItem(key, '1')
    else localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
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
    const rawModelId = modelId || localStorage.getItem('nexuslocal_selected_model_id')
    const rawProviderId = providerId || localStorage.getItem('nexuslocal_selected_provider_id')
    const preferred = effectivePreferredModel(rawModelId, isAutoOptIn())
    return {
      modelId: preferred,
      providerId: preferred === 'auto' ? 'auto' : preferred ? rawProviderId : null,
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

function readReasoningEffortByModel(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  try {
    const raw = localStorage.getItem(_scopedKey('reasoning_effort_by_model'))
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function persistReasoningEffortForModel(modelId: string, level: string) {
  if (typeof window === 'undefined') return
  try {
    const map = readReasoningEffortByModel()
    map[modelId] = level
    localStorage.setItem(_scopedKey('reasoning_effort_by_model'), JSON.stringify(map))
  } catch {
    /* ignore */
  }
}

function readReasoningEffortAuto(): string {
  if (typeof window === 'undefined') return 'medium'
  try {
    return localStorage.getItem(_scopedKey('reasoning_effort_auto')) || 'medium'
  } catch {
    return 'medium'
  }
}

function persistReasoningEffortAuto(level: string) {
  if (typeof window === 'undefined') return
  try {
    localStorage.setItem(_scopedKey('reasoning_effort_auto'), level)
  } catch {
    /* ignore */
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
    setAutoOptIn(modelId === 'auto')

    if (providerId && providerId !== 'auto') {
      const map = readLastModelByProvider()
      map[providerId] = modelId
      const mapJson = JSON.stringify(map)
      localStorage.setItem(_scopedKey('last_model_by_provider'), mapJson)
      localStorage.setItem('nexuslocal_last_model_by_provider', mapJson)
    }
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
  const preferred = effectivePreferredModel(preferredModelId, isAutoOptIn())

  if (preferred === 'auto') {
    return { modelId: 'auto', providerId: 'auto' }
  }

  // 1) modelo persistido/atual ainda existe
  if (preferred) {
    const found = models.find((m) => m.id === preferred)
    if (found) return { modelId: found.id, providerId: found.provider_id }
  }

  // 2) provedor persistido: último modelo daquele provedor, senão o primeiro da lista
  if (preferredProviderId && preferredProviderId !== 'auto') {
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
  isGenerating: boolean
  uiLevel: 'simple' | 'intermediate' | 'advanced'
  simpleSpeed: 'fast' | 'think'
  setSimpleSpeed: (speed: 'fast' | 'think') => void
  processSteps: ProcessStep[]
  processStartedAt: number | null
  lastCacheHit: { type: string; similarity: number } | null

  // Intelligent UI (blocos nexus-ui/1 na bolha)
  /** null = ainda não carregado. Enquanto null, nada é renderizado (ausente = desligado). */
  intelligentUiConfig: IntelligentUiConfig | null
  loadIntelligentUiConfig: () => Promise<void>
  setIntelligentUiConfig: (cfg: IntelligentUiConfig | null) => void
  /** Blocos do host (`ui_progress`) recebidos durante o stream; viram parte da mensagem no finalizeStream. */
  streamingUiBlocks: UiEnvelope | null

  // Model selection
  models: Model[]
  selectedModelId: string | null
  selectedProviderId: string | null
  reasoningEffortByModel: Record<string, string>
  reasoningEffortAuto: string
  setReasoningEffortForModel: (modelId: string, level: string) => void
  setReasoningEffortAuto: (level: string) => void
  getActiveReasoningEffort: () => string | null

  // View
  view: 'chat' | 'admin' | 'conversations' | 'artifacts' | 'projects' | 'library' | 'proactive' | 'agents'
  previousView: 'chat' | 'conversations' | 'artifacts' | 'projects' | 'library' | 'proactive' | 'agents'
  theme: 'light' | 'dark' | 'system'
  chatFont: 'sans' | 'serif' | 'mono'
  locale: string
  modelSortMode: 'ranking' | 'alphabetical'
  hapticFeedback: boolean
  displayName: string
  fullName: string
  occupation: string
  customInstructions: string

  // Library state
  libraryItems: LibraryItem[]
  libraryLoading: boolean
  libraryFilter: 'all' | 'generated' | 'image' | 'document'
  librarySearch: string
  setLibraryFilter: (filter: 'all' | 'generated' | 'image' | 'document') => void
  setLibrarySearch: (search: string) => void
  loadLibrary: (filter?: 'all' | 'generated' | 'image' | 'document', search?: string) => Promise<void>
  deleteLibraryItem: (id: string) => Promise<void>

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
  flushStreamDraft: () => void
  clearStreamDraft: () => void
  beginProcess: (thinkingTitle?: string) => void
  startProcessStep: (step: ProcessStep) => void
  updateProcessStep: (id: string, update: Partial<Pick<ProcessStep, 'detail' | 'subSteps' | 'status'>>) => void
  uiCorrectionRequested: Record<string, boolean>
  finalizeStream: (messageId: string, artifactMeta?: { id: string; type: string; title: string }, artifacts?: { id: string; type: string; title: string }[], relayUsed?: boolean, relayModel?: string | null, webSearchUsed?: boolean, webSearchQuery?: string, webSearchSources?: WebSearchSource[], wasFallback?: boolean, uiBlocks?: UiEnvelope | null, processDurationMs?: number, serverSteps?: ProcessStep[], uiErrors?: UiError[], uiDropped?: number, finalModelId?: string | null, finalModelName?: string | null, finalProviderId?: string | null, requestedModel?: string | null, servedBy?: string | null, failoverTier?: string | null, spliced?: boolean, outcome?: string, attemptCount?: number) => void
  handleUiProgress: (block: ProgressBlock) => void
  lastAutoRouteDecision: AutoRouteDecisionInfo | null
  setAutoRouteDecision: (decision: AutoRouteDecisionInfo | null) => void
  setStreaming: (v: boolean) => void
  setIsGenerating: (v: boolean) => void
  setUiLevel: (level: 'simple' | 'intermediate' | 'advanced') => void
  addUserMessage: (content: string, attachments?: Attachment[]) => void
  setConversationCreated: (id: string, title: string) => void
  setLastCacheHit: (hit: { type: string; similarity: number } | null) => void
  loadModels: () => Promise<void>
  selectModel: (modelId: string, providerId: string) => void
  /** Troca de provedor: restaura o último modelo usado nele (ou o 1º por ranking). */
  selectProvider: (providerId: string) => void
  setSidebarOpen: (v: boolean) => void
  setView: (v: 'chat' | 'admin' | 'conversations' | 'artifacts' | 'projects' | 'library' | 'proactive' | 'agents') => void
  closeSettings: () => void
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
  updateFusionStatus: (modelId: string, status: FusionStatusEntry['status'], response?: string, confidence?: FusionStatusEntry['confidence'], confidenceReason?: string | null, originalModelId?: string | null) => void
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
  // Toasts empilhados (máx. 3 visíveis) — ver App.tsx <Toast />
  toasts: ToastItem[]
  showToast: (message: string, type?: ToastItem['type'], options?: { title?: string; action?: ToastItem['action']; durationMs?: number; id?: string }) => void
  hideToast: (id?: string) => void
  isOnline: boolean
  setIsOnline: (online: boolean) => void
  lastUserMessage: { text: string; conversationId: string | null; modelId: string | null; providerId: string | null; fusionMode: boolean; webSearchActive: boolean; projectId: string | null } | null
  setLastUserMessage: (msg: { text: string; conversationId: string | null; modelId: string | null; providerId: string | null; fusionMode: boolean; webSearchActive: boolean; projectId: string | null } | null) => void

  // ── Assistente proativo (F2) ─────────────────────────────────────────────
  /** Status transitório ("pesquisando…") da conversa em pesquisa. */
  proactiveStatus: { conversation_id: string; stage: string } | null
  /** Conversas com insight proativo não visto (badge ✦ na sidebar). */
  conversationsWithInsight: Record<string, true>
  /** Insights inline aguardando momento calmo (sem streaming/digitação). */
  pendingInlineInsights: ProactiveInsight[]
  /** F3: fila de insights prontos ainda não entregues (≤ 3, nunca vencidos) — cartão/toast/badge. */
  pendingInsights: ProactiveInsight[]
  /** Texto a ser pré-preenchido no composer (ex.: "Quero saber mais"). */
  composerPrefill: string | null
  setComposerPrefill: (text: string | null) => void
  noteTyping: () => void
  handleProactiveStatus: (evt: { conversation_id: string; stage: string }) => void
  handleProactiveInsight: (evt: { insight: ProactiveInsight; channel_hint?: ProactiveChannelHint }) => void
  /** `proactive_pending` (WS) ou `GET /pending` (boot): funde, marca badges e avisa uma vez. */
  handleProactivePending: (evt: { insights: ProactiveInsight[] }, opts?: { quiet?: boolean }) => void
  loadPendingInsights: () => Promise<void>
  prunePendingInsights: () => void
  /** "Abrir conversa" no cartão: vai à origem; a presença faz o backend entregar a bolha. */
  openPendingInsight: (insightId: string) => Promise<void>
  /** "Dispensar" no cartão: ack `dismissed` + some da fila (não apaga no servidor). */
  dismissPendingInsight: (insightId: string) => Promise<void>
  /** "Me conta aqui": `new_chat` cria a conversa iniciada pela IA; `same` só pré-preenche. */
  expandProactiveInsight: (insightId: string, mode: ProactiveExpandMode) => Promise<void>
  flushPendingInlineInsights: () => void
  ackProactiveInsight: (insightId: string, action: ProactiveAckAction, opts?: { silent?: boolean }) => Promise<void>
  pauseProactive: () => Promise<void>
  /** F4.3.3 — preferências do usuário (fonte: servidor), hidratadas no boot. */
  proactiveSettings: ProactiveSettings | null
  loadProactiveSettings: () => Promise<ProactiveSettings | null>
  updateProactiveSettings: (
    patch: Parameters<typeof api.updateProactiveSettings>[0],
    opts?: { silent?: boolean },
  ) => Promise<ProactiveSettings | null>
  unblockProactiveTopic: (topicHash: string) => Promise<boolean>
  markProactiveOnboardingSeen: () => Promise<void>
  addErrorMessage: (content: string) => void
  handleImagePending: (event: { conversation_id: string; message_id: string; task_id: string; prompt: string }) => void
  handleImageReady: (event: { conversation_id: string; message_id: string; task_id: string; attachment: Attachment }) => void
  handleImageFailed: (event: { conversation_id: string; message_id: string; task_id: string; error: string }) => void
  // Companion Modal ("conversa curta entre amigos" + artefato)
  proactiveCompanionOpen: boolean
  proactiveCompanionInsight: ProactiveInsight | null
  proactiveCompanionMessages: CompanionMessage[]
  isCompanionSending: boolean
  openProactiveCompanion: (insight: ProactiveInsight, initialPrompt?: string) => void
  closeProactiveCompanion: () => void
  sendProactiveCompanionMessage: (text: string) => Promise<void>
}

// ── Assistente proativo: estado efêmero fora do store ──────────────────────
const PROACTIVE_TYPING_GUARD_MS = 3000
const PROACTIVE_STATUS_TTL_MS = 60_000
let _proactiveLastTypingAt = 0
let _proactiveFlushTimer: ReturnType<typeof setTimeout> | null = null
let _proactiveStatusTimer: ReturnType<typeof setTimeout> | null = null
const _proactiveAcked = new Set<string>()
/** Pendentes já anunciados (toast/cartão) — nunca avisar duas vezes o mesmo insight. */
const _proactiveAnnounced = new Set<string>()
let _proactiveExpanding: string | null = null

function proactiveMessageFromInsight(insight: ProactiveInsight): Message {
  // Prefixo §3.4 no idioma do insight (ao vivo × "enquanto você estava fora") — espelha o backend
  return {
    id: insight.message_id || `proactive-${insight.id}`,
    role: 'assistant',
    kind: 'proactive',
    content: bubbleContent(insight),
    created_at: insight.created_at || new Date().toISOString(),
    proactive_insight_id: insight.id,
    insight: { ...insight, status: insight.status || 'delivered' },
    web_search_sources: (insight.sources || []).map((src) => ({ title: src.title, url: src.url })),
  }
}

function _proactiveAppendMessage(insight: ProactiveInsight) {
  const state = useStore.getState()
  const exists = state.messages.some(
    (m) => m.proactive_insight_id === insight.id || (insight.message_id && m.id === insight.message_id)
  )
  if (exists) return
  useStore.setState((s) => ({ messages: [...s.messages, proactiveMessageFromInsight(insight)] }))
}

function _proactiveNotifyElsewhere(insight: ProactiveInsight) {
  const store = useStore.getState()
  useStore.setState((s) => ({
    conversationsWithInsight: { ...s.conversationsWithInsight, [insight.conversation_id]: true },
  }))
  const message = toastPreview(insight.text || '')
  store.showToast(message, 'proactive', {
    id: `proactive-${insight.id}`,
    title: i18n.t('proactive.toastTitle', { topic: insight.topic }),
    durationMs: 8000,
    action: {
      label: i18n.t('proactive.toastView'),
      onClick: () => {
        const st = useStore.getState()
        st.hideToast(`proactive-${insight.id}`)
        if (st.view !== 'chat') st.setView('chat')
        void st.loadConversation(insight.conversation_id)
      },
    },
  })
}

/** Substitui o bloco de mesmo id ou acrescenta até o teto de blocos (spec §5, `ui_progress`). */
function upsertUiBlock(env: UiEnvelope | null, block: ProgressBlock): UiEnvelope {
  const blocks = [...(env?.blocks ?? [])]
  const idx = blocks.findIndex((b) => b.id === block.id)
  if (idx >= 0) blocks[idx] = block
  else if (blocks.length < MAX_BLOCKS) blocks.push(block)
  return { v: 1, blocks }
}


export const useStore = create<AppState>((set, get) => {
  let pendingStreamTokens: string[] = []
  let cancelScheduledStreamFlush: (() => void) | null = null

  const commitPendingStreamTokens = () => {
    cancelScheduledStreamFlush = null
    if (!pendingStreamTokens.length) return

    const content = pendingStreamTokens.join('')
    pendingStreamTokens = []
    set((s) => ({ streamingContent: s.streamingContent + content }))
  }

  const flushPendingStreamTokens = () => {
    cancelScheduledStreamFlush?.()
    commitPendingStreamTokens()
  }

  const discardPendingStreamTokens = () => {
    cancelScheduledStreamFlush?.()
    cancelScheduledStreamFlush = null
    pendingStreamTokens = []
  }

  const scheduleStreamFlush = () => {
    if (cancelScheduledStreamFlush) return

    if (typeof requestAnimationFrame === 'function') {
      const frameId = requestAnimationFrame(() => {
        cancelScheduledStreamFlush = null
        commitPendingStreamTokens()
      })
      cancelScheduledStreamFlush = () => cancelAnimationFrame(frameId)
      return
    }

    const timeoutId = setTimeout(() => {
      cancelScheduledStreamFlush = null
      commitPendingStreamTokens()
    }, 16)
    cancelScheduledStreamFlush = () => clearTimeout(timeoutId)
  }

  return ({
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
    discardPendingStreamTokens()
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
      uiCorrectionRequested: {},
      activeArtifact: null,
      artifactPanelOpen: false,
      displayName: '',
      fullName: '',
      occupation: '',
      customInstructions: '',
      reasoningEffortByModel: {},
      reasoningEffortAuto: 'medium',
    })
  },

  conversations: [],
  activeConversationId: null,
  activeConversation: null,
  sidebarOpen: typeof window !== 'undefined' ? window.innerWidth > 768 : true,
  messages: [],
  streamingContent: '',
  isStreaming: false,
  isGenerating: false,
  uiLevel: (typeof window !== 'undefined' ? (localStorage.getItem('nexuslocal_ui_level') as 'simple' | 'intermediate' | 'advanced') : null) || 'simple',
  simpleSpeed: (typeof window !== 'undefined' ? (localStorage.getItem('nexuslocal_simple_speed') as 'fast' | 'think') : null) || 'fast',
  processSteps: [],
  processStartedAt: null,
  lastCacheHit: null,
  toasts: [],
  isOnline: typeof window !== 'undefined' ? navigator.onLine : true,
  lastUserMessage: null as { text: string; conversationId: string | null; modelId: string | null; providerId: string | null; fusionMode: boolean; webSearchActive: boolean; projectId: string | null } | null,
  proactiveStatus: null,
  conversationsWithInsight: {},
  pendingInlineInsights: [],
  pendingInsights: [],
  proactiveSettings: null,
  composerPrefill: null,
  intelligentUiConfig: null,
  streamingUiBlocks: null,
  models: [],
  selectedModelId: typeof window !== 'undefined' ? readPersistedModelSelection().modelId : null,
  selectedProviderId: typeof window !== 'undefined' ? readPersistedModelSelection().providerId : null,
  reasoningEffortByModel: typeof window !== 'undefined' ? readReasoningEffortByModel() : {},
  reasoningEffortAuto: typeof window !== 'undefined' ? readReasoningEffortAuto() : 'medium',
  view: 'chat',
  previousView: 'chat',
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
  proactiveCompanionOpen: false,
  proactiveCompanionInsight: null,
  proactiveCompanionMessages: [],
  isCompanionSending: false,
  libraryItems: [],
  libraryLoading: false,
  libraryFilter: 'all',
  librarySearch: '',
  projectAssignConversationId: null,
  activeProjectId: null,
  projectNameById: {},

  loadConversations: async (search?: string, filter?: string, page?: number, limit?: number) => {
    const conversations = await api.getConversations(search, filter, page, limit)
    set({ conversations })
  },

  loadConversation: async (id: string) => {
    const conv = await api.getConversation(id)
    discardPendingStreamTokens()
    set((s) => {
      // Abrir a conversa limpa o badge ✦ de insight não visto
      const { [id]: _seen, ...restBadges } = s.conversationsWithInsight
      void _seen
      return {
        activeConversationId: id,
        activeConversation: conv,
        messages: conv.messages,
        streamingContent: '',
        streamingUiBlocks: null,
        processSteps: [],
        processStartedAt: null,
        activeArtifact: null,
        artifactPanelOpen: false,
        artifactHistory: [],
        activeConversationArtifacts: [],
        _pendingArtifactId: null,
        view: 'chat',
        // Keep RAG context when opening a chat that belongs to a project
        activeProjectId: conv.project_id || null,
        conversationsWithInsight: restBadges,
        proactiveStatus: s.proactiveStatus && s.proactiveStatus.conversation_id === id ? s.proactiveStatus : null,
        composerPrefill: null,
      }
    })
    // Puxa a lista de artifacts da conversa em segundo plano
    get().loadActiveConversationArtifacts()
  },

  startNewConversation: () => {
    discardPendingStreamTokens()
    set({
      activeConversationId: null,
      activeConversation: null,
      messages: [],
      streamingContent: '',
      streamingUiBlocks: null,
      isStreaming: false,
      processSteps: [],
      processStartedAt: null,
      activeArtifact: null,
      artifactPanelOpen: false,
      artifactHistory: [],
      activeConversationArtifacts: [],
      _pendingArtifactId: null,
      view: 'chat',
      // Leaving explicit project context unless user opens a project chat again
      activeProjectId: null,
      proactiveStatus: null,
      composerPrefill: null,
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

  showToast: (message, type = 'info', options) => {
    const id = options?.id || `toast-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const durationMs = options?.durationMs ?? (type === 'proactive' ? 8000 : 5000)
    const item: ToastItem = { id, message, type, title: options?.title, action: options?.action }
    set((s) => {
      const next = [...s.toasts.filter((t) => t.id !== id), item]
      // Mantém no máximo 3 toasts visíveis (descarta os mais antigos)
      return { toasts: next.slice(-3) }
    })
    setTimeout(() => get().hideToast(id), durationMs)
  },

  hideToast: (id) => set((s) => ({ toasts: id ? s.toasts.filter((t) => t.id !== id) : [] })),

  setIsOnline: (online) => set({ isOnline: online }),
  setLastUserMessage: (msg) => set({ lastUserMessage: msg }),

  // ── Assistente proativo (F2) ─────────────────────────────────────────────
  setComposerPrefill: (text) => set({ composerPrefill: text }),
  noteTyping: () => {
    _proactiveLastTypingAt = Date.now()
  },
  handleProactiveStatus: ({ conversation_id, stage }) => {
    set({ proactiveStatus: { conversation_id, stage } })
    // Falha silenciosa no backend não pode deixar o indicador preso
    if (_proactiveStatusTimer) clearTimeout(_proactiveStatusTimer)
    _proactiveStatusTimer = setTimeout(() => {
      _proactiveStatusTimer = null
      const cur = get().proactiveStatus
      if (cur && cur.conversation_id === conversation_id) set({ proactiveStatus: null })
    }, PROACTIVE_STATUS_TTL_MS)
  },
  handleProactiveInsight: ({ insight, channel_hint }) => {
    if (!insight || !insight.id) return
    const { activeConversationId, view, proactiveStatus } = get()
    if (proactiveStatus && proactiveStatus.conversation_id === insight.conversation_id) {
      set({ proactiveStatus: null })
    }
    // Entregue (inline/pending_inline) ⇒ deixa de ser pendente em todas as abas
    if (get().pendingInsights.some((p) => p.id === insight.id)) {
      set((s) => ({ pendingInsights: s.pendingInsights.filter((p) => p.id !== insight.id) }))
      get().hideToast(`proactive-pending-${insight.id}`)
    }
    const isOpenHere = view === 'chat' && !!activeConversationId && activeConversationId === insight.conversation_id
    if (isOpenHere && channel_hint !== 'pending') {
      // Inline — mas só em momento calmo (sem streaming / digitação recente)
      set((s) => ({
        pendingInlineInsights: s.pendingInlineInsights.some((p) => p.id === insight.id)
          ? s.pendingInlineInsights
          : [...s.pendingInlineInsights, insight],
      }))
      get().flushPendingInlineInsights()
      return
    }
    _proactiveNotifyElsewhere(insight)
  },
  handleProactivePending: ({ insights }, opts) => {
    const now = Date.now()
    const before = get().pendingInsights
    const after = mergePending(before, Array.isArray(insights) ? insights : [], now)
    const fresh = newIds(before, after).filter((id) => !_proactiveAnnounced.has(id))
    for (const id of fresh) _proactiveAnnounced.add(id)
    const badges: Record<string, true> = {}
    for (const i of after) badges[i.conversation_id] = true
    set((s) => ({
      pendingInsights: after,
      conversationsWithInsight: { ...s.conversationsWithInsight, ...badges },
    }))
    if (fresh.length === 0 || opts?.quiet) return

    const { view, activeConversationId } = get()
    const atHome = view === 'chat' && !activeConversationId
    if (atHome) return // o cartão de boas-vindas já mostra

    const items = after.filter((i) => fresh.includes(i.id))
    if (items.length === 1) {
      const only = items[0]
      get().showToast(toastPreview(only.text || ''), 'proactive', {
        id: `proactive-pending-${only.id}`,
        title: i18n.t('proactive.toastTitle', { topic: only.topic }),
        durationMs: 8000,
        action: {
          label: i18n.t('proactive.toastView'),
          onClick: () => {
            const st = useStore.getState()
            st.hideToast(`proactive-pending-${only.id}`)
            void st.openPendingInsight(only.id)
          },
        },
      })
      return
    }
    // Vários de uma vez ⇒ um único toast agrupado que leva à tela inicial (cartão)
    const toastId = `proactive-pending-group-${items.map((i) => i.id).join('.')}`
    get().showToast(items.map((i) => i.topic).join(' · '), 'proactive', {
      id: toastId,
      title: i18n.t('proactive.toastGrouped', { count: items.length }),
      durationMs: 10000,
      action: {
        label: i18n.t('proactive.toastView'),
        onClick: () => {
          const st = useStore.getState()
          st.hideToast(toastId)
          st.startNewConversation()
        },
      },
    })
  },
  loadPendingInsights: async () => {
    try {
      const res = await api.getProactivePending()
      get().handleProactivePending({ insights: res.insights || [] })
    } catch (e) {
      console.warn('[proactive] pendentes indisponíveis:', e)
    }
  },
  prunePendingInsights: () => {
    const cur = get().pendingInsights
    const next = pruneExpired(cur, Date.now())
    if (next !== cur) set({ pendingInsights: next })
  },
  openPendingInsight: async (insightId) => {
    const item = get().pendingInsights.find((p) => p.id === insightId)
    if (!item) return
    const st = get()
    if (st.view !== 'chat') st.setView('chat')
    // Na origem, a presença dispara a entrega inline (prefixo "enquanto você estava fora")
    await st.loadConversation(item.conversation_id)
  },
  dismissPendingInsight: async (insightId) => {
    const item = get().pendingInsights.find((p) => p.id === insightId)
    set((s) => ({ pendingInsights: s.pendingInsights.filter((p) => p.id !== insightId) }))
    if (item) {
      set((s) => {
        const stillPending = s.pendingInsights.some((p) => p.conversation_id === item.conversation_id)
        if (stillPending) return {}
        const { [item.conversation_id]: _gone, ...rest } = s.conversationsWithInsight
        void _gone
        return { conversationsWithInsight: rest }
      })
    }
    await get().ackProactiveInsight(insightId, 'dismissed', { silent: true })
  },
  expandProactiveInsight: async (insightId, mode) => {
    if (_proactiveExpanding === insightId) return
    _proactiveExpanding = insightId
    try {
      const result = await api.expandProactiveInsight(insightId, mode)
      set((s) => ({ pendingInsights: s.pendingInsights.filter((p) => p.id !== insightId) }))
      get().hideToast(`proactive-pending-${insightId}`)
      const st = get()
      if (st.view !== 'chat') st.setView('chat')
      if (mode === 'same') {
        await st.loadConversation(result.conversation_id)
        if (result.prefill) get().setComposerPrefill(result.prefill)
        return
      }
      await st.loadConversation(result.conversation_id)
      // A conversa nova precisa aparecer na sidebar (com o marcador ✦ de origem)
      void get().loadConversations()
    } catch (e) {
      console.warn('[proactive] expand falhou:', e)
      get().showToast(i18n.t('proactive.expandError'), 'error')
    } finally {
      _proactiveExpanding = null
    }
  },
  flushPendingInlineInsights: () => {
    const { pendingInlineInsights, isStreaming, fusionActive, activeConversationId, view } = get()
    if (pendingInlineInsights.length === 0) return
    const sinceTyping = Date.now() - _proactiveLastTypingAt
    const busy = isStreaming || fusionActive
    if (busy || sinceTyping < PROACTIVE_TYPING_GUARD_MS) {
      if (_proactiveFlushTimer) clearTimeout(_proactiveFlushTimer)
      const delay = busy ? 1000 : Math.max(250, PROACTIVE_TYPING_GUARD_MS - sinceTyping + 50)
      _proactiveFlushTimer = setTimeout(() => {
        _proactiveFlushTimer = null
        get().flushPendingInlineInsights()
      }, delay)
      return
    }
    set({ pendingInlineInsights: [] })
    for (const insight of pendingInlineInsights) {
      const stillHere = view === 'chat' && activeConversationId === insight.conversation_id
      if (stillHere) {
        _proactiveAppendMessage(insight)
      } else {
        // Usuário trocou de conversa enquanto esperávamos → toast + badge
        _proactiveNotifyElsewhere(insight)
      }
    }
  },
  ackProactiveInsight: async (insightId, action, opts) => {
    const key = `${insightId}:${action}`
    if (_proactiveAcked.has(key)) return
    _proactiveAcked.add(key)
    let result: Awaited<ReturnType<typeof api.ackProactiveInsight>> | null = null
    try {
      result = await api.ackProactiveInsight(insightId, action)
    } catch (e) {
      _proactiveAcked.delete(key)
      if (!opts?.silent) console.warn('[proactive] ack falhou:', e)
      if (action !== 'seen' && action !== 'know_more') get().showToast(i18n.t('proactive.ackError'), 'error')
      return
    }
    if (action !== 'know_more') {
      set((s) => ({
        messages: s.messages.map((m) =>
          m.proactive_insight_id === insightId || m.insight?.id === insightId
            ? { ...m, insight: m.insight ? { ...m.insight, status: action } : m.insight }
            : m
        ),
      }))
    }
    if (action === 'blocked' && !opts?.silent) {
      // F4.3.2 — efeito imediato + "Desfazer" (DELETE /blocklist/{hash} reabre a bolha)
      const topicHash = result?.topic_hash || null
      const toastId = `proactive-blocked-${insightId}`
      get().showToast(i18n.t('proactive.blockedToast'), 'info', {
        id: toastId,
        durationMs: 8000,
        action: topicHash
          ? {
              label: i18n.t('proactive.undo'),
              onClick: () => {
                get().hideToast(toastId)
                _proactiveAcked.delete(key)
                void get().unblockProactiveTopic(topicHash)
              },
            }
          : undefined,
      })
      void get().loadProactiveSettings()
    }
  },
  pauseProactive: async () => {
    try {
      const settings = await api.updateProactiveSettings({ enabled: false })
      set({ proactiveSettings: settings, pendingInsights: [] })
      const toastId = 'proactive-paused'
      get().showToast(i18n.t('proactive.pausedToast'), 'info', {
        id: toastId,
        durationMs: 8000,
        action: {
          label: i18n.t('proactive.reactivate'),
          onClick: () => {
            get().hideToast(toastId)
            void get().updateProactiveSettings({ enabled: true })
          },
        },
      })
    } catch (e) {
      console.warn('[proactive] pausar falhou:', e)
      get().showToast(i18n.t('proactive.ackError'), 'error')
    }
  },
  loadProactiveSettings: async () => {
    try {
      const settings = await api.getProactiveSettings()
      set({ proactiveSettings: settings })
      return settings
    } catch (e) {
      console.warn('[proactive] settings indisponíveis:', e)
      return null
    }
  },
  updateProactiveSettings: async (patch, opts) => {
    try {
      const settings = await api.updateProactiveSettings(patch)
      set((s) => ({
        proactiveSettings: settings,
        // desligar limpa a fila local; o servidor já expirou as pendências
        pendingInsights: settings.enabled ? s.pendingInsights : [],
      }))
      if (!opts?.silent && patch.enabled === true) {
        get().showToast(i18n.t('proactive.enabledToast'), 'success', { durationMs: 6000 })
      }
      return settings
    } catch (e) {
      console.warn('[proactive] salvar preferências falhou:', e)
      if (!opts?.silent) get().showToast(i18n.t('proactive.ackError'), 'error')
      return null
    }
  },
  unblockProactiveTopic: async (topicHash) => {
    try {
      const res = await api.unblockProactiveTopic(topicHash)
      const restored = new Set(res.restored_insight_ids || [])
      set((s) => ({
        proactiveSettings: s.proactiveSettings
          ? {
              ...s.proactiveSettings,
              blocked_topics: (s.proactiveSettings.blocked_topics || []).filter((b) => b.topic_hash !== topicHash),
            }
          : s.proactiveSettings,
        messages: restored.size
          ? s.messages.map((m) =>
              m.insight && restored.has(m.insight.id) ? { ...m, insight: { ...m.insight, status: 'seen' } } : m
            )
          : s.messages,
      }))
      for (const id of restored) _proactiveAcked.delete(`${id}:blocked`)
      get().showToast(i18n.t('proactive.unblockedToast'), 'success', { durationMs: 4000 })
      return true
    } catch (e) {
      console.warn('[proactive] desbloquear falhou:', e)
      get().showToast(i18n.t('proactive.ackError'), 'error')
      return false
    }
  },
  markProactiveOnboardingSeen: async () => {
    try {
      const res = await api.markProactiveOnboardingSeen()
      set((s) => ({
        proactiveSettings: s.proactiveSettings
          ? { ...s.proactiveSettings, onboarding_seen_at: res.onboarding_seen_at, onboarding_eligible: false }
          : s.proactiveSettings,
      }))
    } catch (e) {
      console.warn('[proactive] onboarding-seen falhou:', e)
    }
  },

  openProactiveCompanion: (insight, initialPrompt) => {
    if (insight.id) {
      void get().ackProactiveInsight(insight.id, 'know_more', { silent: true })
    }
    const initialGreeting = insight.text || ''
    const initialMessages: CompanionMessage[] = []
    if (initialGreeting) {
      initialMessages.push({
        id: `greeting-${insight.id}`,
        role: 'assistant',
        content: initialGreeting,
        created_at: new Date().toISOString(),
        artifact: insight.artifact_id
          ? {
              id: insight.artifact_id,
              title: insight.artifact_title || insight.topic,
              content: insight.artifact_content || '',
              version: 1,
            }
          : null,
      })
    }
    set({
      proactiveCompanionOpen: true,
      proactiveCompanionInsight: insight,
      proactiveCompanionMessages: initialMessages,
      isCompanionSending: false,
    })
    if (initialPrompt && initialPrompt.trim()) {
      void get().sendProactiveCompanionMessage(initialPrompt.trim())
    }
  },

  closeProactiveCompanion: () => {
    set({ proactiveCompanionOpen: false })
  },

  sendProactiveCompanionMessage: async (text: string) => {
    const { proactiveCompanionInsight, proactiveCompanionMessages, isCompanionSending } = get()
    if (!proactiveCompanionInsight || isCompanionSending || !text.trim()) return

    const userMsg: CompanionMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text.trim(),
      created_at: new Date().toISOString(),
    }

    const updatedMessages = [...proactiveCompanionMessages, userMsg]
    set({
      proactiveCompanionMessages: updatedMessages,
      isCompanionSending: true,
    })

    try {
      const history = updatedMessages
        .slice(0, -1)
        .map((m) => ({ role: m.role, content: m.content }))

      const res = await api.chatProactiveCompanion(
        proactiveCompanionInsight.id,
        userMsg.content,
        history,
      )

      const assistantMsg: CompanionMessage = {
        id: `lumi-${Date.now()}`,
        role: 'assistant',
        content: res.reply,
        created_at: new Date().toISOString(),
        artifact: res.artifact || undefined,
      }

      set((s) => ({
        proactiveCompanionMessages: [...s.proactiveCompanionMessages, assistantMsg],
        proactiveCompanionInsight:
          res.artifact && s.proactiveCompanionInsight
            ? {
                ...s.proactiveCompanionInsight,
                artifact_id: res.artifact.id,
                artifact_title: res.artifact.title,
                artifact_content: res.artifact.content,
              }
            : s.proactiveCompanionInsight,
      }))

      if (res.artifact) {
        void get().loadActiveConversationArtifacts()
      }
    } catch (e) {
      console.error('[proactive] companion chat falhou:', e)
      const errorMsg: CompanionMessage = {
        id: `err-${Date.now()}`,
        role: 'assistant',
        content: 'Tive uma pequena instabilidade para processar sua pergunta agora, mas você ainda pode visualizar todas as pesquisas no artefato!',
        created_at: new Date().toISOString(),
      }
      set((s) => ({
        proactiveCompanionMessages: [...s.proactiveCompanionMessages, errorMsg],
      }))
    } finally {
      set({ isCompanionSending: false })
    }
  },

  handleImagePending: (event) => {
    const anyEvt = event as any
    const convId = event.conversation_id || anyEvt.conv_id
    const msgId = event.message_id || anyEvt.msg_id
    const { activeConversationId, messages } = get()
    if (convId && activeConversationId && convId !== activeConversationId) return

    const existing = messages.find((m) => m.id === msgId)
    if (existing) return

    const msg: Message = {
      id: msgId,
      role: 'assistant',
      content: `🎨 Gerando imagem: "${event.prompt}"...`,
      created_at: new Date().toISOString(),
      provider: 'cloudflare',
      model_display_name: 'Flux 1 Schnell',
    }
    set((s) => ({
      messages: [...s.messages, msg],
      isStreaming: false,
    }))
  },

  handleImageReady: (event) => {
    const anyEvt = event as any
    const convId = event.conversation_id || anyEvt.conv_id
    const msgId = event.message_id || anyEvt.msg_id

    // Redireciona caso chegue evento com status de falha
    if (anyEvt.status === 'failed') {
      get().handleImageFailed({
        conversation_id: convId,
        message_id: msgId,
        task_id: event.task_id,
        error: anyEvt.error || 'Falha na geração da imagem',
      })
      return
    }

    const { activeConversationId, messages } = get()
    if (convId && activeConversationId && convId !== activeConversationId) {
      get().showToast('Imagem gerada com sucesso!', 'success')
      return
    }

    const rawAtt = event.attachment || anyEvt.attachment
    const att: Attachment = rawAtt || {
      id: anyEvt.attachment_id || `att_${Date.now()}`,
      filename: 'image.jpg',
      mime_type: 'image/jpeg',
      file_type: 'image',
      size_bytes: 0,
      file_url: anyEvt.file_url || anyEvt.url || '',
    }

    const updated = messages.map((m) => {
      if (m.id === msgId) {
        const atts = m.attachments || []
        const hasAtt = atts.some((a) => a.id === att.id)
        const newAtts = hasAtt ? atts : [...atts, att]
        const cleanContent = m.content.startsWith('🎨 Gerando imagem:') ? '' : m.content
        return {
          ...m,
          content: cleanContent,
          attachments: newAtts,
        }
      }
      return m
    })

    const exists = messages.some((m) => m.id === msgId)
    if (!exists) {
      const newMsg: Message = {
        id: msgId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
        provider: 'cloudflare',
        model_display_name: 'Flux 1 Schnell',
        attachments: [att],
      }
      set((s) => ({ messages: [...s.messages, newMsg], isStreaming: false }))
    } else {
      set({ messages: updated, isStreaming: false })
    }

    get().showToast('Imagem gerada com sucesso!', 'success')
    if (get().view === 'library') {
      get().loadLibrary()
    }
  },

  handleImageFailed: (event) => {
    const anyEvt = event as any
    const convId = event.conversation_id || anyEvt.conv_id
    const msgId = event.message_id || anyEvt.msg_id
    const errorText = event.error || anyEvt.error || 'Erro na geração de imagem'
    const { activeConversationId, messages } = get()

    if (!convId || !activeConversationId || convId === activeConversationId) {
      const updated = messages.map((m) => {
        if (m.id === msgId) {
          return {
            ...m,
            content: `⚠️ Falha ao gerar imagem: ${errorText}`,
          }
        }
        return m
      })
      set({ messages: updated, isStreaming: false })
    }
    get().showToast(`Falha na geração da imagem: ${errorText}`, 'error')
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
    if (!token) return
    pendingStreamTokens.push(token)
    scheduleStreamFlush()
  },

  flushStreamDraft: () => {
    flushPendingStreamTokens()
  },

  clearStreamDraft: () => {
    discardPendingStreamTokens()
    set({ streamingContent: '', streamingUiBlocks: null })
  },

  beginProcess: (thinkingTitle = 'Thinking') => {
    set((s) => {
      const thinkStep = { id: 'thinking', type: 'think' as const, title: thinkingTitle, status: 'running' as const }
      const already = s.processSteps.some((step) => step.id === 'thinking')
      const processSteps = already
        ? s.processSteps.map((step) => step.id === 'thinking' ? { ...step, ...thinkStep } : step)
        : [...s.processSteps, thinkStep]
      return {
        isStreaming: true,
        processSteps,
        processStartedAt: s.processStartedAt ?? Date.now(),
      }
    })
  },

  startProcessStep: (step: ProcessStep) => {
    set((s) => {
      const steps = s.processSteps.some((item) => item.id === step.id)
        ? s.processSteps.map((item) => item.id === step.id ? { ...item, ...step } : item)
        : [...s.processSteps, step]
      return {
        isStreaming: true,
        isGenerating: false,
        processStartedAt: s.processStartedAt ?? Date.now(),
        processSteps: steps,
      }
    })
  },

  updateProcessStep: (id, update) => {
    set((s) => ({
      processSteps: s.processSteps.map((step) => step.id === id ? { ...step, ...update } : step),
    }))
  },

  uiCorrectionRequested: {},
  finalizeStream: (
    messageId: string,
    artifactMeta?: { id: string; type: string; title: string },
    artifacts?: { id: string; type: string; title: string }[],
    relayUsed?: boolean,
    relayModel?: string | null,
    webSearchUsed?: boolean,
    webSearchQuery?: string,
    webSearchSources?: WebSearchSource[],
    wasFallback?: boolean,
    uiBlocks?: UiEnvelope | null,
    processDurationMs?: number,
    serverSteps?: ProcessStep[],
    uiErrors?: UiError[],
    uiDropped?: number,
    finalModelId?: string | null,
    finalModelName?: string | null,
    finalProviderId?: string | null,
    requestedModel?: string | null,
    servedBy?: string | null,
    failoverTier?: string | null,
    spliced?: boolean,
    outcome?: string,
    attemptCount?: number
  ) => {
    flushPendingStreamTokens()
    const { streamingContent, selectedModelId, models, lastAutoRouteDecision, processSteps, processStartedAt, streamingUiBlocks } = get()
    const resolvedModelId = lastAutoRouteDecision?.chosen_model_id || selectedModelId
    const activeModel = models.find((m) => m.id === resolvedModelId)
    const clientSteps = processSteps
    const clientHasSearch = clientSteps.some((step) => step.type === 'search' || step.type === 'navigate')
    const rawSteps = clientHasSearch || !serverSteps?.length
      ? (serverSteps?.length ? [...serverSteps, ...clientSteps] : clientSteps)
      : [...serverSteps, ...clientSteps.filter((step) => step.type === 'think')]

    // Deduplica os passos pelo id de forma estrita para evitar duplicações na UI
    const seenStepIds = new Set<string>()
    const baseSteps: ProcessStep[] = []
    for (const step of rawSteps) {
      if (!seenStepIds.has(step.id)) {
        seenStepIds.add(step.id)
        baseSteps.push(step)
      }
    }

    const completedSteps = baseSteps.map((step) => ({
      ...step,
      status: step.status === 'failed' ? 'failed' as const : 'completed' as const,
    }))
    if (webSearchSources?.length) {
      const existingUrls = new Set(
        completedSteps.filter((s) => s.type === 'navigate' && s.detail).map((s) => s.detail)
      )
      webSearchSources.forEach((source, index) => {
        if (!existingUrls.has(source.url)) {
          completedSteps.push({
            id: `source-${index}-${messageId}`,
            type: 'navigate' as const,
            title: source.title || source.url,
            detail: source.url,
            status: 'completed' as const,
          })
        }
      })
    }
    const msg: Message = {
      id: messageId,
      role: 'assistant',
      content: streamingContent,
      // O badge deve apontar o modelo que RESpondeu. Após failover o backend
      // envia finalModel* (pós-failover); sem eles usa o modelo resolvido/solicitado.
      model_id: (finalModelId || resolvedModelId) ?? undefined,
      created_at: new Date().toISOString(),
      model_display_name:
        finalModelName ||
        (finalModelId ? models.find((m) => m.id === finalModelId)?.display_name : undefined) ||
        lastAutoRouteDecision?.chosen_model_name ||
        activeModel?.display_name,
      provider:
        finalProviderId ||
        (finalModelId ? models.find((m) => m.id === finalModelId)?.provider_name : undefined) ||
        lastAutoRouteDecision?.provider_id ||
        activeModel?.provider_name,
      relay_used: relayUsed,
      relay_model: relayModel,
      web_search_used: webSearchUsed,
      web_search_query: webSearchQuery,
      web_search_sources: webSearchSources,
      process_steps: completedSteps,
      process_duration_ms: processDurationMs ?? (processStartedAt ? Date.now() - processStartedAt : undefined),
      was_fallback: wasFallback,
      requested_model: requestedModel ?? undefined,
      served_by: (servedBy || finalModelId || resolvedModelId) ?? undefined,
      failover_tier: failoverTier ?? undefined,
      spliced: spliced ?? false,
      outcome: outcome ?? 'success',
      attempt_count: attemptCount ?? 1,
      auto_route: lastAutoRouteDecision,
      ui_errors: uiErrors,
      ui_dropped: uiDropped,
      // Blocos do host (ui_progress) primeiro, depois os do modelo; teto de 6, id único
      ui_blocks: mergeUiEnvelopes(streamingUiBlocks, uiBlocks),
      // Popula os metadados do artifact no objeto de mensagem para que o badge seja exibido
      ...(artifactMeta
        ? { artifact_id: artifactMeta.id, artifact_type: artifactMeta.type, artifact_title: artifactMeta.title }
        : {}),
      artifacts: artifacts || (artifactMeta ? [artifactMeta] : []),
    }
    set((s) => ({
      messages: [...s.messages, msg],
      streamingContent: '',
      streamingUiBlocks: null,
      isStreaming: false,
      processSteps: [],
      processStartedAt: null,
      lastAutoRouteDecision: null,
    }))
  },

  handleUiProgress: (block: ProgressBlock) => {
    set((s) => {
      // Durante o stream a mensagem do assistente ainda não existe em `messages`
      // (a última é a do usuário): o bloco do host fica num buffer próprio e é
      // mesclado no finalizeStream. Fora do stream, atualiza a última mensagem
      // do assistente — nunca uma bolha do usuário.
      if (s.isStreaming) {
        return { streamingUiBlocks: upsertUiBlock(s.streamingUiBlocks, block) }
      }
      const msgs = [...s.messages]
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role !== 'assistant') continue
        msgs[i] = { ...msgs[i], ui_blocks: upsertUiBlock(msgs[i].ui_blocks ?? null, block) }
        return { messages: msgs }
      }
      return {}
    })
  },

  lastAutoRouteDecision: null,
  setAutoRouteDecision: (decision: AutoRouteDecisionInfo | null) => set({ lastAutoRouteDecision: decision }),

  setStreaming: (v: boolean) => set((s) => ({
    isStreaming: v,
    ...(v ? {} : { processSteps: s.processSteps.map((step) => step.status === 'running' ? { ...step, status: 'failed' as const } : step), processStartedAt: null }),
  })),
  setIsGenerating: (v: boolean) => set({ isGenerating: v }),
  setUiLevel: (level) => {
    localStorage.setItem('nexuslocal_ui_level', level)
    set({ uiLevel: level })
    if (level === 'simple') {
      get().selectModel('auto', 'auto')
      const sp = get().simpleSpeed || 'fast'
      get().setReasoningEffortAuto(sp === 'fast' ? 'low' : 'high')
    }
  },
  setSimpleSpeed: (speed) => {
    localStorage.setItem('nexuslocal_simple_speed', speed)
    set({ simpleSpeed: speed })
    get().selectModel('auto', 'auto')
    get().setReasoningEffortAuto(speed === 'fast' ? 'low' : 'high')
  },

  setLastCacheHit: (hit) => set({ lastCacheHit: hit }),

  loadIntelligentUiConfig: async () => {
    try {
      const cfg = await api.getIntelligentUiConfig()
      set({ intelligentUiConfig: cfg })
    } catch {
      // Backend antigo ou erro de rede: trata como desligado (ausente = falso).
      set({ intelligentUiConfig: { enabled: false, image_hosts: [], allow_private_http: false, source: 'default' } })
    }
  },
  setIntelligentUiConfig: (cfg) => set({ intelligentUiConfig: cfg }),

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

  setReasoningEffortForModel: (modelId: string, level: string) => {
    persistReasoningEffortForModel(modelId, level)
    set((s) => ({
      reasoningEffortByModel: {
        ...s.reasoningEffortByModel,
        [modelId]: level,
      },
    }))
  },

  setReasoningEffortAuto: (level: string) => {
    persistReasoningEffortAuto(level)
    set({ reasoningEffortAuto: level })
  },

  getActiveReasoningEffort: () => {
    const { selectedModelId, models, reasoningEffortByModel, reasoningEffortAuto } = get()
    if (selectedModelId === 'auto') {
      return reasoningEffortAuto || 'medium'
    }
    if (!selectedModelId) return null
    const model = models.find((m) => m.id === selectedModelId)
    if (!model) return null
    const ctrl = model.reasoning_control
    if (!ctrl || ctrl === 'none' || ctrl === 'always_on') {
      return null
    }
    const saved = reasoningEffortByModel[model.id]
    if (saved && model.reasoning_levels && model.reasoning_levels.includes(saved)) {
      return saved
    }
    if (model.reasoning_default) {
      return model.reasoning_default
    }
    if (model.reasoning_levels && model.reasoning_levels.length > 0) {
      return model.reasoning_levels[0]
    }
    return null
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

  setSidebarOpen: (v: boolean) => {
    // Ao fechar, solta o focus preso dentro da sidebar: no mobile o <aside>
    // recebe inert + aria-hidden no commit seguinte, e focus em descendente
    // dispara o aviso do Chrome "Blocked aria-hidden ... descendant retained focus".
    if (!v) {
      const active = document.activeElement
      if (active instanceof HTMLElement && active.closest('.sidebar')) active.blur()
    }
    set({ sidebarOpen: v })
  },
  setView: (v: 'chat' | 'admin' | 'conversations' | 'artifacts' | 'projects' | 'library' | 'proactive' | 'agents') => {
    const current = get().view
    if (current !== 'admin' && v === 'admin') {
      set({ previousView: current, view: v })
    } else {
      set({ view: v })
    }
  },
  closeSettings: () => {
    const prev = get().previousView || 'chat'
    set({ view: prev })
  },
  setLibraryFilter: (filter) => {
    set({ libraryFilter: filter })
    get().loadLibrary(filter, get().librarySearch)
  },
  setLibrarySearch: (search) => {
    set({ librarySearch: search })
    get().loadLibrary(get().libraryFilter, search)
  },
  loadLibrary: async (filter, search) => {
    const f = filter !== undefined ? filter : get().libraryFilter
    const s = search !== undefined ? search : get().librarySearch
    set({ libraryLoading: true })
    try {
      const res = await api.getLibraryItems(f, s)
      set({ libraryItems: res.items || [], libraryLoading: false })
    } catch (err) {
      console.error('Failed to load library:', err)
      set({ libraryLoading: false })
    }
  },
  deleteLibraryItem: async (id: string) => {
    try {
      await api.deleteLibraryItem(id)
      set((s) => ({
        libraryItems: s.libraryItems.filter((item) => item.id !== id),
      }))
      get().showToast('Item excluído da biblioteca', 'info')
    } catch (err) {
      console.error('Failed to delete library item:', err)
      get().showToast('Erro ao excluir item', 'error')
    }
  },
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

    // Sincroniza role atualizado do servidor (ex: promoção a admin)
    try {
      const me = await api.getMyAccount()
      if (me && me.role) {
        const currentUser = get().user
        if (currentUser && currentUser.role !== me.role) {
          const updatedUser = { ...currentUser, role: me.role }
          localStorage.setItem('nexuslocal_user', JSON.stringify(updatedUser))
          set({ user: updatedUser })
        }
      }
    } catch {
      /* ignore */
    }

    // F4.3.3 — preferências do assistente proativo vêm do servidor (fonte da verdade,
    // vale em qualquer dispositivo); o useProactive só limpa no logout.
    void get().loadProactiveSettings()
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
    if (get().activeConversationId === id) discardPendingStreamTokens()
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
  updateFusionStatus: (modelId: string, status: FusionStatusEntry['status'], response?: string, confidence?: FusionStatusEntry['confidence'], confidenceReason?: string | null, originalModelId?: string | null) => {
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
            (fs.model_id === modelId || (originalModelId && fs.model_id === originalModelId))
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
  })
})
