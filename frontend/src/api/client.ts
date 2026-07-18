import type { Conversation, ConversationDetail, Model, Provider, CacheStats, CacheSettings, CacheEntry, EnhancerConfig, FusionConfig, Artifact, Attachment, VisionRelayConfig, WebSearchConfig, WebSearchLog } from '../types'

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
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json()
}

export const api = {
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
  updateModel: (id: string, data: { enabled?: boolean; context_length?: number }) =>
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
  deleteUser: (id: string) => fetchJSON(`/admin/users/${id}`, { method: 'DELETE' }),

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

  // Ranking Weights
  getRankingWeights: () => fetchJSON<any>('/ranking/weights'),
  saveRankingWeights: (data: any) =>
    fetchJSON<any>('/ranking/weights', {
      method: 'POST',
      body: JSON.stringify(data)
    }),
  getRankings: () => fetchJSON<any[]>('/ranking'),

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
}

export interface MemoryStatsApi {
  active_facts: number
  inactive_facts: number
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