import { useState, useRef, useEffect, useMemo } from 'react'
import { ChevronDown, AlertCircle, Check, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { RankBadge } from './RankBadge'
import { useIsMobile } from '../hooks/useIsMobile'
import { BottomSheet } from './ui/BottomSheet'
import type { Model } from '../types'

interface ModelSelectorProps {
  compact?: boolean
  className?: string
}

function formatContext(tokens?: number): string | null {
  if (!tokens || tokens <= 0) return null
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(tokens % 1_000_000 === 0 ? 0 : 1)}M`
  if (tokens >= 1_000) return `${Math.round(tokens / 1_000)}k`
  return `${tokens}`
}

export function ModelSelector({ compact = false, className = '' }: ModelSelectorProps = {}) {
  const { t } = useTranslation()
  const {
    models,
    selectedModelId,
    selectedProviderId,
    selectModel,
    isStreaming,
    modelSortMode,
  } = useStore()

  const [open, setOpen] = useState(false)
  const [providerFilter, setProviderFilter] = useState<string>('all')
  const [showAllModels, setShowAllModels] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()

  const isAuto = selectedModelId === 'auto'

  // Guarda a última seleção manual para restauração instantânea ao desligar Auto
  const lastManualModelIdRef = useRef<string>(
    selectedModelId && selectedModelId !== 'auto' ? selectedModelId : ''
  )
  const lastManualProviderIdRef = useRef<string>(
    selectedProviderId && selectedProviderId !== 'auto' ? selectedProviderId : ''
  )

  useEffect(() => {
    if (selectedModelId && selectedModelId !== 'auto') {
      lastManualModelIdRef.current = selectedModelId
    }
    if (selectedProviderId && selectedProviderId !== 'auto') {
      lastManualProviderIdRef.current = selectedProviderId
    }
  }, [selectedModelId, selectedProviderId])

  useEffect(() => {
    if (!open || isMobile) return
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open, isMobile])

  useEffect(() => {
    if (!open || isMobile) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, isMobile])

  // Lista de provedores únicos disponíveis no catálogo
  const availableProviders = useMemo(() => {
    const set = new Set<string>()
    models.forEach((m) => {
      if (m.provider_id) set.add(m.provider_id)
    })
    return Array.from(set).sort()
  }, [models])

  // Filtragem visual por provedor (sem alterar o modelo selecionado no store)
  const filteredModels = useMemo(() => {
    if (providerFilter === 'all') return models
    return models.filter((m) => m.provider_id === providerFilter)
  }, [models, providerFilter])

  // Ordenação dos modelos
  const sortedModels = useMemo(() => {
    return [...filteredModels].sort((a, b) => {
      if (modelSortMode === 'ranking') {
        const scoreA = a.nexuslocal_score ?? -1
        const scoreB = b.nexuslocal_score ?? -1
        if (scoreA !== scoreB) return scoreB - scoreA
      }
      return a.display_name.localeCompare(b.display_name)
    })
  }, [filteredModels, modelSortMode])

  // Modelos exibidos (com limite inicial de 6 se não expandido)
  const displayedModels = useMemo(() => {
    if (showAllModels || sortedModels.length <= 6) return sortedModels
    return sortedModels.slice(0, 6)
  }, [sortedModels, showAllModels])

  const selectedModel = useMemo(() => {
    if (isAuto) return null
    return models.find((m) => m.id === selectedModelId) || null
  }, [models, isAuto, selectedModelId])

  const handleSelectModel = (m: Model) => {
    selectModel(m.id, m.provider_id)
    lastManualModelIdRef.current = m.id
    lastManualProviderIdRef.current = m.provider_id
    setOpen(false)
  }

  const handleToggleAuto = () => {
    if (isAuto) {
      // Restaura seleção manual anterior
      const fallback =
        models.find((m) => m.id === lastManualModelIdRef.current) ||
        models[0]
      if (fallback) {
        selectModel(fallback.id, fallback.provider_id)
      }
    } else {
      // Ativa Smart Router
      if (selectedModelId && selectedModelId !== 'auto') {
        lastManualModelIdRef.current = selectedModelId
        lastManualProviderIdRef.current = selectedProviderId || ''
      }
      selectModel('auto', 'auto')
    }
  }

  const renderCockpitContent = () => (
    <>
      {/* CAMADA 1: Auto-Roteamento Inteligente (Smart Router) */}
      <div className="cockpit-auto-card">
        <div className="cockpit-auto-info">
          <span className="cockpit-auto-icon">🎯</span>
          <div className="cockpit-auto-texts">
            <span className="cockpit-auto-title">
              {t('chat.smartRouter', { defaultValue: 'Roteamento Inteligente' })}
            </span>
            <span className="cockpit-auto-desc">
              {t('chat.smartRouterSub', {
                defaultValue: 'Seleciona a melhor IA por contexto, cota e velocidade',
              })}
            </span>
          </div>
        </div>
        <button
          type="button"
          className={`nexus-toggle-switch ${isAuto ? 'active' : ''}`}
          onClick={handleToggleAuto}
          aria-label={t('chat.smartRouter', { defaultValue: 'Roteamento Inteligente' })}
          aria-checked={isAuto}
        >
          <span className="nexus-toggle-thumb" />
        </button>
      </div>

      {/* CAMADA 2: Filtro Horizontal de Provedores (Abas em Pílulas) */}
      <div className="cockpit-provider-tabs" role="tablist">
        <button
          type="button"
          className={`provider-tab-pill ${providerFilter === 'all' ? 'active' : ''}`}
          onClick={() => {
            setProviderFilter('all')
            setShowAllModels(false)
          }}
          role="tab"
          aria-selected={providerFilter === 'all'}
        >
          {t('chat.allProviders', { defaultValue: 'Todos' })}
        </button>
        {availableProviders.map((prov) => (
          <button
            key={prov}
            type="button"
            className={`provider-tab-pill ${providerFilter === prov ? 'active' : ''}`}
            onClick={() => {
              setProviderFilter(prov)
              setShowAllModels(false)
            }}
            role="tab"
            aria-selected={providerFilter === prov}
          >
            {prov}
          </button>
        ))}
      </div>

      {/* CAMADA 3: Lista de Modelos Reais do Catálogo */}
      <div className="cockpit-model-list" role="listbox">
        {displayedModels.map((m) => {
          const isSelected = !isAuto && selectedModelId === m.id
          const ctxText = formatContext(m.context_length)
          const isExhausted = m.quota_status === 'exhausted'

          return (
            <button
              key={`${m.provider_id}-${m.id}`}
              type="button"
              role="option"
              aria-selected={isSelected}
              className={`cockpit-model-item ${isSelected ? 'selected' : ''}`}
              onClick={() => handleSelectModel(m)}
              disabled={isExhausted}
            >
              <div className="cockpit-model-main">
                <span className="cockpit-model-name">{m.display_name}</span>
                <div className="cockpit-model-meta">
                  {providerFilter === 'all' && (
                    <span className="cockpit-model-provider">{m.provider_name || m.provider_id}</span>
                  )}
                  {m.nexuslocal_score !== undefined && (
                    <RankBadge score={m.nexuslocal_score} />
                  )}
                  {ctxText && <span className="cockpit-model-ctx">{ctxText}</span>}
                  {isExhausted && (
                    <span className="cockpit-model-exhausted" title={t('chat.quotaExhausted', { defaultValue: 'Cota esgotada' })}>
                      <AlertCircle size={12} color="var(--error)" />
                    </span>
                  )}
                </div>
              </div>
              <div className="cockpit-model-right">
                {isSelected && <Check size={15} color="var(--primary)" strokeWidth={2.5} />}
              </div>
            </button>
          )
        })}

        {sortedModels.length > 6 && !showAllModels && (
          <button
            type="button"
            className="cockpit-more-btn"
            onClick={() => setShowAllModels(true)}
          >
            <span>
              {t('chat.moreModels', { defaultValue: 'Mais modelos' })} ({sortedModels.length - 6})
            </span>
            <ChevronRight size={14} />
          </button>
        )}
      </div>
    </>
  )

  if (models.length === 0 && !isAuto) {
    return (
      <div className={`model-selector ${compact ? 'compact' : ''} ${className}`.trim()} ref={ref}>
        <button className={`model-trigger ${compact ? 'compact' : ''}`} disabled>
          <span className="model-trigger-name" style={{ color: 'var(--muted-soft)' }}>
            {t('chat.noModel', { defaultValue: 'Sem modelo' })}
          </span>
        </button>
      </div>
    )
  }

  return (
    <div className={`model-selector ${compact ? 'compact' : ''} ${className}`.trim()} ref={ref}>
      <button
        type="button"
        className={`model-trigger ${compact ? 'compact' : ''}`}
        onClick={() => setOpen((o) => !o)}
        disabled={isStreaming}
        aria-expanded={open}
        aria-haspopup={isMobile ? 'dialog' : 'listbox'}
      >
        {isStreaming && <span className="pulse-dot" />}
        <span className="model-trigger-name">
          {isAuto
            ? `🎯 ${t('chat.autoRouter', { defaultValue: 'Auto (Roteador)' })}`
            : selectedModel
            ? selectedModel.display_name
            : t('chat.selectModel')}
        </span>
        <ChevronDown size={13} className={`chevron ${open ? 'open' : ''}`} />
      </button>

      {open && !isMobile && (
        <div className="model-cockpit-popover" role="dialog" aria-label={t('chat.selectModel')}>
          {renderCockpitContent()}
        </div>
      )}

      {isMobile && (
        <BottomSheet
          open={open}
          onClose={() => setOpen(false)}
          title={t('chat.selectModel')}
        >
          <div style={{ padding: '8px 12px 24px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {renderCockpitContent()}
          </div>
        </BottomSheet>
      )}
    </div>
  )
}
