import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Moon,
  Sparkles,
  Zap,
  RotateCcw,
  CheckCircle2,
  Loader2,
  ChevronDown,
  ChevronUp,
  History,
} from 'lucide-react'
import type { DreamLogApi } from '../api/client'
import { dreamStepState } from '../lib/dreamLog'
import { DreamLogCard } from './DreamLogCard'
import { DreamFullHistoryModal } from './DreamFullHistoryModal'

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
  const [isExpanded, setIsExpanded] = useState(false)
  const [isFullModalOpen, setIsFullModalOpen] = useState(false)

  const stepsList = [
    { id: 'snapshot', label: t('memory.dreamStep1') },
    { id: 'model_connect', label: t('memory.dreamStep2') },
    { id: 'analyzing', label: t('memory.dreamStep3') },
    { id: 'flash_tx', label: t('memory.dreamStep4') },
    { id: 'cache_update', label: t('memory.dreamStep5') },
  ]

  // Limite inteligente: apenas o último por padrão, até 5 se expandido
  const displayedLogs = isExpanded ? logs.slice(0, 5) : logs.slice(0, 1)

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
              const status = dreamStepState(idx, liveProgress?.step || 'snapshot')
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
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10005,
            padding: '20px',
            backdropFilter: 'blur(3px)',
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
          {/* Cards exibidos (apenas o último por padrão, até 5 se expandido) */}
          {displayedLogs.map((log, index) => (
            <DreamLogCard
              key={log.id}
              log={log}
              isLatest={index === 0}
              onRollbackClick={(l) => setConfirmRollbackLog(l)}
              rollingBackId={rollingBackId}
              isLiveRunning={isLiveRunning}
            />
          ))}

          {/* Controle de expansão: quando retraído e existem mais logs */}
          {!isExpanded && logs.length > 1 && (
            <button
              type="button"
              onClick={() => setIsExpanded(true)}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                width: '100%',
                padding: '9px 14px',
                borderRadius: '8px',
                border: '1px dashed var(--hairline)',
                background: 'var(--surface-soft)',
                color: 'var(--ink)',
                fontSize: '12px',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = 'var(--primary)'
                e.currentTarget.style.color = 'var(--primary)'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = 'var(--hairline)'
                e.currentTarget.style.color = 'var(--ink)'
              }}
            >
              <ChevronDown size={14} />
              <span>
                {t('memory.dreamJournalShowRecent', {
                  count: Math.min(4, logs.length - 1),
                  defaultValue: `Ver execuções anteriores (${Math.min(4, logs.length - 1)} mais)`,
                })}
              </span>
              <span
                style={{
                  fontSize: '10.5px',
                  padding: '1px 6px',
                  borderRadius: '10px',
                  background: 'var(--surface-card)',
                  color: 'var(--muted)',
                  border: '1px solid var(--hairline)',
                }}
              >
                +{logs.length - 1} no histórico
              </span>
            </button>
          )}

          {/* Controles de navegação: quando expandido */}
          {isExpanded && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '10px',
                marginTop: '2px',
                paddingTop: '6px',
                borderTop: '1px dashed var(--hairline)',
              }}
            >
              {/* Botão de Recolher */}
              <button
                type="button"
                onClick={() => setIsExpanded(false)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--hairline)',
                  background: 'var(--surface-soft)',
                  color: 'var(--muted)',
                  fontSize: '11.5px',
                  fontWeight: 500,
                  cursor: 'pointer',
                  transition: 'color 0.15s ease',
                }}
                onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--ink)')}
                onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--muted)')}
              >
                <ChevronUp size={13} />
                {t('memory.dreamJournalCollapse', { defaultValue: 'Recolher histórico' })}
              </button>

              {/* Botão para abrir modal completo com todos os logs */}
              {logs.length > 5 && (
                <button
                  type="button"
                  onClick={() => setIsFullModalOpen(true)}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '6px 14px',
                    borderRadius: '6px',
                    border: '1px solid rgba(204, 120, 92, 0.35)',
                    background: 'rgba(204, 120, 92, 0.08)',
                    color: 'var(--primary)',
                    fontSize: '11.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(204, 120, 92, 0.15)'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'rgba(204, 120, 92, 0.08)'
                  }}
                >
                  <History size={13} />
                  {t('memory.dreamJournalViewAllModal', {
                    total: logs.length,
                    defaultValue: `Ver histórico completo (${logs.length} consolidações)`,
                  })}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Modal Dedicado para o Histórico Completo */}
      <DreamFullHistoryModal
        isOpen={isFullModalOpen}
        logs={logs}
        onClose={() => setIsFullModalOpen(false)}
        onRollback={(log) => setConfirmRollbackLog(log)}
        rollingBackId={rollingBackId}
        isLiveRunning={isLiveRunning}
      />
    </div>
  )
}
