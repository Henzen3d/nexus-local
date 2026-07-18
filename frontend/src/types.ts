export interface Attachment {
  id: string
  filename: string
  mime_type: string
  file_type: 'document' | 'image'
  size_bytes: number
  thumbnail_url?: string | null
  file_url?: string
  extracted_text?: string | null
}

export interface VisionRelayConfig {
  relay_provider_id: string | null
  relay_model_id: string | null
  relay_system_prompt: string
  enabled: boolean
  cache_descriptions: boolean
}

export interface WebSearchSource {
  title: string
  url: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'fusion_status' | 'error'
  content: string
  model_id?: string
  created_at?: string
  fusion_statuses?: FusionStatusEntry[]
  fusion_judge_model_id?: string | null
  fusion_grounding?: { status: 'checking' | 'searching' | 'done'; queries?: string[]; found?: boolean } | null
  fusion_refined_prompt?: string | null
  artifact_id?: string
  artifact_title?: string
  artifact_type?: string
  artifacts?: { id: string; type: string; title: string }[]
  provider?: string
  model_display_name?: string
  attachments?: Attachment[]
  relay_used?: boolean
  relay_model?: string | null
  web_search_used?: boolean
  web_search_query?: string
  web_search_sources?: WebSearchSource[]
  was_fallback?: boolean
}

export interface Conversation {
  id: string
  title: string
  model_id?: string
  provider_id?: string
  created_at: string
  updated_at: string
  message_count: number
  is_favorite?: boolean
  favorited_at?: string | null
  /** Phase C2: optional project slug for memory summaries */
  project_tag?: string | null
  /** Projects module FK (nullable = chat avulso) */
  project_id?: string | null
}

export interface Project {
  id: string
  name: string
  description?: string
  instructions?: string
  model_default?: string | null
  is_favorite?: boolean
  archived?: boolean
  retrieval_top_k?: number
  retrieval_threshold?: number
  created_at: string
  updated_at: string
  file_count?: number
  chat_count?: number
  memory_preview?: string | null
  memory?: {
    summary_text: string
    last_synthesized_at?: string | null
    scope_badge?: string
  }
}

export interface ProjectFile {
  id: string
  filename: string
  mime_type?: string
  size_bytes?: number
  index_status: 'pending' | 'indexing' | 'ready' | 'error' | string
  index_error?: string | null
  indexed_at?: string | null
  created_at?: string
}

export interface ProjectChat {
  id: string
  title: string
  model_id?: string
  provider_id?: string
  created_at: string
  updated_at: string
  message_count: number
}

export interface MemorySummary {
  id: string
  user_id: string
  scope: 'global' | 'project' | 'conversation'
  scope_ref: string
  summary_md: string
  updated_at: string
}

export interface ConversationDetail extends Conversation {
  messages: Message[]
}

export interface Artifact {
  id: string
  conv_id: string
  msg_id?: string
  type: 'html' | 'markdown' | 'svg' | 'code' | 'jsx'
  title: string
  content: string
  version: number
  artifact_group_id: string
  created_at: string
  visibility?: 'Publicado' | 'Privado'
  view_count?: number
  thumbnail?: string | null
}

export interface Model {
  id: string
  display_name: string
  context_length: number
  provider_id: string
  provider_name: string
  supports_vision?: boolean
  // Ranking fields (from model_rankings + model_quota_status)
  nexuslocal_score?: number | null
  popularity_rank?: number | null
  quality_score?: number | null
  quota_status?: 'available' | 'degraded' | 'exhausted'
  internal_usage_count?: number
  known_rpm?: number | null
  known_rpd?: number | null
  current_minute_count?: number | null
  current_day_count?: number | null
}

export interface ProviderModel {
  id: string
  display_name: string
  enabled: boolean
  context_length: number
  context_source?: string
  confirmed_free?: boolean
}


export interface Provider {
  id: string
  name: string
  base_url: string
  /** Provedor utilizável (chave pessoal, global, compartilhada ou ollama) */
  has_key: boolean
  /** Chave própria do usuário em user_api_keys */
  has_personal_key?: boolean
  is_shared?: boolean
  /** Admin: compartilha a chave deste provedor com outros usuários */
  share_admin_key?: boolean
  /** Eco do toggle global (meta) */
  share_admin_keys_global?: boolean
  enabled: boolean
  is_free: boolean
  models: ProviderModel[]
  masked_key?: string
}

export interface WebSearchConfig {
  enabled: boolean
  search_provider: 'duckduckgo' | 'brave'
  api_key: string
  max_results: number
  heuristic_enabled: boolean
  heuristic_sensitivity: 'low' | 'medium' | 'high'
  injection_template?: string
}

export interface FreeRegistryConfig {
  last_updated: string | null
  threshold: number
  hide_unconfirmed: boolean
}

export interface WebSearchLog {
  id: string
  conversation_id: string
  message_id: string
  query: string
  trigger_type: 'manual' | 'heuristic'
  results_count: number
  created_at: string
}

export type WSMessage =
  | { type: 'ready' }
  | { type: 'ping' }
  | { type: 'pong' }
  | { type: 'conversation_created'; conversation_id: string; title: string; project_id?: string | null }
  | { type: 'stream_start'; conversation_id: string; from_cache?: boolean; cache_type?: string | null; cache_similarity?: number | null }
  | { type: 'token'; content: string }
  | { type: 'stream_end'; message_id: string; conversation_id: string; artifact_id?: string | null; artifact_type?: string | null; artifact_title?: string | null; artifacts?: { id: string; type: string; title: string }[]; relay_used?: boolean; relay_model?: string | null; web_search_used?: boolean; web_search_query?: string; web_search_sources?: WebSearchSource[]; was_fallback?: boolean }
  | { type: 'error'; message: string }
  | { type: 'failover_notice'; original_model: string; fallback_model: string; reason: string }
  | { type: 'project_context_notice'; message: string; tokens_est: number; safe_input_tokens: number }
  | { type: 'project_context_debug'; project_id: string; debug: unknown; file_chunks: ProjectContextFileChunk[]; chat_chunks: ProjectContextChatChunk[]; tokens_est: number; trimmed: unknown; safe_input_tokens: number; system_tokens_est: number }
  | { type: 'fusion_start'; models: string[] }
  | { type: 'fusion_phase'; phase: 'refining' | 'proposers' | 'grounding' | 'judge' | string }
  | { type: 'fusion_status'; model_id: string; provider_id: string; status: 'running' | 'done' | 'error'; response?: string; confidence?: FusionConfidence | null; confidence_reason?: string | null }
  | { type: 'fusion_judge_start'; model_id: string }
  | { type: 'fusion_grounding'; status: 'checking' | 'searching' | 'done'; queries?: string[]; found?: boolean }
  | { type: 'fusion_refined_prompt'; prompt: string }
  | { type: 'artifact'; id: string; artifact_type: 'html' | 'markdown' | 'svg' | 'code' | 'jsx'; title: string; conv_id: string; msg_id: string }
  | { type: 'search_start'; query: string }

export interface ProjectContextFileChunk {
  filename: string | null
  score: number
  preview: string
}

export interface ProjectContextChatChunk {
  conversation_id: string | null
  score: number
  preview: string
}


export interface CacheStats {
  exact: { entries: number; hits: number; tokens_saved: number }
  semantic: { entries: number; hits: number; tokens_saved: number; embedder_ready: boolean; embedder_error: string | null }
  total_hits: number
  total_tokens_saved: number
}

export interface CacheSettings {
  enabled: boolean
  exact_enabled: boolean
  semantic_enabled: boolean
  exact_ttl_hours: number
  semantic_ttl_hours: number
  similarity_threshold: number
}

export interface CacheEntry {
  id: string
  key: string
  model_id: string
  hits: number
  token_est: number
  created_at: string
  last_hit: string | null
}

export interface EnhancerConfig {
  enhancer_provider_id: string | null
  enhancer_model_id: string | null
  enhancer_enabled: boolean
  enhancer_system_prompt: string
}

export interface FusionModel {
  id: number
  provider_id: string
  model_id: string
  position: number
}

export interface FusionConfig {
  judge_provider_id: string
  judge_model_id: string
  judge_system_prompt: string
  enabled: boolean
  grounding_enabled: boolean
  models: FusionModel[]
}

export type FusionModelStatus = 'pending' | 'running' | 'done' | 'error'

export type FusionConfidence = 'alta' | 'media' | 'baixa'

export interface FusionStatusEntry {
  model_id: string
  provider_id: string
  status: FusionModelStatus
  response?: string
  confidence?: FusionConfidence | null
  confidence_reason?: string | null
}

// ─── Fase 7: Arquitetura de Adapters ──────────────────────────────────────────

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, any>;
}

export interface NormalizedMetadata {
  tokens_generated?: number;
  input_tokens?: number;
  tokens_per_second?: number;
  total_time_ms?: number;
  reasoning_time_ms?: number;
  model_id?: string;
  provider?: string;
}

export interface NormalizedResponse {
  reasoning: string | null;
  answer: string;
  isThinking?: boolean;
  toolCalls?: ToolCall[];
  metadata?: NormalizedMetadata;
}