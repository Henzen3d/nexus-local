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
  const trimmed = raw.trim()
  const match = /^(https?):\/\/([^/?#\s]+)(\/[^?#\s]*)?([?#]\S*)?$/i.exec(trimmed)
  if (!match || /[@\\]/.test(match[2])) return trimmed
  try {
    const url = new URL(trimmed)
    const scheme = match[1].toLowerCase()
    const authority = match[2].toLowerCase()
    const host = url.port === '' ? authority.replace(/:\d+$/, '') : authority
    return `${scheme}://${host}${match[3] ?? '/'}${match[4] ?? ''}`
  } catch {
    return trimmed
  }
}

const SOURCES_HEADING = /^(?:fontes(?:[ \t]+(?:de informação|consultadas|utilizadas|citadas|e referências))?|referências|sources|references|fuentes(?:[ \t]+consultadas)?|referencias)$/iu

function sourceSectionEntry(line: string): string | null {
  if (/^\s/.test(line)) return null
  let heading = line.trimEnd().replace(/^#{1,6}[ \t]+/, '').replace(/[ \t]+#+$/, '')
  const emphasis = /^(\*{1,2}|_{1,2})(.+?)\1(?=[ \t]*:|[ \t]|$)/.exec(heading)
  if (emphasis) {
    heading = emphasis[2] + heading.slice(emphasis[0].length)
  }
  const colon = heading.indexOf(':')
  const label = colon === -1 ? heading : heading.slice(0, colon).trimEnd()
  return SOURCES_HEADING.test(label) ? (colon === -1 ? '' : heading.slice(colon + 1).trim()) : null
}

function sourceEntryUrl(line: string): string | null {
  // A linha deve conter só a citação. Marcadores de lista, por si sós, não autorizam remover a prosa.
  if (/^(?:[ \t]*\t| {4})/.test(line)) return null
  const entry = line.trim()
    .replace(/^(?:[-*+•]|\d+[.)])[ \t]+/, '')
    .replace(/^\[\d+\][ \t]+/, '')
  const link = /^\[(?:[^\]\\]|\\.)+\]\((https?:\/\/[^\s<>]+)\)$/i.exec(entry)
  if (link) return link[1]
  const autolink = /^<(https?:\/\/[^\s<>]+)>$/i.exec(entry)
  if (autolink) return autolink[1]
  return /^https?:\/\/[^\s<>\[\]]+$/i.test(entry) ? entry : null
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

  const lines = content.split('\n')
  let fence: string | null = null
  let header: { line: number; inlineEntry: string } | null = null
  for (const [index, line] of lines.entries()) {
    const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line.trimEnd())
    if (fence) {
      if (marker && marker[1][0] === fence[0] && marker[1].length >= fence.length && !marker[2]) {
        fence = null
      }
      continue
    }
    if (marker) {
      fence = marker[1]
      continue
    }
    const inlineEntry = sourceSectionEntry(line)
    if (inlineEntry !== null) header = { line: index, inlineEntry }
  }
  if (fence || !header) return content

  const entries = [header.inlineEntry, ...lines.slice(header.line + 1)].filter((line) => line.trim())
  if (entries.length === 0) return content

  const knownUrls = new Set(sources.map((source) => normalizeComparableUrl(source.url)))
  const allEntriesAreDuplicates = entries.every((entry) => {
    const url = sourceEntryUrl(entry)
    return url !== null && knownUrls.has(normalizeComparableUrl(url))
  })
  if (!allEntriesAreDuplicates) return content

  const body = lines.slice(0, header.line).join('\n').trimEnd()
  return body.trim() ? body : content
}
