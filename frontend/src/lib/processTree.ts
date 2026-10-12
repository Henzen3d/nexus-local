import type { ProcessStep, WebSearchSource } from '../types'

export interface SearchTrace {
  used?: boolean
  query?: string
  sources?: WebSearchSource[]
}

export interface ProcessTreeLabels {
  searching: string
  reading: string
}

function hasSearchStep(steps: ProcessStep[]): boolean {
  return steps.some((step) => step.type === 'search' || step.type === 'navigate')
}

/** Junta passos de pesquisa e raciocínio numa árvore só. Não descarta busca quando há think. */
export function mergeProcessTree(
  steps: ProcessStep[] | undefined,
  search: SearchTrace | undefined,
  labels: ProcessTreeLabels,
): ProcessStep[] {
  const merged = (steps ?? []).map((step) => ({ ...step }))
  if (hasSearchStep(merged)) return merged
  if (!search?.used && !search?.query && !search?.sources?.length) return merged

  const query = (search?.query || '').trim()
  if (query) {
    merged.unshift({
      id: 'web-search',
      type: 'search',
      title: labels.searching,
      detail: query,
      status: 'completed',
    })
  }

  const seen = new Set(
    merged.filter((step) => step.type === 'navigate' && step.detail).map((step) => step.detail),
  )
  for (const [index, source] of (search?.sources ?? []).entries()) {
    if (!source.url || seen.has(source.url)) continue
    seen.add(source.url)
    merged.push({
      id: `source-${index}`,
      type: 'navigate',
      title: source.title || labels.reading,
      detail: source.url,
      status: 'completed',
    })
  }
  return merged
}
