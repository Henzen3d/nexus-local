import { useCallback, useEffect, useMemo, useState } from 'react'
import { Save, Sparkles, ToggleLeft, ToggleRight, RefreshCw, Activity, AlertTriangle, Power } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type {
  Provider,
  ProactiveAdminConfig,
  ProactiveAdminConfigUpdate,
  ProactiveAdminStats,
  ProactiveLogsResponse,
  ProactiveStatus,
} from '../types'

// ─── ProactiveAdminSettings — painel admin (F4.4) ────────────────────────────
// Config global em `meta` (efeito imediato, sem reiniciar), kill-switch com
// confirmação, estatísticas 24h/7d + latências p95 e logs anonimizados
// (nunca o texto da mensagem do usuário nem o texto sintetizado).

type NumericField =
  | 'max_per_hour_conv'
  | 'max_per_day_user'
  | 'topic_cooldown_hours'
  | 'max_pending'
  | 'concurrency'
  | 'total_timeout_s'
  | 'research_timeout_s'
  | 'synth_timeout_s'
  | 'expiry_news_hours'
  | 'expiry_default_days'

const NUMERIC_FIELDS: NumericField[] = [
  'max_per_hour_conv',
  'max_per_day_user',
  'topic_cooldown_hours',
  'max_pending',
  'concurrency',
  'total_timeout_s',
  'research_timeout_s',
  'synth_timeout_s',
  'expiry_news_hours',
  'expiry_default_days',
]

const STATUS_FILTERS: Array<ProactiveStatus | ''> = [
  '',
  'detected',
  'researching',
  'ready',
  'delivered',
  'seen',
  'dismissed',
  'blocked',
  'expired',
  'failed',
]

const LOGS_PAGE = 50

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`
}

export function ProactiveAdminSettings() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<ProactiveAdminConfig | null>(null)
  const [draft, setDraft] = useState<ProactiveAdminConfig | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [stats, setStats] = useState<ProactiveAdminStats | null>(null)
  const [logs, setLogs] = useState<ProactiveLogsResponse | null>(null)
  const [logStatus, setLogStatus] = useState<ProactiveStatus | ''>('')
  const [logOffset, setLogOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirmKill, setConfirmKill] = useState(false)

  const loadConfig = useCallback(async () => {
    const [cfg, provs] = await Promise.all([api.getProactiveAdminConfig(), api.getProviders()])
    setConfig(cfg)
    setDraft(cfg)
    setProviders(provs.filter((p) => p.has_key && p.enabled))
  }, [])

  const loadStats = useCallback(async () => {
    try {
      setStats(await api.getProactiveAdminStats())
    } catch (e) {
      console.warn('[proactive-admin] stats:', e)
    }
  }, [])

  const loadLogs = useCallback(async (offset: number, status: ProactiveStatus | '') => {
    try {
      setLogs(await api.getProactiveLogs({ limit: LOGS_PAGE, offset, status: status || undefined }))
    } catch (e) {
      console.warn('[proactive-admin] logs:', e)
    }
  }, [])

  useEffect(() => {
    let alive = true
    ;(async () => {
      try {
        await loadConfig()
        await Promise.all([loadStats(), loadLogs(0, '')])
      } catch (e) {
        console.error(e)
        if (alive) setError(t('proactive.admin.loadError'))
      } finally {
        if (alive) setLoading(false)
      }
    })()
    return () => {
      alive = false
    }
  }, [loadConfig, loadStats, loadLogs, t])

  const dirty = useMemo(() => {
    if (!config || !draft) return false
    return (Object.keys(draft) as Array<keyof ProactiveAdminConfig>).some(
      (k) => k !== 'limits' && k !== 'kill_switch' && draft[k] !== config[k],
    )
  }, [config, draft])

  const apply = async (patch: ProactiveAdminConfigUpdate) => {
    setSaving(true)
    setError(null)
    try {
      const res = await api.updateProactiveAdminConfig(patch)
      setConfig(res)
      setDraft(res)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      void loadStats()
      return res
    } catch (e) {
      console.error(e)
      setError(e instanceof Error && e.message ? e.message : t('proactive.admin.saveError'))
      return null
    } finally {
      setSaving(false)
    }
  }

  const save = async () => {
    if (!config || !draft) return
    const patch: ProactiveAdminConfigUpdate = {}
    for (const k of Object.keys(draft) as Array<keyof ProactiveAdminConfig>) {
      if (k === 'limits' || k === 'kill_switch' || k === 'enabled_global') continue
      if (draft[k] !== config[k]) (patch as Record<string, unknown>)[k] = draft[k] ?? ''
    }
    if (Object.keys(patch).length === 0) return
    await apply(patch)
  }

  const toggleGlobal = async () => {
    if (!config) return
    if (config.enabled_global) {
      setConfirmKill(true)
      return
    }
    await apply({ enabled_global: true })
  }

  const confirmKillSwitch = async () => {
    setConfirmKill(false)
    await apply({ enabled_global: false })
  }

  const changeLogStatus = (status: ProactiveStatus | '') => {
    setLogStatus(status)
    setLogOffset(0)
    void loadLogs(0, status)
  }

  const changeLogPage = (delta: number) => {
    const next = Math.max(0, logOffset + delta)
    setLogOffset(next)
    void loadLogs(next, logStatus)
  }

  if (loading) return null
  if (!config || !draft) {
    return (
      <div className="enhancer-settings proactive-admin">
        <div className="enhancer-header">
          <Sparkles size={20} />
          <div>
            <h3>{t('proactive.admin.title')}</h3>
            <p>{error || t('proactive.admin.loadError')}</p>
          </div>
        </div>
      </div>
    )
  }

  const detectorProvider = providers.find((p) => p.id === draft.detector_provider_id)
  const synthProvider = providers.find((p) => p.id === draft.synth_provider_id)
  const detectorModels = detectorProvider?.models.filter((m) => m.enabled) ?? []
  const synthModels = synthProvider?.models.filter((m) => m.enabled) ?? []
  const limits = config.limits || {}
  const w24 = stats?.windows['24h']
  const w7 = stats?.windows['7d']

  return (
    <div className="enhancer-settings proactive-admin" data-testid="proactive-admin">
      <div className="enhancer-header">
        <Sparkles size={20} />
        <div>
          <h3>{t('proactive.admin.title')}</h3>
          <p>{t('proactive.admin.desc')}</p>
        </div>
      </div>

      {/* Kill-switch */}
      <div className={`enhancer-toggle-row proactive-admin-kill ${config.enabled_global ? '' : 'off'}`}>
        <div className="enhancer-toggle-info">
          <span>
            <Power size={14} aria-hidden="true" /> {t('proactive.admin.globalToggle')}
          </span>
          <small>{config.enabled_global ? t('proactive.admin.globalOnHint') : t('proactive.admin.globalOffHint')}</small>
          {config.kill_switch && (
            <small className="proactive-admin-kill-summary">
              {t('proactive.admin.killSummary', { cancelled: config.kill_switch.cancelled, expired: config.kill_switch.expired })}
            </small>
          )}
        </div>
        <button
          type="button"
          className={`toggle-btn ${config.enabled_global ? 'on' : 'off'}`}
          onClick={() => void toggleGlobal()}
          disabled={saving}
          aria-pressed={config.enabled_global}
        >
          {config.enabled_global ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.enabled_global ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {confirmKill && (
        <div className="proactive-admin-confirm" role="alertdialog" aria-labelledby="proactive-kill-title">
          <AlertTriangle size={18} aria-hidden="true" />
          <div>
            <strong id="proactive-kill-title">{t('proactive.admin.killConfirmTitle')}</strong>
            <p>{t('proactive.admin.killConfirmBody')}</p>
            <div className="proactive-admin-confirm-actions">
              <button type="button" className="btn btn-danger" onClick={() => void confirmKillSwitch()} disabled={saving}>
                {t('proactive.admin.killConfirmYes')}
              </button>
              <button type="button" className="btn btn-ghost" onClick={() => setConfirmKill(false)}>
                {t('common.cancel')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modelos */}
      <div className="proactive-admin-grid">
        <div className="enhancer-field">
          <label>{t('proactive.admin.detectorProvider')}</label>
          <select
            value={draft.detector_provider_id ?? ''}
            onChange={(e) => setDraft({ ...draft, detector_provider_id: e.target.value || null, detector_model_id: null })}
          >
            <option value="">{t('proactive.admin.useChatModel')}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="enhancer-field">
          <label>{t('proactive.admin.detectorModel')}</label>
          <select
            value={draft.detector_model_id ?? ''}
            onChange={(e) => setDraft({ ...draft, detector_model_id: e.target.value || null })}
            disabled={!draft.detector_provider_id}
          >
            <option value="">{!draft.detector_provider_id ? t('toolsSettings.selectProviderFirst') : t('toolsSettings.selectModel')}</option>
            {detectorModels.map((m) => (
              <option key={m.id} value={m.id}>{m.display_name}</option>
            ))}
          </select>
        </div>
        <div className="enhancer-field">
          <label>{t('proactive.admin.synthProvider')}</label>
          <select
            value={draft.synth_provider_id ?? ''}
            onChange={(e) => setDraft({ ...draft, synth_provider_id: e.target.value || null, synth_model_id: null })}
          >
            <option value="">{t('proactive.admin.sameAsDetector')}</option>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="enhancer-field">
          <label>{t('proactive.admin.synthModel')}</label>
          <select
            value={draft.synth_model_id ?? ''}
            onChange={(e) => setDraft({ ...draft, synth_model_id: e.target.value || null })}
            disabled={!draft.synth_provider_id}
          >
            <option value="">{!draft.synth_provider_id ? t('toolsSettings.selectProviderFirst') : t('toolsSettings.selectModel')}</option>
            {synthModels.map((m) => (
              <option key={m.id} value={m.id}>{m.display_name}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('proactive.admin.fallback')}</span>
          <small>{t('proactive.admin.fallbackDesc')}</small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${draft.allow_chat_model_fallback ? 'on' : 'off'}`}
          onClick={() => setDraft({ ...draft, allow_chat_model_fallback: !draft.allow_chat_model_fallback })}
          aria-pressed={draft.allow_chat_model_fallback}
        >
          {draft.allow_chat_model_fallback ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {draft.allow_chat_model_fallback ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {/* Limites e tempos */}
      <div className="proactive-admin-grid">
        {NUMERIC_FIELDS.map((field) => {
          const range = limits[field]
          const isFloat = field.endsWith('_s')
          return (
            <div className="enhancer-field" key={field}>
              <label>
                {t(`proactive.admin.field.${field}`)}
                {range && <span className="proactive-admin-range"> {range[0]}–{range[1]}</span>}
              </label>
              <input
                type="number"
                className="proactive-admin-input"
                value={draft[field]}
                min={range?.[0]}
                max={range?.[1]}
                step={isFloat ? 0.5 : 1}
                onChange={(e) => {
                  const v = isFloat ? parseFloat(e.target.value) : parseInt(e.target.value, 10)
                  setDraft({ ...draft, [field]: Number.isFinite(v) ? v : draft[field] })
                }}
              />
            </div>
          )
        })}
      </div>

      {error && (
        <div className="proactive-admin-error" role="alert">
          <AlertTriangle size={14} aria-hidden="true" /> {error}
        </div>
      )}

      <div className="enhancer-actions">
        <button type="button" className={`save-btn ${saved ? 'saved' : ''}`} onClick={() => void save()} disabled={!dirty || saving}>
          <Save size={14} />
          {saved ? t('proactive.admin.saved') : t('common.save')}
        </button>
        <small className="proactive-field-help">{t('proactive.admin.saveHint')}</small>
      </div>

      {/* Estatísticas */}
      <div className="proactive-admin-section-head">
        <h4>
          <Activity size={16} aria-hidden="true" /> {t('proactive.admin.statsTitle')}
        </h4>
        <button type="button" className="proactive-action" onClick={() => void loadStats()}>
          <RefreshCw size={14} aria-hidden="true" /> {t('proactive.admin.refresh')}
        </button>
      </div>
      {stats && w24 && w7 ? (
        <>
          <div className="proactive-admin-cards">
            <StatCard label={t('proactive.admin.stat.total24h')} value={String(w24.total)} sub={t('proactive.admin.stat.total7d', { n: w7.total })} />
            <StatCard label={t('proactive.admin.stat.delivered')} value={String(w24.delivered)} sub={`7d: ${w7.delivered}`} />
            <StatCard label={t('proactive.admin.stat.knowMoreRate')} value={pct(w24.know_more_rate)} sub={`7d: ${pct(w7.know_more_rate)}`} />
            <StatCard label={t('proactive.admin.stat.blockedRate')} value={pct(w24.blocked_rate)} sub={`7d: ${pct(w7.blocked_rate)}`} />
            <StatCard label={t('proactive.admin.stat.failureRate')} value={pct(w24.failure_rate)} sub={`7d: ${pct(w7.failure_rate)}`} />
            <StatCard label={t('proactive.admin.stat.usersEnabled')} value={String(stats.users_enabled)} sub={t('proactive.admin.stat.usersActive', { n: w24.users })} />
            <StatCard label={t('proactive.admin.stat.pendingNow')} value={String(stats.pending_now)} sub={t('proactive.admin.stat.inFlight', { n: stats.runtime.tasks_in_flight })} />
            <StatCard
              label={t('proactive.admin.stat.latencyP95')}
              value={ms(stats.latency.total_p95_ms)}
              sub={`${t('proactive.admin.stat.research')} ${ms(stats.latency.research_p95_ms)} · ${t('proactive.admin.stat.synth')} ${ms(stats.latency.synth_p95_ms)}`}
            />
          </div>
          <div className="proactive-admin-status-row">
            {(Object.keys(w7.by_status) as ProactiveStatus[]).map((st) => (
              <span key={st} className={`proactive-admin-status-pill status-${st}`}>
                {t(`proactive.admin.status.${st}`)} <strong>{w7.by_status[st]}</strong>
              </span>
            ))}
          </div>
        </>
      ) : (
        <small className="proactive-field-help">{t('proactive.admin.statsEmpty')}</small>
      )}

      {/* Logs anonimizados */}
      <div className="proactive-admin-section-head">
        <h4>{t('proactive.admin.logsTitle')}</h4>
        <div className="proactive-admin-logs-controls">
          <select value={logStatus} onChange={(e) => changeLogStatus(e.target.value as ProactiveStatus | '')} aria-label={t('proactive.admin.logsFilter')}>
            {STATUS_FILTERS.map((st) => (
              <option key={st || 'all'} value={st}>
                {st ? t(`proactive.admin.status.${st}`) : t('proactive.admin.logsAll')}
              </option>
            ))}
          </select>
          <button type="button" className="proactive-action" onClick={() => void loadLogs(logOffset, logStatus)}>
            <RefreshCw size={14} aria-hidden="true" /> {t('proactive.admin.refresh')}
          </button>
        </div>
      </div>
      <p className="proactive-field-help">{t('proactive.admin.logsPrivacy')}</p>
      {logs && logs.rows.length > 0 ? (
        <>
          <div className="proactive-admin-table-wrap">
            <table className="proactive-admin-table">
              <thead>
                <tr>
                  <th>{t('proactive.admin.col.when')}</th>
                  <th>{t('proactive.admin.col.user')}</th>
                  <th>{t('proactive.admin.col.category')}</th>
                  <th>{t('proactive.admin.col.topic')}</th>
                  <th>{t('proactive.admin.col.status')}</th>
                  <th>{t('proactive.admin.col.channel')}</th>
                  <th>{t('proactive.admin.col.latency')}</th>
                  <th>{t('proactive.admin.col.error')}</th>
                </tr>
              </thead>
              <tbody>
                {logs.rows.map((row) => (
                  <tr key={row.id}>
                    <td title={row.created_at}>{new Date(row.created_at.endsWith('Z') ? row.created_at : `${row.created_at}Z`).toLocaleString()}</td>
                    <td>{row.username}</td>
                    <td>{t(`proactive.category.${row.category}`, { defaultValue: row.category })}</td>
                    <td className="proactive-admin-topic" title={row.topic}>{row.topic}</td>
                    <td><span className={`proactive-admin-status-pill status-${row.status}`}>{t(`proactive.admin.status.${row.status}`)}</span></td>
                    <td>{row.channel || '—'}</td>
                    <td title={`${ms(row.latency_detect_ms)} / ${ms(row.latency_research_ms)} / ${ms(row.latency_synth_ms)}`}>
                      {ms((row.latency_detect_ms || 0) + (row.latency_research_ms || 0) + (row.latency_synth_ms || 0) || null)}
                    </td>
                    <td>{row.error_code || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="proactive-admin-pager">
            <button type="button" className="proactive-action" onClick={() => changeLogPage(-LOGS_PAGE)} disabled={logOffset === 0}>
              {t('proactive.admin.prev')}
            </button>
            <span>{t('proactive.admin.logsPage', { from: logOffset + 1, to: Math.min(logOffset + logs.rows.length, logs.total), total: logs.total })}</span>
            <button type="button" className="proactive-action" onClick={() => changeLogPage(LOGS_PAGE)} disabled={logOffset + LOGS_PAGE >= logs.total}>
              {t('proactive.admin.next')}
            </button>
          </div>
        </>
      ) : (
        <small className="proactive-field-help">{t('proactive.admin.logsEmpty')}</small>
      )}
    </div>
  )
}

function StatCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="proactive-admin-card">
      <span className="proactive-admin-card-label">{label}</span>
      <strong className="proactive-admin-card-value">{value}</strong>
      {sub && <small className="proactive-admin-card-sub">{sub}</small>}
    </div>
  )
}
