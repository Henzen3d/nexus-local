/**
 * Parser e validador do contrato nexus-ui/1 espelhado no frontend.
 * Garante que somente envelopes estritamente válidos sejam renderizados.
 */

import type {
  CardBlock,
  ChartBlock,
  ControlsBlock,
  ProgressBlock,
  SandboxBlock,
  UiBlock,
  UiEnvelope,
} from '../types'

const ID_REGEX = /^[a-z0-9_-]{1,32}$/
const FIELD_ID_REGEX = /^[a-z0-9_]{1,32}$/
const SELECT_VALUE_REGEX = /^[a-zA-Z0-9._-]{1,64}$/
const PLACEHOLDER_REGEX = /\{([a-zA-Z0-9_]+)\}/g

const MAX_BLOCKS = 4

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
  if (typeof item.label !== 'string' || item.label.length < 1 || item.label.length > 80) {
    return null
  }

  const hasValue = 'value' in item
  const hasMax = 'max' in item
  if (hasValue !== hasMax) return null

  let cleanValue: number | undefined
  let cleanMax: number | undefined

  if (hasValue && hasMax) {
    const val = item.value
    const mx = item.max
    if (typeof val !== 'number' || typeof mx !== 'number') return null
    if (Number.isNaN(val) || Number.isNaN(mx) || !Number.isFinite(val) || !Number.isFinite(mx)) return null
    if (mx < 1 || mx > 1000 || val < 0 || val > mx) return null
    cleanValue = val
    cleanMax = mx
  }

  const cleanSteps: ProgressBlock['steps'] = []
  if (Array.isArray(item.steps)) {
    if (item.steps.length > 12) return null
    let activeCount = 0
    const seenStepIds = new Set<string>()

    for (const s of item.steps) {
      if (!s || typeof s !== 'object') return null
      const step = s as Record<string, unknown>
      if (typeof step.id !== 'string' || !ID_REGEX.test(step.id) || seenStepIds.has(step.id)) return null
      if (typeof step.label !== 'string' || step.label.length < 1 || step.label.length > 80) return null
      if (step.state !== 'pending' && step.state !== 'active' && step.state !== 'done' && step.state !== 'error') {
        return null
      }
      seenStepIds.add(step.id)
      if (step.state === 'active') activeCount++
      cleanSteps.push({
        id: step.id,
        label: step.label,
        state: step.state,
      })
    }
    if (activeCount > 1) return null
  }

  if (cleanValue === undefined && (!cleanSteps || cleanSteps.length === 0)) {
    return null
  }

  const out: ProgressBlock = {
    id: item.id as string,
    type: 'progress',
    label: item.label,
  }
  if (cleanValue !== undefined) {
    out.value = cleanValue
    out.max = cleanMax
  }
  if (cleanSteps && cleanSteps.length > 0) {
    out.steps = cleanSteps
  }
  return out
}

function validateCard(item: Record<string, unknown>): CardBlock | null {
  if (typeof item.title !== 'string' || item.title.length < 1 || item.title.length > 80) {
    return null
  }

  const out: CardBlock = {
    id: item.id as string,
    type: 'card',
    title: item.title,
  }

  if (typeof item.body === 'string') {
    if (item.body.length > 400) return null
    out.body = item.body
  }

  if (Array.isArray(item.facts)) {
    if (item.facts.length > 6) return null
    const cleanFacts = []
    for (const f of item.facts) {
      if (!f || typeof f !== 'object') return null
      const fact = f as Record<string, unknown>
      if (typeof fact.label !== 'string' || fact.label.length < 1 || fact.label.length > 40) return null
      if (typeof fact.value !== 'string' || fact.value.length < 1 || fact.value.length > 40) return null
      cleanFacts.push({ label: fact.label, value: fact.value })
    }
    out.facts = cleanFacts
  }

  if (item.image && typeof item.image === 'object') {
    const img = item.image as Record<string, unknown>
    if (
      typeof img.url === 'string' &&
      typeof img.alt === 'string' &&
      img.alt.length >= 1 &&
      img.alt.length <= 120
    ) {
      out.image = { url: img.url.trim(), alt: img.alt }
    }
  }

  return out
}

function validateChart(item: Record<string, unknown>): ChartBlock | null {
  if (typeof item.title !== 'string' || item.title.length < 1 || item.title.length > 80) return null
  if (item.kind !== 'bar' && item.kind !== 'line' && item.kind !== 'compare') return null
  if (typeof item.x_key !== 'string' || item.x_key.length < 1 || item.x_key.length > 40) return null
  if (!Array.isArray(item.series)) return null

  if (item.kind === 'bar' && item.series.length !== 1) return null
  if (item.kind === 'line' && (item.series.length < 1 || item.series.length > 3)) return null
  if (item.kind === 'compare' && (item.series.length < 2 || item.series.length > 4)) return null

  const cleanSeries = []
  const seenSeriesKeys = new Set<string>()
  for (const s of item.series) {
    if (!s || typeof s !== 'object') return null
    const ser = s as Record<string, unknown>
    if (typeof ser.key !== 'string' || ser.key.length < 1 || ser.key.length > 40 || seenSeriesKeys.has(ser.key)) {
      return null
    }
    const label = typeof ser.label === 'string' && ser.label.length <= 60 ? ser.label : ser.key
    seenSeriesKeys.add(ser.key)
    cleanSeries.push({ key: ser.key, label })
  }

  if (!Array.isArray(item.rows) || item.rows.length < 1 || item.rows.length > 24) return null
  const cleanRows = []

  for (const r of item.rows) {
    if (!r || typeof r !== 'object') return null
    const row = r as Record<string, unknown>
    if (!(item.x_key in row)) return null
    const xVal = row[item.x_key]
    if (typeof xVal !== 'string' && typeof xVal !== 'number') return null
    const strX = String(xVal)
    if (strX.length < 1 || strX.length > 40) return null

    const cleanRowObj: Record<string, string | number> = { [item.x_key]: strX }

    for (const sKey of seenSeriesKeys) {
      if (!(sKey in row)) return null
      const numVal = row[sKey]
      if (typeof numVal !== 'number' || Number.isNaN(numVal) || !Number.isFinite(numVal)) return null
      cleanRowObj[sKey] = numVal
    }
    cleanRows.push(cleanRowObj)
  }

  return {
    id: item.id as string,
    type: 'chart',
    title: item.title,
    kind: item.kind,
    x_key: item.x_key,
    series: cleanSeries,
    rows: cleanRows,
  }
}

function validateControls(item: Record<string, unknown>): ControlsBlock | null {
  if (typeof item.title !== 'string' || item.title.length < 1 || item.title.length > 80) return null
  if (typeof item.submit_label !== 'string' || item.submit_label.length < 1 || item.submit_label.length > 32) return null
  if (!Array.isArray(item.fields) || item.fields.length < 1 || item.fields.length > 4) return null

  const cleanFields = []
  const seenFieldIds = new Set<string>()
  const selectFieldIds = new Set<string>()

  for (const f of item.fields) {
    if (!f || typeof f !== 'object') return null
    const field = f as Record<string, unknown>
    if (typeof field.id !== 'string' || !FIELD_ID_REGEX.test(field.id) || seenFieldIds.has(field.id)) return null
    seenFieldIds.add(field.id)
    const label = typeof field.label === 'string' && field.label.length <= 60 ? field.label : field.id

    if (field.kind === 'text') {
      cleanFields.push({
        id: field.id,
        kind: 'text' as const,
        label,
        placeholder: typeof field.placeholder === 'string' ? field.placeholder.slice(0, 200) : undefined,
      })
    } else if (field.kind === 'number' || field.kind === 'range') {
      const mn = field.min
      const mx = field.max
      if (typeof mn !== 'number' || typeof mx !== 'number') return null
      if (Number.isNaN(mn) || Number.isNaN(mx) || !Number.isFinite(mn) || !Number.isFinite(mx)) return null
      if (mn >= mx || mx - mn > 1_000_000) return null
      cleanFields.push({
        id: field.id,
        kind: field.kind as 'number' | 'range',
        label,
        min: mn,
        max: mx,
        step: typeof field.step === 'number' && field.step > 0 ? field.step : 1,
        default: typeof field.default === 'number' && field.default >= mn && field.default <= mx ? field.default : mn,
      })
    } else if (field.kind === 'select') {
      if (!Array.isArray(field.options) || field.options.length < 2 || field.options.length > 8) return null
      const cleanOpts = []
      const seenOpts = new Set<string>()
      for (const o of field.options) {
        if (!o || typeof o !== 'object') return null
        const opt = o as Record<string, unknown>
        if (typeof opt.value !== 'string' || !SELECT_VALUE_REGEX.test(opt.value) || seenOpts.has(opt.value)) return null
        seenOpts.add(opt.value)
        const optLabel = typeof opt.label === 'string' && opt.label.length >= 1 ? opt.label.slice(0, 40) : opt.value
        cleanOpts.push({ value: opt.value, label: optLabel })
      }
      cleanFields.push({
        id: field.id,
        kind: 'select' as const,
        label,
        options: cleanOpts,
      })
      selectFieldIds.add(field.id)
    } else {
      return null
    }
  }

  let cleanComputed: ControlsBlock['computed'] | undefined
  if (item.computed && typeof item.computed === 'object') {
    const comp = item.computed as Record<string, unknown>
    if (
      typeof comp.template === 'string' &&
      comp.template.length <= 200 &&
      typeof comp.formula === 'string' &&
      comp.formula.length <= 300
    ) {
      cleanComputed = { template: comp.template, formula: comp.formula }
    } else {
      return null
    }
  }

  if (!item.action || typeof item.action !== 'object') return null
  const act = item.action as Record<string, unknown>
  if (act.name !== 'send_message' && act.name !== 'set_model') return null

  if (act.name === 'send_message') {
    if (typeof act.template !== 'string' || act.template.length < 1 || act.template.length > 500) return null
    const matches = Array.from(act.template.matchAll(PLACEHOLDER_REGEX)).map((m) => m[1])
    const validKeys = new Set(seenFieldIds)
    if (cleanComputed) validKeys.add('resultado')
    for (const ph of matches) {
      if (!validKeys.has(ph)) return null
    }
  } else if (act.name === 'set_model') {
    if (typeof act.field !== 'string' || !selectFieldIds.has(act.field)) return null
  }

  const out: ControlsBlock = {
    id: item.id as string,
    type: 'controls',
    title: item.title,
    submit_label: item.submit_label,
    fields: cleanFields,
    action: {
      name: act.name as 'send_message' | 'set_model',
      template: typeof act.template === 'string' ? act.template : undefined,
      field: typeof act.field === 'string' ? act.field : undefined,
    },
  }
  if (cleanComputed) out.computed = cleanComputed
  return out
}

function validateSandbox(item: Record<string, unknown>): SandboxBlock | null {
  if (typeof item.title !== 'string' || item.title.length < 1 || item.title.length > 80) return null
  if (typeof item.html !== 'string' || item.html.length < 1 || item.html.length > 20000) return null

  const out: SandboxBlock = {
    id: item.id as string,
    type: 'sandbox',
    title: item.title,
    html: item.html,
    initial_height:
      typeof item.initial_height === 'number' && item.initial_height >= 120 && item.initial_height <= 800
        ? item.initial_height
        : 300,
    standalone_download: item.standalone_download !== false,
  }

  if (typeof item.css === 'string' && item.css.length <= 20000) {
    out.css = item.css
  }
  if (typeof item.js === 'string' && item.js.length <= 30000) {
    out.js = item.js
  }

  return out
}

/**
 * Validador principal de envelope nexus-ui/1
 */
export function parseUiEnvelope(raw: unknown): UiEnvelope | null {
  if (!raw) return null
  let data: Record<string, unknown>

  if (typeof raw === 'string') {
    if (raw.length > 16000) return null
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

  if (data.v !== 1) return null
  if (!Array.isArray(data.blocks) || data.blocks.length === 0) return null

  const cleanBlocks: UiBlock[] = []
  const seenIds = new Set<string>()

  for (const item of data.blocks.slice(0, MAX_BLOCKS)) {
    if (!item || typeof item !== 'object') continue
    const obj = item as Record<string, unknown>
    if (typeof obj.id !== 'string' || !ID_REGEX.test(obj.id) || seenIds.has(obj.id)) continue

    let validated: UiBlock | null = null
    if (obj.type === 'progress') validated = validateProgress(obj)
    else if (obj.type === 'card') validated = validateCard(obj)
    else if (obj.type === 'chart') validated = validateChart(obj)
    else if (obj.type === 'controls') validated = validateControls(obj)
    else if (obj.type === 'sandbox') validated = validateSandbox(obj)

    if (validated) {
      seenIds.add(obj.id)
      cleanBlocks.push(validated)
    }
  }

  if (cleanBlocks.length === 0) return null

  return {
    v: 1,
    blocks: cleanBlocks,
  }
}
