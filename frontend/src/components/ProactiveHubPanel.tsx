import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Sparkles, Search, MessageSquare, ExternalLink, X, Send,
  Sliders, ShieldCheck, Check, ArrowLeft, RefreshCw, Bell, BellRing,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { ProactiveMascot } from './ProactiveMascot'
import { usePushSubscription } from '../hooks/usePushSubscription'
import type { ProactiveInsight, ProactiveCategory, ProactiveSensitivity, ProactivePersonaStyle } from '../types'

type HubTab = 'feed' | 'investigate' | 'preferences'

export const ProactiveHubPanel: React.FC = () => {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<HubTab>('feed')
  const [history, setHistory] = useState<ProactiveInsight[]>([])
  const [loadingHistory, setLoadingHistory] = useState<boolean>(true)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [searchQuery, setSearchQuery] = useState<string>('')

  // Disparador manual
  const [investigatePrompt, setInvestigatePrompt] = useState<string>('')
  const [investigateCategory, setInvestigateCategory] = useState<ProactiveCategory>('news')
  const [investigating, setInvestigating] = useState<boolean>(false)
  const [investigateResult, setInvestigateResult] = useState<{ insight_id: string; conversation_id: string } | null>(null)

  const setView = useStore((s) => s.setView)
  const openPendingInsight = useStore((s) => s.openPendingInsight)
  const expandProactiveInsight = useStore((s) => s.expandProactiveInsight)
  const dismissPendingInsight = useStore((s) => s.dismissPendingInsight)
  const proactiveSettings = useStore((s) => s.proactiveSettings)
  const loadProactiveSettings = useStore((s) => s.loadProactiveSettings)
  const updateProactiveSettings = useStore((s) => s.updateProactiveSettings)
  const loadConversation = useStore((s) => s.loadConversation)
  const showToast = useStore((s) => s.showToast)

  const { isSupported: pushSupported, isSubscribed: pushSubscribed, subscribe: subscribePush, unsubscribe: unsubscribePush, sendTest: sendTestPush, loading: pushLoading } = usePushSubscription()

  const personaStyle: ProactivePersonaStyle = proactiveSettings?.persona_style || 'lumi'

  const fetchHistory = useCallback(async () => {
    setLoadingHistory(true)
    try {
      const res = await api.getProactiveHistory({ limit: 50 })
      setHistory(res.insights || [])
    } catch (e) {
      console.error('[ProactiveHub] erro ao carregar histórico:', e)
    } finally {
      setLoadingHistory(false)
    }
  }, [])

  useEffect(() => {
    void fetchHistory()
    void loadProactiveSettings()
  }, [fetchHistory, loadProactiveSettings])

  const filteredHistory = useMemo(() => {
    return history.filter((item) => {
      if (statusFilter !== 'all' && item.status !== statusFilter) {
        return false
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase()
        const matchTopic = item.topic.toLowerCase().includes(q)
        const matchText = item.text.toLowerCase().includes(q)
        return matchTopic || matchText
      }
      return true
    })
  }, [history, statusFilter, searchQuery])

  const handleManualInvestigate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!investigatePrompt.trim() || investigating) return

    setInvestigating(true)
    setInvestigateResult(null)
    try {
      const res = await api.investigateProactive(investigatePrompt.trim(), investigateCategory)
      setInvestigateResult(res)
      setInvestigatePrompt('')
      showToast(t('proactive.investigateStarted', { defaultValue: 'Investigação iniciada! O assistente avisará quando terminar.' }), 'proactive')
      // Recarrega o histórico após curto atraso
      setTimeout(() => {
        void fetchHistory()
      }, 2000)
    } catch (err) {
      console.error('[ProactiveHub] erro ao disparar investigação:', err)
      showToast(t('proactive.investigateError', { defaultValue: 'Falha ao iniciar investigação proativa.' }), 'error')
    } finally {
      setInvestigating(false)
    }
  }

  const handleUnblockTopic = async (topicHash: string) => {
    try {
      await api.unblockProactiveTopic(topicHash)
      await loadProactiveSettings()
      showToast(t('proactive.topicUnblocked', { defaultValue: 'Tópico desbloqueado.' }), 'success')
    } catch (e) {
      console.error(e)
    }
  }

  const handleToggleSensitivity = async (s: ProactiveSensitivity) => {
    await updateProactiveSettings({ sensitivity: s })
  }

  const handleTogglePersona = async (style: ProactivePersonaStyle) => {
    await updateProactiveSettings({ persona_style: style })
  }

  const handleTogglePush = async () => {
    if (pushSubscribed) {
      await unsubscribePush()
    } else {
      await subscribePush()
    }
  }

  return (
    <div className="proactive-hub-panel">
      {/* Topo do Painel */}
      <header className="proactive-hub-header">
        <div className="hub-header-left">
          <button
            type="button"
            className="hub-back-btn"
            onClick={() => setView('chat')}
            title={t('common.back', { defaultValue: 'Voltar ao Chat' })}
          >
            <ArrowLeft size={18} />
          </button>
          <div className="hub-identity">
            <ProactiveMascot size={42} state="idle" style={personaStyle} />
            <div>
              <h1 className="hub-title">
                {t('proactive.hubTitle', { defaultValue: 'Assistente Proativo' })}
              </h1>
              <p className="hub-subtitle">
                {proactiveSettings?.enabled
                  ? t('proactive.hubStatusActive', { defaultValue: 'Ativo e pesquisando em segundo plano' })
                  : t('proactive.hubStatusInactive', { defaultValue: 'Pausado (você pode reativar nas preferências)' })}
              </p>
            </div>
          </div>
        </div>

        {/* Abas */}
        <div className="hub-tabs">
          <button
            type="button"
            className={`hub-tab-btn ${activeTab === 'feed' ? 'active' : ''}`}
            onClick={() => setActiveTab('feed')}
          >
            <Sparkles size={16} />
            <span>{t('proactive.tabDiscoveries', { defaultValue: 'Descobertas' })}</span>
          </button>
          <button
            type="button"
            className={`hub-tab-btn ${activeTab === 'investigate' ? 'active' : ''}`}
            onClick={() => setActiveTab('investigate')}
          >
            <Send size={16} />
            <span>{t('proactive.tabInvestigate', { defaultValue: 'Pedir Investigação' })}</span>
          </button>
          <button
            type="button"
            className={`hub-tab-btn ${activeTab === 'preferences' ? 'active' : ''}`}
            onClick={() => setActiveTab('preferences')}
          >
            <Sliders size={16} />
            <span>{t('proactive.tabPreferences', { defaultValue: 'Preferências' })}</span>
          </button>
        </div>
      </header>

      {/* Conteúdo Principal */}
      <main className="proactive-hub-main">
        {activeTab === 'feed' && (
          <div className="hub-feed-view">
            {/* Barra de Filtros e Busca */}
            <div className="hub-feed-toolbar">
              <div className="hub-search-box">
                <Search size={16} className="search-icon" />
                <input
                  type="text"
                  placeholder={t('proactive.searchPlaceholder', { defaultValue: 'Buscar descobertas por tópico ou termo...' })}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
                {searchQuery && (
                  <button type="button" className="clear-search" onClick={() => setSearchQuery('')}>
                    <X size={14} />
                  </button>
                )}
              </div>

              <div className="hub-status-chips">
                <button
                  type="button"
                  className={`status-chip ${statusFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('all')}
                >
                  {t('common.all', { defaultValue: 'Todas' })}
                </button>
                <button
                  type="button"
                  className={`status-chip ${statusFilter === 'ready' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('ready')}
                >
                  {t('proactive.filterReady', { defaultValue: 'Novas / Pendentes' })}
                </button>
                <button
                  type="button"
                  className={`status-chip ${statusFilter === 'delivered' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('delivered')}
                >
                  {t('proactive.filterDelivered', { defaultValue: 'Entregues' })}
                </button>
                <button
                  type="button"
                  className={`status-chip ${statusFilter === 'seen' ? 'active' : ''}`}
                  onClick={() => setStatusFilter('seen')}
                >
                  {t('proactive.filterSeen', { defaultValue: 'Vistas' })}
                </button>
              </div>

              <button
                type="button"
                className="hub-refresh-btn"
                onClick={fetchHistory}
                title={t('common.refresh', { defaultValue: 'Atualizar' })}
              >
                <RefreshCw size={15} className={loadingHistory ? 'is-spinning' : ''} />
              </button>
            </div>

            {/* Lista do Feed */}
            {loadingHistory ? (
              <div className="hub-loading-state">
                <ProactiveMascot size={48} state="researching" style={personaStyle} />
                <p>{t('common.loading', { defaultValue: 'Carregando descobertas...' })}</p>
              </div>
            ) : filteredHistory.length === 0 ? (
              <div className="hub-empty-state">
                <ProactiveMascot size={64} state="idle" style={personaStyle} />
                <h3>{t('proactive.feedEmptyTitle', { defaultValue: 'Nenhuma descoberta encontrada' })}</h3>
                <p>
                  {searchQuery
                    ? t('proactive.feedEmptySearch', { defaultValue: 'Nenhum resultado corresponde à sua pesquisa.' })
                    : t('proactive.feedEmptyDesc', {
                        defaultValue: 'Converse no NexusLocal normalmente! O assistente detecta temas de interesse e pesquisa novidades espontaneamente.',
                      })}
                </p>
              </div>
            ) : (
              <div className="hub-feed-grid">
                {filteredHistory.map((item) => (
                  <article key={item.id} className="hub-insight-card">
                    <div className="card-top">
                      <div className="topic-group">
                        <Sparkles size={16} className="card-sparkle" />
                        <h2 className="card-topic">{item.topic}</h2>
                      </div>
                      <span className={`card-status-badge status-${item.status}`}>
                        {item.status === 'ready' ? t('proactive.badgeReady', { defaultValue: 'Pronto' }) : item.status}
                      </span>
                    </div>

                    <p className="card-text">{item.text}</p>

                    {item.sources && item.sources.length > 0 && (
                      <div className="card-sources">
                        {item.sources.map((s, idx) => (
                          <a
                            key={idx}
                            href={s.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="card-source-link"
                            title={s.title}
                          >
                            <span>{s.domain || 'fonte'}</span>
                            <ExternalLink size={11} />
                          </a>
                        ))}
                      </div>
                    )}

                    <footer className="card-actions">
                      <button
                        type="button"
                        className="card-btn card-btn--open"
                        onClick={() => openPendingInsight(item.id)}
                      >
                        <MessageSquare size={14} />
                        <span>{t('proactive.cardOpen', { defaultValue: 'Abrir conversa' })}</span>
                      </button>
                      <button
                        type="button"
                        className="card-btn card-btn--tell"
                        onClick={() => expandProactiveInsight(item.id, 'new_chat')}
                      >
                        <Sparkles size={14} />
                        <span>{t('proactive.cardTellMeHere', { defaultValue: 'Me conta aqui' })}</span>
                      </button>
                      {item.status === 'ready' && (
                        <button
                          type="button"
                          className="card-btn card-btn--dismiss"
                          onClick={() => dismissPendingInsight(item.id)}
                          title={t('proactive.cardDismiss', { defaultValue: 'Dispensar' })}
                        >
                          <X size={14} />
                        </button>
                      )}
                    </footer>
                  </article>
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'investigate' && (
          <div className="hub-investigate-view">
            <div className="investigate-hero">
              <ProactiveMascot size={56} state={investigating ? 'researching' : 'ready'} style={personaStyle} />
              <div className="hero-copy">
                <h2>{t('proactive.investigateTitle', { defaultValue: 'Pedir uma Investigação Espontânea' })}</h2>
                <p>
                  {t('proactive.investigateDesc', {
                    defaultValue: 'Digite o tema ou assunto que você quer que o assistente pesquise na web. Ele sintetiza fontes confiáveis e entrega o resumo completo.',
                  })}
                </p>
              </div>
            </div>

            <form className="investigate-form" onSubmit={handleManualInvestigate}>
              <div className="form-group">
                <label htmlFor="investigate-input">
                  {t('proactive.investigateLabel', { defaultValue: 'Tema ou pergunta da pesquisa:' })}
                </label>
                <textarea
                  id="investigate-input"
                  rows={3}
                  placeholder={t('proactive.investigateInputPlaceholder', {
                    defaultValue: 'Ex: Últimas novidades e lançamentos do Rust 2026...',
                  })}
                  value={investigatePrompt}
                  onChange={(e) => setInvestigatePrompt(e.target.value)}
                  disabled={investigating}
                  required
                />
              </div>

              <div className="form-group">
                <label>{t('proactive.categoryLabel', { defaultValue: 'Categoria:' })}</label>
                <div className="category-chips">
                  {(['news', 'event', 'product', 'place'] as ProactiveCategory[]).map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      className={`cat-chip ${investigateCategory === cat ? 'active' : ''}`}
                      onClick={() => setInvestigateCategory(cat)}
                      disabled={investigating}
                    >
                      {cat === 'news' && '📰 '}
                      {cat === 'event' && '📅 '}
                      {cat === 'product' && '⚡ '}
                      {cat === 'place' && '📍 '}
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              <div className="form-actions">
                <button
                  type="submit"
                  className="investigate-submit-btn"
                  disabled={investigating || !investigatePrompt.trim()}
                >
                  <Send size={16} />
                  <span>{investigating ? t('proactive.investigatingBtn', { defaultValue: 'Pesquisando...' }) : t('proactive.investigateSubmit', { defaultValue: 'Iniciar Investigação' })}</span>
                </button>
              </div>
            </form>

            {investigateResult && (
              <div className="investigate-success-box">
                <Check size={20} className="success-icon" />
                <div className="success-text">
                  <h3>{t('proactive.investigationCreatedTitle', { defaultValue: 'Investigação em andamento!' })}</h3>
                  <p>{t('proactive.investigationCreatedDesc', { defaultValue: 'Uma conversa dedicada foi criada para acompanhar os resultados.' })}</p>
                </div>
                <button
                  type="button"
                  className="view-conv-btn"
                  onClick={() => {
                    void loadConversation(investigateResult.conversation_id)
                    setView('chat')
                  }}
                >
                  <MessageSquare size={14} />
                  <span>{t('proactive.openInvestigationChat', { defaultValue: 'Ir para conversa' })}</span>
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'preferences' && (
          <div className="hub-preferences-view">
            {/* Estilo do Assistente / Persona */}
            <section className="pref-section">
              <h2 className="pref-title">
                {t('proactive.personaStyleTitle', { defaultValue: 'Identidade Visual do Assistente' })}
              </h2>
              <div className="persona-selector">
                <div
                  className={`persona-card ${personaStyle === 'lumi' ? 'selected' : ''}`}
                  onClick={() => handleTogglePersona('lumi')}
                >
                  <ProactiveMascot size={48} state="idle" style="lumi" />
                  <div className="persona-info">
                    <h3>{t('proactive.personaLumiTitle', { defaultValue: 'Nexus Lumi (Kawaii Tech)' })}</h3>
                    <p>{t('proactive.personaLumiDesc', { defaultValue: 'Expressivo, carismático e dinâmico com microexpressões.' })}</p>
                  </div>
                </div>

                <div
                  className={`persona-card ${personaStyle === 'core' ? 'selected' : ''}`}
                  onClick={() => handleTogglePersona('core')}
                >
                  <ProactiveMascot size={48} state="idle" style="core" />
                  <div className="persona-info">
                    <h3>{t('proactive.personaCoreTitle', { defaultValue: 'Nexus Core (Minimalista)' })}</h3>
                    <p>{t('proactive.personaCoreDesc', { defaultValue: 'Geométrico, discreto e estritamente corporativo.' })}</p>
                  </div>
                </div>
              </div>
            </section>

            {/* Sensibilidade */}
            <section className="pref-section">
              <h2 className="pref-title">
                {t('proactive.sensitivityTitle', { defaultValue: 'Frequência de Pesquisa' })}
              </h2>
              <div className="sensitivity-selector">
                {(['low', 'medium', 'high'] as ProactiveSensitivity[]).map((level) => (
                  <button
                    key={level}
                    type="button"
                    className={`sens-btn ${proactiveSettings?.sensitivity === level ? 'active' : ''}`}
                    onClick={() => handleToggleSensitivity(level)}
                  >
                    <span className="sens-name">{level}</span>
                    <span className="sens-desc">
                      {level === 'low' && t('proactive.sensLow', { defaultValue: 'Até 1 / dia (só temas fortes)' })}
                      {level === 'medium' && t('proactive.sensMedium', { defaultValue: 'Até 3 / dia (equilibrado)' })}
                      {level === 'high' && t('proactive.sensHigh', { defaultValue: 'Até 5 / dia (alta curiosidade)' })}
                    </span>
                  </button>
                ))}
              </div>
            </section>

            {/* Web Push */}
            {pushSupported && (
              <section className="pref-section">
                <h2 className="pref-title">
                  {t('proactive.pushNotificationsTitle', { defaultValue: 'Notificações Nativas (Web Push / PWA)' })}
                </h2>
                <div className="pref-row">
                  <div className="pref-row-info">
                    <p className="pref-label">{t('proactive.pushLabel', { defaultValue: 'Receber alertas quando o app estiver fechado' })}</p>
                    <p className="pref-hint">{t('proactive.pushHint', { defaultValue: 'Respeita horários silenciosos configurados.' })}</p>
                  </div>
                  <div className="push-controls">
                    <button
                      type="button"
                      className={`toggle-switch ${pushSubscribed ? 'is-on' : ''}`}
                      onClick={handleTogglePush}
                      disabled={pushLoading}
                    >
                      <span className="switch-thumb" />
                    </button>
                    {pushSubscribed && (
                      <button
                        type="button"
                        className="test-push-btn"
                        onClick={sendTestPush}
                        disabled={pushLoading}
                      >
                        <BellRing size={14} />
                        <span>{t('proactive.sendTestPush', { defaultValue: 'Enviar teste' })}</span>
                      </button>
                    )}
                  </div>
                </div>
              </section>
            )}

            {/* Tópicos Bloqueados */}
            <section className="pref-section">
              <h2 className="pref-title">
                <ShieldCheck size={18} />
                <span>{t('proactive.blockedTopicsTitle', { defaultValue: 'Tópicos Bloqueados' })}</span>
              </h2>
              {proactiveSettings?.blocked_topics && proactiveSettings.blocked_topics.length > 0 ? (
                <div className="blocked-topics-list">
                  {proactiveSettings.blocked_topics.map((tItem) => (
                    <div key={tItem.topic_hash} className="blocked-topic-tag">
                      <span>{tItem.topic_label}</span>
                      <button
                        type="button"
                        onClick={() => handleUnblockTopic(tItem.topic_hash)}
                        title={t('proactive.unblockTopic', { defaultValue: 'Desbloquear' })}
                      >
                        <X size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="pref-hint">{t('proactive.noBlockedTopics', { defaultValue: 'Nenhum tópico bloqueado no momento.' })}</p>
              )}
            </section>
          </div>
        )}
      </main>
    </div>
  )
}
