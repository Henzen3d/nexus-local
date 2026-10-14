/**
 * Fila de insights pendentes no cliente (assistente proativo — F3.5).
 *
 * Invariantes (01-decisao §2.3): no máximo 3 pendentes, nunca mostrar insight
 * vencido, dedupe por id, ordem = mais antigo primeiro (o backend expira o mais
 * antigo quando entra o 4º). Módulo puro (sem store/DOM) para `node:test`.
 */
import type { ProactiveInsight } from '../types'

export const MAX_PENDING = 3
/** Insight pronto há menos de 10 min ⇒ título "Tenho uma novidade" em vez de "Enquanto você esteve fora…" */
export const FRESH_WINDOW_MS = 10 * 60_000

/** Timestamps do backend são UTC sem sufixo (`datetime('now')`). */
export function parseUtc(ts: string | null | undefined): number | null {
  if (!ts) return null
  const normalized = /(Z|[+-]\d{2}:?\d{2})$/.test(ts) ? ts : ts.replace(' ', 'T') + 'Z'
  const ms = Date.parse(normalized)
  return Number.isNaN(ms) ? null : ms
}

export function isExpired(insight: Pick<ProactiveInsight, 'expires_at'>, now: number): boolean {
  const exp = parseUtc(insight.expires_at)
  return exp !== null && exp <= now
}

function readyAt(insight: ProactiveInsight): number {
  return parseUtc(insight.ready_at) ?? parseUtc(insight.created_at) ?? 0
}

export function pruneExpired(list: ProactiveInsight[], now: number): ProactiveInsight[] {
  const kept = list.filter((i) => !isExpired(i, now))
  return kept.length === list.length ? list : kept
}

/**
 * Funde a fila atual com um lote novo (`proactive_pending` do WS ou `GET /pending`):
 * dedupe por id (o lote novo prevalece), descarta vencidos, ordena por `ready_at`
 * e corta em `max` — os mais antigos ficam, espelhando o backend.
 */
export function mergePending(
  current: ProactiveInsight[],
  incoming: ProactiveInsight[],
  now: number,
  max: number = MAX_PENDING,
): ProactiveInsight[] {
  const byId = new Map<string, ProactiveInsight>()
  for (const item of current) if (item && item.id) byId.set(item.id, item)
  for (const item of incoming) if (item && item.id) byId.set(item.id, { ...byId.get(item.id), ...item })
  const merged = Array.from(byId.values()).filter((i) => !isExpired(i, now) && (i.status ?? 'ready') === 'ready')
  merged.sort((a, b) => readyAt(a) - readyAt(b))
  return merged.slice(0, max)
}

/** Ids que entraram agora (para avisar uma única vez). */
export function newIds(before: ProactiveInsight[], after: ProactiveInsight[]): string[] {
  const seen = new Set(before.map((i) => i.id))
  return after.filter((i) => !seen.has(i.id)).map((i) => i.id)
}

export function isFresh(list: ProactiveInsight[], now: number, windowMs: number = FRESH_WINDOW_MS): boolean {
  if (list.length === 0) return false
  const newest = Math.max(...list.map(readyAt))
  return newest > 0 && now - newest < windowMs
}

export type RelativeAge =
  | { key: 'justNow' }
  | { key: 'minutes'; n: number }
  | { key: 'hours'; n: number }
  | { key: 'yesterday' }
  | { key: 'days'; n: number }

/** "há N min / há N h / ontem / há N dias" — o texto final vem do i18n. */
export function relativeAge(ts: string | null | undefined, now: number): RelativeAge {
  const at = parseUtc(ts)
  if (at === null) return { key: 'justNow' }
  const diffMin = Math.max(0, Math.floor((now - at) / 60_000))
  if (diffMin < 1) return { key: 'justNow' }
  if (diffMin < 60) return { key: 'minutes', n: diffMin }
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return { key: 'hours', n: diffH }
  const diffD = Math.floor(diffH / 24)
  if (diffD < 2) return { key: 'yesterday' }
  return { key: 'days', n: diffD }
}

/** Prefixos §3.4 — espelham `backend/proactive/delivery.py` (texto das bolhas sem recarregar). */
const LIVE_PREFIX: Record<string, (topic: string) => string> = {
  'pt-BR': (t) => `Fiquei curioso com **${t}** e fui pesquisar: `,
  'en-US': (t) => `I got curious about **${t}** and looked it up: `,
  'es-ES': (t) => `Me dio curiosidad **${t}** y fui a investigar: `,
}
const RETURN_PREFIX: Record<string, (topic: string) => string> = {
  'pt-BR': (t) => `Enquanto você estava fora, pesquisei sobre **${t}**: `,
  'en-US': (t) => `While you were away, I looked into **${t}**: `,
  'es-ES': (t) => `Mientras no estabas, investigué sobre **${t}**: `,
}

function pickLang(language: string | null | undefined): 'pt-BR' | 'en-US' | 'es-ES' {
  const lang = (language || 'pt-BR').toLowerCase()
  if (lang.startsWith('en')) return 'en-US'
  if (lang.startsWith('es')) return 'es-ES'
  return 'pt-BR'
}

/** Conteúdo da bolha a partir do evento `proactive_insight` (sem buscar a mensagem no servidor). */
export function bubbleContent(insight: Pick<ProactiveInsight, 'topic' | 'text' | 'language' | 'channel'>): string {
  const table = insight.channel === 'pending_inline' ? RETURN_PREFIX : LIVE_PREFIX
  const prefix = table[pickLang(insight.language)](insight.topic)
  return prefix + (insight.text || '').trim()
}

/** Preview curto para toast (sem markdown). */
export function toastPreview(text: string, max = 140): string {
  const plain = (text || '').replace(/\*\*/g, '').replace(/\s+/g, ' ').trim()
  return plain.length > max ? plain.slice(0, max - 1).trimEnd() + '…' : plain
}
