import { useEffect, useState, useMemo } from 'react'
import {
  Wrench, CloudSun, DollarSign, MapPin, BookOpen, Newspaper, Languages,
  Globe, Sparkles, Terminal, BarChart2, CheckCircle2, AlertTriangle, XCircle,
  RefreshCw, Trash2, Play, ExternalLink, Search, Filter, ShieldCheck,
  Check, Power, Info, Database, Layers, ArrowUpRight, Cpu
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type {
  ToolsStatusResponse,
  ToolFamilyStatus,
  ToolProviderStatus,
  PublicApiItem,
  ToolConfig
} from '../types'

export function ToolsPanel() {
  const { t } = useTranslation()
  const [activeSubTab, setActiveSubTab] = useState<'families' | 'catalog' | 'config'>('families')

  // Status & Families
  const [statusData, setStatusData] = useState<ToolsStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [testingProviderId, setTestingProviderId] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ id: string; success: boolean; data?: any; error?: string; latency?: number } | null>(null)
  const [clearingFamily, setClearingFamily] = useState<string | null>(null)
  const [cacheClearMsg, setCacheClearMsg] = useState<{ family: string; count: number } | null>(null)

  // Public APIs Catalog
  const [catalogApis, setCatalogApis] = useState<PublicApiItem[]>([])
  const [catalogTotal, setCatalogTotal] = useState(0)
  const [catalogLoading, setCatalogLoading] = useState(false)
  const [catalogSearch, setCatalogSearch] = useState('')
  const [catalogRelevance, setCatalogRelevance] = useState<string>('')
  const [syncingApis, setSyncingApis] = useState(false)
  const [syncReport, setSyncReport] = useState<any | null>(null)

  // Tool Config
  const [config, setConfig] = useState<ToolConfig | null>(null)
  const [savingConfig, setSavingConfig] = useState(false)
  const [configSaved, setConfigSaved] = useState(false)

  // Carrega status geral das famílias
  const loadStatus = async () => {
    try {
      const res = await api.getToolsStatus()
      setStatusData(res)
    } catch (err) {
      console.error('[ToolsPanel] Erro ao carregar status:', err)
    } finally {
      setLoading(false)
    }
  }

  // Carrega catálogo de APIs públicas
  const loadCatalog = async () => {
    setCatalogLoading(true)
    try {
      const res = await api.getPublicApis({
        search: catalogSearch || undefined,
        relevance: catalogRelevance || undefined,
        limit: 50,
      })
      setCatalogApis(res.apis)
      setCatalogTotal(res.total)
    } catch (err) {
      console.error('[ToolsPanel] Erro ao carregar catálogo:', err)
    } finally {
      setCatalogLoading(false)
    }
  }

  // Carrega configuração das ferramentas
  const loadConfig = async () => {
    try {
      const res = await api.getToolConfig()
      setConfig(res)
    } catch (err) {
      console.error('[ToolsPanel] Erro ao carregar config:', err)
    }
  }

  useEffect(() => {
    loadStatus()
    loadConfig()
  }, [])

  useEffect(() => {
    if (activeSubTab === 'catalog') {
      loadCatalog()
    }
  }, [activeSubTab, catalogRelevance])

  // Toggle de provedor
  const handleToggleProvider = async (providerId: string, currentEnabled: boolean) => {
    try {
      await api.toggleToolProvider(providerId, !currentEnabled)
      await loadStatus()
    } catch (err) {
      console.error('[ToolsPanel] Erro ao alternar provedor:', err)
    }
  }

  // Teste ao vivo de provedor
  const handleTestProvider = async (providerId: string) => {
    setTestingProviderId(providerId)
    setTestResult(null)
    const t0 = performance.now()
    try {
      const res = await api.testToolProvider(providerId)
      const lat = Math.round(performance.now() - t0)
      setTestResult({
        id: providerId,
        success: res.success,
        data: res.data,
        error: res.error,
        latency: lat,
      })
    } catch (err: any) {
      setTestResult({
        id: providerId,
        success: false,
        error: err.message || 'Falha ao executar teste',
      })
    } finally {
      setTestingProviderId(null)
    }
  }

  // Limpeza de cache por família
  const handleClearCache = async (family: string) => {
    setClearingFamily(family)
    try {
      const res = await api.clearToolCache(family)
      setCacheClearMsg({ family, count: res.cleared_entries })
      setTimeout(() => setCacheClearMsg(null), 3500)
      await loadStatus()
    } catch (err) {
      console.error('[ToolsPanel] Erro ao limpar cache:', err)
    } finally {
      setClearingFamily(null)
    }
  }

  // Sincronização manual com GitHub
  const handleSyncPublicApis = async () => {
    setSyncingApis(true)
    setSyncReport(null)
    try {
      const res = await api.syncPublicApis()
      setSyncReport(res)
      await loadCatalog()
    } catch (err: any) {
      setSyncReport({ success: false, error: err.message })
    } finally {
      setSyncingApis(false)
    }
  }

  // Salvar configuração global
  const handleSaveConfig = async () => {
    if (!config) return
    setSavingConfig(true)
    try {
      await api.updateToolConfig(config)
      setConfigSaved(true)
      setTimeout(() => setConfigSaved(false), 2000)
    } catch (err) {
      console.error('[ToolsPanel] Erro ao salvar config:', err)
    } finally {
      setSavingConfig(false)
    }
  }

  // Mapeamento de ícones por família
  const getFamilyIcon = (fid: string) => {
    switch (fid) {
      case 'weather': return <CloudSun size={18} className="text-amber-500" />
      case 'currency': return <DollarSign size={18} className="text-emerald-500" />
      case 'brasil': return <MapPin size={18} className="text-green-500" />
      case 'knowledge': return <BookOpen size={18} className="text-blue-500" />
      case 'news': return <Newspaper size={18} className="text-purple-500" />
      case 'translation': return <Languages size={18} className="text-cyan-500" />
      case 'geo': return <Globe size={18} className="text-teal-500" />
      case 'fun': return <Sparkles size={18} className="text-pink-500" />
      case 'code_exec': return <Terminal size={18} className="text-indigo-500" />
      case 'diagrams': return <BarChart2 size={18} className="text-orange-500" />
      default: return <Wrench size={18} className="text-primary" />
    }
  }

  return (
    <div className="tools-panel-container">
      {/* Header com Estatísticas Globais */}
      <div className="tools-panel-header">
        <div className="tools-title-area">
          <div className="tools-icon-badge">
            <Wrench size={22} className="text-primary" />
          </div>
          <div>
            <h2 className="tools-title">{t('tools.title', 'Ferramentas & APIs Gratuitas')}</h2>
            <p className="tools-subtitle">
              {t('tools.subtitle', 'Pool de APIs públicas com failover inteligente, cache TTL e auto-descoberta.')}
            </p>
          </div>
        </div>

        {statusData?.global_stats && (
          <div className="tools-stats-grid">
            <div className="stat-card">
              <span className="stat-label">{t('tools.activeProviders', 'Provedores Ativos')}</span>
              <span className="stat-val status-online">
                <span className="status-dot online" /> {statusData.global_stats.active_providers}
              </span>
            </div>
            {statusData.global_stats.exhausted_providers > 0 && (
              <div className="stat-card warning">
                <span className="stat-label">{t('tools.exhaustedProviders', 'Exaustos / 429')}</span>
                <span className="stat-val status-warn">
                  <span className="status-dot warn" /> {statusData.global_stats.exhausted_providers}
                </span>
              </div>
            )}
            <div className="stat-card">
              <span className="stat-label">{t('tools.calls24h', 'Chamadas 24h')}</span>
              <span className="stat-val">{statusData.global_stats.total_calls_24h.toLocaleString()}</span>
            </div>
            <div className="stat-card">
              <span className="stat-label">{t('tools.cacheHitRate', 'Taxa de Cache')}</span>
              <span className="stat-val">{(statusData.global_stats.cache_hit_rate * 100).toFixed(0)}%</span>
            </div>
          </div>
        )}
      </div>

      {/* Navegação Secundária */}
      <div className="tools-subtab-nav">
        <button
          className={`subtab-btn ${activeSubTab === 'families' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('families')}
        >
          <Layers size={14} /> {t('tools.familiesTab', 'Famílias & Provedores')}
        </button>
        <button
          className={`subtab-btn ${activeSubTab === 'catalog' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('catalog')}
        >
          <Database size={14} /> {t('tools.catalogTab', 'Catálogo Public APIs')}
        </button>
        <button
          className={`subtab-btn ${activeSubTab === 'config' ? 'active' : ''}`}
          onClick={() => setActiveSubTab('config')}
        >
          <Cpu size={14} /> {t('tools.configTab', 'Políticas & Quotas')}
        </button>
      </div>

      {/* ABA 1: Famílias & Provedores */}
      {activeSubTab === 'families' && (
        <div className="tools-families-view">
          {loading ? (
            <div className="tools-loading-state">
              <RefreshCw size={24} className="animate-spin text-primary" />
              <span>{t('tools.loading', 'Carregando status das ferramentas...')}</span>
            </div>
          ) : (
            <div className="tools-families-grid">
              {statusData?.families.map((fam) => (
                <div key={fam.id} className="family-card">
                  {/* Card Header */}
                  <div className="family-card-header">
                    <div className="family-header-left">
                      <div className="family-icon-wrap">{getFamilyIcon(fam.id)}</div>
                      <div>
                        <div className="family-name-row">
                          <h3 className="family-name">{fam.display_name}</h3>
                          <span className={`family-badge ${fam.enabled ? 'enabled' : 'disabled'}`}>
                            {fam.enabled ? t('tools.active', 'Ativo') : t('tools.inactive', 'Inativo')}
                          </span>
                        </div>
                        <p className="family-desc">{fam.description}</p>
                      </div>
                    </div>
                    <div className="family-header-actions">
                      <span className="ttl-badge" title="Tempo de vida no cache">
                        TTL: {Math.round(fam.ttl_seconds / 60)}m
                      </span>
                      <button
                        className="clear-cache-btn custom-tooltip-trigger"
                        onClick={() => handleClearCache(fam.id)}
                        disabled={clearingFamily === fam.id}
                        data-tooltip={t('tools.clearCacheTooltip', 'Limpar entradas de cache')}
                      >
                        <Trash2 size={13} />
                        {clearingFamily === fam.id ? '...' : t('tools.clearCache', 'Cache')}
                      </button>
                    </div>
                  </div>

                  {cacheClearMsg?.family === fam.id && (
                    <div className="cache-cleared-notice">
                      <Check size={12} /> {t('tools.cacheCleared', { count: cacheClearMsg.count, defaultValue: `${cacheClearMsg.count} itens limpos do cache.` })}
                    </div>
                  )}

                  {/* Provedores da Família */}
                  <div className="providers-list">
                    {fam.providers.map((prov) => {
                      const isTesting = testingProviderId === prov.id
                      const isCurrentTest = testResult?.id === prov.id

                      return (
                        <div
                          key={prov.id}
                          className={`provider-item ${prov.status === 'exhausted' ? 'is-exhausted' : ''} ${!prov.enabled ? 'is-disabled' : ''}`}
                        >
                          <div className="provider-info-col">
                            <div className="provider-name-row">
                              <span className="priority-pill">#{prov.fallback_order}</span>
                              <span className="provider-name">{prov.display_name}</span>
                              {prov.requires_key && (
                                <span className="key-pill" title={`Requer chave de API (${prov.env_key_name || 'env'})`}>
                                  🔑 Key
                                </span>
                              )}
                              {prov.status === 'exhausted' ? (
                                <span className="status-pill exhausted">
                                  <AlertTriangle size={11} /> 429 Cota
                                </span>
                              ) : prov.enabled ? (
                                <span className="status-pill available">
                                  <CheckCircle2 size={11} /> OK
                                </span>
                              ) : (
                                <span className="status-pill disabled">
                                  <XCircle size={11} /> Desligado
                                </span>
                              )}
                            </div>
                            <div className="provider-url-row">
                              <span className="provider-url">{prov.base_url}</span>
                            </div>
                          </div>

                          <div className="provider-stats-col">
                            <span className="stat-chip" title="Chamadas nas últimas 24h">
                              {prov.total_calls_24h} calls
                            </span>
                            <span className="stat-chip" title="Latência média recente">
                              {prov.avg_latency_ms}ms
                            </span>
                          </div>

                          <div className="provider-actions-col">
                            <button
                              className="prov-action-btn test-btn custom-tooltip-trigger"
                              onClick={() => handleTestProvider(prov.id)}
                              disabled={isTesting}
                              data-tooltip={t('tools.testProvider', 'Testar conexão')}
                            >
                              <Play size={12} className={isTesting ? 'animate-spin' : ''} />
                            </button>
                            <button
                              className={`prov-action-btn toggle-btn ${prov.enabled ? 'active' : ''}`}
                              onClick={() => handleToggleProvider(prov.id, prov.enabled)}
                              title={prov.enabled ? t('tools.disable', 'Desabilitar') : t('tools.enable', 'Habilitar')}
                            >
                              <Power size={13} />
                            </button>
                          </div>

                          {/* Resultado do Teste Inline */}
                          {isCurrentTest && (
                            <div className={`test-result-box ${testResult.success ? 'success' : 'error'}`}>
                              <div className="test-res-header">
                                {testResult.success ? (
                                  <span className="res-tag success">
                                    <CheckCircle2 size={12} /> Teste OK ({testResult.latency}ms)
                                  </span>
                                ) : (
                                  <span className="res-tag error">
                                    <AlertTriangle size={12} /> Falha no Teste
                                  </span>
                                )}
                                <button className="close-test" onClick={() => setTestResult(null)}>
                                  <XCircle size={12} />
                                </button>
                              </div>
                              <pre className="test-res-body">
                                {testResult.success
                                  ? JSON.stringify(testResult.data, null, 2)
                                  : testResult.error}
                              </pre>
                            </div>
                          )}
                        </div>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ABA 2: Catálogo Public APIs */}
      {activeSubTab === 'catalog' && (
        <div className="tools-catalog-view">
          <div className="catalog-toolbar">
            <div className="catalog-search-wrap">
              <Search size={14} className="search-icon" />
              <input
                type="text"
                placeholder={t('tools.searchCatalog', 'Buscar APIs descobertas (nome, descrição)...')}
                value={catalogSearch}
                onChange={(e) => setCatalogSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && loadCatalog()}
                className="catalog-search-input"
              />
            </div>

            <div className="catalog-filters">
              <select
                value={catalogRelevance}
                onChange={(e) => setCatalogRelevance(e.target.value)}
                className="catalog-select"
              >
                <option value="">{t('tools.allRelevance', 'Todas Relevâncias')}</option>
                <option value="high">{t('tools.relevanceHigh', 'Alta Relevância')}</option>
                <option value="medium">{t('tools.relevanceMedium', 'Média Relevância')}</option>
                <option value="low">{t('tools.relevanceLow', 'Baixa Relevância')}</option>
              </select>

              <button
                className="sync-btn"
                onClick={handleSyncPublicApis}
                disabled={syncingApis}
              >
                <RefreshCw size={13} className={syncingApis ? 'animate-spin' : ''} />
                {syncingApis ? t('tools.syncing', 'Sincronizando...') : t('tools.syncGithub', 'Sincronizar com GitHub')}
              </button>
            </div>
          </div>

          {syncReport && (
            <div className={`sync-report-notice ${syncReport.success ? 'success' : 'error'}`}>
              {syncReport.success ? (
                <>
                  <Check size={14} />
                  <span>
                    Sincronização concluída! {syncReport.total_apis || 0} APIs analisadas ({syncReport.high_relevance || 0} de alta relevância).
                  </span>
                </>
              ) : (
                <>
                  <AlertTriangle size={14} />
                  <span>Erro ao sincronizar: {syncReport.error}</span>
                </>
              )}
            </div>
          )}

          <div className="catalog-table-container">
            {catalogLoading ? (
              <div className="tools-loading-state">
                <RefreshCw size={24} className="animate-spin text-primary" />
                <span>Carregando APIs descobertas...</span>
              </div>
            ) : catalogApis.length === 0 ? (
              <div className="catalog-empty-state">
                <Database size={32} className="text-muted" />
                <p>Nenhuma API encontrada com os filtros atuais.</p>
                <button className="sync-btn" onClick={handleSyncPublicApis} disabled={syncingApis}>
                  Sincronizar repositório public-apis
                </button>
              </div>
            ) : (
              <table className="catalog-table">
                <thead>
                  <tr>
                    <th>API</th>
                    <th>Categoria</th>
                    <th>Autenticação</th>
                    <th>Relevância</th>
                    <th>Status</th>
                    <th>Link</th>
                  </tr>
                </thead>
                <tbody>
                  {catalogApis.map((apiItem) => (
                    <tr key={apiItem.id}>
                      <td className="api-name-cell">
                        <strong>{apiItem.api_name}</strong>
                        <p className="api-desc">{apiItem.description}</p>
                      </td>
                      <td>
                        <span className="cat-chip">{apiItem.category || 'Geral'}</span>
                      </td>
                      <td>
                        <span className="auth-chip">{apiItem.auth ? apiItem.auth : 'Sem Chave'}</span>
                      </td>
                      <td>
                        <span className={`relevance-badge ${apiItem.relevance}`}>
                          {apiItem.relevance.toUpperCase()}
                        </span>
                      </td>
                      <td>
                        {apiItem.integrated ? (
                          <span className="integrated-badge">
                            <CheckCircle2 size={12} /> Integrado
                          </span>
                        ) : (
                          <span className="candidate-badge">Descoberto</span>
                        )}
                      </td>
                      <td>
                        <a
                          href={apiItem.url}
                          target="_blank"
                          rel="noreferrer"
                          className="api-ext-link"
                          title="Abrir documentação"
                        >
                          <ArrowUpRight size={14} />
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="catalog-footer">
            <span>Total descobertas: {catalogTotal}</span>
          </div>
        </div>
      )}

      {/* ABA 3: Políticas & Quotas */}
      {activeSubTab === 'config' && config && (
        <div className="tools-config-view">
          <div className="config-card">
            <h3 className="config-title">Políticas de Execução & Rate Limiting</h3>
            <p className="config-desc">
              Parâmetros operacionais para balancear a cota gratuita e proteção contra sobrecarga.
            </p>

            <div className="config-form">
              <label className="config-row">
                <div className="config-info">
                  <span className="config-label">Módulo Global de Ferramentas</span>
                  <span className="config-hint">Habilita ou suspende totalmente o sistema de ferramentas externas (Kill-switch).</span>
                </div>
                <input
                  type="checkbox"
                  checked={config.global_enabled}
                  onChange={(e) => setConfig({ ...config, global_enabled: e.target.checked })}
                  className="config-checkbox"
                />
              </label>

              <label className="config-row">
                <div className="config-info">
                  <span className="config-label">Detecção Automática de Intenção no Chat</span>
                  <span className="config-hint">Executa automaticamente consultas de clima, moedas e conhecimento com base no prompt.</span>
                </div>
                <input
                  type="checkbox"
                  checked={config.auto_detection}
                  onChange={(e) => setConfig({ ...config, auto_detection: e.target.checked })}
                  className="config-checkbox"
                />
              </label>

              <label className="config-row">
                <div className="config-info">
                  <span className="config-label">Limite de Chamadas por Minuto / Usuário</span>
                  <span className="config-hint">Janela deslizante de rate limiting por usuário (padrão: 10 exec/min).</span>
                </div>
                <input
                  type="number"
                  min="1"
                  max="60"
                  value={config.rate_limit_per_user}
                  onChange={(e) => setConfig({ ...config, rate_limit_per_user: parseInt(e.target.value) || 10 })}
                  className="config-number-input"
                />
              </label>

              <div className="config-actions">
                <button
                  className="save-config-btn"
                  onClick={handleSaveConfig}
                  disabled={savingConfig}
                >
                  {savingConfig ? (
                    <RefreshCw size={13} className="animate-spin" />
                  ) : configSaved ? (
                    <Check size={13} />
                  ) : (
                    <ShieldCheck size={13} />
                  )}
                  {configSaved ? 'Configurações Salvas!' : 'Salvar Alterações'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
