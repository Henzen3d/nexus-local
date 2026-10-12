import { useState, useRef, useEffect, useMemo } from 'react'
import {
  ChevronDown,
  AlertCircle,
  Check,
  ChevronRight,
  ChevronLeft,
  Route,
  Server,
  Cpu,
  Search,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { pickManualFallback } from '../lib/modelSelection'
import { useIsMobile } from '../hooks/useIsMobile'
import { BottomSheet } from './ui/BottomSheet'
import type { Model } from '../types'

interface ModelSelectorProps {
  compact?: boolean
  className?: string
}

type SubmenuType = 'none' | 'providers' | 'models'

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
    loadModels,
    isStreaming,
    modelSortMode,
  } = useStore()

  const [open, setOpen] = useState(false)
  const [activeSubmenu, setActiveSubmenu] = useState<SubmenuType>('none')
  const [providerFilter, setProviderFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState('')

  const ref = useRef<HTMLDivElement>(null)
  const isMobile = useIsMobile()

  const isAuto = selectedModelId === 'auto'
  const wantManualRef = useRef(false)

  useEffect(() => {
    loadModels()
  }, [loadModels])

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

  const handleClose = () => {
    setOpen(false)
    setActiveSubmenu('none')
    setSearchQuery('')
  }

  useEffect(() => {
    if (!open || isMobile) return
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        handleClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open, isMobile])

  useEffect(() => {
    if (!open || isMobile) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activeSubmenu !== 'none') {
          setActiveSubmenu('none')
        } else {
          handleClose()
        }
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, activeSubmenu, isMobile])

  // Lista de provedores únicos disponíveis no catálogo
  const availableProviders = useMemo(() => {
    const set = new Set<string>()
    models.forEach((m) => {
      if (m.provider_id) set.add(m.provider_id)
    })
    return Array.from(set).sort()
  }, [models])

  // Nome formatado do provedor atualmente selecionado no filtro
  const currentProviderLabel = useMemo(() => {
    if (providerFilter === 'all') {
      return t('chat.allProviders', { defaultValue: 'Todos' })
    }
    const modelWithProvider = models.find((m) => m.provider_id === providerFilter)
    return modelWithProvider?.provider_name || providerFilter
  }, [providerFilter, models, t])

  // Filtragem visual por provedor
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

  // 3 principais modelos exibidos no menu inicial
  const top3Models = useMemo(() => {
    if (sortedModels.length <= 3) return sortedModels
    // Se o modelo manual ativo estiver no filtro atual, garante ele entre os 3 (como primeiro)
    if (!isAuto && selectedModelId) {
      const currentSelected = sortedModels.find((m) => m.id === selectedModelId)
      if (currentSelected) {
        const others = sortedModels.filter((m) => m.id !== selectedModelId)
        return [currentSelected, ...others.slice(0, 2)]
      }
    }
    return sortedModels.slice(0, 3)
  }, [sortedModels, isAuto, selectedModelId])

  // Modelos filtrados pela barra de busca do submenu "Mais modelos"
  const searchFilteredModels = useMemo(() => {
    if (!searchQuery.trim()) return sortedModels
    const q = searchQuery.toLowerCase().trim()
    return sortedModels.filter(
      (m) =>
        m.display_name.toLowerCase().includes(q) ||
        m.id.toLowerCase().includes(q) ||
        (m.provider_name && m.provider_name.toLowerCase().includes(q)) ||
        (m.provider_id && m.provider_id.toLowerCase().includes(q))
    )
  }, [sortedModels, searchQuery])

  const selectedModel = useMemo(() => {
    if (isAuto) return null
    return models.find((m) => m.id === selectedModelId) || null
  }, [models, isAuto, selectedModelId])

  const handleSelectModel = (m: Model) => {
    selectModel(m.id, m.provider_id)
    lastManualModelIdRef.current = m.id
    lastManualProviderIdRef.current = m.provider_id
    wantManualRef.current = false
    handleClose()
  }

  const applyManual = () => {
    const fallback = pickManualFallback(
      models,
      lastManualModelIdRef.current,
      lastManualProviderIdRef.current,
    )
    if (!fallback) {
      wantManualRef.current = true
      return false
    }
    wantManualRef.current = false
    lastManualModelIdRef.current = fallback.id
    lastManualProviderIdRef.current = fallback.provider_id
    selectModel(fallback.id, fallback.provider_id)
    return true
  }

  const handleToggleAuto = () => {
    if (isStreaming) return
    if (isAuto) {
      applyManual()
      return
    }
    wantManualRef.current = false
    if (selectedModelId && selectedModelId !== 'auto') {
      lastManualModelIdRef.current = selectedModelId
      lastManualProviderIdRef.current = selectedProviderId || ''
    }
    selectModel('auto', 'auto')
  }

  useEffect(() => {
    if (!wantManualRef.current || !isAuto || models.length === 0) return
    applyManual()
  }, [models, isAuto])

  // Submenu: Seleção de Provedores
  const renderProvidersSubmenu = () => (
    <div className="cockpit-submenu-content">
      {isMobile && (
        <div className="cockpit-submenu-header">
          <button
            type="button"
            className="cockpit-back-btn"
            onClick={() => setActiveSubmenu('none')}
          >
            <ChevronLeft size={16} />
            <span>{t('chat.back', { defaultValue: 'Voltar' })}</span>
          </button>
          <span className="cockpit-submenu-title">
            {t('chat.providerLabel', { defaultValue: 'Provedor' })}
          </span>
        </div>
      )}
      <div className="cockpit-submenu-list" role="listbox">
        <button
          type="button"
          className={`cockpit-submenu-item ${providerFilter === 'all' ? 'selected' : ''}`}
          onClick={() => {
            setProviderFilter('all')
            setActiveSubmenu('none')
          }}
        >
          <span>{t('chat.allProvidersOption', { defaultValue: 'Todos os provedores' })}</span>
          {providerFilter === 'all' && <Check size={14} color="var(--primary)" strokeWidth={2.5} />}
        </button>
        {availableProviders.map((prov) => {
          const isSelected = providerFilter === prov
          const provModel = models.find((m) => m.provider_id === prov)
          const provName = provModel?.provider_name || prov
          return (
            <button
              key={prov}
              type="button"
              className={`cockpit-submenu-item ${isSelected ? 'selected' : ''}`}
              onClick={() => {
                setProviderFilter(prov)
                setActiveSubmenu('none')
              }}
            >
              <span>{provName}</span>
              {isSelected && <Check size={14} color="var(--primary)" strokeWidth={2.5} />}
            </button>
          )
        })}
      </div>
    </div>
  )

  // Submenu: Catálogo Completo de Modelos
  const renderModelsSubmenu = () => (
    <div className="cockpit-submenu-content">
      {isMobile && (
        <div className="cockpit-submenu-header">
          <button
            type="button"
            className="cockpit-back-btn"
            onClick={() => {
              setActiveSubmenu('none')
              setSearchQuery('')
            }}
          >
            <ChevronLeft size={16} />
            <span>{t('chat.back', { defaultValue: 'Voltar' })}</span>
          </button>
          <span className="cockpit-submenu-title">
            {t('chat.moreModels', { defaultValue: 'Mais modelos' })}
          </span>
        </div>
      )}
      <div className="cockpit-search-box">
        <Search size={13} className="cockpit-search-icon" />
        <input
          type="text"
          className="cockpit-search-input"
          placeholder={t('chat.searchModels', { defaultValue: 'Buscar modelos…' })}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          autoFocus={!isMobile}
        />
      </div>
      <div className="cockpit-submenu-list all-models-scroll" role="listbox">
        {searchFilteredModels.map((m) => {
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
                  <span className="cockpit-model-provider">{m.provider_name || m.provider_id}</span>
                  {ctxText && <span className="cockpit-model-ctx">{ctxText}</span>}
                  {isExhausted && (
                    <span
                      className="cockpit-model-exhausted"
                      title={t('chat.quotaExhausted', { defaultValue: 'Cota esgotada' })}
                    >
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
        {searchFilteredModels.length === 0 && (
          <div className="cockpit-no-results">
            <span>{t('conversations.noSearchResults', { defaultValue: 'Nenhum resultado' })}</span>
          </div>
        )}
      </div>
    </div>
  )

  // Menu Principal
  const renderMainMenu = () => (
    <>
      {/* Opção 1: Roteamento Inteligente (Smart Router) sem emoji */}
      <button
        type="button"
        className="cockpit-auto-card"
        onClick={handleToggleAuto}
        disabled={isStreaming}
        role="switch"
        aria-checked={isAuto}
        aria-label={t('chat.smartRouter', { defaultValue: 'Roteamento Inteligente' })}
      >
        <div className="cockpit-auto-info">
          <div className="cockpit-svg-icon-wrap" aria-hidden="true">
            <Route size={15} strokeWidth={2} />
          </div>
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
        <span
          className={`nexus-toggle-switch ${isAuto ? 'active' : ''}`}
          aria-hidden="true"
        >
          <span className="nexus-toggle-thumb" />
        </span>
      </button>

      <div className="cockpit-divider" />

      {/* Opção 2: Seletor de Provedor com Seta Lateral */}
      <button
        type="button"
        className={`cockpit-nav-row ${activeSubmenu === 'providers' ? 'active' : ''}`}
        onClick={() => setActiveSubmenu(activeSubmenu === 'providers' ? 'none' : 'providers')}
        onMouseEnter={() => !isMobile && setActiveSubmenu('providers')}
        aria-expanded={activeSubmenu === 'providers'}
      >
        <div className="cockpit-nav-left">
          <Server size={14} strokeWidth={1.8} className="cockpit-row-icon" />
          <span>{t('chat.providerLabel', { defaultValue: 'Provedor' })}</span>
        </div>
        <div className="cockpit-nav-right">
          <span className="cockpit-nav-value">{currentProviderLabel}</span>
          <ChevronRight size={14} className="cockpit-nav-chevron" />
        </div>
      </button>

      <div className="cockpit-divider" />

      {/* Opção 3: Os 3 Principais Modelos */}
      <div className="cockpit-model-list-compact" role="listbox">
        {top3Models.map((m) => {
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
                  {ctxText && <span className="cockpit-model-ctx">{ctxText}</span>}
                  {isExhausted && (
                    <span
                      className="cockpit-model-exhausted"
                      title={t('chat.quotaExhausted', { defaultValue: 'Cota esgotada' })}
                    >
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
      </div>

      {/* Opção 4: Mais Modelos > */}
      <button
        type="button"
        className={`cockpit-nav-row ${activeSubmenu === 'models' ? 'active' : ''}`}
        onClick={() => setActiveSubmenu(activeSubmenu === 'models' ? 'none' : 'models')}
        onMouseEnter={() => !isMobile && setActiveSubmenu('models')}
        aria-expanded={activeSubmenu === 'models'}
      >
        <div className="cockpit-nav-left">
          <Cpu size={14} strokeWidth={1.8} className="cockpit-row-icon" />
          <span>{t('chat.moreModels', { defaultValue: 'Mais modelos' })}</span>
        </div>
        <div className="cockpit-nav-right">
          {sortedModels.length > 3 && (
            <span className="cockpit-nav-badge">{sortedModels.length}</span>
          )}
          <ChevronRight size={14} className="cockpit-nav-chevron" />
        </div>
      </button>
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
      {/* Botão de Trigger (Pill no rodapé) — Sem emojis */}
      <button
        type="button"
        className={`model-trigger ${compact ? 'compact' : ''}`}
        onClick={() => {
          if (open) {
            handleClose()
          } else {
            setOpen(true)
          }
        }}
        disabled={isStreaming}
        aria-expanded={open}
        aria-haspopup={isMobile ? 'dialog' : 'listbox'}
      >
        {isStreaming && <span className="pulse-dot" />}
        <span className="model-trigger-name">
          {isAuto ? (
            <span className="model-trigger-auto-badge">
              <Route size={12} strokeWidth={2} />
              {t('chat.autoRouter', { defaultValue: 'Roteamento Inteligente' })}
            </span>
          ) : selectedModel ? (
            selectedModel.display_name
          ) : (
            t('chat.selectModel')
          )}
        </span>
        <ChevronDown size={13} className={`chevron ${open ? 'open' : ''}`} />
      </button>

      {/* Desktop Popover com Flyout Cascata */}
      {open && !isMobile && (
        <div
          className="model-cockpit-popover"
          role="dialog"
          aria-label={t('chat.selectModel')}
          onMouseLeave={() => {
            // Mantém submenu ativo se o cursor for para o flyout (controlado no wrapper)
          }}
        >
          {renderMainMenu()}

          {/* Submenu lateral (flyout à esquerda para não estourar a tela) */}
          {activeSubmenu !== 'none' && (
            <div
              className="cockpit-submenu-flyout"
              role="dialog"
              onMouseEnter={() => {}}
            >
              {activeSubmenu === 'providers' && renderProvidersSubmenu()}
              {activeSubmenu === 'models' && renderModelsSubmenu()}
            </div>
          )}
        </div>
      )}

      {/* Mobile BottomSheet (Drill-down nativo com botão Voltar) */}
      {isMobile && (
        <BottomSheet
          open={open}
          onClose={handleClose}
          title={t('chat.selectModel')}
        >
          <div style={{ padding: '8px 12px 24px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {activeSubmenu === 'none' && renderMainMenu()}
            {activeSubmenu === 'providers' && renderProvidersSubmenu()}
            {activeSubmenu === 'models' && renderModelsSubmenu()}
          </div>
        </BottomSheet>
      )}
    </div>
  )
}
