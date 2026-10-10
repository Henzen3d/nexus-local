import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Moon,
  Sparkles,
  Zap,
  RotateCcw,
  CheckCircle2,
  Clock,
  Layers,
  ShieldAlert,
  Loader2,
  AlertCircle,
  HelpCircle,
} from 'lucide-react'
import type { DreamLogApi } from '../api/client'

interface DreamJournalSectionProps {
  logs: DreamLogApi[]
  loading: boolean
  isLiveRunning: boolean
  liveProgress: { step: string; pct: number; msg?: string; error?: string } | null
  rollingBackId: string | null
  onSimulate: () => void
  onRunNow: () => void
  onRollback: (log: DreamLogApi) => void
}

export function DreamJournalSection({
  logs,
  loading,
  isLiveRunning,
  liveProgress,
  rollingBackId,
  onSimulate,
  onRunNow,
  onRollback,
}: DreamJournalSectionProps) {
  const { t } = useTranslation()
  const [confirmRollbackLog, setConfirmRollbackLog] = useState<DreamLogApi | null>(null)

  const stepsList = [
    { id: 'snapshot', label: t('memory.dreamStep1') },
    { id: 'model_connect', label: t('memory.dreamStep2') },
    { id: 'analyzing', label: t('memory.dreamStep3') },
    { id: 'flash_tx', label: t('memory.dreamStep4') },
    { id: 'cache_update', label: t('memory.dreamStep5') },
  ]

  const getStepStatus = (stepIndex: number, currentPct: number) => {
    // 5 steps approx 20% each
    const stepThreshold = (stepIndex + 1) * 20
    if (currentPct >= stepThreshold) return 'done'
    if (currentPct >= stepThreshold - 20) return 'active'
    return 'pending'
  }

  return (
    <div
      style={{
        background: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '12px',
        padding: '16px 18px',
        marginBottom: '20px',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          marginBottom: '14px',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div style={{ flex: 1, minWidth: 260 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Moon size={18} style={{ color: 'var(--primary)' }} />
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--ink)' }}>
              {t('memory.dreamJournalTitle')}
            </h3>
          </div>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--muted)', lineHeight: 1.45 }}>
            {t('memory.dreamJournalDesc')}
          </p>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={onSimulate}
            disabled={isLiveRunning}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 14px',
              borderRadius: '8px',
              border: '1px solid var(--hairline)',
              background: 'var(--surface-soft)',
              color: 'var(--ink)',
              fontSize: '12.5px',
              fontWeight: 500,
              cursor: isLiveRunning ? 'not-allowed' : 'pointer',
              opacity: isLiveRunning ? 0.6 : 1,
            }}
          >
            <Sparkles size={14} style={{ color: 'var(--primary)' }} />
            {t('memory.dreamSimulateBtn')}
          </button>
          <button
            type="button"
            onClick={onRunNow}
            disabled={isLiveRunning}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 14px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--primary)',
              color: '#fff',
              fontSize: '12.5px',
              fontWeight: 600,
              cursor: isLiveRunning ? 'not-allowed' : 'pointer',
              opacity: isLiveRunning ? 0.7 : 1,
            }}
          >
            {isLiveRunning ? (
              <Loader2 size={14} className="spin-animation" />
            ) : (
              <Zap size={14} />
            )}
            {isLiveRunning ? t('memory.dreamRunning') : t('memory.dreamRunNowBtn')}
          </button>
        </div>
      </div>

      {/* Live Running Progress Card */}
      {isLiveRunning && (
        <div
          style={{
            background: 'var(--surface-soft)',
            border: '1px solid rgba(204, 120, 92, 0.3)',
            borderRadius: '10px',
            padding: '14px 16px',
            marginBottom: '16px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)', display: 'flex', alignItems: 'center', gap: 6 }}>
              <Loader2 size={14} className="spin-animation" style={{ color: 'var(--primary)' }} />
              {t('memory.dreamLiveTitle')}
            </span>
            <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--primary)' }}>
              {liveProgress?.pct ?? 0}%
            </span>
          </div>

          {/* Progress Bar */}
          <div
            style={{
              height: '6px',
              background: 'var(--hairline)',
              borderRadius: '3px',
              overflow: 'hidden',
              marginBottom: '12px',
            }}
          >
            <div
              style={{
                width: `${liveProgress?.pct ?? 5}%`,
                height: '100%',
                background: 'var(--primary)',
                transition: 'width 0.3s ease',
              }}
            />
          </div>

          {/* Step Checklist */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {stepsList.map((st, idx) => {
              const status = getStepStatus(idx, liveProgress?.pct ?? 0)
              return (
                <div
                  key={st.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: '12px',
                    color: status === 'done' ? 'var(--ink)' : status === 'active' ? 'var(--primary)' : 'var(--muted)',
                    fontWeight: status === 'active' ? 600 : 400,
                  }}
                >
                  {status === 'done' ? (
                    <CheckCircle2 size={14} style={{ color: 'var(--success, #22c55e)' }} />
                  ) : status === 'active' ? (
                    <Loader2 size={14} className="spin-animation" style={{ color: 'var(--primary)' }} />
                  ) : (
                    <div
                      style={{
                        width: 14,
                        height: 14,
                        borderRadius: '50%',
                        border: '1.5px solid var(--hairline)',
                      }}
                    />
                  )}
                  <span>{st.label}</span>
                </div>
              )
            })}
          </div>

          {liveProgress?.msg && (
            <div style={{ marginTop: '10px', fontSize: '11.5px', color: 'var(--muted)', fontStyle: 'italic' }}>
              {liveProgress.msg}
            </div>
          )}
        </div>
      )}

      {/* Confirmation Modal for Rollback */}
      {confirmRollbackLog && (
        <div
          onClick={() => setConfirmRollbackLog(null)}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.55)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10001,
            padding: '20px',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--canvas)',
              borderRadius: '14px',
              padding: '20px 24px',
              width: '100%',
              maxWidth: '460px',
              boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
              border: '1px solid var(--hairline)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: '8px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  color: 'var(--error, #ef4444)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <RotateCcw size={16} />
              </div>
              <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--ink)' }}>
                Reverter Consolidação
              </h4>
            </div>

            <p style={{ fontSize: '13px', color: 'var(--body)', margin: '0 0 16px 0', lineHeight: 1.5 }}>
              {t('memory.dreamRollbackConfirm', {
                date: new Date(confirmRollbackLog.created_at).toLocaleString(),
              })}
            </p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setConfirmRollbackLog(null)}
                style={{
                  padding: '7px 14px',
                  borderRadius: '8px',
                  border: '1px solid var(--hairline)',
                  background: 'transparent',
                  color: 'var(--ink)',
                  fontSize: '12.5px',
                  cursor: 'pointer',
                }}
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                onClick={() => {
                  const logToRollback = confirmRollbackLog
                  setConfirmRollbackLog(null)
                  onRollback(logToRollback)
                }}
                disabled={rollingBackId === confirmRollbackLog.id}
                style={{
                  padding: '7px 16px',
                  borderRadius: '8px',
                  border: 'none',
                  background: 'var(--error, #ef4444)',
                  color: '#fff',
                  fontSize: '12.5px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {rollingBackId === confirmRollbackLog.id ? t('common.loading') : 'Confirmar Reversão'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* History Log List */}
      {loading ? (
        <p style={{ color: 'var(--muted)', fontSize: '12.5px', textAlign: 'center', padding: '16px 0', margin: 0 }}>
          {t('common.loading')}
        </p>
      ) : logs.length === 0 ? (
        <div
          style={{
            textAlign: 'center',
            padding: '24px 16px',
            border: '1px dashed var(--hairline)',
            borderRadius: '10px',
            color: 'var(--muted)',
          }}
        >
          <Moon size={24} style={{ opacity: 0.3, marginBottom: '6px' }} />
          <p style={{ margin: 0, fontSize: '12.5px' }}>{t('memory.dreamEmptyLogs')}</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {logs.map((log) => {
            const noise =
              log.facts_before > 0
                ? Math.max(
                    0,
                    Math.round(((log.facts_before - log.facts_after) / log.facts_before) * 100)
                  )
                : 0

            return (
              <div
                key={log.id}
                style={{
                  background: 'var(--surface-soft)',
                  border: '1px solid var(--hairline)',
                  borderRadius: '10px',
                  padding: '12px 14px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                }}
              >
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
                    <span
                      style={{
                        fontSize: '12.5px',
                        fontWeight: 600,
                        color: 'var(--ink)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '4px',
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
                    >
                      {log.provider_id} · {log.model_id}
                    </span>
                    {log.status === 'rolled_back' && (
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 700,
                          borderRadius: '4px',
                          padding: '1px 6px',
                          background: 'rgba(239, 68, 68, 0.1)',
                          color: 'var(--error, #ef4444)',
                        }}
                      >
                        REVERTIDO
                      </span>
                    )}
                  </div>

                  {/* Rollback Button / Status Pill */}
                  <div>
                    {log.can_rollback ? (
                      <button
                        type="button"
                        onClick={() => setConfirmRollbackLog(log)}
                        disabled={rollingBackId === log.id || isLiveRunning}
                        title={t('memory.dreamRollbackBtn')}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '4px 10px',
                          borderRadius: '6px',
                          border: '1px solid var(--hairline)',
                          background: 'var(--canvas)',
                          color: 'var(--error, #ef4444)',
                          fontSize: '11px',
                          fontWeight: 600,
                          cursor: 'pointer',
                        }}
                      >
                        <RotateCcw size={11} />
                        {rollingBackId === log.id ? t('common.loading') : t('memory.dreamRollbackBtn')}
                      </button>
                    ) : !log.snapshot_id ? (
                      <span
                        title={t('memory.dreamSnapshotExpiredTooltip')}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                          fontSize: '10.5px',
                          color: 'var(--muted)',
                          background: 'var(--surface-card)',
                          padding: '2px 7px',
                          borderRadius: '4px',
                        }}
                      >
                        <HelpCircle size={10} />
                        {t('memory.dreamSnapshotExpired')}
                      </span>
                    ) : log.status === 'rolled_back' ? null : (
                      <span
                        title={t('memory.dreamRollbackTooltip')}
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '3px',
                          fontSize: '10.5px',
                          color: 'var(--muted-soft)',
                          background: 'var(--surface-card)',
                          padding: '2px 7px',
                          borderRadius: '4px',
                        }}
                      >
                        <ShieldAlert size={10} />
                        {t('memory.dreamRollbackBlocked')}
                      </span>
                    )}
                  </div>
                </div>

                {/* Metrics Breakdown */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--primary)' }}>
                    {log.facts_before} fatos ➔ {log.facts_after} consolidados (-{noise}% de ruído)
                  </span>
                  {log.facts_merged > 0 && (
                    <span
                      style={{
                        fontSize: '10.5px',
                        color: 'var(--muted)',
                        background: 'var(--surface-card)',
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
                      padding: '1px 6px',
                      borderRadius: '4px',
                    }}
                  >
                    0 fixados alterados
                  </span>
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
                    }}
                  >
                    "{log.summary_notes}"
                  </p>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
