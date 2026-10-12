/** Auto só vale se a pessoa ligou o toggle. `auto` gravado sem opt-in é o padrão antigo e deve cair. */
export function effectivePreferredModel(
  storedModelId: string | null | undefined,
  optedIn: boolean,
): string | null {
  if (!storedModelId) return null
  if (storedModelId === 'auto') return optedIn ? 'auto' : null
  return storedModelId
}

export function pickManualFallback<T extends { id: string; provider_id: string; quota_status?: string }>(
  models: T[],
  lastModelId: string,
  lastProviderId: string,
): T | null {
  const usable = models.filter((m) => m.id && m.id !== 'auto')
  if (!usable.length) return null

  const byId = usable.find((m) => m.id === lastModelId && m.quota_status !== 'exhausted')
  if (byId) return byId

  if (lastProviderId && lastProviderId !== 'auto') {
    const byProvider = usable.find(
      (m) => m.provider_id === lastProviderId && m.quota_status !== 'exhausted',
    )
    if (byProvider) return byProvider
  }

  return usable.find((m) => m.quota_status !== 'exhausted') || usable[0]
}
