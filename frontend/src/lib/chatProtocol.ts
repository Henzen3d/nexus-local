import type {
  StreamEndFailureMessage,
  StreamEndSuccessMessage,
  WSMessage,
} from '../types'

const KNOWN_TYPES = new Set([
  'ready',
  'ping',
  'pong',
  'conversation_created',
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

function sanitizePhaseLatencies(raw: unknown): Record<string, number> | undefined {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined
  const out: Record<string, number> = {}
  let hasAny = false
  for (const [k, v] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof v === 'number' && Number.isFinite(v)) {
      out[k] = v
      hasAny = true
    }
  }
  return hasAny ? out : undefined
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

  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    return null
  }

  const obj = parsed as Record<string, unknown>
  if (!nonEmptyString(obj.type)) return null
  const type = obj.type
  if (!KNOWN_TYPES.has(type)) return null

  switch (type) {
    case 'ready':
    case 'ping':
    case 'pong':
      return { type }

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
        cache_similarity: typeof obj.cache_similarity === 'number' ? obj.cache_similarity : null,
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
        message: obj.message,
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
        rawFinish === 'empty'

      if (!isExplicitFailure && hasValidIds && (!rawOutcome || rawOutcome === 'success')) {
        const phase_latencies = sanitizePhaseLatencies(obj.phase_latencies)
        return {
          ...(obj as unknown as StreamEndSuccessMessage),
          type: 'stream_end',
          outcome: 'success',
          message_id: obj.message_id as string,
          conversation_id: obj.conversation_id as string,
          turn_id: optionalString(obj.turn_id) ?? null,
          ...(phase_latencies ? { phase_latencies } : {}),
        }
      }

      const failureOutcome: StreamEndFailureMessage['outcome'] =
        rawOutcome === 'empty' || rawFinish === 'empty'
          ? 'empty'
          : rawOutcome === 'timeout' || rawFinish === 'timeout'
            ? 'timeout'
            : rawOutcome === 'cancelled'
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
        message: typeof obj.message === 'string' ? obj.message : undefined,
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

    default:
      return obj as unknown as WSMessage
  }
}
