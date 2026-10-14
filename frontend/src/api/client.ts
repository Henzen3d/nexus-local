import type { Conversation, ConversationDetail, Model, Provider, CacheStats, CacheSettings, CacheEntry, EnhancerConfig, FusionConfig, Artifact, Attachment, LibraryItem, VisionRelayConfig, WebSearchConfig, WebSearchLog, AutoRouterPreviewResult, RankingEntry, RankingSyncResult } from '../types'

export interface UserProfileApi {
  user_id?: string
  display_name?: string
  full_name?: string
  occupation?: string
  custom_instructions?: string
  memory_enabled?: number | boolean
  updated_at?: string | null
}

const apiURL = import.meta.env.VITE_API_URL
const BASE = apiURL ? (apiURL.endsWith('/api') ? apiURL : `${apiURL}/api`) : '/api'

/** Evento global disparado quando a API responde 401 (token expirado/revogado). */
export const UNAUTHORIZED_EVENT = 'nexuslocal:unauthorized'

export class ApiError extends Error {
  status: number
  detail?: string
  constructor(status: number, detail?: string) {
    super(`HTTP ${status}`)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

let unauthorizedNotified = false

function notifyUnauthorized() {
  // Evita uma tempestade de eventos quando várias chamadas falham ao mesmo tempo
  if (unauthorizedNotified) return
  unauthorizedNotified = true
  setTimeout(() => { unauthorizedNotified = false }, 2000)
  window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
}

async function fetchJSON<T>(url: string, opts?: RequestInit): Promise<T> {
  const token = localStorage.getItem('nexuslocal_token')
  const headers: HeadersInit = { 'Content-Type': 'application/json' }
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const res = await fetch(BASE + url, {
    ...opts,
    headers: {
      ...headers,
      ...(opts?.headers || {})
    },
  })
  if (!res.ok) {
    // 401 em rota autenticada = sessão expirada/revogada → volta para o login.
    // O login em si também devolve 401 (credenciais erradas) e não deve deslogar ninguém.
    if (res.status === 401 && token && !url.startsWith('/auth/login')) {
      notifyUnauthorized()
    }
    let detail: string | undefined
    try {
      const body = await res.json()
      if (body && typeof body.detail === 'string') detail = body.detail
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return res.json()
}

export const api = {
  offerUiCorrection: (messageId: string) => fetchJSON<{ ok: boolean }>('/intelligent-ui/correction-offered', {
    method: 'POST', body: JSON.stringify({ message_id: messageId }),
  }),
  // Conversations
  getConversations: (search?: string, filter?: string, page = 1, limit = 100) => {
    const params = new URLSearchParams()
    if (search) params.append('search', search)
    if (filter) params.append('filter', filter)
    params.append('page', page.toString())
    params.append('limit', limit.toString())
    return fetchJSON<Conversation[]>(`/conversations?${params.toString()}`)
  },
  getConversation: (id: string) => fetchJSON<ConversationDetail>(`/conversations/${id}`),
  favoriteConversation: (id: string) =>
    fetchJSON<{ ok: boolean; is_favorite: boolean }>(`/conversations/${id}/favorite`, {
      method: 'PATCH',
    }),
  updateConversation: (
    id: string,
    data: { title?: string; project_tag?: string | null; project_id?: string | null }
  ) =>
    fetchJSON<{ ok: boolean; project_tag?: string | null; project_id?: string | null }>(
      `/conversations/${id}`,
      {
        method: 'PATCH',
        body: JSON.stringify(data),
      }
    ),
  renameConversation: (id: string, title: string) =>
    fetchJSON(`/conversations/${id}/rename`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  deleteConversation: (id: string) =>
    fetchJSON(`/conversations/${id}`, { method: 'DELETE' }),

  // Models
  getModels: () => fetchJSON<Model[]>('/admin/models'),

  // Admin
  getProviders: () => fetchJSON<Provider[]>('/admin/providers'),
  updateProvider: (id: string, data: {
    api_key?: string
    enabled?: boolean
    base_url?: string
    share_admin_key?: boolean
    account_id?: string
  }) =>
    fetchJSON(`/admin/providers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  getShareConfig: () => fetchJSON<{ share_admin_keys: boolean }>('/admin/providers/share-config'),
  updateShareConfig: (share_admin_keys: boolean) =>
    fetchJSON<{ ok: boolean }>('/admin/providers/share-config', {
      method: 'POST',
      body: JSON.stringify({ share_admin_keys }),
    }),
  toggleModel: (id: string, enabled: boolean) =>
    fetchJSON(`/admin/models/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),
  updateModel: (id: string, data: {
    enabled?: boolean
    context_length?: number
    reasoning_control?: string
    reasoning_levels?: string[] | null
    reasoning_default?: string | null
    reasoning_control_source?: string
  }) =>
    fetchJSON(`/admin/models/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  confirmModelFree: (id: string) =>
    fetchJSON(`/admin/models/${id}/confirm-free`, {
      method: 'POST',
    }),
  syncProviderModels: (id: string) =>
    fetchJSON(`/admin/providers/${id}/sync`, { method: 'POST' }),
  syncAllProvidersModels: () =>
    fetchJSON('/admin/providers/sync', { method: 'POST' }),
  toggleAllModels: (providerId: string, enabled: boolean) =>
    fetchJSON(`/admin/providers/${providerId}/models/toggle`, {
      method: 'POST',
      body: JSON.stringify({ enabled }),
    }),
  getFreeRegistryConfig: () => fetchJSON<import('../types').FreeRegistryConfig>('/admin/free-registry/config'),
  updateFreeRegistryConfig: (data: Partial<import('../types').FreeRegistryConfig>) =>
    fetchJSON('/admin/free-registry/config', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  syncFreeRegistry: () => fetchJSON<{ status: string; inserted_count?: number; match_report?: any; last_updated?: string }>('/admin/free-registry/sync', { method: 'POST' }),

  // Cache
  getCacheStats: () => fetchJSON<CacheStats>('/cache/stats'),
  getCacheSettings: () => fetchJSON<CacheSettings>('/cache/settings'),
  updateCacheSettings: (data: Partial<CacheSettings>) =>
    fetchJSON('/cache/settings', { method: 'PATCH', body: JSON.stringify(data) }),
  getCacheEntries: (type: 'exact' | 'semantic', limit = 50) =>
    fetchJSON<CacheEntry[]>(`/cache/entries/${type}?limit=${limit}`),
  deleteCacheEntry: (type: 'exact' | 'semantic', id: string) =>
    fetchJSON(`/cache/entries/${type}/${id}`, { method: 'DELETE' }),
  clearCache: (expiredOnly = false) =>
    fetchJSON(`/cache/clear?expired_only=${expiredOnly}`, { method: 'DELETE' }),

  // Enhancer
  getEnhancerConfig: () => fetchJSON<EnhancerConfig>('/enhancer/config'),
  saveEnhancerConfig: (data: Partial<EnhancerConfig>) =>
    fetchJSON<EnhancerConfig>('/enhancer/config', { method: 'POST', body: JSON.stringify(data) }),
  enhancePrompt: (prompt: string) =>
    fetchJSON<{ enhanced_prompt: string }>('/enhancer/process', { method: 'POST', body: JSON.stringify({ prompt }) }),

  // Fusion
  getFusionConfig: () => fetchJSON<FusionConfig>('/fusion/config'),
  saveFusionConfig: (data: Partial<FusionConfig>) =>
    fetchJSON<FusionConfig>('/fusion/config', { method: 'POST', body: JSON.stringify(data) }),
  saveFusionJudge: (data: { judge_provider_id: string; judge_model_id: string; judge_system_prompt?: string }) =>
    fetchJSON<FusionConfig>('/fusion/judge', { method: 'POST', body: JSON.stringify(data) }),

  // Artifacts
  getAllArtifacts: (search?: string) => {
    const url = search ? `/artifacts?search=${encodeURIComponent(search)}` : '/artifacts'
    return fetchJSON<Artifact[]>(url)
  },
  getArtifacts: (convId: string) => fetchJSON<Artifact[]>(`/artifacts/${convId}`),
  getArtifact: (id: string) => fetchJSON<Artifact>(`/artifacts/item/${id}`),
  getArtifactHistory: (groupId: string) => fetchJSON<Artifact[]>(`/artifacts/history/${groupId}`),
  deleteArtifact: (id: string) => fetchJSON(`/artifacts/${id}`, { method: 'DELETE' }),

  // Auth
  register: (data: any) => fetchJSON<{ token: string; user: any }>('/auth/register', { method: 'POST', body: JSON.stringify(data) }),
  login: (data: any) => fetchJSON<{ token: string; user: any }>('/auth/login', { method: 'POST', body: JSON.stringify(data) }),

  // User Management
  getUsers: () => fetchJSON<any[]>('/admin/users'),
  createUser: (data: { username: string; password: string; email?: string; phone?: string }) =>
    fetchJSON<{ user: { id: string; username: string; role: string } }>('/admin/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  deleteUser: (id: string) => fetchJSON(`/admin/users/${id}`, { method: 'DELETE' }),
  resetUserPassword: (id: string, password: string) =>
    fetchJSON(`/admin/users/${id}/password`, { method: 'PATCH', body: JSON.stringify({ password }) }),
  setUserProviderKey: (userId: string, providerId: string, api_key: string) =>
    fetchJSON(`/admin/users/${userId}/providers/${providerId}/key`, {
      method: 'PUT',
      body: JSON.stringify({ api_key }),
    }),
  setOwnProviderKey: (providerId: string, api_key: string, account_id?: string) =>
    fetchJSON(`/me/providers/${providerId}/key`, {
      method: 'PUT',
      body: JSON.stringify({ api_key, account_id }),
    }),

  // Attachments
  uploadAttachment: (file: File, modelId: string): Promise<Attachment> => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('model_id', modelId)
    const token = localStorage.getItem('nexuslocal_token')
    const headers: HeadersInit = {}
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    return fetch(BASE + '/attachments/upload', {
      method: 'POST',
      headers,
      body: formData
    }).then(async (res) => {
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const body = await res.json()
          if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : detail
        } catch {
          /* ignore */
        }
        throw new Error(detail)
      }
      const data = await res.json()
      // Backend returns `attachment_id`; UI / chat WS expect `id`
      return {
        id: data.id ?? data.attachment_id,
        filename: data.filename,
        mime_type: data.mime_type,
        file_type: data.file_type,
        size_bytes: data.size_bytes,
        thumbnail_url: data.thumbnail_url ?? null,
        file_url: data.file_url,
        extracted_text: data.extracted_text ?? data.extracted_text_preview ?? null,
      } as Attachment
    })
  },

  // Library & Attachments
  getLibraryItems: (filterType = 'all', search = '', limit = 100, offset = 0) => {
    const params = new URLSearchParams()
    if (filterType && filterType !== 'all') params.append('filter_type', filterType)
    if (search && search.trim()) params.append('search', search.trim())
    if (limit) params.append('limit', limit.toString())
    if (offset) params.append('offset', offset.toString())
    const qs = params.toString() ? `?${params.toString()}` : ''
    return fetchJSON<{ items: LibraryItem[]; total: number }>(`/attachments/library${qs}`)
  },
  deleteLibraryItem: (id: string) =>
    fetchJSON<{ status: string; deleted_id: string }>(`/attachments/${id}`, {
      method: 'DELETE',
    }),

  // Vision Relay
  getVisionRelayConfig: () => fetchJSON<VisionRelayConfig>('/vision-relay/config'),
  saveVisionRelayConfig: (data: Partial<VisionRelayConfig>) =>
    fetchJSON<VisionRelayConfig>('/vision-relay/config', {
      method: 'POST',
      body: JSON.stringify(data)
    }),

  // Web Search
  getWebSearchConfig: () => fetchJSON<WebSearchConfig>('/web-search/config'),
  saveWebSearchConfig: (data: Partial<WebSearchConfig>) =>
    fetchJSON<{ ok: boolean }>('/web-search/config', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  getWebSearchLogs: (limit = 50) => fetchJSON<WebSearchLog[]>(`/web-search/logs?limit=${limit}`),

  // Families
  getFamilies: () => fetchJSON<any[]>('/families/'),
  getFamily: (id: string) => fetchJSON<any>(`/families/${id}`),
  createFamily: (data: any) => fetchJSON<any>('/families/', { method: 'POST', body: JSON.stringify(data) }),
  updateFamily: (id: string, data: any) => fetchJSON<any>(`/families/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteFamily: (id: string) => fetchJSON<any>(`/families/${id}`, { method: 'DELETE' }),
  getFamilyMembers: (id: string) => fetchJSON<any[]>(`/families/${id}/members`),
  addFamilyMember: (id: string, data: any) => fetchJSON<any>(`/families/${id}/members`, { method: 'POST', body: JSON.stringify(data) }),
  removeFamilyMember: (id: string, model_id: string) => fetchJSON<any>(`/families/${id}/members/${encodeURIComponent(model_id)}`, { method: 'DELETE' }),
  suggestFamilies: () => fetchJSON<any[]>('/families/suggest'),

  // Dashboard
  getDashboardStats: (days: number = 30) => fetchJSON<any>(`/dashboard/stats?days=${days}`),
  getDashboardFailovers: (limit: number = 50) => fetchJSON<any[]>(`/dashboard/failovers?limit=${limit}`),
  getDashboardQuotas: () => fetchJSON<any[]>('/dashboard/quotas'),
  getAutoRouterStats: (days: number = 30) => fetchJSON<any>(`/dashboard/auto-router/stats?days=${days}`),
  getAutoRouterPolicy: () => fetchJSON<{ policy: string }>('/dashboard/auto-router/policy'),
  setAutoRouterPolicy: (policy: string) =>
    fetchJSON<{ status: string; policy: string }>('/dashboard/auto-router/policy', {
      method: 'POST',
      body: JSON.stringify({ policy }),
    }),
  previewAutoRouter: (payload: {
    prompt: string
    web_search?: boolean
    has_attachment?: boolean
    previous_model_id?: string | null
    previous_intent?: string | null
    policy?: string | null
    reasoning_effort?: string | null
    limit?: number
  }) =>
    fetchJSON<AutoRouterPreviewResult>('/dashboard/auto-router/preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  // Ranking Weights
  getRankingWeights: () => fetchJSON<any>('/ranking/weights'),
  saveRankingWeights: (data: any) =>
    fetchJSON<any>('/ranking/weights', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  getRankings: (scope: 'available' | 'all' = 'available') =>
    fetchJSON<RankingEntry[]>(`/ranking?scope=${scope}`),
  syncRankings: () => fetchJSON<RankingSyncResult>('/ranking/sync', { method: 'POST' }),

  // Memory
  getUserMemory: () => fetchJSON<any[]>('/memory'),
  getUserMemoryPreview: () =>
    fetchJSON<{
      fact_count: number
      block: string
      block_chars: number
      fingerprint?: string
      profile?: UserProfileApi
    }>('/memory/preview'),
  deleteMemoryFact: (id: string) => fetchJSON<any>(`/memory/${id}`, { method: 'DELETE' }),
  pinMemoryFact: (id: string, pinned: boolean) =>
    fetchJSON<{ status: string; id: string; is_pinned: boolean }>(`/memory/${id}/pin`, {
      method: 'PATCH',
      body: JSON.stringify({ pinned }),
    }),
  clearAllMemory: () => fetchJSON<any>('/memory/clear', { method: 'POST' }),
  getUserProfile: () => fetchJSON<UserProfileApi>('/memory/profile'),
  saveUserProfile: (data: Partial<UserProfileApi>) =>
    fetchJSON<UserProfileApi>('/memory/profile', {
      method: 'PUT',
      body: JSON.stringify({
        display_name: data.display_name,
        full_name: data.full_name,
        occupation: data.occupation,
        custom_instructions: data.custom_instructions,
        memory_enabled: data.memory_enabled === undefined ? undefined : !!data.memory_enabled,
      }),
    }),
  getTtsSettings: () =>
    fetchJSON<{ voice: string; auto: boolean; voices: { id: string; name: string; edge: string }[] }>('/tts/settings'),
  saveTtsSettings: (data: { voice?: string; auto?: boolean }) =>
    fetchJSON<{ voice: string; auto: boolean; voices: { id: string; name: string; edge: string }[] }>('/tts/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  speak: async (text: string, voice?: string, signal?: AbortSignal) => {
    const token = localStorage.getItem('nexuslocal_token')
    const headers: HeadersInit = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(BASE + '/tts', {
      method: 'POST',
      headers,
      body: JSON.stringify({ text, voice }),
      signal,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return res.blob()
  },
  getMemoryExtractorConfig: () =>
    fetchJSON<MemoryExtractorConfig>('/memory/extractor-config'),
  saveMemoryExtractorConfig: (data: Partial<MemoryExtractorConfig>) =>
    fetchJSON<MemoryExtractorConfig>('/memory/extractor-config', {
      method: 'PUT',
      body: JSON.stringify({
        memory_extractor_provider_id: data.memory_extractor_provider_id,
        memory_extractor_model_id: data.memory_extractor_model_id,
        memory_extractor_enabled: data.memory_extractor_enabled,
        memory_llm_summaries_enabled: data.memory_llm_summaries_enabled,
      }),
    }),
  getMemorySummaries: (scope?: string) =>
    fetchJSON<import('../types').MemorySummary[]>(
      scope ? `/memory/summaries?scope=${encodeURIComponent(scope)}` : '/memory/summaries'
    ),
  refreshMemorySummaries: () =>
    fetchJSON<import('../types').MemorySummary[]>('/memory/summaries/refresh', { method: 'POST' }),
  getMemoryStats: () => fetchJSON<MemoryStatsApi>('/memory/stats'),
  exportMemory: () => fetchJSON<MemoryExportBundle>('/memory/export'),
  importMemory: (data: MemoryExportBundle & { mode?: 'merge' | 'replace' }) =>
    fetchJSON<{ status: string; mode: string; imported_facts: number; imported_summaries: number }>(
      '/memory/import',
      { method: 'POST', body: JSON.stringify(data) }
    ),
  getMemoryImportPrompt: () =>
    fetchJSON<{ prompt: string; title: string; steps: string[] }>('/memory/import-prompt'),
  importMemoryText: (data: {
    text: string
    mode?: 'merge' | 'replace'
    merge_instructions_into_profile?: boolean
  }) =>
    fetchJSON<{
      status: string
      mode: string
      imported_facts: number
      sections_found: string[]
      profile_instructions_updated: boolean
    }>('/memory/import-text', { method: 'POST', body: JSON.stringify(data) }),

  // Dream Memory Consolidator
  updateMemoryFact: (id: string, data: { fact: string; category?: string }) =>
    fetchJSON<{ status: string; fact: any }>(`/memory/facts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  exportMemoryBundle: () => fetchJSON<any>('/memory/export-bundle'),
  getDreamLogs: () => fetchJSON<DreamLogApi[]>('/memory/dream-logs'),
  getMemorySnapshots: () => fetchJSON<DreamSnapshotApi[]>('/memory/snapshots'),
  rollbackMemorySnapshot: (snapshotId: string) =>
    fetchJSON<{ status: string; message: string }>(`/memory/snapshots/${snapshotId}/rollback`, {
      method: 'POST',
    }),
  getDreamConfig: () => fetchJSON<DreamConfigApi>('/memory/dream-config'),
  saveDreamConfig: (data: Partial<DreamConfigApi>) =>
    fetchJSON<{ status: string }>('/memory/dream-config', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  dreamPreview: (data?: { provider_id?: string; model_id?: string }) =>
    fetchJSON<DreamPreviewResponse>('/memory/dream-preview', {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),
  dreamRunNowStream: async (
    data?: { provider_id?: string; model_id?: string },
    onEvent?: (event: { step: string; pct: number; msg?: string; result?: any; error?: string }) => void,
    signal?: AbortSignal
  ) => {
    const token = localStorage.getItem('nexuslocal_token')
    const headers: HeadersInit = { 'Content-Type': 'application/json' }
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(BASE + '/memory/dream-run-now', {
      method: 'POST',
      headers,
      body: JSON.stringify(data || {}),
      signal,
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const reader = res.body?.getReader()
    if (!reader) return
    const decoder = new TextDecoder()
    let buffer = ''
    let sawTerminal = false
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6))
            if (parsed.step === 'done' || parsed.step === 'error' || parsed.error) sawTerminal = true
            if (onEvent) onEvent(parsed)
          } catch {}
        }
      }
    }
    if (!sawTerminal) throw new Error('conexão interrompida antes do fim')
  },

  // Projects (persistent context workspaces)
  listProjects: (sort = 'updated', q?: string) => {
    const params = new URLSearchParams({ sort })
    if (q) params.append('q', q)
    return fetchJSON<import('../types').Project[]>(`/projects?${params.toString()}`)
  },
  getProject: (id: string) => fetchJSON<import('../types').Project>(`/projects/${id}`),
  createProject: (data: { name: string; description?: string; instructions?: string }) =>
    fetchJSON<import('../types').Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  updateProject: (
    id: string,
    data: Partial<{
      name: string
      description: string
      instructions: string
      is_favorite: boolean
      archived: boolean
      model_default: string | null
      retrieval_top_k: number
      retrieval_threshold: number
    }>
  ) =>
    fetchJSON<import('../types').Project>(`/projects/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
  deleteProject: (id: string) =>
    fetchJSON<{ ok: boolean }>(`/projects/${id}`, { method: 'DELETE' }),
  patchProjectMemory: (id: string, summary_text: string) =>
    fetchJSON<{ ok: boolean; summary_text: string }>(`/projects/${id}/memory`, {
      method: 'PATCH',
      body: JSON.stringify({ summary_text }),
    }),
  listProjectFiles: (id: string) =>
    fetchJSON<import('../types').ProjectFile[]>(`/projects/${id}/files`),
  uploadProjectFile: (projectId: string, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    const token = localStorage.getItem('nexuslocal_token')
    const headers: HeadersInit = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    return fetch(BASE + `/projects/${projectId}/files`, {
      method: 'POST',
      headers,
      body: formData,
    }).then((res) => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json() as Promise<import('../types').ProjectFile>
    })
  },
  deleteProjectFile: (projectId: string, fileId: string) =>
    fetchJSON<{ ok: boolean }>(`/projects/${projectId}/files/${fileId}`, { method: 'DELETE' }),
  listProjectChats: (id: string) =>
    fetchJSON<import('../types').ProjectChat[]>(`/projects/${id}/chats`),
  createProjectChat: (projectId: string, data?: { title?: string; model_id?: string; provider_id?: string }) =>
    fetchJSON<{ id: string; project_id: string; title: string }>(`/projects/${projectId}/chats`, {
      method: 'POST',
      body: JSON.stringify(data || {}),
    }),

  // Image Generation
  getImageGenConfig: () => fetchJSON<import('../types').ImageGenConfig>('/image-gen/config'),
  saveImageGenConfig: (data: Partial<import('../types').ImageGenConfig>) =>
    fetchJSON<{ ok: boolean; config: import('../types').ImageGenConfig }>('/image-gen/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getImageModels: () => fetchJSON<import('../types').ImageModel[]>('/image-gen/models'),

  // ── Intelligent UI ──────────────────────────────────────────────
  getIntelligentUiConfig: () => fetchJSON<import('../types').IntelligentUiConfig>('/intelligent-ui/config'),
  getIntelligentUiStats: () => fetchJSON<import('../types').IntelligentUiStats>('/intelligent-ui/stats'),
  saveIntelligentUiConfig: (data: Partial<import('../types').IntelligentUiConfig>) =>
    fetchJSON<{ ok: boolean; config: import('../types').IntelligentUiConfig }>('/intelligent-ui/config', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getImageTasks: (conversationId?: string) => {
    const params = conversationId ? `?conversation_id=${encodeURIComponent(conversationId)}` : ''
    return fetchJSON<import('../types').ImageTask[]>(`/image-gen/tasks${params}`)
  },

  // Assistente proativo (F2)
  getProactiveSettings: () => fetchJSON<import('../types').ProactiveSettings>('/proactive/settings'),
  updateProactiveSettings: (
    data: Partial<
      Pick<
        import('../types').ProactiveSettings,
        'enabled' | 'sensitivity' | 'categories' | 'quiet_hours' | 'push_enabled' | 'persona_style'
      >
    > & {
      onboarding_seen?: boolean
      clear_quiet_hours?: boolean
    },
  ) =>
    fetchJSON<{ ok: boolean } & import('../types').ProactiveSettings>('/proactive/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  ackProactiveInsight: (insightId: string, action: import('../types').ProactiveAckAction) =>
    fetchJSON<{ ok: boolean; id: string; status: import('../types').ProactiveStatus; topic_hash?: string | null }>(
      `/proactive/insights/${encodeURIComponent(insightId)}/ack`,
      { method: 'POST', body: JSON.stringify({ action }) },
    ),
  // F4 — controles do usuário
  markProactiveOnboardingSeen: () =>
    fetchJSON<{ ok: boolean; onboarding_seen_at: string | null; enabled: boolean }>(
      '/proactive/settings/onboarding-seen', { method: 'POST' },
    ),
  unblockProactiveTopic: (topicHash: string) =>
    fetchJSON<{ ok: boolean; topic_hash: string; removed: boolean; restored_insight_ids: string[] }>(
      `/proactive/blocklist/${encodeURIComponent(topicHash)}`, { method: 'DELETE' },
    ),
  // F4 — admin
  getProactiveAdminConfig: () => fetchJSON<import('../types').ProactiveAdminConfig>('/proactive/admin-config'),
  updateProactiveAdminConfig: (data: import('../types').ProactiveAdminConfigUpdate) =>
    fetchJSON<{ ok: boolean } & import('../types').ProactiveAdminConfig>('/proactive/admin-config', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  getProactiveLogs: (params: { limit?: number; offset?: number; status?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.limit) q.set('limit', String(params.limit))
    if (params.offset) q.set('offset', String(params.offset))
    if (params.status) q.set('status', params.status)
    const qs = q.toString()
    return fetchJSON<import('../types').ProactiveLogsResponse>(`/proactive/logs${qs ? `?${qs}` : ''}`)
  },
  getProactiveAdminStats: (days?: number) =>
    fetchJSON<import('../types').ProactiveAdminStats>(
      `/proactive/admin-stats${days ? `?days=${encodeURIComponent(String(days))}` : ''}`,
    ),
  // F3 — fila de pendentes (boot) e "Me conta aqui"
  getProactivePending: () =>
    fetchJSON<{ insights: import('../types').ProactiveInsight[] }>('/proactive/pending'),
  expandProactiveInsight: (insightId: string, mode: import('../types').ProactiveExpandMode) =>
    fetchJSON<import('../types').ProactiveExpandResult>(
      `/proactive/insights/${encodeURIComponent(insightId)}/expand`,
      { method: 'POST', body: JSON.stringify({ mode }) },
    ),
  chatProactiveCompanion: (
    insightId: string,
    message: string,
    history: Array<{ role: string; content: string }> = []
  ) =>
    fetchJSON<{
      ok: boolean
      reply: string
      artifact?: { id: string; title: string; content: string; version: number } | null
    }>('/proactive/companion/chat', {
      method: 'POST',
      body: JSON.stringify({ insight_id: insightId, message, history }),
    }),
  // F6 — Web Push no PWA
  getVapidPublicKey: () => fetchJSON<{ publicKey: string }>('/push/vapid-public-key'),
  subscribePush: (data: { endpoint: string; keys: { p256dh: string; auth: string }; user_agent?: string }) =>
    fetchJSON<{ ok: boolean; subscription_id: number }>('/push/subscribe', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  unsubscribePush: (endpoint: string) =>
    fetchJSON<{ ok: boolean; removed: boolean }>(`/push/subscribe?endpoint=${encodeURIComponent(endpoint)}`, {
      method: 'DELETE',
    }),
  testPushNotification: () =>
    fetchJSON<{ ok: boolean; sent?: number; reason?: string }>('/push/test', {
      method: 'POST',
    }),
  // F7 — Central Hub & Histórico
  getProactiveHistory: (params: { limit?: number; status?: string } = {}) => {
    const q = new URLSearchParams()
    if (params.limit) q.set('limit', String(params.limit))
    if (params.status) q.set('status', params.status)
    const qs = q.toString()
    return fetchJSON<{ insights: import('../types').ProactiveInsight[] }>(`/proactive/history${qs ? `?${qs}` : ''}`)
  },
  investigateProactive: (prompt: string, category?: string) =>
    fetchJSON<{ ok: boolean; insight_id: string; conversation_id: string }>('/proactive/investigate', {
      method: 'POST',
      body: JSON.stringify({ prompt, category }),
    }),
}

export interface MemoryStatsApi {
  active_facts: number
  inactive_facts: number
  pinned_facts?: number
  dream_count?: number
  last_dream_at?: string | null
  by_category: Record<string, number>
  summaries_count: number
  last_fact_update?: string | null
  extractions_total: number
  extractions_today: number
}

export interface MemoryExportBundle {
  format?: string
  exported_at?: string
  user_id?: string
  profile?: Partial<UserProfileApi>
  facts?: Array<{
    category?: string
    fact?: string
    fact_key?: string | null
    confidence?: number
    is_pinned?: number
  }>
  summaries?: Array<{
    scope?: string
    scope_ref?: string
    summary_md?: string
  }>
  mode?: 'merge' | 'replace'
}

export interface MemoryExtractorConfig {
  memory_extractor_provider_id?: string | null
  memory_extractor_model_id?: string | null
  memory_extractor_enabled?: boolean
  memory_llm_summaries_enabled?: boolean
  resolved_source?: 'memory_extractor' | 'enhancer' | 'chat_fallback'
}

export interface DreamLogApi {
  id: string
  user_id: string
  snapshot_id?: string | null
  provider_id: string
  model_id: string
  facts_before: number
  facts_after: number
  facts_merged: number
  facts_superseded: number
  facts_created: number
  facts_total_active: number
  duration_ms: number
  status: 'running' | 'success' | 'failed' | 'rolled_back' | 'aborted_safety' | 'purged_by_user'
  summary_notes?: string | null
  error_message?: string | null
  can_rollback?: boolean
  created_at: string
}

export interface DreamConfigApi {
  dream_enabled: boolean
  dream_min_idle_minutes: number
  dream_min_hours_between_runs: number
  dream_min_active_facts: number
  dream_provider_id: string
  dream_model_id: string
}

export interface DreamSnapshotApi {
  id: string
  trigger_type: string
  facts_count: number
  snapshot_hash: string
  is_compressed: number
  created_at: string
}

export interface DreamOperationApi {
  action: 'merge' | 'supersede' | 'archive' | 'keep'
  source_fact_ids?: string[]
  old_fact_id?: string
  fact_id?: string
  new_fact?: {
    category: string
    fact_key?: string
    fact: string
    confidence: number
    is_pinned: boolean
  }
  reason?: string
}

export interface DreamPreviewResponse {
  summary_of_changes: string
  operations: DreamOperationApi[]
  facts_before: number
  projected_active: number
  actions_breakdown: {
    merge: number
    supersede: number
    archive: number
    keep: number
  }
  provider_id?: string
  model_id?: string
  clusters_count?: number
}