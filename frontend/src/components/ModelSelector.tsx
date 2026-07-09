import { useState, useRef, useEffect } from 'react'
import { ChevronDown, AlertCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
import { useStore } from '../store/useStore'
import { RankBadge } from './RankBadge'
import type { Model } from '../types'

export function ModelSelector() {
  const { t, i18n: i18nHook } = useTranslation()
  const { models, selectedModelId, selectedProviderId, selectModel, isStreaming, modelSortMode } = useStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // Filter models by currently selected provider
  const filteredModels = selectedProviderId
    ? models.filter((m) => m.provider_id === selectedProviderId)
    : models

  // Sort according to modelSortMode (ranking vs alphabetical)
  const providerModels = [...filteredModels].sort((a, b) => {
    if (modelSortMode === 'ranking') {
      const scoreA = a.nexuslocal_score ?? -1
      const scoreB = b.nexuslocal_score ?? -1
      if (scoreA !== scoreB) {
        return scoreB - scoreA
      }
    }
    return a.display_name.localeCompare(b.display_name)
  })

  // Calcula o rank global de cada modelo ativo baseado em seu score do ranking geral
  const sortedGlobalModels = [...models]
    .filter((m) => m.nexuslocal_score !== undefined && m.nexuslocal_score !== null)
    .sort((a, b) => (b.nexuslocal_score ?? 0) - (a.nexuslocal_score ?? 0))

  const getGlobalRank = (modelId: string) => {
    const idx = sortedGlobalModels.findIndex((m) => m.id === modelId)
    return idx !== -1 ? idx + 1 : null
  }

  const selected = providerModels.find((m) => m.id === selectedModelId)
    ?? models.find((m) => m.id === selectedModelId) // fallback: any match

  if (providerModels.length === 0) {
    return (
      <div className="model-selector" ref={ref}>
        <button className="model-trigger" disabled>
          <span className="model-trigger-name" style={{ color: 'var(--muted-soft)' }}>
            {t('chat.noModel')}
          </span>
        </button>
      </div>
    )
  }

  return (
    <div className="model-selector" ref={ref}>
      <button
        className="model-trigger"
        onClick={() => setOpen((o) => !o)}
        disabled={isStreaming}
      >
        {isStreaming && <span className="pulse-dot" />}
        <span className="model-trigger-name">
          {selected ? selected.display_name : t('chat.selectModel')}
        </span>
        <ChevronDown size={13} className={`chevron ${open ? 'open' : ''}`} />
      </button>

      {open && (
        <div className="model-dropdown">
          {providerModels.map((m) => {
            const tooltip = getQuotaTooltip(m, i18nHook.language)
            return (
              <button
                key={m.id}
                className={`model-option ${m.id === selectedModelId ? 'selected' : ''} ${m.quota_status === 'exhausted' ? 'model-option-exhausted' : ''}`}
                title={tooltip}
                onClick={() => {
                  selectModel(m.id, m.provider_id)
                  setOpen(false)
                }}
              >
                <span className="model-option-name">
                  {m.display_name}
                  {m.quota_status === 'exhausted' && (
                    <span title={t('chat.rateLimitExhausted')} style={{ display: 'inline-flex', alignItems: 'center' }}>
                      <AlertCircle
                        size={11}
                        style={{ marginLeft: 5, color: 'var(--error)', verticalAlign: 'middle' }}
                      />
                    </span>
                  )}
                </span>
                <span className="model-option-right">
                  {m.nexuslocal_score != null && (
                    <RankBadge
                      score={m.nexuslocal_score}
                      rank={getGlobalRank(m.id)}
                      popularityRank={m.popularity_rank}
                      qualityScore={m.quality_score}
                      internalUsageCount={m.internal_usage_count ?? 0}
                    />
                  )}
                  <span className="model-option-ctx">{formatCtx(m.context_length)}</span>
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function getQuotaTooltip(m: Model, language: string) {
  if (!m.known_rpd) return undefined
  const limit = m.known_rpd
  const current = m.current_day_count || 0
  const ratio = limit > 0 ? current / limit : 0
  const pct = Math.round(ratio * 100)
  const filledCount = Math.min(10, Math.max(0, Math.round(ratio * 10)))
  const emptyCount = 10 - filledCount
  const bar = '▓'.repeat(filledCount) + '░'.repeat(emptyCount)
  
  const currentStr = current.toLocaleString(language)
  const limitStr = limit.toLocaleString(language)
  
  let tooltip = i18n.t('chat.usageToday', { bar, pct, current: currentStr, limit: limitStr })
  if (m.known_rpm) {
    const currentMin = m.current_minute_count || 0
    tooltip += `\n${i18n.t('chat.rpmLimit', { current: currentMin, limit: m.known_rpm })}`
  }
  return tooltip
}

function formatCtx(n: number) {
  if (n >= 1000000) return `${(n / 1000000).toFixed(0)}M ctx`
  if (n >= 1000) return `${(n / 1000).toFixed(0)}K ctx`
  return `${n} ctx`
}
