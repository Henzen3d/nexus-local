import { useState, useMemo, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  X,
  History,
  Search,
  Filter,
  CheckCircle2,
  RotateCcw,
  AlertCircle,
  Moon,
} from 'lucide-react'
import type { DreamLogApi } from '../api/client'
import { DreamLogCard } from './DreamLogCard'

interface DreamFullHistoryModalProps {
  isOpen: boolean
  logs: DreamLogApi[]
  onClose: () => void
  onRollback: (log: DreamLogApi) => void
  rollingBackId: string | null
  isLiveRunning: boolean
}

type StatusFilter = 'all' | 'success' | 'rolled_back' | 'failed'

export function DreamFullHistoryModal({
  isOpen,
  logs,
  onClose,
  onRollback,
  rollingBackId,
  isLiveRunning,
}: DreamFullHistoryModalProps) {
  const { t } = useTranslation()
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')

  // Fechar ao pressionar tecla ESC
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  // Filtragem combinada por busca e status
  const filteredLogs = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return logs.filter((log) => {
      // Filtro de status
      if (statusFilter === 'success' && log.status !== 'success') return false
      if (statusFilter === 'rolled_back' && log.status !== 'rolled_back') return false
      if (
        statusFilter === 'failed' &&
        log.status !== 'failed' &&
        log.status !== 'aborted_safety'
      ) {
        return false
      }

      // Filtro de texto (busca)
      if (!q) return true
      const dateStr = new Date(log.created_at).toLocaleString().toLowerCase()
      const notes = (log.summary_notes || '').toLowerCase()
      const provider = (log.provider_id || '').toLowerCase()
      const model = (log.model_id || '').toLowerCase()
      const err = (log.error_message || '').toLowerCase()

      return (
        notes.includes(q) ||
        provider.includes(q) ||
        model.includes(q) ||
        dateStr.includes(q) ||
        err.includes(q)
      )
    })
  }, [logs, searchQuery, statusFilter])

  if (!isOpen) return null

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0, 0, 0, 0.65)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10002,
        padding: '20px',
        backdropFilter: 'blur(4px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--canvas)',
          borderRadius: '16px',
          width: '100%',
          maxWidth: '780px',
          maxHeight: '88vh',
          display: 'flex',
          flexDirection: 'column',
          boxShadow: '0 24px 64px rgba(0, 0, 0, 0.4)',
          border: '1px solid var(--hairline)',
          overflow: 'hidden',
          animation: 'fadeScaleIn 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
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
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: '10px',
                background: 'rgba(204, 120, 92, 0.12)',
                color: 'var(--primary)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <History size={20} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--ink)' }}>
                {t('memory.dreamJournalFullHistoryTitle', {
                  defaultValue: 'Histórico Completo do Diário de Sonhos',
                })}
              </h3>
              <p style={{ margin: '3px 0 0', fontSize: '12px', color: 'var(--muted)' }}>
                {t('memory.dreamJournalFullHistoryDesc', {
                  defaultValue:
                    'Registro cronológico detalhado de todos os ciclos de consolidação de memória executados.',
                })}{' '}
                ({logs.length} no total)
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar modal"
            style={{
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--muted)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '6px',
              borderRadius: '6px',
              transition: 'background 0.15s ease',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Filters and Search Bar */}
        <div
          style={{
            padding: '12px 22px',
            borderBottom: '1px solid var(--hairline)',
            background: 'var(--surface-card)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '10px',
          }}
        >
          {/* Campo de Busca */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              background: 'var(--canvas)',
              border: '1px solid var(--hairline)',
              borderRadius: '8px',
              padding: '6px 12px',
              flex: '1 1 240px',
              maxWidth: '380px',
            }}
          >
            <Search size={14} style={{ color: 'var(--muted)' }} />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('memory.dreamJournalSearchPlaceholder', {
                defaultValue: 'Buscar por modelo, provedor, data ou resumo...',
              })}
              style={{
                background: 'transparent',
                border: 'none',
                outline: 'none',
                fontSize: '12.5px',
                color: 'var(--ink)',
                width: '100%',
              }}
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                style={{
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                  color: 'var(--muted)',
                }}
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Filtros de Status */}
          <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
            <span style={{ fontSize: '11px', color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Filter size={11} />
            </span>
            {(
              [
                { id: 'all', label: t('memory.dreamJournalFilterAll', { defaultValue: 'Todos' }) },
                { id: 'success', label: t('memory.dreamJournalFilterSuccess', { defaultValue: 'Sucesso' }) },
                { id: 'rolled_back', label: t('memory.dreamJournalFilterRolledBack', { defaultValue: 'Revertidos' }) },
                { id: 'failed', label: t('memory.dreamJournalFilterFailed', { defaultValue: 'Falhas' }) },
              ] as const
            ).map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setStatusFilter(f.id)}
                style={{
                  fontSize: '11.5px',
                  fontWeight: statusFilter === f.id ? 600 : 400,
                  padding: '4px 9px',
                  borderRadius: '6px',
                  border: statusFilter === f.id ? '1px solid rgba(204, 120, 92, 0.4)' : '1px solid var(--hairline)',
                  background: statusFilter === f.id ? 'rgba(204, 120, 92, 0.12)' : 'var(--canvas)',
                  color: statusFilter === f.id ? 'var(--primary)' : 'var(--muted)',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* Scrollable List of Logs */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px 22px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
          }}
        >
          {filteredLogs.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '36px 16px',
                border: '1px dashed var(--hairline)',
                borderRadius: '10px',
                color: 'var(--muted)',
              }}
            >
              <Moon size={28} style={{ opacity: 0.3, marginBottom: '8px' }} />
              <p style={{ margin: 0, fontSize: '13px' }}>
                {t('memory.dreamJournalNoFilterResults', {
                  defaultValue: 'Nenhum ciclo de consolidação corresponde aos filtros aplicados.',
                })}
              </p>
              {(searchQuery || statusFilter !== 'all') && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchQuery('')
                    setStatusFilter('all')
                  }}
                  style={{
                    marginTop: '10px',
                    fontSize: '12px',
                    color: 'var(--primary)',
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  Limpar filtros
                </button>
              )}
            </div>
          ) : (
            filteredLogs.map((log, index) => (
              <DreamLogCard
                key={log.id}
                log={log}
                isLatest={index === 0 && !searchQuery && statusFilter === 'all'}
                onRollbackClick={onRollback}
                rollingBackId={rollingBackId}
                isLiveRunning={isLiveRunning}
              />
            ))
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 22px',
            borderTop: '1px solid var(--hairline)',
            background: 'var(--surface-soft)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontSize: '12px', color: 'var(--muted)' }}>
            {t('memory.dreamJournalShowingCount', {
              shown: filteredLogs.length,
              total: logs.length,
              defaultValue: `Exibindo ${filteredLogs.length} de ${logs.length} consolidações`,
            })}
          </span>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '7px 18px',
              borderRadius: '8px',
              border: '1px solid var(--hairline)',
              background: 'var(--canvas)',
              color: 'var(--ink)',
              fontSize: '12.5px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            {t('common.close', { defaultValue: 'Fechar' })}
          </button>
        </div>
      </div>
    </div>
  )
}
