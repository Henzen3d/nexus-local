import React, { useState } from 'react'
import { Target, Sparkles, Cpu, Clock, ShieldCheck, Zap } from 'lucide-react'
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
      style={{ position: 'relative', display: 'inline-flex', alignItems: 'center' }}
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span
        className="auto-route-badge"
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '2px 8px',
          borderRadius: '12px',
          fontSize: '11px',
          fontWeight: 600,
          background: 'var(--accent-subtle, rgba(99, 102, 241, 0.12))',
          color: 'var(--accent, #6366f1)',
          border: '1px solid var(--accent-border, rgba(99, 102, 241, 0.25))',
          cursor: 'pointer',
          userSelect: 'none',
          transition: 'all 0.18s ease',
        }}
      >
        <Target size={11} className="auto-route-icon" />
        <span>Auto: {decision.reason_pt || decision.intent}</span>
      </span>

      {showTooltip && (
        <div
          className="auto-route-popover"
          style={{
            position: 'absolute',
            bottom: 'calc(100% + 6px)',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 1000,
            width: '270px',
            background: 'var(--surface-dropdown, #18181b)',
            border: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.12))',
            borderRadius: '10px',
            padding: '10px 12px',
            boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.4)',
            fontSize: '11.5px',
            lineHeight: 1.45,
            color: 'var(--text, #e4e4e7)',
            backdropFilter: 'blur(12px)',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontWeight: 700,
              fontSize: '12px',
              color: 'var(--accent-light, #818cf8)',
              marginBottom: '6px',
              borderBottom: '1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))',
              paddingBottom: '4px',
            }}
          >
            <Sparkles size={13} />
            <span>{t('autoRouter.decisionTitle', { defaultValue: 'Decisão do Smart Router' })}</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
              <span style={{ color: 'var(--text-muted, #a1a1aa)' }}>
                {t('autoRouter.intent', { defaultValue: 'Intenção' })}:
              </span>
              <span style={{ fontWeight: 600 }}>
                {decision.reason_pt} ({confidencePct}%)
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
              <span style={{ color: 'var(--text-muted, #a1a1aa)' }}>
                {t('autoRouter.modelChosen', { defaultValue: 'Modelo Escolhido' })}:
              </span>
              <span style={{ fontWeight: 600, color: 'var(--accent, #6366f1)' }}>
                {decision.chosen_model_name}
              </span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
              <span style={{ color: 'var(--text-muted, #a1a1aa)' }}>
                {t('autoRouter.policy', { defaultValue: 'Política' })}:
              </span>
              <span>{formatPolicy(decision.policy)}</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
              <span style={{ color: 'var(--text-muted, #a1a1aa)' }}>
                {t('autoRouter.latency', { defaultValue: 'Tempo de Decisão' })}:
              </span>
              <span style={{ color: 'var(--success, #10b981)', fontWeight: 600 }}>
                {latency}
              </span>
            </div>

            {decision.matched_signals && decision.matched_signals.length > 0 && (
              <div style={{ marginTop: '3px', paddingTop: '3px', borderTop: '1px dashed var(--border-subtle, rgba(255, 255, 255, 0.06))' }}>
                <span style={{ color: 'var(--text-muted, #a1a1aa)', fontSize: '10.5px' }}>
                  {t('autoRouter.signals', { defaultValue: 'Sinais' })}:{' '}
                </span>
                <span style={{ fontSize: '10.5px', color: 'var(--text-secondary, #d4d4d8)' }}>
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
