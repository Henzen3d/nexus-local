import React, { useState } from 'react'
import { Target, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { AutoRouteDecisionInfo } from '../types'

interface AutoRouteBadgeProps {
  decision: AutoRouteDecisionInfo
}

export function AutoRouteBadge({ decision }: AutoRouteBadgeProps) {
  const { t } = useTranslation()
  const [showTooltip, setShowTooltip] = useState(false)

  const formatPolicy = (policy: string) => {
    switch (policy) {
      case 'economical_free':
        return t('autoRouter.policyEconomical', { defaultValue: 'Econômica (Free-First)' })
      case 'max_performance':
        return t('autoRouter.policyPerformance', { defaultValue: 'Máxima Performance' })
      case 'balanced_smart':
      default:
        return t('autoRouter.policyBalanced', { defaultValue: 'Equilibrada (Smart)' })
    }
  }

  const confidencePct = Math.round((decision.confidence ?? 0.9) * 100)
  const latency = decision.decision_latency_ms ? `${decision.decision_latency_ms}ms` : '< 1ms'

  return (
    <div
      className="auto-route-badge-container"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
      onClick={() => setShowTooltip((prev) => !prev)}
    >
      <span className="auto-route-badge">
        <Target size={11} className="auto-route-icon" />
        <span>Auto: {decision.reason_pt || decision.intent}</span>
      </span>

      {showTooltip && (
        <div className="auto-route-popover" role="tooltip">
          <div className="auto-route-popover-header">
            <Sparkles size={13} />
            <span>{t('autoRouter.decisionTitle', { defaultValue: 'Decisão do Smart Router' })}</span>
          </div>

          <div className="auto-route-popover-body">
            <div className="auto-route-popover-row">
              <span className="auto-route-popover-label">
                {t('autoRouter.intent', { defaultValue: 'Intenção' })}:
              </span>
              <span className="auto-route-popover-val">
                {decision.reason_pt} ({confidencePct}%)
              </span>
            </div>

            <div className="auto-route-popover-row">
              <span className="auto-route-popover-label">
                {t('autoRouter.modelChosen', { defaultValue: 'Modelo Escolhido' })}:
              </span>
              <span className="auto-route-popover-model">
                {decision.chosen_model_name}
              </span>
            </div>

            <div className="auto-route-popover-row">
              <span className="auto-route-popover-label">
                {t('autoRouter.policy', { defaultValue: 'Política' })}:
              </span>
              <span className="auto-route-popover-val">{formatPolicy(decision.policy)}</span>
            </div>

            <div className="auto-route-popover-row">
              <span className="auto-route-popover-label">
                {t('autoRouter.latency', { defaultValue: 'Tempo de Decisão' })}:
              </span>
              <span className="auto-route-popover-latency">
                {latency}
              </span>
            </div>

            {decision.matched_signals && decision.matched_signals.length > 0 && (
              <div className="auto-route-popover-signals">
                <span className="auto-route-popover-label">
                  {t('autoRouter.signals', { defaultValue: 'Sinais' })}:{' '}
                </span>
                <span className="auto-route-popover-signals-text">
                  {decision.matched_signals.slice(0, 2).join(', ')}
                </span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

