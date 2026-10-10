import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Sparkles, CheckCircle2, RefreshCw, Archive, Check, ArrowRight, Layers, ShieldCheck } from 'lucide-react'
import type { DreamPreviewResponse } from '../api/client'

interface DreamPreviewModalProps {
  isOpen: boolean
  preview: DreamPreviewResponse | null
  loading: boolean
  applying: boolean
  onClose: () => void
  onApply: () => void
}

type TabType = 'merge' | 'supersede' | 'archive' | 'keep'

export function DreamPreviewModal({
  isOpen,
  preview,
  loading,
  applying,
  onClose,
  onApply,
}: DreamPreviewModalProps) {
  const { t } = useTranslation()
  const [activeTab, setActiveTab] = useState<TabType>('merge')

  if (!isOpen) return null

  const operations = preview?.operations || []
  const merges = operations.filter((op) => op.action === 'merge')
  const supersedes = operations.filter((op) => op.action === 'supersede')
  const archives = operations.filter((op) => op.action === 'archive')
  const keeps = operations.filter((op) => op.action === 'keep')

  const noiseReduction =
    preview && preview.facts_before > 0
      ? Math.max(
          0,
          Math.round(
            ((preview.facts_before - preview.projected_active) / preview.facts_before) * 100
          )
        )
      : 0

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
        padding: '20px',
        backdropFilter: 'blur(3px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--canvas)',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '740px',
          maxHeight: '88vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 24px 64px rgba(0,0,0,0.35)',
          border: '1px solid var(--hairline)',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 22px',
            borderBottom: '1px solid var(--hairline)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'var(--surface-soft)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: '8px',
                background: 'rgba(204, 120, 92, 0.12)',
                color: 'var(--primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Sparkles size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--ink)' }}>
                {t('memory.dreamPreviewTitle')}
              </h3>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--muted)' }}>
                {t('memory.dreamPreviewDesc')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={applying}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--muted)',
              padding: '6px',
              borderRadius: '6px',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '18px 22px' }}>
          {loading ? (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--muted)' }}>
              <RefreshCw size={28} className="spin-animation" style={{ opacity: 0.6, marginBottom: 12 }} />
              <p style={{ margin: 0, fontSize: '13.5px' }}>{t('memory.dreamRunning')}</p>
            </div>
          ) : preview ? (
            <>
              {/* Telemetry Stats Bar */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                  gap: '10px',
                  marginBottom: '16px',
                }}
              >
                <div
                  style={{
                    background: 'var(--surface-card)',
                    border: '1px solid var(--hairline)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  }}
                >
                  <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Antes</div>
                  <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--ink)', marginTop: 2 }}>
                    {preview.facts_before} fatos
                  </div>
                </div>
                <div
                  style={{
                    background: 'var(--surface-card)',
                    border: '1px solid var(--hairline)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  }}
                >
                  <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Depois (Estimado)</div>
                  <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--primary)', marginTop: 2 }}>
                    {preview.projected_active} fatos
                  </div>
                </div>
                <div
                  style={{
                    background: 'var(--surface-card)',
                    border: '1px solid var(--hairline)',
                    borderRadius: '10px',
                    padding: '10px 14px',
                  }}
                >
                  <div style={{ fontSize: '11px', color: 'var(--muted)' }}>Redução de Ruído</div>
                  <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--success, #22c55e)', marginTop: 2 }}>
                    -{noiseReduction}%
                  </div>
                </div>
              </div>

              {/* Summary of changes */}
              {preview.summary_of_changes && (
                <div
                  style={{
                    background: 'var(--surface-soft)',
                    border: '1px solid var(--hairline)',
                    borderRadius: '10px',
                    padding: '12px 14px',
                    marginBottom: '16px',
                    fontSize: '12.5px',
                    color: 'var(--body)',
                    lineHeight: 1.5,
                  }}
                >
                  <strong>Resumo da análise:</strong> {preview.summary_of_changes}
                </div>
              )}

              {/* Tabs */}
              <div
                style={{
                  display: 'flex',
                  gap: '6px',
                  borderBottom: '1px solid var(--hairline)',
                  marginBottom: '14px',
                  overflowX: 'auto',
                }}
              >
                <button
                  type="button"
                  onClick={() => setActiveTab('merge')}
                  style={{
                    padding: '8px 12px',
                    border: 'none',
                    borderBottom: activeTab === 'merge' ? '2px solid var(--primary)' : '2px solid transparent',
                    background: 'transparent',
                    color: activeTab === 'merge' ? 'var(--primary)' : 'var(--muted)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <Layers size={14} />
                  {t('memory.dreamPreviewTabMerge', { count: merges.length })}
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('supersede')}
                  style={{
                    padding: '8px 12px',
                    border: 'none',
                    borderBottom: activeTab === 'supersede' ? '2px solid var(--primary)' : '2px solid transparent',
                    background: 'transparent',
                    color: activeTab === 'supersede' ? 'var(--primary)' : 'var(--muted)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <RefreshCw size={14} />
                  {t('memory.dreamPreviewTabSupersede', { count: supersedes.length })}
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('archive')}
                  style={{
                    padding: '8px 12px',
                    border: 'none',
                    borderBottom: activeTab === 'archive' ? '2px solid var(--primary)' : '2px solid transparent',
                    background: 'transparent',
                    color: activeTab === 'archive' ? 'var(--primary)' : 'var(--muted)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <Archive size={14} />
                  {t('memory.dreamPreviewTabArchive', { count: archives.length })}
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('keep')}
                  style={{
                    padding: '8px 12px',
                    border: 'none',
                    borderBottom: activeTab === 'keep' ? '2px solid var(--primary)' : '2px solid transparent',
                    background: 'transparent',
                    color: activeTab === 'keep' ? 'var(--primary)' : 'var(--muted)',
                    fontSize: '12.5px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                  }}
                >
                  <Check size={14} />
                  {t('memory.dreamPreviewTabKeep', { count: keeps.length })}
                </button>
              </div>

              {/* Tab Content List */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {activeTab === 'merge' && merges.length === 0 && (
                  <p style={{ color: 'var(--muted)', fontSize: '13px', textAlign: 'center', padding: '24px 0' }}>
                    Nenhuma fusão proposta neste ciclo.
                  </p>
                )}
                {activeTab === 'merge' &&
                  merges.map((op, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-card)',
                        border: '1px solid var(--hairline)',
                        borderRadius: '10px',
                        padding: '12px 14px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                        <span
                          style={{
                            fontSize: '10.5px',
                            fontWeight: 700,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: 'rgba(34, 197, 94, 0.12)',
                            color: 'var(--success, #22c55e)',
                            textTransform: 'uppercase',
                          }}
                        >
                          Fusão ({op.source_fact_ids?.length || 0} fatos de origem)
                        </span>
                        {op.new_fact?.category && (
                          <span
                            style={{
                              fontSize: '10px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              background: 'var(--surface-soft)',
                              color: 'var(--muted)',
                            }}
                          >
                            {op.new_fact.category}
                          </span>
                        )}
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '8px',
                          background: 'var(--surface-soft)',
                          borderRadius: '8px',
                          padding: '10px',
                          marginBottom: '6px',
                        }}
                      >
                        <ArrowRight size={14} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>
                          {op.new_fact?.fact}
                        </div>
                      </div>
                      {op.reason && (
                        <div style={{ fontSize: '11.5px', color: 'var(--muted)', fontStyle: 'italic' }}>
                          Motivo: {op.reason}
                        </div>
                      )}
                    </div>
                  ))}

                {activeTab === 'supersede' && supersedes.length === 0 && (
                  <p style={{ color: 'var(--muted)', fontSize: '13px', textAlign: 'center', padding: '24px 0' }}>
                    Nenhuma atualização de fato proposta neste ciclo.
                  </p>
                )}
                {activeTab === 'supersede' &&
                  supersedes.map((op, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-card)',
                        border: '1px solid var(--hairline)',
                        borderRadius: '10px',
                        padding: '12px 14px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                        <span
                          style={{
                            fontSize: '10.5px',
                            fontWeight: 700,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: 'rgba(234, 179, 8, 0.12)',
                            color: 'var(--warning, #eab308)',
                            textTransform: 'uppercase',
                          }}
                        >
                          Atualização
                        </span>
                      </div>
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '8px',
                          background: 'var(--surface-soft)',
                          borderRadius: '8px',
                          padding: '10px',
                          marginBottom: '6px',
                        }}
                      >
                        <ArrowRight size={14} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: 2 }} />
                        <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>
                          {op.new_fact?.fact}
                        </div>
                      </div>
                      {op.reason && (
                        <div style={{ fontSize: '11.5px', color: 'var(--muted)', fontStyle: 'italic' }}>
                          Motivo: {op.reason}
                        </div>
                      )}
                    </div>
                  ))}

                {activeTab === 'archive' && archives.length === 0 && (
                  <p style={{ color: 'var(--muted)', fontSize: '13px', textAlign: 'center', padding: '24px 0' }}>
                    Nenhum fato a arquivar neste ciclo.
                  </p>
                )}
                {activeTab === 'archive' &&
                  archives.map((op, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-card)',
                        border: '1px solid var(--hairline)',
                        borderRadius: '10px',
                        padding: '12px 14px',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
                        <span
                          style={{
                            fontSize: '10.5px',
                            fontWeight: 700,
                            padding: '2px 6px',
                            borderRadius: '4px',
                            background: 'rgba(239, 68, 68, 0.12)',
                            color: 'var(--error, #ef4444)',
                            textTransform: 'uppercase',
                          }}
                        >
                          Arquivar (Ruído / Contradição)
                        </span>
                      </div>
                      <div style={{ fontSize: '12.5px', color: 'var(--body)', marginBottom: '4px' }}>
                        ID: {op.fact_id || (op.source_fact_ids && op.source_fact_ids[0])}
                      </div>
                      {op.reason && (
                        <div style={{ fontSize: '11.5px', color: 'var(--muted)', fontStyle: 'italic' }}>
                          Motivo: {op.reason}
                        </div>
                      )}
                    </div>
                  ))}

                {activeTab === 'keep' && keeps.length === 0 && (
                  <p style={{ color: 'var(--muted)', fontSize: '13px', textAlign: 'center', padding: '24px 0' }}>
                    Nenhum fato explicitamente listado.
                  </p>
                )}
                {activeTab === 'keep' &&
                  keeps.map((op, idx) => (
                    <div
                      key={idx}
                      style={{
                        background: 'var(--surface-card)',
                        border: '1px solid var(--hairline)',
                        borderRadius: '10px',
                        padding: '10px 14px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                      }}
                    >
                      <ShieldCheck size={14} style={{ color: 'var(--success, #22c55e)' }} />
                      <div style={{ fontSize: '12.5px', color: 'var(--body)' }}>
                        Fato preservado inalterado (ID: {op.fact_id || (op.source_fact_ids && op.source_fact_ids[0])})
                      </div>
                    </div>
                  ))}
              </div>
            </>
          ) : (
            <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '32px 0' }}>
              {t('memory.dreamPreviewEmptyOps')}
            </p>
          )}
        </div>

        {/* Footer Actions */}
        <div
          style={{
            padding: '14px 22px',
            borderTop: '1px solid var(--hairline)',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
            background: 'var(--surface-soft)',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            disabled={applying}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              border: '1px solid var(--hairline)',
              background: 'transparent',
              color: 'var(--ink)',
              fontSize: '13px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            {t('common.cancel')}
          </button>
          <button
            type="button"
            onClick={onApply}
            disabled={applying || loading || !preview}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 18px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--primary)',
              color: '#fff',
              fontSize: '13px',
              fontWeight: 600,
              cursor: applying || loading || !preview ? 'not-allowed' : 'pointer',
              opacity: applying || loading || !preview ? 0.7 : 1,
            }}
          >
            <CheckCircle2 size={15} />
            {applying ? t('memory.dreamPreviewApplying') : t('memory.dreamPreviewApplyBtn')}
          </button>
        </div>
      </div>
    </div>
  )
}
