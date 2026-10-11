import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Clock,
  RotateCcw,
  ShieldAlert,
  AlertCircle,
  Loader2,
  HelpCircle,
  Sparkles,
  Layers,
  Timer,
} from 'lucide-react'
import type { DreamLogApi } from '../api/client'
import { describeDreamLog } from '../lib/dreamLog'

export interface DreamLogCardProps {
  log: DreamLogApi
  isLatest?: boolean
  onRollbackClick: (log: DreamLogApi) => void
  rollingBackId: string | null
  isLiveRunning: boolean
}

export function DreamLogCard({
  log,
  isLatest = false,
  onRollbackClick,
  rollingBackId,
  isLiveRunning,
}: DreamLogCardProps) {
  const { t } = useTranslation()
  const view = describeDreamLog(log)

  const pillStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10.5px',
    color: 'var(--muted-soft)',
    background: 'var(--surface-card)',
    padding: '3px 8px',
    borderRadius: '6px',
    border: '1px solid var(--hairline)',
  } as const

  return (
    <div
      style={{
        background: isLatest ? 'var(--surface-card)' : 'var(--surface-soft)',
        border: isLatest ? '1px solid rgba(204, 120, 92, 0.4)' : '1px solid var(--hairline)',
        borderRadius: '10px',
        padding: '12px 14px',
        display: 'flex',
        flexDirection: 'column',
        gap: '9px',
        boxShadow: isLatest ? '0 2px 8px rgba(204, 120, 92, 0.05)' : 'none',
        transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
      }}
    >
      {/* Top Bar: Data, Modelo, Badges & Ação */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '8px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          {/* Timestamp */}
          <span
            style={{
              fontSize: '12.5px',
              fontWeight: 600,
              color: 'var(--ink)',
              display: 'flex',
              alignItems: 'center',
              gap: '5px',
            }}
          >
            <Clock size={12} style={{ color: 'var(--muted)' }} />
            {new Date(log.created_at).toLocaleString([], {
              month: 'short',
              day: 'numeric',
              hour: '2-digit',
              minute: '2-digit',
            })}
          </span>

          {/* Provedor / Modelo */}
          <span
            style={{
              fontSize: '10.5px',
              fontFamily: 'ui-monospace, monospace',
              background: 'var(--surface-card)',
              border: '1px solid var(--hairline)',
              borderRadius: '4px',
              padding: '1px 6px',
              color: 'var(--muted)',
            }}
            title={`${log.provider_id} · ${log.model_id}`}
          >
            {log.provider_id} · {log.model_id}
          </span>

          {/* Badge: Mais recente */}
          {isLatest && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                fontSize: '10px',
                fontWeight: 700,
                borderRadius: '4px',
                padding: '1px 7px',
                background: 'rgba(204, 120, 92, 0.12)',
                color: 'var(--primary)',
                border: '1px solid rgba(204, 120, 92, 0.25)',
              }}
            >
              <Sparkles size={10} />
              {t('memory.dreamJournalLatestBadge', { defaultValue: 'Mais recente' })}
            </span>
          )}

          {/* Status Badge: Revertido */}
          {log.status === 'rolled_back' && (
            <span
              style={{
                fontSize: '10px',
                fontWeight: 700,
                borderRadius: '4px',
                padding: '1px 6px',
                background: 'rgba(239, 68, 68, 0.1)',
                color: 'var(--error, #ef4444)',
                border: '1px solid rgba(239, 68, 68, 0.2)',
              }}
            >
              REVERTIDO
            </span>
          )}

          {/* Status Badge: Aborted Safety */}
          {log.status === 'aborted_safety' && (
            <span
              style={{
                fontSize: '10px',
                fontWeight: 700,
                borderRadius: '4px',
                padding: '1px 6px',
                background: 'rgba(234, 179, 8, 0.1)',
                color: 'var(--warning, #eab308)',
                border: '1px solid rgba(234, 179, 8, 0.2)',
              }}
            >
              SEGURANÇA ATIVADA
            </span>
          )}
        </div>

        {/* Botão de Reversão / Status Pill */}
        <div>
          {view.pill === 'rollback' ? (
            <button
              type="button"
              onClick={() => onRollbackClick(log)}
              disabled={rollingBackId === log.id || isLiveRunning}
              title={t('memory.dreamRollbackBtn')}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 10px',
                borderRadius: '6px',
                border: '1px solid var(--hairline)',
                background: 'var(--canvas)',
                color: 'var(--error, #ef4444)',
                fontSize: '11px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'background 0.15s ease',
              }}
            >
              <RotateCcw size={11} />
              {rollingBackId === log.id ? t('common.loading') : t('memory.dreamRollbackBtn')}
            </button>
          ) : view.pill === 'expired' ? (
            <span title={t('memory.dreamSnapshotExpiredTooltip')} style={pillStyle}>
              <HelpCircle size={10} />
              {t('memory.dreamSnapshotExpired')}
            </span>
          ) : view.pill === 'blocked' ? (
            <span title={t('memory.dreamRollbackTooltip')} style={pillStyle}>
              <ShieldAlert size={10} />
              {t('memory.dreamRollbackBlocked')}
            </span>
          ) : view.pill === 'failed' ? (
            <span title={view.headline} style={{ ...pillStyle, color: 'var(--error, #ef4444)' }}>
              <AlertCircle size={10} />
              Falhou
            </span>
          ) : view.pill === 'running' ? (
            <span title={view.headline} style={pillStyle}>
              <Loader2 size={10} className="spin-animation" />
              Em andamento
            </span>
          ) : null}
        </div>
      </div>

      {/* Metrics Breakdown */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: '12px',
            fontWeight: 600,
            color: view.showNoise ? 'var(--primary)' : 'var(--error, #ef4444)',
          }}
        >
          {view.showNoise
            ? `${log.facts_before} fatos ➔ ${log.facts_after} consolidados (-${view.noisePct}% de ruído)`
            : view.headline}
        </span>
        {log.facts_merged > 0 && (
          <span
            style={{
              fontSize: '10.5px',
              color: 'var(--muted)',
              background: 'var(--surface-card)',
              border: '1px solid var(--hairline)',
              padding: '1px 6px',
              borderRadius: '4px',
            }}
          >
            {log.facts_merged} fundidos
          </span>
        )}
        {log.facts_superseded > 0 && (
          <span
            style={{
              fontSize: '10.5px',
              color: 'var(--muted)',
              background: 'var(--surface-card)',
              border: '1px solid var(--hairline)',
              padding: '1px 6px',
              borderRadius: '4px',
            }}
          >
            {log.facts_superseded} atualizados
          </span>
        )}
        <span
          style={{
            fontSize: '10.5px',
            color: 'var(--muted)',
            background: 'var(--surface-card)',
            border: '1px solid var(--hairline)',
            padding: '1px 6px',
            borderRadius: '4px',
          }}
        >
          0 fixados alterados
        </span>
        {log.duration_ms > 0 && (
          <span
            style={{
              fontSize: '10.5px',
              color: 'var(--muted)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '3px',
              marginLeft: 'auto',
            }}
            title="Tempo de processamento"
          >
            <Timer size={10} />
            {(log.duration_ms / 1000).toFixed(1)}s
          </span>
        )}
      </div>

      {/* Notes / summary if present */}
      {log.summary_notes && (
        <p
          style={{
            margin: 0,
            fontSize: '12px',
            color: 'var(--body)',
            lineHeight: 1.45,
            fontStyle: 'italic',
            borderLeft: '2px solid rgba(204, 120, 92, 0.25)',
            paddingLeft: '8px',
          }}
        >
          "{log.summary_notes}"
        </p>
      )}
    </div>
  )
}
