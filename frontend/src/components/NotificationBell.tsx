import React, { useState, useRef, useEffect, useCallback } from 'react'
import { Bell, Sparkles, MessageSquare, ExternalLink, X, ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import type { ProactiveInsight } from '../types'

export const NotificationBell: React.FC = () => {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const bellRef = useRef<HTMLDivElement>(null)

  const pendingInsights = useStore((s) => s.pendingInsights)
  const openPendingInsight = useStore((s) => s.openPendingInsight)
  const dismissPendingInsight = useStore((s) => s.dismissPendingInsight)
  const expandProactiveInsight = useStore((s) => s.expandProactiveInsight)
  const openProactiveCompanion = useStore((s) => s.openProactiveCompanion)
  const setView = useStore((s) => s.setView)
  const proactiveSettings = useStore((s) => s.proactiveSettings)

  const unreadCount = pendingInsights.length
  const personaStyle = proactiveSettings?.persona_style || 'lumi'

  // Fechar ao clicar fora ou pressionar ESC
  useEffect(() => {
    if (!isOpen) return

    const handleClickOutside = (e: MouseEvent) => {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [isOpen])

  const ageLabel = useCallback(
    (insight: ProactiveInsight) => {
      const ts = insight.ready_at || insight.created_at
      if (!ts) return ''
      const when = new Date(ts.replace(' ', 'T') + (ts.includes('Z') ? '' : 'Z')).getTime()
      if (Number.isNaN(when)) return ''
      const diffMin = Math.max(1, Math.round((Date.now() - when) / 60000))
      if (diffMin < 60) return t('proactive.cardMinutesAgo', { count: diffMin, defaultValue: `há ${diffMin} min` })
      const diffHours = Math.round(diffMin / 60)
      if (diffHours < 24) return t('proactive.cardHoursAgo', { count: diffHours, defaultValue: `há ${diffHours} h` })
      const diffDays = Math.round(diffHours / 24)
      return t('proactive.cardDaysAgo', { count: diffDays, defaultValue: `há ${diffDays} d` })
    },
    [t]
  )

  const handleOpenConversation = async (insightId: string) => {
    setIsOpen(false)
    await openPendingInsight(insightId)
  }

  const handleOpenCompanion = (insight: ProactiveInsight) => {
    setIsOpen(false)
    openProactiveCompanion(insight)
  }

  const handleExpandNewChat = async (insightId: string) => {
    setIsOpen(false)
    await expandProactiveInsight(insightId, 'new_chat')
  }

  const handleGoToHub = () => {
    setIsOpen(false)
    setView('proactive')
  }

  return (
    <div className="notification-bell-container" ref={bellRef}>
      <button
        type="button"
        className={`notification-bell-btn ${unreadCount > 0 ? 'has-unread' : ''} ${isOpen ? 'is-active' : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-label={t('proactive.notificationsBell', { count: unreadCount, defaultValue: `Notificações (${unreadCount})` })}
        title={t('proactive.notificationsTitle', { defaultValue: 'Descobertas Proativas' })}
      >
        <Bell size={18} className="bell-icon" />
        {unreadCount > 0 && (
          <span className="notification-bell-badge" aria-hidden="true">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          {/* Backdrop para mobile */}
          <div className="notification-backdrop" onClick={() => setIsOpen(false)} aria-hidden="true" />

          <div className="notification-popover" role="dialog" aria-modal="true" aria-label={t('proactive.notificationsTitle')}>
            <div className="notification-popover-header">
              <div className="popover-title-row">
                <Sparkles size={26} className="text-primary" />
                <span className="popover-title">
                  {t('proactive.notificationsTitle', { defaultValue: 'Descobertas Proativas' })}
                </span>
                {unreadCount > 0 && (
                  <span className="popover-counter-pill">{unreadCount}</span>
                )}
              </div>
              <button
                type="button"
                className="popover-close-btn"
                onClick={() => setIsOpen(false)}
                aria-label={t('common.close', { defaultValue: 'Fechar' })}
              >
                <X size={16} />
              </button>
            </div>

            <div className="notification-popover-content">
              {unreadCount === 0 ? (
                <div className="notification-empty-state">
                  <Sparkles size={54} className="text-primary" />
                  <p className="empty-title">{t('proactive.emptyTitle', { defaultValue: 'Tudo em dia!' })}</p>
                  <p className="empty-desc">
                    {t('proactive.emptyDesc', {
                      defaultValue: 'O assistente avisará aqui assim que encontrar novas pesquisas e atualizações para você.',
                    })}
                  </p>
                </div>
              ) : (
                <div className="notification-items-list">
                  {pendingInsights.map((insight) => (
                    <div key={insight.id} className="notification-item-card">
                      <div className="item-card-top">
                        <span className="item-topic">
                          <Sparkles size={13} className="item-sparkle" />
                          {insight.topic}
                        </span>
                        <div className="item-meta">
                          <span className="item-age">{ageLabel(insight)}</span>
                          <button
                            type="button"
                            className="item-dismiss-btn"
                            title={t('proactive.cardDismiss', { defaultValue: 'Dispensar' })}
                            onClick={() => dismissPendingInsight(insight.id)}
                          >
                            <X size={13} />
                          </button>
                        </div>
                      </div>

                      <p className="item-text-preview">
                        {insight.text.length > 130 ? `${insight.text.slice(0, 130)}…` : insight.text}
                      </p>

                      {insight.sources && insight.sources.length > 0 && (
                        <div className="item-sources-row">
                          {insight.sources.slice(0, 3).map((source, sIdx) => (
                            <a
                              key={sIdx}
                              href={source.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="item-source-chip"
                              onClick={(e) => e.stopPropagation()}
                              title={source.title}
                            >
                              <span className="source-domain">{source.domain || 'fonte'}</span>
                              <ExternalLink size={10} />
                            </a>
                          ))}
                        </div>
                      )}

                      <div className="item-actions-row">
                        <button
                          type="button"
                          className="item-action-btn item-action-open"
                          onClick={() => handleOpenCompanion(insight)}
                          title={t('proactive.openCompanionTitle', { defaultValue: 'Conversar em modal dedicado com o assistente' })}
                        >
                          <Sparkles size={13} />
                          <span>{t('proactive.talkToLumi', { defaultValue: 'Conversar' })}</span>
                        </button>
                        <button
                          type="button"
                          className="item-action-btn item-action-expand"
                          onClick={() => handleOpenConversation(insight.id)}
                        >
                          <MessageSquare size={13} />
                          <span>{t('proactive.cardOpen', { defaultValue: 'Abrir conversa' })}</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="notification-popover-footer">
              <button type="button" className="footer-hub-link" onClick={handleGoToHub}>
                <span>{t('proactive.goToHub', { defaultValue: 'Ver todas no Hub do Assistente' })}</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
