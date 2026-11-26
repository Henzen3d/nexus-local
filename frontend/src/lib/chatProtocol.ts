import type {
  ProcessStep,
  StreamEndFailureMessage,
  StreamEndSuccessMessage,
  WebSearchSource,
  WSMessage,
} from '../types'
import {
  sanitizeErrorText,
  sanitizeProcessStep,
  sanitizeProcessSteps,
  sanitizeStepDetail,
  sanitizeStepTitle,
} from './sanitization.ts'

const TURN_PROGRESS_TYPES = new Set<WSMessage['type']>([
  'request_ack', 'stream_start', 'stream_clear', 'token', 'ui_progress', 'search_start',
  'tool_executing', 'tool_executed', 'tool_failed',
  'process_step_start', 'process_step_update', 'process_step_end',
  'auto_route_decision', 'triage_decision', 'failover_notice', 'history_trimmed',
  'effort_dropped', 'image_pending', 'fusion_start', 'fusion_phase', 'fusion_status',
  'fusion_judge_start', 'fusion_grounding', 'fusion_refined_prompt',
])

export function isTurnProgressFrame(type: WSMessage['type']): boolean {
  return TURN_PROGRESS_TYPES.has(type)
}

const KNOWN_TYPES = new Set([
  'ready',
  'ping',
  'pong',
  'request_ack',
  'conversation_created',
  'tool_executing',
  'tool_executed',
  'tool_failed',
  'stream_start',
  'stream_clear',
  'token',
  'stream_end',
  'ui_progress',
  'error',
  'failover_notice',
  'project_context_notice',
  'project_context_debug',
  'fusion_start',
  'fusion_phase',
  'fusion_status',
  'fusion_judge_start',
  'fusion_grounding',
  'fusion_refined_prompt',
  'artifact',
  'search_start',
  'process_step_start',
  'process_step_update',
  'process_step_end',
  'auto_route_decision',
  'triage_decision',
  'image_pending',
  'image_ready',
  'image_failed',
  'effort_dropped',
  'history_trimmed',
  'proactive_status',
  'proactive_insight',
  'proactive_pending',
])

function nonEmptyString(v: unknown): v is string {
  return typeof v === 'string' && v.trim().length > 0
}

function optionalString(v: unknown): string | undefined {
  return typeof v === 'string' && v.length > 0 ? v : undefined
}

function objectRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

function stringList(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((item) => typeof item === 'string')
}

function optionalNumber(v: unknown): number | undefined {
  return typeof v === 'number' && Number.isFinite(v) ? v : undefined
}

function optionalBoolean(v: unknown): boolean | undefined {
  return typeof v === 'boolean' ? v : undefined
}

function processStepType(v: unknown): v is ProcessStep['type'] {
  return v === 'think' || v === 'search' || v === 'navigate' || v === 'tool'
}

function processStep(v: unknown): v is ProcessStep {
  return objectRecord(v) && nonEmptyString(v.id) && processStepType(v.type) &&
    typeof v.title === 'string' &&
    (v.status === 'running' || v.status === 'completed' || v.status === 'failed') &&
    (v.subSteps == null || stringList(v.subSteps)) &&
    (v.detail == null || typeof v.detail === 'string')
}

function searchSource(v: unknown): v is WebSearchSource {
  return objectRecord(v) && nonEmptyString(v.url) && typeof v.title === 'string' &&
    (v.snippet == null || typeof v.snippet === 'string') &&
    (v.index == null || (typeof v.index === 'number' && Number.isSafeInteger(v.index) && v.index > 0)) &&
    (v.was_read == null || typeof v.was_read === 'boolean')
}

function artifact(v: unknown): v is { id: string; type: string; title: string } {
  return objectRecord(v) && nonEmptyString(v.id) && typeof v.type === 'string' && typeof v.title === 'string'
}

function sanitizePhaseLatencies(raw: unknown): Record<string, number> | undefined {
  if (!objectRecord(raw)) return undefined
  const entries = Object.entries(raw).filter((entry): entry is [string, number] =>
    optionalNumber(entry[1]) !== undefined)
  return entries.length ? Object.fromEntries(entries) : undefined
}

export function isStreamEndSuccess(
  msg: WSMessage
): msg is StreamEndSuccessMessage {
  return (
    msg.type === 'stream_end' &&
    msg.outcome === 'success' &&
    nonEmptyString((msg as StreamEndSuccessMessage).message_id) &&
    nonEmptyString((msg as StreamEndSuccessMessage).conversation_id)
  )
}

export function isStreamEndFailure(
  msg: WSMessage
): msg is StreamEndFailureMessage {
  return msg.type === 'stream_end' && !isStreamEndSuccess(msg)
}

/**
 * Decodes and validates a raw WebSocket JSON frame into a typed ``WSMessage``.
 * Returns ``null`` for malformed JSON, unknown event types, or frames missing
 * mandatory fields. Never allows a ``stream_end`` without valid ``message_id``
 * to be treated as success (normalizes it into ``StreamEndFailureMessage`` so
 * the UI always unlocks cleanly without creating an ID-less message bubble).
 */
export function decodeChatFrame(raw: string): WSMessage | null {
  if (typeof raw !== 'string' || !raw.trim()) return null

  let parsed: unknown
  try {
    parsed = JSON.parse(raw)
  } catch {
    return null
  }

  if (!objectRecord(parsed)) return null
  const obj = parsed
  if (!nonEmptyString(obj.type)) return null
  const type = obj.type
  if (!KNOWN_TYPES.has(type)) return null

  switch (type) {
    case 'ready':
    case 'ping':
    case 'pong':
      return { type }

    case 'request_ack':
      if (!nonEmptyString(obj.conversation_id) || !nonEmptyString(obj.user_message_id)) return null
      return {
        type: 'request_ack',
        request_id: optionalString(obj.request_id) ?? null,
        conversation_id: obj.conversation_id,
        user_message_id: obj.user_message_id,
        turn_id: optionalString(obj.turn_id) ?? null,
        project_id: typeof obj.project_id === 'string' ? obj.project_id : null,
        status: optionalString(obj.status),
      }

    case 'tool_executing':
      if (!nonEmptyString(obj.family)) return null
      return {
        type: 'tool_executing',
        family: obj.family,
        action: optionalString(obj.action),
        turn_id: optionalString(obj.turn_id) ?? null,
        conversation_id: optionalString(obj.conversation_id) ?? null,
      }

    case 'tool_executed':
      if (!nonEmptyString(obj.family)) return null
      return {
        type: 'tool_executed',
        family: obj.family,
        provider: optionalString(obj.provider),
        cached: optionalBoolean(obj.cached),
        fallback: optionalBoolean(obj.fallback),
        source_count: optionalNumber(obj.source_count),
        turn_id: optionalString(obj.turn_id) ?? null,
        conversation_id: optionalString(obj.conversation_id) ?? null,
      }

    case 'tool_failed':
      if (!nonEmptyString(obj.family)) return null
      return {
        type: 'tool_failed',
        family: obj.family,
        error: typeof obj.error === 'string' ? obj.error : 'tool_error',
        turn_id: optionalString(obj.turn_id) ?? null,
        conversation_id: optionalString(obj.conversation_id) ?? null,
      }

    case 'conversation_created':
      if (!nonEmptyString(obj.conversation_id)) return null
      return {
        type: 'conversation_created',
        conversation_id: obj.conversation_id,
        title: typeof obj.title === 'string' ? obj.title : '',
        project_id: typeof obj.project_id === 'string' ? obj.project_id : null,
        turn_id: optionalString(obj.turn_id) ?? null,
      }

    case 'stream_start':
      if (!nonEmptyString(obj.conversation_id)) return null
      return {
        type: 'stream_start',
        conversation_id: obj.conversation_id,
        turn_id: optionalString(obj.turn_id) ?? null,
        from_cache: typeof obj.from_cache === 'boolean' ? obj.from_cache : undefined,
        cache_type: typeof obj.cache_type === 'string' ? obj.cache_type : null,
        cache_similarity: optionalNumber(obj.cache_similarity) ?? null,
      }

    case 'stream_clear':
      return {
        type: 'stream_clear',
        turn_id: optionalString(obj.turn_id) ?? null,
        conversation_id: optionalString(obj.conversation_id) ?? null,
      }

    case 'token':
      if (typeof obj.content !== 'string') return null
      return {
        type: 'token',
        content: obj.content,
        turn_id: optionalString(obj.turn_id) ?? null,
        conversation_id: optionalString(obj.conversation_id) ?? null,
      }

    case 'error':
      if (typeof obj.message !== 'string') return null
      return {
        type: 'error',
        message: sanitizeErrorText(obj.message),
        turn_id: optionalString(obj.turn_id) ?? null,
        conversation_id: optionalString(obj.conversation_id) ?? null,
      }

    case 'stream_end': {
      const rawOutcome = typeof obj.outcome === 'string' ? obj.outcome : undefined
      const rawFinish = typeof obj.finish_reason === 'string' ? obj.finish_reason : undefined
      const hasValidIds = nonEmptyString(obj.message_id) && nonEmptyString(obj.conversation_id)

      const isExplicitFailure =
        rawOutcome === 'error' ||
        rawOutcome === 'empty' ||
        rawOutcome === 'timeout' ||
        rawOutcome === 'cancelled' ||
        rawFinish === 'error' ||
        rawFinish === 'timeout' ||
        rawFinish === 'empty' ||
        rawFinish === 'cancelled'

      if (!isExplicitFailure && hasValidIds && (!rawOutcome || rawOutcome === 'success')) {
        const uiBlocks = objectRecord(obj.ui_blocks) && obj.ui_blocks.v === 1 &&
          Array.isArray(obj.ui_blocks.blocks) && obj.ui_blocks.blocks.every((block) =>
            objectRecord(block) && nonEmptyString(block.id) && nonEmptyString(block.type))
          ? obj.ui_blocks as unknown as StreamEndSuccessMessage['ui_blocks']
          : undefined
        const uiErrors = Array.isArray(obj.ui_errors)
          ? (obj.ui_errors.filter((item) =>
              objectRecord(item) && nonEmptyString(item.code) && typeof item.hint === 'string',
            ) as StreamEndSuccessMessage['ui_errors'])
          : undefined
        return {
          type: 'stream_end',
          outcome: 'success',
          message_id: obj.message_id as string,
          conversation_id: obj.conversation_id as string,
          turn_id: optionalString(obj.turn_id) ?? null,
          finish_reason: rawFinish,
          from_cache: optionalBoolean(obj.from_cache),
          cache_type: optionalString(obj.cache_type),
          cache_similarity: optionalNumber(obj.cache_similarity),
          artifact_id: optionalString(obj.artifact_id),
          artifact_type: optionalString(obj.artifact_type),
          artifact_title: optionalString(obj.artifact_title),
          artifacts: Array.isArray(obj.artifacts) ? obj.artifacts.filter(artifact) : undefined,
          relay_used: optionalBoolean(obj.relay_used),
          relay_model: optionalString(obj.relay_model),
          relay_status: optionalString(obj.relay_status),
          memory_used: Array.isArray(obj.memory_used)
            ? (obj.memory_used.filter((item) => objectRecord(item) && nonEmptyString(item.fact)) as StreamEndSuccessMessage['memory_used'])
            : undefined,
          memory_none_relevant: optionalBoolean(obj.memory_none_relevant),
          turn_status: optionalString(obj.turn_status),
          web_search_used: optionalBoolean(obj.web_search_used),
          web_search_query: optionalString(obj.web_search_query),
          web_search_sources: Array.isArray(obj.web_search_sources) ? obj.web_search_sources.filter(searchSource) : undefined,
          process_steps: Array.isArray(obj.process_steps)
            ? obj.process_steps.filter(processStep).map(sanitizeProcessStep)
            : undefined,
          process_duration_ms: optionalNumber(obj.process_duration_ms),
          source_count: optionalNumber(obj.source_count),
          was_fallback: optionalBoolean(obj.was_fallback),
          final_model_id: optionalString(obj.final_model_id),
          final_model_name: optionalString(obj.final_model_name),
          final_provider_id: optionalString(obj.final_provider_id),
          requested_model: optionalString(obj.requested_model),
          served_by: optionalString(obj.served_by),
          failover_tier: optionalString(obj.failover_tier),
          spliced: optionalBoolean(obj.spliced),
          attempt_count: optionalNumber(obj.attempt_count),
          phase_latencies: sanitizePhaseLatencies(obj.phase_latencies),
          ui_blocks: uiBlocks,
          ui_errors: uiErrors,
          ui_dropped: optionalNumber(obj.ui_dropped),
        }
      }

      const failureOutcome: StreamEndFailureMessage['outcome'] =
        rawOutcome === 'empty' || rawFinish === 'empty'
          ? 'empty'
          : rawOutcome === 'timeout' || rawFinish === 'timeout'
            ? 'timeout'
            : rawOutcome === 'cancelled' || rawFinish === 'cancelled'
              ? 'cancelled'
              : 'error'

      const reason =
        optionalString(obj.reason) ||
        rawFinish ||
        (rawOutcome === 'success' && !hasValidIds ? 'missing_message_id' : failureOutcome)

      return {
        type: 'stream_end',
        outcome: failureOutcome,
        reason,
        finish_reason: rawFinish,
        conversation_id: optionalString(obj.conversation_id) ?? null,
        turn_id: optionalString(obj.turn_id) ?? null,
        message: typeof obj.message === 'string' ? sanitizeErrorText(obj.message) : undefined,
        request_id: optionalString(obj.request_id) ?? null,
        turn_status: optionalString(obj.turn_status) ?? null,
        partial_content: typeof obj.partial_content === 'string' ? obj.partial_content : null,
      }
    }

    case 'proactive_status':
      if (!nonEmptyString(obj.conversation_id) || !nonEmptyString(obj.stage)) return null
      return obj as unknown as WSMessage

    case 'proactive_insight':
      if (!obj.insight || typeof obj.insight !== 'object') return null
      return obj as unknown as WSMessage

    case 'proactive_pending':
      if (!Array.isArray(obj.insights)) return null
      return obj as unknown as WSMessage

    case 'fusion_start':
      if (!stringList(obj.models)) return null
      return obj as unknown as WSMessage

    case 'search_start':
      if (typeof obj.query !== 'string') return null
      return obj as unknown as WSMessage

    case 'process_step_start':
      if (!nonEmptyString(obj.id) || !processStepType(obj.step_type)) return null
      return {
        ...obj,
        title: typeof obj.title === 'string' ? sanitizeStepTitle(obj.title) : obj.title,
        detail: typeof obj.detail === 'string' ? sanitizeStepDetail(obj.detail) : obj.detail,
      } as unknown as WSMessage

    case 'process_step_update':
      if (!nonEmptyString(obj.id) || (obj.sub_steps != null && !stringList(obj.sub_steps))) return null
      return {
        ...obj,
        detail: typeof obj.detail === 'string' ? sanitizeStepDetail(obj.detail) : obj.detail,
      } as unknown as WSMessage

    case 'process_step_end':
      if (!nonEmptyString(obj.id) || (obj.sub_steps != null && !stringList(obj.sub_steps))) return null
      return {
        ...obj,
        detail: typeof obj.detail === 'string' ? sanitizeStepDetail(obj.detail) : obj.detail,
      } as unknown as WSMessage

    case 'ui_progress':
      if (!objectRecord(obj.block) || obj.block.type !== 'progress' || !nonEmptyString(obj.block.id) ||
          typeof obj.block.label !== 'string' || (obj.block.steps != null && !Array.isArray(obj.block.steps))) return null
      return obj as unknown as WSMessage

    default:
      return obj as unknown as WSMessage
  }
}
