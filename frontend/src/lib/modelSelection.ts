/** Auto só vale se a pessoa ligou o toggle. `auto` gravado sem opt-in é o padrão antigo e deve cair. */
export function effectivePreferredModel(
  storedModelId: string | null | undefined,
  optedIn: boolean,
): string | null {
  if (!storedModelId) return null
  if (storedModelId === 'auto') return optedIn ? 'auto' : null
  return storedModelId
}

export type UiLevel = 'simple' | 'intermediate' | 'advanced'
export type CatalogStatus = 'idle' | 'loading' | 'ready' | 'empty' | 'error'
export type RouteAvailabilityReason = 'ok' | 'loading' | 'empty' | 'all_exhausted' | 'error'

export interface RouteModelLike {
  id: string
  provider_id: string
  quota_status?: string
}

export interface ResolvedModelSelection {
  modelId: string | null
  providerId: string | null
  routeReady: boolean
  reason: RouteAvailabilityReason
}

export function hasEligibleRoute<T extends { id: string; quota_status?: string }>(models: T[]): boolean {
  return models.some((m) => Boolean(m.id) && m.id !== 'auto' && m.quota_status !== 'exhausted')
}

export function pickManualFallback<T extends RouteModelLike>(
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

/**
 * Resolve a rota inicial / após sincronização de catálogo respeitando:
 * - Modo Simples: seleciona 'auto' automaticamente se houver ao menos 1 rota elegível.
 * - Intermediário/Avançado: preserva escolha manual ou opt-in explícito em Auto, caindo
 *   no melhor modelo elegível apenas se necessário.
 * - Catálogo vazio/erro/esgotado: nunca finge rota válida ('modelId: null').
 */
export function resolveInitialModelSelection<T extends RouteModelLike>(params: {
  models: T[]
  catalogStatus: CatalogStatus
  uiLevel: UiLevel
  preferredModelId?: string | null
  preferredProviderId?: string | null
  lastByProvider?: Record<string, string>
  autoOptIn?: boolean
}): ResolvedModelSelection {
  const {
    models,
    catalogStatus,
    uiLevel,
    preferredModelId,
    preferredProviderId,
    lastByProvider = {},
    autoOptIn = false,
  } = params

  if (catalogStatus === 'error') {
    return { modelId: null, providerId: null, routeReady: false, reason: 'error' }
  }
  if (catalogStatus === 'idle' || catalogStatus === 'loading') {
    if (!models.length) {
      return { modelId: null, providerId: null, routeReady: false, reason: 'loading' }
    }
  }

  const usable = models.filter((m) => Boolean(m.id) && m.id !== 'auto')
  if (!usable.length) {
    return { modelId: null, providerId: null, routeReady: false, reason: 'empty' }
  }

  const eligible = usable.filter((m) => m.quota_status !== 'exhausted')
  if (!eligible.length) {
    return { modelId: null, providerId: null, routeReady: false, reason: 'all_exhausted' }
  }

  if (uiLevel === 'simple') {
    return { modelId: 'auto', providerId: 'auto', routeReady: true, reason: 'ok' }
  }

  const preferred = effectivePreferredModel(preferredModelId, autoOptIn)
  if (preferred === 'auto') {
    return { modelId: 'auto', providerId: 'auto', routeReady: true, reason: 'ok' }
  }

  if (preferred) {
    const found = eligible.find((m) => m.id === preferred)
    if (found) {
      return { modelId: found.id, providerId: found.provider_id, routeReady: true, reason: 'ok' }
    }
  }

  if (preferredProviderId && preferredProviderId !== 'auto') {
    const lastId = lastByProvider[preferredProviderId]
    const lastMatch = lastId
      ? eligible.find((m) => m.id === lastId && m.provider_id === preferredProviderId)
      : undefined
    if (lastMatch) {
      return { modelId: lastMatch.id, providerId: lastMatch.provider_id, routeReady: true, reason: 'ok' }
    }
    const provFirst = eligible.find((m) => m.provider_id === preferredProviderId)
    if (provFirst) {
      return { modelId: provFirst.id, providerId: provFirst.provider_id, routeReady: true, reason: 'ok' }
    }
  }

  return { modelId: eligible[0].id, providerId: eligible[0].provider_id, routeReady: true, reason: 'ok' }
}
