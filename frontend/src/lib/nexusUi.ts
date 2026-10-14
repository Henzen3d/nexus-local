/**
 * Parser e validador do contrato nexus-ui/1 espelhado no frontend.
 * Garante que somente envelopes estritamente válidos sejam renderizados,
 * com tolerância e auto-recuperação (auto-healing) para variações de LLMs.
 */

import type {
  CalloutBlock,
  CardBlock,
  ChartBlock,
  ControlsBlock,
  FollowUpBlock,
  MetricBlock,
  MetricItem,
  ProgressBlock,
  SandboxBlock,
  UiBlock,
  UiEnvelope,
} from '../types'

const ID_REGEX = /^[a-z0-9_-]{1,32}$/
const FIELD_ID_REGEX = /^[a-z0-9_]{1,32}$/
const SELECT_VALUE_REGEX = /^[a-zA-Z0-9._-]{1,64}$/
const PLACEHOLDER_REGEX = /\{([a-zA-Z0-9_]+)\}/g

// Espelham backend/ui_blocks/validate.py — mudar lá e aqui juntos (spec, seção 4).
// Plano 12 §0: teto 6 com subtetos por tipo (iframe pesado, gráfico caro, follow_up único).
export const MAX_BLOCKS = 6
const MAX_BLOCKS_PER_TYPE: Record<string, number> = { sandbox: 1, chart: 2, follow_up: 1, options: 1 }
const MAX_RAW_JSON_LENGTH = 16000
const MAX_CONTROL_FIELDS = 4
const MAX_METRIC_ITEMS = 4
const MAX_FOLLOW_UP_ITEMS = 4
const CALLOUT_KINDS = ['info', 'success', 'warning', 'danger'] as const
// Sinônimos que modelos usam; qualquer outra coisa vira `info`.
const CALLOUT_KIND_ALIASES: Record<string, CalloutBlock['kind']> = {
  error: 'danger',
  erro: 'danger',
  alert: 'danger',
  critical: 'danger',
  warn: 'warning',
  aviso: 'warning',
  atencao: 'warning',
  atenção: 'warning',
  caution: 'warning',
  ok: 'success',
  sucesso: 'success',
  done: 'success',
  note: 'info',
  tip: 'info',
  nota: 'info',
  dica: 'info',
}
const MAX_SANDBOX_HTML = 12000
const MAX_SANDBOX_CSS = 4000
const MAX_SANDBOX_JS = 8000

/**
 * Validação rigorosa de URLs de imagens conforme a Seção 6 da spec.
 */
export function isAllowedImageUrl(
  url: string,
  allowedHosts: string[] = [],
  currentHost?: string,
  allowPrivateHttp = false
): boolean {
  if (typeof url !== 'string') return false
  const trimmed = url.trim()
  if (!trimmed || trimmed.length > 2048) return false

  const lower = trimmed.toLowerCase()
  for (const blocked of ['javascript:', 'data:', 'blob:', 'file:']) {
    if (lower.startsWith(blocked)) return false
  }

  // URL relativa do app (ex: /attachments/foto.png)
  if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
    return true
  }

  try {
    const parsed = new URL(trimmed)
    if (parsed.username || parsed.password) return false
    const scheme = parsed.protocol.replace(':', '').toLowerCase()
    const host = parsed.hostname.toLowerCase()

    if (scheme !== 'http' && scheme !== 'https') return false

    // Host da própria página
    if (currentHost && (host === currentHost.toLowerCase() || host === currentHost.split(':')[0].toLowerCase())) {
      return true
    }

    // Host na lista branca
    const hostsSet = new Set(allowedHosts.map((h) => h.trim().toLowerCase()))
    if (hostsSet.has(host)) return true

    // Checagem de host privado (.local, localhost, IPs privados)
    const isPrivate =
      host === 'localhost' ||
      host.endsWith('.local') ||
      /^127\./.test(host) ||
      /^10\./.test(host) ||
      /^192\.168\./.test(host) ||
      /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(host)

    if (isPrivate) {
      return allowPrivateHttp && (scheme === 'http' || scheme === 'https')
    }

    return false
  } catch {
    return false
  }
}

function validateProgress(item: Record<string, unknown>): ProgressBlock | null {
  const label = typeof item.label === 'string' && item.label.trim() ? item.label.trim().slice(0, 80) : 'Progresso'

  let cleanValue: number | undefined
  let cleanMax: number | undefined

  if (item.value !== undefined && item.max !== undefined) {
    const val = Number(item.value)
    const mx = Number(item.max)
    if (!Number.isNaN(val) && !Number.isNaN(mx) && Number.isFinite(val) && Number.isFinite(mx)) {
      if (mx >= 1 && mx <= 1000 && val >= 0 && val <= mx) {
        cleanValue = Math.round(val * 100) / 100
        cleanMax = Math.round(mx * 100) / 100
      }
    }
  }

  const cleanSteps: ProgressBlock['steps'] = []
  if (Array.isArray(item.steps) && item.steps.length > 0) {
    let activeCount = 0
    const seenStepIds = new Set<string>()

    for (let idx = 0; idx < item.steps.slice(0, 12).length; idx++) {
      const s = item.steps[idx]
      if (!s || typeof s !== 'object') continue
      const step = s as Record<string, unknown>

      let stepId = typeof step.id === 'string' && ID_REGEX.test(step.id) ? step.id : `step_${idx + 1}`
      if (seenStepIds.has(stepId)) stepId = `step_${idx + 1}`
      seenStepIds.add(stepId)

      const sLabel = typeof step.label === 'string' ? step.label.trim().slice(0, 80) : `Etapa ${idx + 1}`
      const rawState = String(step.state || 'pending').toLowerCase().trim()
      let sState: 'pending' | 'active' | 'done' | 'error' = 'pending'

      if (['done', 'concluido', 'concluído', 'completed'].includes(rawState)) {
        sState = 'done'
      } else if (['active', 'ativo', 'executando', 'running'].includes(rawState)) {
        sState = 'active'
        activeCount++
      } else if (['error', 'erro', 'failed', 'falha'].includes(rawState)) {
        sState = 'error'
      }

      cleanSteps.push({
        id: stepId,
        label: sLabel,
        state: sState,
      })
    }

    if (activeCount > 1) {
      let lastActive = false
      for (let i = cleanSteps.length - 1; i >= 0; i--) {
        if (cleanSteps[i].state === 'active') {
          if (!lastActive) lastActive = true
          else cleanSteps[i].state = 'done'
        }
      }
    }
  }

  if (cleanValue === undefined && cleanSteps.length === 0) {
    return null
  }

  const out: ProgressBlock = {
    id: (item.id as string) || 'progress_1',
    type: 'progress',
    label,
  }
  if (cleanValue !== undefined) {
    out.value = cleanValue
    out.max = cleanMax
  }
  if (cleanSteps.length > 0) {
    out.steps = cleanSteps
  }
  return out
}

function validateCard(item: Record<string, unknown>): CardBlock | null {
  const title = typeof item.title === 'string' && item.title.trim() ? item.title.trim().slice(0, 80) : 'Informações'

  const out: CardBlock = {
    id: (item.id as string) || 'card_1',
    type: 'card',
    title,
  }

  if (item.body !== undefined && item.body !== null) {
    out.body = String(item.body).slice(0, 400)
  }

  if (Array.isArray(item.facts)) {
    const cleanFacts = []
    for (const f of item.facts.slice(0, 6)) {
      if (!f || typeof f !== 'object') continue
      const fact = f as Record<string, unknown>
      const label = String(fact.label || '').trim().slice(0, 40)
      const val = String(fact.value || '').trim().slice(0, 40)
      if (label && val) {
        cleanFacts.push({ label, value: val })
      }
    }
    if (cleanFacts.length > 0) {
      out.facts = cleanFacts
    }
  }

  if (item.image && typeof item.image === 'object') {
    const img = item.image as Record<string, unknown>
    if (typeof img.url === 'string' && img.url.trim()) {
      const alt = typeof img.alt === 'string' ? img.alt.slice(0, 120) : title
      out.image = { url: img.url.trim(), alt }
    }
  }

  return out
}

function validateChart(item: Record<string, unknown>): ChartBlock | null {
  const title = typeof item.title === 'string' && item.title.trim() ? item.title.trim().slice(0, 80) : 'Gráfico Comparativo'
  // kind ausente → 'bar'; kind presente mas desconhecido → bloco descartado (como no Python)
  if (item.kind !== undefined && item.kind !== null && typeof item.kind !== 'string') return null
  let kind = (typeof item.kind === 'string' && item.kind.trim() ? item.kind.trim().toLowerCase() : 'bar') as
    | 'bar'
    | 'line'
    | 'compare'
  if (!['bar', 'line', 'compare'].includes(kind)) return null

  const xKey = typeof item.x_key === 'string' && item.x_key.trim() ? item.x_key.trim().slice(0, 40) : 'x'
  if (!Array.isArray(item.series) || item.series.length === 0) return null

  // Normalização de series aninhadas (formato Chart.js / Highcharts gerado por LLMs)
  const firstS = item.series[0] as Record<string, unknown> | undefined
  if (firstS && Array.isArray(firstS.rows)) {
    const cleanSeries: { key: string; label: string }[] = []
    const rowsByX: Record<string, Record<string, string | number>> = {}

    for (let idx = 0; idx < item.series.slice(0, 4).length; idx++) {
      const s = item.series[idx] as Record<string, unknown>
      if (!s || typeof s !== 'object') continue
      const sKey = `series_${idx + 1}`
      const sLabel = String(s.name || s.label || `Série ${idx + 1}`).slice(0, 60)
      cleanSeries.push({ key: sKey, label: sLabel })

      if (Array.isArray(s.rows)) {
        for (const r of s.rows) {
          if (!r || typeof r !== 'object') continue
          const rowObj = r as Record<string, unknown>
          const xVal = rowObj.x ?? rowObj[xKey] ?? rowObj.label
          if (xVal === undefined || xVal === null) continue
          const xStr = String(xVal).slice(0, 40)
          const yNum = Number(rowObj.y ?? 0)
          if (!rowsByX[xStr]) {
            rowsByX[xStr] = { [xKey]: xStr }
          }
          rowsByX[xStr][sKey] = Number.isFinite(yNum) ? yNum : 0
        }
      }
    }

    const cleanRows = Object.values(rowsByX).slice(0, 24)
    if (cleanSeries.length > 1 && kind === 'bar') kind = 'compare'

    return {
      id: (item.id as string) || 'chart_1',
      type: 'chart',
      title,
      kind,
      x_key: xKey,
      series: cleanSeries,
      rows: cleanRows,
    }
  }

  // Formato padrão plano
  const cleanSeries: { key: string; label: string }[] = []
  const seenKeys = new Set<string>()

  for (let idx = 0; idx < item.series.slice(0, 4).length; idx++) {
    const s = item.series[idx] as Record<string, unknown>
    if (!s || typeof s !== 'object') continue
    const sKey = String(s.key || `s_${idx + 1}`).slice(0, 40)
    const sLabel = String(s.label || s.name || sKey).slice(0, 60)
    if (seenKeys.has(sKey)) continue
    seenKeys.add(sKey)
    cleanSeries.push({ key: sKey, label: sLabel })
  }

  if (cleanSeries.length === 0) return null
  if (kind === 'bar' && cleanSeries.length !== 1) return null
  if (kind === 'line' && (cleanSeries.length < 1 || cleanSeries.length > 3)) return null
  if (kind === 'compare' && (cleanSeries.length < 2 || cleanSeries.length > 4)) return null

  if (!Array.isArray(item.rows) || item.rows.length === 0) return null
  const cleanRows: Record<string, string | number>[] = []

  for (const r of item.rows.slice(0, 24)) {
    if (!r || typeof r !== 'object') continue
    const row = r as Record<string, unknown>
    let xVal = row[xKey]
    if (xVal === undefined) {
      for (const k of Object.keys(row)) {
        if (!seenKeys.has(k)) {
          xVal = row[k]
          break
        }
      }
    }
    if (xVal === undefined || xVal === null) continue
    const rowObj: Record<string, string | number> = { [xKey]: String(xVal).slice(0, 40) }
    let hasNum = false

    for (const sKey of seenKeys) {
      const num = Number(row[sKey] ?? 0)
      if (Number.isFinite(num)) {
        rowObj[sKey] = num
        hasNum = true
      } else {
        rowObj[sKey] = 0
      }
    }

    if (hasNum) cleanRows.push(rowObj)
  }

  if (cleanRows.length === 0) return null

  return {
    id: (item.id as string) || 'chart_1',
    type: 'chart',
    title,
    kind,
    x_key: xKey,
    series: cleanSeries,
    rows: cleanRows,
  }
}

function validateControls(item: Record<string, unknown>): ControlsBlock | null {
  const title = typeof item.title === 'string' && item.title.trim() ? item.title.trim().slice(0, 80) : 'Controles'
  const submitLabel =
    typeof item.submit_label === 'string' && item.submit_label.trim() ? item.submit_label.trim().slice(0, 32) : 'Enviar'

  if (!Array.isArray(item.fields) || item.fields.length === 0) return null

  const cleanFields: ControlsBlock['fields'] = []
  const seenIds = new Set<string>()
  const selectFields: string[] = []

  for (let idx = 0; idx < item.fields.slice(0, MAX_CONTROL_FIELDS).length; idx++) {
    const f = item.fields[idx] as Record<string, unknown>
    if (!f || typeof f !== 'object') continue

    let fId = typeof f.id === 'string' && FIELD_ID_REGEX.test(f.id) ? f.id : `f_${idx + 1}`
    if (seenIds.has(fId)) fId = `f_${idx + 1}`
    seenIds.add(fId)

    const fKind = f.kind as 'text' | 'select' | 'number' | 'range'
    const fLabel = String(f.label || fId).slice(0, 60)

    if (fKind === 'text') {
      cleanFields.push({
        id: fId,
        kind: 'text',
        label: fLabel,
        placeholder: typeof f.placeholder === 'string' ? f.placeholder.slice(0, 200) : undefined,
      })
    } else if (fKind === 'number' || fKind === 'range') {
      const mn = Number(f.min ?? 0)
      const mx = Number(f.max ?? 100)
      const step = Number(f.step ?? 1)
      const def = f.default !== undefined ? Number(f.default) : undefined
      cleanFields.push({
        id: fId,
        kind: fKind,
        label: fLabel,
        min: Number.isFinite(mn) ? mn : 0,
        max: Number.isFinite(mx) && mx > mn ? mx : 100,
        step: Number.isFinite(step) && step > 0 ? step : 1,
        default: def !== undefined && Number.isFinite(def) ? def : undefined,
      })
    } else if (fKind === 'select') {
      if (!Array.isArray(f.options) || f.options.length < 2) continue
      const cleanOpts: { value: string; label: string }[] = []
      const seenVals = new Set<string>()

      for (const o of f.options) {
        if (!o || typeof o !== 'object') continue
        const opt = o as Record<string, unknown>
        const val = String(opt.value || '').trim()
        const lbl = String(opt.label || val).trim().slice(0, 40)
        if (!val || seenVals.has(val)) continue
        seenVals.add(val)
        cleanOpts.push({ value: val, label: lbl })
      }

      if (cleanOpts.length >= 2) {
        cleanFields.push({
          id: fId,
          kind: 'select',
          label: fLabel,
          options: cleanOpts,
        })
        selectFields.push(fId)
      }
    }
  }

  if (cleanFields.length === 0) return null

  let cleanComputed: ControlsBlock['computed'] | undefined
  if (item.computed && typeof item.computed === 'object') {
    const comp = item.computed as Record<string, unknown>
    if (typeof comp.template === 'string' && typeof comp.formula === 'string') {
      cleanComputed = {
        template: comp.template.slice(0, 200),
        formula: comp.formula.slice(0, 300),
      }
    }
  }

  // action é obrigatória e só aceita os dois nomes do contrato; sem inventar
  // template ("Enviar dados") — o Python descarta e o TS tem de descartar igual.
  if (!item.action || typeof item.action !== 'object' || Array.isArray(item.action)) return null
  const act = item.action as Record<string, unknown>
  if (act.name !== 'send_message' && act.name !== 'set_model') return null
  const actionName = act.name
  const outAction: ControlsBlock['action'] = {
    name: actionName,
  }

  if (actionName === 'send_message') {
    if (typeof act.template !== 'string' || !act.template.trim()) return null
    const tmpl = act.template
    const placeholders = Array.from(tmpl.matchAll(PLACEHOLDER_REGEX)).map((m) => m[1])
    const validKeys = new Set(seenIds)
    if (cleanComputed) validKeys.add('resultado')
    for (const ph of placeholders) {
      if (!validKeys.has(ph)) return null
    }
    outAction.template = tmpl.slice(0, 500)
  } else if (actionName === 'set_model') {
    const targetField = typeof act.field === 'string' ? act.field : selectFields[0]
    if (!targetField || !selectFields.includes(targetField)) return null
    outAction.field = targetField
  }

  const out: ControlsBlock = {
    id: (item.id as string) || 'controls_1',
    type: 'controls',
    title,
    submit_label: submitLabel,
    fields: cleanFields,
    action: outAction,
  }
  if (cleanComputed) out.computed = cleanComputed
  return out
}

/** Altura inicial do sandbox: aceita número ou string numérica, arredonda, 120..800, senão 300. */
function normalizeSandboxHeight(raw: unknown): number {
  const n = typeof raw === 'number' ? raw : typeof raw === 'string' && raw.trim() ? Number(raw) : NaN
  if (!Number.isFinite(n)) return 300
  const h = Math.round(n)
  return h >= 120 && h <= 800 ? h : 300
}

function validateSandbox(item: Record<string, unknown>): SandboxBlock | null {
  const title = typeof item.title === 'string' && item.title.trim() ? item.title.trim().slice(0, 80) : 'Simulação'
  if (typeof item.html !== 'string' || item.html.length < 1 || item.html.length > MAX_SANDBOX_HTML) return null

  const out: SandboxBlock = {
    id: (item.id as string) || 'sandbox_1',
    type: 'sandbox',
    title,
    html: item.html,
    initial_height: normalizeSandboxHeight(item.initial_height),
    standalone_download: item.standalone_download !== false,
  }

  if (typeof item.css === 'string' && item.css.length <= MAX_SANDBOX_CSS) {
    out.css = item.css
  }
  if (typeof item.js === 'string' && item.js.length <= MAX_SANDBOX_JS) {
    out.js = item.js
  }

  return out
}

/** Texto aparado dentro de [min, max]; qualquer outra coisa → null. */
function cleanText(value: unknown, min: number, max: number): string | null {
  if (value === null || value === undefined || typeof value === 'boolean' || typeof value === 'object') return null
  const text = String(value).trim()
  if (text.length < min) return null
  return text.slice(0, max)
}

function validateMetric(item: Record<string, unknown>): MetricBlock | null {
  if (!Array.isArray(item.items)) return null
  const cleanItems: MetricItem[] = []
  for (const raw of item.items) {
    if (cleanItems.length >= MAX_METRIC_ITEMS) break
    if (!raw || typeof raw !== 'object') continue
    const r = raw as Record<string, unknown>
    const label = cleanText(r.label, 1, 40)
    if (label === null) continue
    let value: number | string | null
    if (typeof r.value === 'boolean') value = null
    else if (typeof r.value === 'number') value = Number.isFinite(r.value) ? r.value : null // NaN não vira texto
    else value = cleanText(r.value, 1, 24)
    if (value === null) continue
    const clean: MetricItem = { label, value }
    const unit = cleanText(r.unit, 1, 8)
    if (unit !== null && typeof value === 'number') clean.unit = unit
    const delta = cleanText(r.delta, 1, 12)
    if (delta !== null) clean.delta = delta
    const trend = String(r.trend || '').trim().toLowerCase()
    if (trend === 'up' || trend === 'down' || trend === 'flat') clean.trend = trend
    const good = String(r.good || '').trim().toLowerCase()
    if (good === 'up' || good === 'down') clean.good = good
    const hint = cleanText(r.hint, 1, 40)
    if (hint !== null) clean.hint = hint
    cleanItems.push(clean)
  }
  if (cleanItems.length === 0) return null
  const out: MetricBlock = { id: (item.id as string) || 'metric_1', type: 'metric', items: cleanItems }
  const title = cleanText(item.title, 1, 80)
  if (title !== null) out.title = title
  return out
}

function normalizeCalloutKind(raw: unknown): CalloutBlock['kind'] {
  const kind = String(raw || 'info').trim().toLowerCase()
  if ((CALLOUT_KINDS as readonly string[]).includes(kind)) return kind as CalloutBlock['kind']
  return CALLOUT_KIND_ALIASES[kind] ?? 'info'
}

function validateCallout(item: Record<string, unknown>): CalloutBlock | null {
  const body = cleanText(item.body, 1, 400)
  if (body === null) return null
  const out: CalloutBlock = {
    id: (item.id as string) || 'callout_1',
    type: 'callout',
    kind: normalizeCalloutKind(item.kind),
    body,
  }
  const title = cleanText(item.title, 1, 60)
  if (title !== null) out.title = title
  return out
}

function validateFollowUp(item: Record<string, unknown>): FollowUpBlock | null {
  if (!Array.isArray(item.items)) return null
  const cleanItems: string[] = []
  const seen = new Set<string>()
  for (let raw of item.items) {
    if (cleanItems.length >= MAX_FOLLOW_UP_ITEMS) break
    if (raw && typeof raw === 'object') {
      const r = raw as Record<string, unknown>
      raw = r.label || r.text
    }
    const text = cleanText(raw, 3, 80)
    if (text === null || seen.has(text.toLowerCase())) continue
    seen.add(text.toLowerCase())
    cleanItems.push(text)
  }
  if (cleanItems.length === 0) return null
  return { id: (item.id as string) || 'follow_up_1', type: 'follow_up', items: cleanItems }
}

/**
 * Bloco sem `type`: inferido pelos campos, na mesma ordem do Python (spec §4).
 * `items` de textos → follow_up; `items` de {label, value} → metric; `kind` de
 * callout com `body` → callout. O card fica por último (title/body são comuns).
 */
function inferType(obj: Record<string, unknown>): string | null {
  if (obj.kind && obj.series) return 'chart'
  if (obj.steps || (obj.value !== undefined && obj.max !== undefined)) return 'progress'
  if (obj.fields) return 'controls'
  if (obj.html) return 'sandbox'
  if (Array.isArray(obj.items) && obj.items.length > 0) {
    if (obj.items.every((x) => typeof x === 'string')) return 'follow_up'
    if (obj.items.every((x) => x && typeof x === 'object' && 'label' in x && 'value' in x)) return 'metric'
  }
  const kind = String(obj.kind || '').trim().toLowerCase()
  if (obj.body !== undefined && ((CALLOUT_KINDS as readonly string[]).includes(kind) || kind in CALLOUT_KIND_ALIASES)) {
    return 'callout'
  }
  if (obj.facts || obj.body || obj.title) return 'card'
  return null
}

/**
 * Validador principal de envelope nexus-ui/1
 */
export function parseUiEnvelope(raw: unknown): UiEnvelope | null {
  if (!raw) return null
  let data: Record<string, unknown>

  if (typeof raw === 'string') {
    if (raw.length > MAX_RAW_JSON_LENGTH) return null
    try {
      data = JSON.parse(raw)
    } catch {
      return null
    }
  } else if (typeof raw === 'object' && raw !== null) {
    data = raw as Record<string, unknown>
  } else {
    return null
  }

  if (!data || typeof data !== 'object' || Array.isArray(data)) return null
  if ('v' in data && data.v !== 1 && data.v !== '1') return null

  // Normalização de bloco único ou ausência de "blocks"
  if (!Array.isArray(data.blocks)) {
    if (data.blocks && typeof data.blocks === 'object') {
      data = { ...data, blocks: [data.blocks] }
    } else if (data.type || inferType(data)) {
      data = { v: 1, blocks: [data] }
    } else {
      return null
    }
  }

  // v ausente → assume 1 (tolerância); v presente e diferente de 1 → outro contrato, rejeita
  if ('v' in data && data.v !== 1 && data.v !== '1') return null
  data.v = 1

  let cleanBlocks: UiBlock[] = []
  const seenIds = new Set<string>()
  const perType: Record<string, number> = {}

  for (let idx = 0; idx < (data.blocks as unknown[]).slice(0, MAX_BLOCKS).length; idx++) {
    const item = (data.blocks as unknown[])[idx]
    if (!item || typeof item !== 'object') continue
    const obj = { ...(item as Record<string, unknown>) }

    let bType = typeof obj.type === 'string' ? obj.type.trim().toLowerCase() : undefined
    if (!bType) {
      // Sem tipo e sem campos reconhecíveis: descarta, como no Python.
      bType = inferType(obj) ?? ''
      obj.type = bType
    }

    // Subteto por tipo (plano 12 §0): o excedente cai, os demais seguem.
    if (bType in MAX_BLOCKS_PER_TYPE && (perType[bType] ?? 0) >= MAX_BLOCKS_PER_TYPE[bType]) continue

    let bId = obj.id as string | undefined
    if (typeof bId !== 'string' || !ID_REGEX.test(bId) || seenIds.has(bId)) {
      bId = `${bType || 'block'}_${idx + 1}`
    }
    obj.id = bId

    let validated: UiBlock | null = null
    if (bType === 'progress') validated = validateProgress(obj)
    else if (bType === 'card') validated = validateCard(obj)
    else if (bType === 'chart') validated = validateChart(obj)
    else if (bType === 'controls') validated = validateControls(obj)
    else if (bType === 'sandbox') validated = validateSandbox(obj)
    else if (bType === 'metric') validated = validateMetric(obj)
    else if (bType === 'callout') validated = validateCallout(obj)
    else if (bType === 'follow_up') validated = validateFollowUp(obj)

    if (validated) {
      seenIds.add(bId)
      perType[bType] = (perType[bType] ?? 0) + 1
      cleanBlocks.push(validated)
    }
  }

  if (cleanBlocks.length === 0) return null

  // `follow_up` é sempre o último bloco (plano 12 §2.3): se veio antes, vai para o fim.
  if (cleanBlocks.some((b) => b.type === 'follow_up') && cleanBlocks[cleanBlocks.length - 1].type !== 'follow_up') {
    cleanBlocks = [...cleanBlocks.filter((b) => b.type !== 'follow_up'), ...cleanBlocks.filter((b) => b.type === 'follow_up')]
  }

  return {
    v: 1,
    blocks: cleanBlocks,
  }
}

/**
 * Remove blocos nexus-ui e chart fences do texto para exibição limpa em Markdown.
 */
/**
 * Remove os fences nexus-ui da prosa para exibição (o envelope já veio do servidor).
 * Mesmas âncoras do extrator Python (backend/ui_blocks/extract.py): a abertura
 * tem de estar no início da linha; menção inline a ```nexus-ui na prosa não é fence.
 */
export function stripUiFences(text: string): string {
  if (!text) return ''
  return text
    .replace(/^[ \t]{0,3}```(?:nexus-ui(?:\/1)?|nexus)[ \t]*\r?\n[\s\S]*?\r?\n[ \t]{0,3}```[ \t]*$/gm, '')
    .replace(/^[ \t]{0,3}```(?:chart|ui)[ \t]*\r?\n\s*\{[\s\S]*?\}\s*\r?\n[ \t]{0,3}```[ \t]*$/gm, '')
    .replace(/^[ \t]{0,3}```(?:nexus-ui(?:\/1)?|nexus)[ \t]*(?:\r?\n[\s\S]*)?$/gm, '')
    .trim()
}

// Plano 12.6: API aditiva; parseUiEnvelope mantém o retorno legado.
export const UI_ERROR_CODES = [
  'unknown_type', 'missing_required', 'type_mismatch', 'limit_exceeded',
  'invalid_action', 'invalid_expression', 'unsafe_url', 'duplicate_id',
  'invalid_json', 'fence_unclosed', 'rejected_envelope',
] as const
export type UiErrorCode = typeof UI_ERROR_CODES[number]
export interface UiError {
  code: UiErrorCode
  block_id: string
  path: string
  message: string
  hint: string
}
const UI_SIGNATURES: Record<string, string> = {
  progress: 'progress: value, max or steps[{label,state}]',
  card: 'card: title, body?, facts?, image?',
  chart: 'chart: kind bar|line|compare, x_key, series[{key,label}], rows[]',
  controls: 'controls: fields[], action{name:send_message|set_model,template?|field?}',
  sandbox: 'sandbox: title, html, css?, js?',
  metric: 'metric: items[{label,value}]',
  callout: 'callout: body, kind info|success|warning|danger',
  follow_up: 'follow_up: items[string]',
}
const UI_REQUIRED: Record<string, string> = {
  chart: 'series', controls: 'fields', sandbox: 'html', metric: 'items', callout: 'body', follow_up: 'items',
}
export function parseUiEnvelopeWithDiagnostics(raw: unknown, imageHosts: string[] = [], allowPrivateHttp = false): { envelope: UiEnvelope | null; errors: UiError[]; dropped: number } {
  const result: { envelope: UiEnvelope | null; errors: UiError[]; dropped: number } = { envelope: null, errors: [], dropped: 0 }
  const error = (code: UiErrorCode, blockId = '', path = '', hint = '') => {
    if (result.errors.length < 4) result.errors.push({ code, block_id: blockId.slice(0, 32), path: path.slice(0, 80), message: `${code}: ${path || 'envelope'}`.slice(0, 160), hint: hint.slice(0, 160) })
  }
  if (typeof raw === 'string') {
    if (raw.length > MAX_RAW_JSON_LENGTH) { error('limit_exceeded'); return result }
    try { raw = JSON.parse(raw) } catch { error('invalid_json'); return result }
  }
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) { error('rejected_envelope'); return result }
  const data = raw as Record<string, unknown>
  let blocks = data.blocks ?? (data.type || inferType(data) ? [data] : [])
  if (blocks && typeof blocks === 'object' && !Array.isArray(blocks)) blocks = [blocks]
  if ('v' in data && data.v !== 1 && data.v !== '1') {
    result.dropped = Array.isArray(blocks) ? blocks.length : 0
    error('rejected_envelope', '', 'v'); return result
  }
  if (!Array.isArray(blocks) || !blocks.length) { error('rejected_envelope', '', 'blocks'); return result }
  result.envelope = parseUiEnvelope(structuredClone(data))
  const counts: Record<string, number> = {}
  blocks.slice(0, MAX_BLOCKS).forEach((rawBlock: unknown, idx: number) => {
    let blockId = String(idx)
    if (!rawBlock || typeof rawBlock !== 'object' || Array.isArray(rawBlock)) {
      result.dropped++; error('type_mismatch', blockId, `blocks[${idx}]`); return
    }
    const block = rawBlock as Record<string, unknown>
    if (typeof block.id === 'string') blockId = block.id
    const kind = String(block.type || inferType(block) || '').trim().toLowerCase()
    const hint = Object.prototype.hasOwnProperty.call(UI_SIGNATURES, kind) ? UI_SIGNATURES[kind] : ''
    let code: UiErrorCode, path: string
    if (!Object.prototype.hasOwnProperty.call(UI_SIGNATURES, kind)) { code = 'unknown_type'; path = 'type' }
    else if ((counts[kind] ?? 0) >= (MAX_BLOCKS_PER_TYPE[kind] ?? MAX_BLOCKS)) { code = 'limit_exceeded'; path = 'blocks' }
    else {
      const clean = parseUiEnvelope({ v: 1, blocks: [structuredClone(block)] })
      if (clean) {
        counts[kind] = (counts[kind] ?? 0) + 1
        const image = block.image as Record<string, unknown> | undefined
        if (image && typeof image.url === 'string' && !isAllowedImageUrl(image.url, imageHosts, undefined, allowPrivateHttp)) error('unsafe_url', blockId, 'image.url', hint)
        return
      }
      const required = UI_REQUIRED[kind]
      const value = block[required]
      const action = block.action as Record<string, unknown> | undefined
      if (required && (value === undefined || value === null || value === '' || (Array.isArray(value) && !value.length))) { code = 'missing_required'; path = required }
      else if (kind === 'controls' && (!action || !['send_message', 'set_model'].includes(String(action.name)))) { code = 'invalid_action'; path = 'action.name' }
      else if (kind === 'controls') { code = 'invalid_action'; path = 'action' }
      else if (kind === 'sandbox' && typeof block.html === 'string' && block.html.length > MAX_SANDBOX_HTML) { code = 'limit_exceeded'; path = 'html' }
      else if (kind === 'chart' && (!block.rows || (Array.isArray(block.rows) && !block.rows.length)) && !(Array.isArray(block.series) && block.series[0] && typeof block.series[0] === 'object' && 'rows' in block.series[0])) { code = 'missing_required'; path = 'rows' }
      else { code = 'type_mismatch'; path = kind === 'chart' && !['bar', 'line', 'compare'].includes(String(block.kind || 'bar').trim().toLowerCase()) ? 'kind' : required || 'value' }
    }
    result.dropped++; error(code, blockId, path, hint)
  })
  if (blocks.length > MAX_BLOCKS) { result.dropped += blocks.length - MAX_BLOCKS; error('limit_exceeded', String(MAX_BLOCKS), 'blocks') }
  return result
}

/** Diagnostic counterpart of extract_ui; never used to render client-side payloads. */
export function diagnoseUiText(text: string, imageHosts: string[] = [], allowPrivateHttp = false) {
  const primary = [...text.matchAll(/^[ \t]{0,3}```(?:nexus-ui(?:\/1)?|nexus)[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]{0,3}```[ \t]*$/gm)]
  const alternate = primary.length ? [] : [...text.matchAll(/^[ \t]{0,3}```(?:chart|ui)[ \t]*\r?\n\s*(\{[\s\S]*?\})\s*\r?\n[ \t]{0,3}```[ \t]*$/gm)]
  const matches = primary.length ? primary : alternate
  if (matches.length) return parseUiEnvelopeWithDiagnostics(matches[matches.length - 1][1].trim(), imageHosts, allowPrivateHttp)
  if (/^[ \t]{0,3}```(?:nexus-ui(?:\/1)?|nexus)[ \t]*(?:\r?\n[\s\S]*)?$/m.test(text)) {
    return { envelope: null, dropped: 1, errors: [{ code: 'fence_unclosed' as const, block_id: '', path: '', message: 'fence_unclosed: envelope', hint: '' }] }
  }
  return { envelope: null, dropped: 0, errors: [] }
}
