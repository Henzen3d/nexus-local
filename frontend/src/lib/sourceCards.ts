import type { WebSearchSource } from '../types'

export function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

export function faviconUrl(url: string): string {
  const host = sourceHost(url)
  return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=64`
}

export function pageCountKey(count: number): 'chat.pagesCount_one' | 'chat.pagesCount_other' {
  return count === 1 ? 'chat.pagesCount_one' : 'chat.pagesCount_other'
}

export function normalizeComparableUrl(raw: string): string {
  try {
    const trimmed = raw.trim()
    const urlObj = new URL(trimmed)
    const host = urlObj.hostname.replace(/^www\./i, '').toLowerCase()
    let path = urlObj.pathname.toLowerCase()
    if (path.length > 1 && path.endsWith('/')) {
      path = path.slice(0, -1)
    }
    return `${host}${path}`
  } catch {
    return raw.trim().replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/$/, '').toLowerCase()
  }
}

/**
 * Helper puro de apresentação para remover apenas seção final reconhecível
 * de fontes/referências duplicadas quando todos os links já constam na lista estruturada (T4.2).
 * Preserva links inéditos, blocos de código e texto substantivo.
 */
export function stripDuplicateTrailingSources(
  content: string,
  sources?: WebSearchSource[] | null,
): string {
  if (!content || !sources || sources.length === 0) {
    return content
  }

  // Se o texto terminar com bloco de código não fechado, não mexe
  const fenceCount = (content.match(/```/g) || []).length
  if (fenceCount % 2 !== 0) {
    return content
  }

  // Regex para cabeçalho terminal reconhecível de fontes/referências
  const headerMatch = content.match(
    /(?:\r?\n){1,3}(?:#{1,4}\s*)?(?:\*{1,2})?(?:Fontes(?:(?:\s+de\s+informação|\s+consultadas|\s+utilizadas|\s+citadas))?|Referências|Fontes\s+e\s+Referências|Sources|References)(?::)?(?:\*{1,2})?:?\s*(?:\r?\n)+([\s\S]*)$/i,
  )
  if (!headerMatch || headerMatch.index === undefined) {
    return content
  }

  const beforeHeader = content.slice(0, headerMatch.index)
  // Se o corte ocorreu dentro de um bloco de código, aborta
  const beforeFences = (beforeHeader.match(/```/g) || []).length
  if (beforeFences % 2 !== 0) {
    return content
  }

  const tailBody = headerMatch[1].trim()
  if (!tailBody) {
    return beforeHeader.trimEnd()
  }

  // Extrai todas as URLs do bloco final
  const urlMatches = tailBody.match(/https?:\/\/[^\s\)\],]+/gi)
  if (!urlMatches || urlMatches.length === 0) {
    return content
  }

  // Conjunto de URLs normalizadas das fontes estruturadas
  const knownUrls = new Set(sources.map((s) => normalizeComparableUrl(s.url)))

  // Todas as URLs da seção final devem pertencer às fontes estruturadas
  const allUrlsKnown = urlMatches.every((u) => knownUrls.has(normalizeComparableUrl(u)))
  if (!allUrlsKnown) {
    return content
  }

  // Valida que cada linha não vazia do bloco é uma entrada de citação/link, e não prosa substantiva
  const lines = tailBody.split(/\r?\n/).map((l) => l.trim()).filter(Boolean)
  const isLineSourceEntry = (line: string): boolean => {
    return (
      /^[-*•]\s+/i.test(line) ||
      /^\d+[\.\)]\s+/i.test(line) ||
      /^\[\d+\]\s*/i.test(line) ||
      /^https?:\/\//i.test(line) ||
      /^\[.+\]\(https?:\/\/.+\)/i.test(line)
    )
  }

  if (!lines.every(isLineSourceEntry)) {
    return content
  }

  return beforeHeader.trimEnd()
}
