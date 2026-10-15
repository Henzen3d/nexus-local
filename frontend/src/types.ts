import type { UiError } from './lib/nexusUi'
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

export interface LibraryItem {
  id: string
  message_id?: string | null
  conversation_id?: string | null
  conversation_title?: string | null
  filename: string
  mime_type: string
  file_type: 'document' | 'image'
  size_bytes: number
  storage_path: string
  thumbnail_path?: string | null
  thumbnail_url?: string | null
  file_url: string
  created_at: string
  is_generated: boolean
  prompt?: string | null
  model_id?: string | null
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
  snippet?: string
}

export type ProcessStepType = 'think' | 'search' | 'navigate' | 'tool'

export interface ProcessStep {
  id: string
  type: ProcessStepType
  title: string
  detail?: string
  subSteps?: string[]
  status: 'running' | 'completed' | 'failed'
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
  process_steps?: ProcessStep[]
  process_duration_ms?: number
  was_fallback?: boolean
  auto_route?: AutoRouteDecisionInfo | null
  ui_errors?: UiError[]
  ui_dropped?: number
  ui_blocks?: UiEnvelope | null
  /** Assistente proativo (F2): bolha gerada sem pedido do usuário */
  kind?: 'normal' | 'proactive'
  proactive_insight_id?: string | null
  insight?: ProactiveInsight | null
}

// ─── Assistente proativo (F2) ────────────────────────────────────────────────

export type ProactiveCategory = 'event' | 'news' | 'product' | 'place' | 'other'
export type ProactiveStatus =
  | 'detected' | 'researching' | 'ready' | 'delivered' | 'seen'
  | 'dismissed' | 'blocked' | 'expired' | 'failed'

export interface ProactiveSource {
  title: string
  url: string
  domain: string
}

/** Shape do contrato §3.2 (`proactive_insight.insight`) e do `insight` anexado no GET da conversa */
export interface ProactiveInsight {
  id: string
  conversation_id: string
  message_id: string | null
  topic: string
  category: ProactiveCategory
  text: string
  reason_line?: string
  sources: ProactiveSource[]
  follow_ups: string[]
  status?: ProactiveStatus | null
  language?: string | null
  expires_at?: string | null
  created_at?: string | null
  /** F3: canal efetivo da entrega (inline | toast | pending_inline | new_chat …) */
  channel?: ProactiveChannel | null
  ready_at?: string | null
  /** F3.3: conversa criada por "Me conta aqui" (quando existir) */
  spawned_conversation_id?: string | null
  /** F3: conversa de origem (presente nos pendentes e nas bolhas de chat novo) */
  origin?: ProactiveOrigin | null
  /** F4.3.2: hash do tópico — "Desfazer" do bloqueio (`DELETE /blocklist/{hash}`) */
  topic_hash?: string | null
  /** Artefato gerado em background com os dados da pesquisa */
  artifact_id?: string | null
  artifact_title?: string | null
  artifact_content?: string | null
}

export interface CompanionMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at?: string
  artifact?: { id: string; title: string; content: string; version: number } | null
}

export interface ProactiveOrigin {
  conversation_id: string
  title: string
}

export type ProactiveChannel =
  | 'inline' | 'toast' | 'pending_card' | 'pending_inline' | 'new_chat' | 'push'

export type ProactiveChannelHint = 'inline' | 'toast' | 'pending'
export type ProactiveExpandMode = 'same' | 'new_chat'

export interface ProactiveExpandResult {
  ok: boolean
  mode: ProactiveExpandMode
  conversation_id: string
  /** mode=same: texto sugerido para o composer (follow_ups[0]) */
  prefill?: string
  topic?: string
  /** mode=new_chat */
  message_id?: string
  title?: string
  created?: boolean
}
export type ProactiveSensitivity = 'low' | 'medium' | 'high'

export interface ProactiveQuietHours {
  start: string
  end: string
}

export interface ProactiveBlockedTopic {
  topic_hash: string
  topic_label: string
  created_at?: string | null
}

export interface ProactiveUserStats {
  insights_30d: number
  delivered_30d: number
  know_more_30d: number
  blocked_30d: number
}

export type ProactivePersonaStyle = 'lumi' | 'core'

export interface ProactiveSettings {
  enabled: boolean
  sensitivity: ProactiveSensitivity
  categories: ProactiveCategory[]
  quiet_hours?: ProactiveQuietHours | null
  push_enabled?: boolean
  persona_style?: ProactivePersonaStyle
  onboarding_seen_at?: string | null
  updated_at?: string | null
  allowed_categories?: ProactiveCategory[]
  allowed_sensitivities?: ProactiveSensitivity[]
  /** F4.1.1 */
  blocked_topics?: ProactiveBlockedTopic[]
  stats?: ProactiveUserStats
  conversation_count?: number
  /** F4.2.1 — onboarding nunca visto, desligado e ≥ 3 conversas (fonte: servidor) */
  onboarding_eligible?: boolean
  /** F4.1.5 — eco do PUT {enabled:false} */
  disabled?: { cancelled: number; expired: number }
}

export type ProactiveAckAction = 'seen' | 'dismissed' | 'blocked' | 'know_more'

/** F4.4.1 — configuração global (admin), persistida em `meta` */
export interface ProactiveAdminConfig {
  enabled_global: boolean
  detector_provider_id: string | null
  detector_model_id: string | null
  synth_provider_id: string | null
  synth_model_id: string | null
  allow_chat_model_fallback: boolean
  max_per_hour_conv: number
  max_per_day_user: number
  topic_cooldown_hours: number
  max_pending: number
  concurrency: number
  total_timeout_s: number
  research_timeout_s: number
  synth_timeout_s: number
  expiry_news_hours: number
  expiry_default_days: number
  /** F5.4.3 — libera o modal de onboarding para quem ainda não ativou (meta `proactive_onboarding_enabled`) */
  onboarding_enabled: boolean
  limits?: Record<string, [number, number]>
  kill_switch?: { cancelled: number; expired: number }
}

export type ProactiveAdminConfigUpdate = Partial<Omit<ProactiveAdminConfig, 'limits' | 'kill_switch'>>

/** F4.4.2 — linha anonimizada (nunca o texto da mensagem) */
export interface ProactiveLogRow {
  id: string
  created_at: string
  username: string
  category: ProactiveCategory | string
  topic: string
  confidence: number | null
  status: ProactiveStatus
  channel: ProactiveChannel | null
  latency_detect_ms: number | null
  latency_research_ms: number | null
  latency_synth_ms: number | null
  detector_model: string | null
  synth_model: string | null
  error_code: string | null
}

export interface ProactiveLogsResponse {
  rows: ProactiveLogRow[]
  total: number
  limit: number
  offset: number
  status?: string | null
}

export interface ProactiveStatsWindow {
  total: number
  by_status: Record<ProactiveStatus, number>
  delivered: number
  know_more: number
  blocked: number
  dismissed: number
  users: number
  know_more_rate: number | null
  blocked_rate: number | null
  failure_rate: number | null
}

/** F5.2.4 — um dia (UTC) da série do dashboard; dias sem dados vêm zerados */
export interface ProactiveDailyPoint extends Record<ProactiveStatus, number> {
  day: string
  total: number
  know_more: number
  tokens_in: number
  tokens_out: number
}

/** F5.2.4 — tokens estimados (chars/4) por janela */
export interface ProactiveTokenTotals {
  tokens_in: number
  tokens_out: number
  insights: number
}

/** F5.2.5 — alarme `failed/total > threshold` nas últimas 24 h (com amostra mínima) */
export interface ProactiveFailureAlert {
  active: boolean
  failed: number
  total: number
  ratio: number | null
  threshold: number
  min_samples: number
}

/** F4.4.3 (+ F5.2.4/F5.2.5: `tokens`, `daily`, `alert`) */
export interface ProactiveAdminStats {
  windows: { '24h': ProactiveStatsWindow; '7d': ProactiveStatsWindow }
  tokens?: { '24h': ProactiveTokenTotals; '7d': ProactiveTokenTotals }
  daily?: ProactiveDailyPoint[]
  days?: number
  alert?: ProactiveFailureAlert
  latency: {
    samples: number
    detect_p50_ms: number | null
    detect_p95_ms: number | null
    research_p50_ms: number | null
    research_p95_ms: number | null
    synth_p50_ms: number | null
    synth_p95_ms: number | null
    total_p95_ms: number | null
  }
  users_enabled: number
  pending_now: number
  blocklist_size: number
  runtime: {
    tasks_in_flight: number
    presence: {
      users_online?: number
      users_active?: number
      sockets?: number
      transitions_last_hour?: number
      transitions_by_kind?: Record<string, number>
    }
  }
}

export type PresenceState = 'active' | 'idle' | 'hidden'

/** Toast com ação opcional e fila (F2.7.7) — `showToast(message, type)` continua funcionando */
export interface ToastItem {
  id: string
  message: string
  type: 'success' | 'error' | 'info' | 'proactive'
  title?: string
  action?: { label: string; onClick: () => void }
  durationMs?: number
}

export type UiBlockType =
  | 'progress'
  | 'card'
  | 'chart'
  | 'table'
  | 'controls'
  | 'options'
  | 'sandbox'
  | 'metric'
  | 'callout'
  | 'follow_up'

export interface ProgressStep {
  id: string
  label: string
  state: 'pending' | 'active' | 'done' | 'error'
}

export interface ProgressBlock {
  id: string
  type: 'progress'
  label: string
  value?: number | string
  max?: number
  steps?: ProgressStep[]
}

export interface CardFact {
  label: string
  value: string
}

export interface CardBlock {
  id: string
  type: 'card'
  title: string
  body?: string
  image?: { url: string; alt: string }
  facts?: CardFact[]
}

export interface ChartSeries {
  key: string
  label: string
}

export interface ChartBlock {
  id: string
  type: 'chart'
  title: string
  kind: 'bar' | 'line' | 'compare' | 'pie'
  x_key: string
  series: ChartSeries[]
  rows: Record<string, string | number>[]
  unit?: string
  x_label?: string
  y_label?: string
  stacked?: boolean
}

export interface TableColumn {
  key: string
  label: string
  kind?: 'text' | 'number' | 'date'
  unit?: string
}

export interface TableSort {
  key: string
  dir: 'asc' | 'desc'
}

export interface TableBlock {
  id: string
  type: 'table'
  title?: string
  columns: TableColumn[]
  rows: Record<string, string | number | null>[]
  sort?: TableSort
}

export interface ControlField {
  id: string
  kind: 'text' | 'select' | 'number' | 'range'
  label: string
  placeholder?: string
  min?: number
  max?: number
  step?: number
  default?: number
  options?: { value: string; label: string }[]
}

export interface ControlAction {
  name: 'send_message' | 'set_model'
  template?: string
  field?: string
}

export interface ControlComputed {
  id?: string
  template: string
  formula: string
}

export interface ControlsBlock {
  id: string
  type: 'controls'
  title: string
  submit_label: string
  fields: ControlField[]
  computed?: ControlComputed | ControlComputed[]
  action: ControlAction
}

export interface SceneParam {
  id: string
  label: string
  kind: 'range' | 'number' | 'select'
  min?: number
  max?: number
  step?: number
  default: number | string
  options?: { value: string; label: string }[]
}

export interface SceneReadout {
  key: string
  label: string
  unit?: string
}

export interface SandboxBlock {
  id: string
  type: 'sandbox'
  kind?: 'scene'
  mode?: '3d' | '2d'
  title: string
  initial_height?: number
  html?: string
  css?: string
  js?: string
  code?: string
  params?: SceneParam[]
  readout?: SceneReadout[]
  standalone_download?: boolean
}

/** Indicador de `metric` (plano 12 §2.1): valor com delta e tendência, estilo KPI. */
export interface MetricItem {
  label: string
  value: number | string
  /** Só acompanha `value` numérico. */
  unit?: string
  delta?: string
  trend?: 'up' | 'down' | 'flat'
  /** Qual direção é boa (padrão `up`): define a cor do delta. */
  good?: 'up' | 'down'
  hint?: string
}

export interface MetricBlock {
  id: string
  type: 'metric'
  title?: string
  items: MetricItem[]
}

/** Aviso curto com destaque (plano 12 §2.2). */
export interface CalloutBlock {
  id: string
  type: 'callout'
  kind: 'info' | 'success' | 'warning' | 'danger'
  title?: string
  body: string
}

/** Sugestões de próxima pergunta (plano 12 §2.3); sempre o último bloco do envelope. */
export interface FollowUpBlock {
  id: string
  type: 'follow_up'
  items: string[]
}

export interface OptionItem {
  value: string
  label: string
  description?: string
}

export interface OptionsBlock {
  id: string
  type: 'options'
  question: string
  mode?: 'single' | 'multiple'
  options: OptionItem[]
  allow_other?: boolean
  action: {
    name: 'send_message'
    template: string
  }
}

export type UiBlock =
  | ProgressBlock
  | CardBlock
  | ChartBlock
  | TableBlock
  | ControlsBlock
  | OptionsBlock
  | SandboxBlock
  | MetricBlock
  | CalloutBlock
  | FollowUpBlock

export interface UiEnvelope {
  v: 1
  blocks: UiBlock[]
}

/** Configuração efetiva do Intelligent UI (GET /api/intelligent-ui/config). */
export interface IntelligentUiConfig {
  enabled: boolean
  /** Hosts remotos confiáveis para imagem de cartão (já normalizados pelo servidor). */
  image_hosts: string[]
  allow_private_http: boolean
  /** De onde veio o valor efetivo: painel ('db'), .env ('env') ou padrão. */
  source?: 'db' | 'env' | 'default'
  updated_at?: string | null
}

/** Contadores do processo (GET /api/intelligent-ui/stats, admin). Zeram no restart. */
export interface IntelligentUiStats {
  since: string
  turns: number
  offered: number
  produced: number
  produced_when_offered: number
  produced_without_offer: number
  valid: number
  blocks_in: number
  blocks_out: number
  blocks_dropped: number
  discarded: Record<'no_fence' | 'invalid_json' | 'rejected_envelope' | 'empty_after_validation', number>
  block_types: Record<string, number>
  corrections?: Record<string, { correction_offered: number; correction_requested: number; correction_valid: number; valid_rate: number | null }>
  rates: {
    produced_given_offered: number | null
    valid_given_produced: number | null
    blocks_kept: number | null
  }
}

export interface AutoRouteAlternative {
  model_id: string
  model_name: string
  provider_id: string
  fit_score: number
  tags?: string[]
}

export interface AutoRouteDecisionInfo {
  chosen_model_id: string
  chosen_model_name: string
  provider_id: string
  intent: string
  reason_pt: string
  confidence: number
  policy: string
  temperature: number
  decision_latency_ms: number
  matched_signals?: string[]
  /** 1 = leve, 2 = média, 3 = pesada (calibração 2026) */
  complexity?: number
  fit_score?: number
  /** Esforço de raciocínio adaptativo aplicado (null = modelo sem dial) */
  reasoning_effort?: string | null
  model_tags?: string[]
  alternatives?: AutoRouteAlternative[]
}

export interface AutoRouterPreviewCandidate {
  model_id: string
  model_name: string
  provider_id: string
  fit_score: number
  quality_score: number
  has_ranking: boolean
  is_free: boolean
  quota_status?: string
  tags: string[]
  breakdown?: Record<string, number>
}

export interface AutoRouterPreviewResult {
  intent: {
    intent: string
    complexity: number
    complexity_score: number
    confidence: number
    reason_label_pt: string
    matched_signals: string[]
    recommended_temperature: number
    inherited_from_history: boolean
    min_context_length_required: number
    processing_time_ms: number
  }
  policy: string
  decision: AutoRouteDecisionInfo
  ranking: AutoRouterPreviewCandidate[]
  candidates_considered: number
  catalog_size: number
}

/** Linha de GET /api/ranking (Configurações → Rankings de Modelos). */
export interface RankingEntry {
  model_id: string
  quality_score: number
  popularity_rank: number | null
  internal_usage_count: number
  nexuslocal_score: number
  quality_contribution: number
  popularity_contribution: number
  usage_contribution: number
  popularity_normalized: number
  usage_normalized: number
  /** 'curated' (model_rankings.json) | 'heuristic' (família/geração, mesma base do roteador) */
  source: string
  display_name?: string | null
  provider_id?: string | null
  provider_name?: string | null
  is_free?: boolean | null
  is_local?: boolean | null
  available?: boolean | null
  unavailable_reason?: 'provider_disabled' | 'model_disabled' | 'missing_key' | 'unconfirmed_free' | string | null
  size_label?: 'nano' | 'small' | 'medium' | 'large' | 'frontier' | string | null
  tags?: string[]
}

export interface RankingSyncResult {
  status: string
  models?: number
  curated?: number
  heuristic?: number
  matched_popularity?: number
  openrouter_models?: number
  popularity_refreshed?: boolean
  updated_scores?: number
  message?: string
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
  /** F3.3: conversa iniciada pelo assistente proativo ("Me conta aqui") */
  origin_insight_id?: string | null
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
  reasoning_control?: string
  reasoning_levels?: string[] | null
  reasoning_default?: string | null
  reasoning_control_source?: string
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
  supports_vision?: boolean
  reasoning_control?: string
  reasoning_levels?: string[] | null
  reasoning_default?: string | null
  reasoning_control_source?: string
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
  account_id?: string | null
}

export interface WebSearchConfig {
  enabled: boolean
  search_provider: 'duckduckgo' | 'brave'
  api_key: string
  api_key_set?: boolean
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
  | { type: 'stream_end'; message_id: string; conversation_id: string; artifact_id?: string | null; artifact_type?: string | null; artifact_title?: string | null; artifacts?: { id: string; type: string; title: string }[]; relay_used?: boolean; relay_model?: string | null; web_search_used?: boolean; web_search_query?: string; web_search_sources?: WebSearchSource[]; process_steps?: ProcessStep[]; was_fallback?: boolean; ui_errors?: UiError[]; ui_dropped?: number; ui_blocks?: UiEnvelope | null; process_duration_ms?: number; source_count?: number }
  | { type: 'ui_progress'; block: ProgressBlock }
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
  | { type: 'process_step_start'; id: string; step_type: ProcessStepType; title: string; detail?: string }
  | { type: 'process_step_update'; id: string; detail?: string; sub_steps?: string[] }
  | { type: 'process_step_end'; id: string; status: 'completed' | 'failed'; sub_steps?: string[] }
  | ({ type: 'auto_route_decision' } & AutoRouteDecisionInfo)
  | { type: 'image_pending'; conversation_id: string; message_id: string; task_id: string; prompt: string }
  | { type: 'image_ready'; conversation_id: string; message_id: string; task_id: string; attachment: Attachment }
  | { type: 'image_failed'; conversation_id: string; message_id: string; task_id: string; error: string }
  | { type: 'effort_dropped'; reason: 'failover' | 'unsupported_model' | 'provider_rejected' | 'invalid_level' }
  | { type: 'proactive_status'; conversation_id: string; stage: 'researching' | 'synthesizing' | string }
  | { type: 'proactive_insight'; insight: ProactiveInsight; channel_hint: ProactiveChannelHint }
  | { type: 'proactive_pending'; insights: ProactiveInsight[] }

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

// ─── Image Generation ──────────────────────────────────────────────────────────

export interface ImageGenConfig {
  enabled: boolean
  auto_detect: boolean
  provider_id: string
  model_id: string
  steps: number
  width: number
  height: number
  daily_cap_per_user: number
}

export interface ImageModel {
  id: string
  provider_id: string
  model_id: string
  display_name: string
  default_steps: number
  max_steps: number
  is_active: boolean
}

export interface ImageTask {
  id: string
  conversation_id: string
  user_id: string
  prompt: string
  provider_id: string
  model_id: string
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message?: string | null
  attachment_id?: string | null
  created_at: string
  completed_at?: string | null
}
