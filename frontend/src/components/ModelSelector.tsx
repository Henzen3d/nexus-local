import { useState, useRef, useEffect } from 'react'
import { ChevronDown, AlertCircle, Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
import { useStore } from '../store/useStore'
import { RankBadge } from './RankBadge'
import { useIsMobile } from '../hooks/useIsMobile'
import { BottomSheet } from './ui/BottomSheet'
import type { Model } from '../types'

export function ModelSelector() {
  const { t, i18n: i18nHook } = useTranslation()
  const { models, selectedModelId, selectedProviderId, selectModel, isStreaming, modelSortMode } = useStore()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()

  useEffect(() => {
    if (!open || isMobile) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open, isMobile])

  useEffect(() => {
    if (!open || isMobile) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, isMobile])

  const filteredModels = selectedProviderId
    ? models.filter((m) => m.provider_id === selectedProviderId)
    : models

  const providerModels = [...filteredModels].sort((a, b) => {
    if (modelSortMode === 'ranking') {
      const scoreA = a.nexuslocal_score ?? -1
      const scoreB = b.nexuslocal_score ?? -1
      if (scoreA !== scoreB) return scoreB - scoreA
    }
    return a.display_name.localeCompare(b.display_name)
  })

  const sortedGlobalModels = [...models]
    .filter((m) => m.nexuslocal_score !== undefined && m.nexuslocal_score !== null)
    .sort((a, b) => (b.nexuslocal_score ?? 0) - (a.nexuslocal_score ?? 0))

  const getGlobalRank = (modelId: string) => {
    const idx = sortedGlobalModels.findIndex((m) => m.id === modelId)
    return idx !== -1 ? idx + 1 : null
  }

  const selected = providerModels.find((m) => m.id === selectedModelId)
    ?? models.find((m) => m.id === selectedModelId)

  const handleSelect = (m: Model) => {
    selectModel(m.id, m.provider_id)
    setOpen(false)
  }

  if (providerModels.length === 0) {
    return (
      <div className="model-selector" ref={ref}>
        <button className="model-trigger" disabled>
          <span className="model-trigger-name" style={{ color: 'var(--muted-soft)' }}>
            {t('chat.noModel', { defaultValue: 'Sem modelo' })}
          </span>
        </button>
      </div>
    )
  }

  return (
    <div className="model-selector" ref={ref}>
      <button
        type="button"
        className="model-trigger"
        onClick={() => setOpen((o) => !o)}
        disabled={isStreaming}
        aria-expanded={open}
        aria-haspopup={isMobile ? 'dialog' : 'listbox'}
      >
        {isStreaming && <span className="pulse-dot" />}
        <span className="model-trigger-name">
          {selected ? selected.display_name : t('chat.selectModel')}
        </span>
        <ChevronDown size={13} className={`chevron ${open ? 'open' : ''}`} />
      </button>

      {open && !isMobile && (
        <div className="model-dropdown" role="listbox">
          {providerModels.map((m) => {
            const tooltip = getQuotaTooltip(m, i18nHook.language)
            return (
              <button
                key={m.id}
                type="button"
                role="option"
                aria-selected={m.id === selectedModelId}
                className={`model-option custom-tooltip-trigger tooltip-up ${m.id === selectedModelId ? 'selected' : ''} ${m.quota_status === 'exhausted' ? 'model-option-exhausted' : ''}`}
                data-tooltip={tooltip}
                onClick={() => handleSelect(m)}
              >
                <span className="model-option-name">
                  {m.display_name}
                  {m.quota_status === 'exhausted' && (
                    <span className="custom-tooltip-trigger tooltip-up" data-tooltip={t('chat.rateLimitExhausted')} style={{ display: 'inline-flex', alignItems: 'center' }}>
                      <AlertCircle size={11} style={{ marginLeft: 5, color: 'var(--error)', verticalAlign: 'middle' }} />
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

      <BottomSheet
        open={open && isMobile}
        onClose={() => setOpen(false)}
        title={t('chat.selectModel')}
      >
        <div className="nl-sheet-list">
          {providerModels.map((m) => {
            const isSelected = m.id === selectedModelId
            const meta = getModelMeta(m, t)
            return (
              <button
                key={m.id}
                type="button"
                className={`nl-sheet-option ${isSelected ? 'selected' : ''} ${m.quota_status === 'exhausted' ? 'exhausted' : ''}`}
                onClick={() => handleSelect(m)}
              >
                <div className="nl-sheet-option-body">
                  <div className="nl-sheet-option-row">
                    <span className="nl-sheet-option-name">{m.display_name}</span>
                    {m.quota_status === 'exhausted' && (
                      <AlertCircle size={14} className="nl-sheet-option-warn" />
                    )}
                    {m.nexuslocal_score != null && (
                      <RankBadge
                        score={m.nexuslocal_score}
                        rank={getGlobalRank(m.id)}
                        popularityRank={m.popularity_rank}
                        qualityScore={m.quality_score}
                        internalUsageCount={m.internal_usage_count ?? 0}
                      />
                    )}
                  </div>
                  {meta && <span className="nl-sheet-option-meta">{meta}</span>}
                </div>
                {isSelected && <Check size={18} className="nl-sheet-option-check" strokeWidth={2.5} />}
              </button>
            )
          })}
        </div>
      </BottomSheet>
    </div>
  )
}

function getModelMeta(m: Model, t: (key: string, opts?: Record<string, unknown>) => string) {
  const parts: string[] = []
  parts.push(formatCtx(m.context_length))
  if (m.quota_status === 'exhausted') {
    parts.push(t('chat.rateLimitExhausted'))
  } else if (m.known_rpd) {
    const current = m.current_day_count || 0
    const limit = m.known_rpd
    const pct = limit > 0 ? Math.round((current / limit) * 100) : 0
    parts.push(`${pct}% ${t('chat.usageShort', { defaultValue: 'uso hoje' })}`)
  }
  return parts.join(' · ')
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
