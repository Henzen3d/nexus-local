import type { Conversation, ConversationDetail, Model, Provider, CacheStats, CacheSettings, CacheEntry, EnhancerConfig, FusionConfig, Artifact, Attachment, VisionRelayConfig, WebSearchConfig, WebSearchLog } from '../types'

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
  updateProvider: (id: string, data: { api_key?: string; enabled?: boolean; base_url?: string }) =>
    fetchJSON(`/admin/providers/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
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
    }).then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.json()
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
}