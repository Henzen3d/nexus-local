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
