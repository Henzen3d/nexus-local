import { useEffect, useState, useRef } from 'react'
import { RefreshCw, AlertTriangle, ShieldCheck, Terminal } from 'lucide-react'
import { api } from '../api/client'
import { useTranslation } from 'react-i18next'

interface LogStats {
  total: number
  error: number
  warning: number
  info: number
  debug: number
}

export function LogsPanel() {
  const { t } = useTranslation()
  const [stats, setStats] = useState<LogStats | null>(null)
  const [errors, setErrors] = useState<string[]>([])
  const [tailLines, setTailLines] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [filter, setFilter] = useState<'ALL' | 'ERROR' | 'WARNING' | 'INFO'>('ALL')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStats = async () => {
    try {
      const data = await api.getLogsStats()
      setStats(data)
    } catch { /* silent */ }
  }

  const fetchErrors = async () => {
    try {
      const data = await api.getLogsErrors({ hours: 24, limit: 50 })
      setErrors(data.errors || [])
    } catch { /* silent */ }
  }

  const fetchTail = async () => {
    setLoading(true)
    try {
      const data = await api.getLogsTail({ lines: 200, level: filter })
      setTailLines(data.lines || [])
    } catch { /* silent */ }
    finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStats()
    fetchErrors()
    fetchTail()
  }, [filter])

  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(() => {
        fetchStats()
        fetchErrors()
        fetchTail()
      }, 10000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [autoRefresh, filter])

  return (
    <div className="logs-monitoring-panel">
      <div className="logs-header">
        <h3 className="logs-title">
          <Terminal size={16} />
          Monitor de Logs do Sistema
        </h3>
        <div className="logs-controls">
          <select value={filter} onChange={e => setFilter(e.target.value as any)}>
            <option value="ALL">Todos</option>
            <option value="ERROR">Erros</option>
            <option value="WARNING">Warnings</option>
            <option value="INFO">Info</option>
          </select>
          <button onClick={() => { fetchStats(); fetchErrors(); fetchTail(); }} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            Atualizar
          </button>
          <label className="auto-refresh-label">
            <input type="checkbox" checked={autoRefresh} onChange={e => setAutoRefresh(e.target.checked)} />
            Auto-refresh (10s)
          </label>
        </div>
      </div>

      {stats && (
        <div className="logs-stats">
          <div className="stat-card error">
            <div className="stat-value">{stats.error}</div>
            <div className="stat-label">Erros</div>
          </div>
          <div className="stat-card warning">
            <div className="stat-value">{stats.warning}</div>
            <div className="stat-label">Warnings</div>
          </div>
          <div className="stat-card info">
            <div className="stat-value">{stats.info}</div>
            <div className="stat-label">Info</div>
          </div>
          <div className="stat-card total">
            <div className="stat-value">{stats.total}</div>
            <div className="stat-label">Total Lines</div>
          </div>
        </div>
      )}

      {errors.length > 0 && (
        <div className="logs-errors-section">
          <h4 className="logs-section-title">
            <AlertTriangle size={14} />
            Últimos Erros e Warnings
          </h4>
          <div className="logs-errors-list">
            {errors.slice(0, 10).map((err, i) => (
              <div key={i} className={`log-line ${err.includes('[ERROR]') ? 'error' : 'warning'}`}>
                {err}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="logs-tail-section">
        <h4 className="logs-section-title">
          <ShieldCheck size={14} />
          Tail de Logs ({tailLines.length} linhas)
        </h4>
        <div className="logs-terminal">
          {tailLines.length === 0 ? (
            <div className="logs-empty">Nenhum log encontrado</div>
          ) : (
            tailLines.map((line, i) => (
              <div key={i} className={`log-line ${
                line.includes('[ERROR]') ? 'error' :
                line.includes('[WARNING]') ? 'warning' :
                line.includes('[INFO]') ? 'info' : 'debug'
              }`}>
                {line}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
