import type { Message, ProcessStep } from '../types.ts'

export type Translator = (key: string, opts?: { defaultValue?: string }) => string

let _translator: Translator | null = null

export function setSanitizationTranslator(t: Translator) {
  _translator = t
}

function translate(key: string, defaultValue: string): string {
  if (_translator) {
    try {
      return _translator(key, { defaultValue })
    } catch {
      return defaultValue
    }
  }
  return defaultValue
}

/**
 * Expressões regulares para detecção de chaves, tokens e URLs sensíveis.
 */
const SENSITIVE_KEY_PATTERNS = [
  /sk-[a-zA-Z0-9_\-]{8,}/g,
  /Bearer\s+[a-zA-Z0-9_\-.~+/]+=*/gi,
  /(?:api[-_]?key|auth[-_]?token|app_id|secret)=([a-zA-Z0-9_\-]+)/gi,
]

const BILLING_URL_PATTERNS = [
  /https?:\/\/[^\s"'<>]*(?:billing|credits|balance|checkout|topup|account\/billing)[^\s"'<>]*/gi,
]

/**
 * Mapeia códigos e mensagens brutas de erro de provedores para chaves i18n de mensagens limpas.
 */
export function classifyRawError(content: string): string {
  const lower = content.toLowerCase()

  // 1. Quota / Crédito / Faturamento (HTTP 402)
  if (
    lower.includes('insufficient_user_quota') ||
    lower.includes('err_credit_gate') ||
    lower.includes('insufficient_quota') ||
    lower.includes('out_of_credits') ||
    lower.includes('credit_exhausted') ||
    lower.includes('quota_exhausted') ||
    lower.includes('usage limit reached') ||
    lower.includes('402') ||
    lower.includes('billing')
  ) {
    return translate('chat.failoverReason.quota_exhausted', 'Crédito indisponível no provedor')
  }

  // 2. Modelo indisponível (HTTP 400 model_unavailable)
  if (
    lower.includes('model_unavailable') ||
    lower.includes('model_temporarily_unavailable') ||
    lower.includes('model is currently unavailable') ||
    lower.includes('temporarily unavailable')
  ) {
    return translate('chat.failoverReason.model_unavailable', 'Modelo temporariamente indisponível')
  }

  // 3. Rate Limit (HTTP 429)
  if (
    lower.includes('rate_limit') ||
    lower.includes('rate limit') ||
    lower.includes('too_many_requests') ||
    lower.includes('429')
  ) {
    return translate('chat.failoverReason.rate_limit', 'Limite de requisições excedido')
  }

  // 4. Timeout (HTTP 504)
  if (
    lower.includes('timeout') ||
    lower.includes('timed out') ||
    lower.includes('deadline exceeded') ||
    lower.includes('504')
  ) {
    return translate('chat.failoverReason.timeout', 'Tempo limite esgotado')
  }

  // 5. Instabilidade / Upstream (HTTP 502 / 503)
  if (
    lower.includes('service_unavailable') ||
    lower.includes('bad_gateway') ||
    lower.includes('upstream') ||
    lower.includes('502') ||
    lower.includes('503')
  ) {
    return translate('chat.failoverReason.upstream', 'Instabilidade no serviço')
  }

  // 6. Autenticação / Permissão (HTTP 401 / 403)
  if (
    lower.includes('unauthorized') ||
    lower.includes('invalid_api_key') ||
    lower.includes('forbidden') ||
    lower.includes('access_denied') ||
    lower.includes('401') ||
    lower.includes('403')
  ) {
    return translate('chat.failoverReason.auth', 'Falha de autenticação')
  }

  // 7. Requisição incompatível / Schema inválido (HTTP 400 geral)
  if (
    lower.includes('invalid_request') ||
    lower.includes('bad_request') ||
    lower.includes('invalid schema') ||
    lower.includes('unrecognized parameter')
  ) {
    return translate('chat.failoverReason.invalid_request', 'Requisição incompatível')
  }

  return translate('chat.failoverReason.generic_error', 'Falha temporária de comunicação')
}

/**
 * Remove chaves de API, credenciais e URLs de cobrança/faturamento de qualquer texto.
 */
export function stripSensitiveSecrets(text: string): string {
  if (!text) return ''
  let cleaned = text

  // Remove URLs de cobrança/billing
  for (const pattern of BILLING_URL_PATTERNS) {
    cleaned = cleaned.replace(pattern, '[link removido]')
  }

  // Remove tokens e chaves
  for (const pattern of SENSITIVE_KEY_PATTERNS) {
    cleaned = cleaned.replace(pattern, '[redacted]')
  }

  return cleaned
}

/**
 * Sanitiza textos de erro para que nunca exponham JSON bruto, chaves, URLs ou metadados de provedor.
 */
export function sanitizeErrorText(rawError: string): string {
  if (!rawError || typeof rawError !== 'string') return ''

  const trimmed = rawError.trim()

  // Se o erro inteiro for um objeto JSON (ex.: {"error": {"message": ...}})
  if ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))) {
    try {
      const parsed = JSON.parse(trimmed)
      const errObj = parsed && typeof parsed === 'object' ? (parsed.error || parsed) : null
      const innerMessage =
        typeof errObj === 'object' && errObj !== null
          ? (errObj.message || errObj.detail || errObj.code || '')
          : ''
      const inspectTarget = innerMessage ? `${trimmed} ${innerMessage}` : trimmed
      return classifyRawError(inspectTarget)
    } catch {
      return classifyRawError(trimmed)
    }
  }

  // Se contiver JSON embutido (ex.: HTTP 402: {"error": ...} ou similar)
  const jsonMatch = trimmed.match(/(\{[\s\S]*\})/)
  if (jsonMatch) {
    const classified = classifyRawError(trimmed)
    const beforeJson = trimmed.slice(0, jsonMatch.index).trim().replace(/:\s*$/, '')
    if (beforeJson && !/error|http\s+\d+/i.test(beforeJson)) {
      return stripSensitiveSecrets(`${beforeJson} (${classified})`)
    }
    return classified
  }

  // Se for uma string de erro que menciona códigos HTTP ou erros conhecidos
  if (/HTTP\s+(?:400|401|402|403|404|429|500|502|503|504)/i.test(trimmed)) {
    return classifyRawError(trimmed)
  }

  return stripSensitiveSecrets(trimmed)
}

/**
 * Sanitiza o detalhe de um passo de execução ou evento de failover.
 * Exemplo:
 *   "Tentativa anterior falhou (HTTP 402: {"error": {"code": "insufficient_user_quota"}}). Alternando para Nemotron..."
 * vira:
 *   "Tentativa anterior falhou (Crédito indisponível no provedor). Alternando para Nemotron..."
 */
export function sanitizeStepDetail(detail?: string | null): string | undefined {
  if (!detail || typeof detail !== 'string') return undefined

  let sanitized = detail.trim()

  // Procura padrões como "Tentativa anterior falhou (...)"
  sanitized = sanitized.replace(
    /\((?:HTTP\s+\d+:\s*)?(\{[\s\S]*?\})\)/g,
    (_, jsonStr) => `(${classifyRawError(jsonStr)})`
  )

  // Se ainda houver JSON bare
  sanitized = sanitized.replace(
    /HTTP\s+\d+:\s*\{[\s\S]*?\}/g,
    (match) => classifyRawError(match)
  )

  // Remove URLs sensíveis e chaves
  sanitized = stripSensitiveSecrets(sanitized)

  return sanitized
}

/**
 * Sanitiza o título de um passo de execução.
 */
export function sanitizeStepTitle(title: string): string {
  if (!title || typeof title !== 'string') return ''

  // Se o título contiver JSON bruto acidental
  if (title.includes('{') && title.includes('}')) {
    return sanitizeErrorText(title)
  }

  return stripSensitiveSecrets(title)
}

/**
 * Sanitiza um ProcessStep completo para garantir segurança em tela e no histórico persistido.
 */
export function sanitizeProcessStep(step: ProcessStep): ProcessStep {
  return {
    ...step,
    title: sanitizeStepTitle(step.title),
    detail: sanitizeStepDetail(step.detail),
    subSteps: step.subSteps ? step.subSteps.map((s) => stripSensitiveSecrets(s)) : undefined,
  }
}

/**
 * Sanitiza uma lista de ProcessStep.
 */
export function sanitizeProcessSteps(steps?: ProcessStep[] | null): ProcessStep[] | undefined {
  if (!steps || !Array.isArray(steps)) return undefined
  return steps.map(sanitizeProcessStep)
}

/**
 * Sanitiza uma mensagem carregada do histórico ou criada localmente.
 */
export function sanitizeMessage(msg: Message): Message {
  const isErrorRole = msg.role === 'error'
  const out: Message = {
    ...msg,
    content: isErrorRole ? sanitizeErrorText(msg.content) : stripSensitiveSecrets(msg.content),
  }
  if (msg.process_steps !== undefined) {
    out.process_steps = sanitizeProcessSteps(msg.process_steps)
  }
  return out
}
