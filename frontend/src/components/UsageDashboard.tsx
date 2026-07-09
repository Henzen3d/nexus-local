import { useEffect, useState } from 'react'
import { Activity, BarChart3, Clock, AlertTriangle, Layers, Calendar } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
} from 'recharts'

export function UsageDashboard() {
  const { t, i18n } = useTranslation()
  const [stats, setStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [failovers, setFailovers] = useState<any[]>([])
  const [quotas, setQuotas] = useState<any[]>([])
  const [days, setDays] = useState(30)

  const load = async () => {
    try {
      setLoading(true)
      const [statsData, failoversData, quotasData] = await Promise.all([
        api.getDashboardStats(days),
        api.getDashboardFailovers(15),
        api.getDashboardQuotas()
      ])
      setStats(statsData)
      setFailovers(failoversData)
      setQuotas(quotasData)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [days])

  if (loading && !stats) {
    return <div className="text-muted-soft">{t('dashboard.loading')}</div>
  }

  if (!stats) {
    return <div className="text-muted-soft">{t('dashboard.loadError')}</div>
  }

  return (
    <div className="usage-dashboard">
      <div className="dashboard-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={20} className="text-primary" />
          <div>
            <h3 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>{t('dashboard.title')}</h3>
            <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted)' }}>{t('dashboard.desc')}</p>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Calendar size={14} className="text-muted" />
          <select 
            value={days} 
            onChange={e => setDays(Number(e.target.value))}
            style={{ padding: '6px 12px', borderRadius: 'var(--radius-md)', border: '1px solid var(--hairline)', background: 'var(--surface)', color: 'var(--ink)', fontSize: '13px', outline: 'none' }}
          >
            <option value={7}>{t('admin.lastDays', { count: 7, defaultValue: 'Últimos 7 dias' })}</option>
            <option value={15}>{t('admin.lastDays', { count: 15, defaultValue: 'Últimos 15 dias' })}</option>
            <option value={30}>{t('admin.lastDays', { count: 30, defaultValue: 'Últimos 30 dias' })}</option>
            <option value={90}>{t('admin.lastDays', { count: 90, defaultValue: 'Últimos 90 dias' })}</option>
          </select>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px' }}>
        <div style={{ background: 'var(--surface-soft)', padding: '16px', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <BarChart3 size={14} /> {t('dashboard.totalCalls')}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--ink)' }}>
            {stats.total_calls.toLocaleString()}
          </div>
        </div>
        <div style={{ background: 'var(--surface-soft)', padding: '16px', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <AlertTriangle size={14} /> {t('dashboard.failovers')}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--ink)' }}>
            {stats.total_failovers.toLocaleString()}
          </div>
        </div>
        <div style={{ background: 'var(--surface-soft)', padding: '16px', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
          <div style={{ fontSize: '12px', color: 'var(--muted)', fontWeight: 600, textTransform: 'uppercase', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Layers size={14} /> {t('dashboard.differentModels')}
          </div>
          <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--ink)' }}>
            {stats.calls_by_model.length}
          </div>
        </div>
      </div>

      {/* Main Chart */}
      <div className="admin-section" style={{ marginBottom: '24px', padding: '16px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
        <h4 style={{ margin: '0 0 16px 0', fontSize: '14px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Clock size={14} /> {t('dashboard.dailyUsage')}
        </h4>
        <div style={{ height: '250px', width: '100%' }}>
          {stats.calls_by_day.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stats.calls_by_day} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" vertical={false} />
                <XAxis dataKey="day" stroke="var(--muted)" fontSize={11} tickMargin={8} tickFormatter={(val: any) => {
                  const d = new Date(val); return `${d.getDate()}/${d.getMonth()+1}`
                }}/>
                <YAxis stroke="var(--muted)" fontSize={11} tickMargin={8} allowDecimals={false} />
                <RechartsTooltip 
                  contentStyle={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: '6px', fontSize: '12px' }}
                  labelStyle={{ fontWeight: 600, marginBottom: '4px' }}
                />
                <Line type="monotone" dataKey="count" name={t('dashboard.requests')} stroke="var(--primary)" strokeWidth={2} dot={{ r: 3, fill: 'var(--primary)' }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted-soft)' }}>
              {t('dashboard.noDataPeriod')}
            </div>
          )}
        </div>
      </div>

      {/* Breakdown grids */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '24px' }}>
        {/* By Provider */}
        <div className="admin-section" style={{ padding: '16px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
          <h4 style={{ margin: '0 0 16px 0', fontSize: '14px', fontWeight: 600 }}>{t('dashboard.usageByProvider')}</h4>
          <div style={{ height: '200px', width: '100%' }}>
            {stats.calls_by_provider.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.calls_by_provider} layout="vertical" margin={{ top: 0, right: 20, left: 20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" horizontal={false} />
                  <XAxis type="number" stroke="var(--muted)" fontSize={11} allowDecimals={false} />
                  <YAxis dataKey="provider_id" type="category" stroke="var(--muted)" fontSize={11} width={80} />
                  <RechartsTooltip 
                    cursor={{ fill: 'var(--surface-soft)' }}
                    contentStyle={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: '6px', fontSize: '12px' }}
                  />
                  <Bar dataKey="count" name={t('dashboard.requests')} fill="var(--cyan)" radius={[0, 4, 4, 0]} barSize={20} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted-soft)' }}>
                {t('dashboard.noData')}
              </div>
            )}
          </div>
        </div>

        {/* By Model */}
        <div className="admin-section" style={{ padding: '16px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
          <h4 style={{ margin: '0 0 16px 0', fontSize: '14px', fontWeight: 600 }}>{t('dashboard.topModels')}</h4>
          <div style={{ height: '200px', width: '100%', overflowY: 'auto', paddingRight: '8px' }}>
            {stats.calls_by_model.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {stats.calls_by_model.map((item: any, idx: number) => {
                  const percent = stats.total_calls > 0 ? Math.round((item.count / stats.total_calls) * 100) : 0
                  return (
                    <div key={item.model_id}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: '70%' }} title={item.model_id}>
                          {item.model_id}
                        </span>
                        <span style={{ color: 'var(--muted)' }}>{item.count} ({percent}%)</span>
                      </div>
                      <div style={{ width: '100%', height: '6px', background: 'var(--surface-soft)', borderRadius: '3px', overflow: 'hidden' }}>
                        <div style={{ width: `${percent}%`, height: '100%', background: 'var(--primary)', borderRadius: '3px' }} />
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted-soft)' }}>
                {t('dashboard.noData')}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Quotas & Provider Status Section (Phase 8.4) */}
      <div className="admin-section" style={{ marginTop: '24px', padding: '16px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <AlertTriangle size={14} className={quotas.length > 0 ? "text-error" : "text-primary"} /> 
          {t('dashboard.quotaStatusTitle')}
        </h4>
        <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: 'var(--muted)' }}>
          {t('dashboard.quotaStatusDesc')}
        </p>

        {quotas.length === 0 ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--cyan)', fontSize: '13px', background: 'rgba(93,184,166,0.06)', padding: '12px', borderRadius: '6px', border: '1px solid rgba(93,184,166,0.15)' }}>
            <span>✓</span> {t('dashboard.allOperatingNormally')}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {quotas.map((q) => (
              <div key={q.model_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: 'var(--surface-soft)', borderRadius: '6px', border: '1px solid var(--hairline)' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>{q.model_name || q.model_id}</span>
                    <span style={{ fontSize: '10px', background: q.status === 'exhausted' ? 'rgba(198,69,69,0.1)' : 'rgba(217,119,6,0.1)', color: q.status === 'exhausted' ? 'var(--error)' : 'var(--warning)', padding: '2px 6px', borderRadius: '10px', fontWeight: 500 }}>
                      {q.status === 'exhausted' ? t('dashboard.exhausted') : t('dashboard.degraded')}
                    </span>
                  </div>
                  <div style={{ fontSize: '11.5px', color: 'var(--muted)', marginTop: '4px' }}>
                    {t('dashboard.providerLabel')}: <strong style={{ textTransform: 'capitalize' }}>{q.provider_id}</strong> | {t('dashboard.consecutiveErrors')}: {q.consecutive_errors}
                    {q.last_error_message && ` | ${t('dashboard.lastError')}: "${q.last_error_message}"`}
                  </div>
                </div>
                <div style={{ fontSize: '11px', color: 'var(--muted)', textAlign: 'right' }}>
                  <div>{t('dashboard.exhaustedAt')}: {q.exhausted_at ? new Date(q.exhausted_at).toLocaleTimeString(i18n.language) : '-'}</div>
                  {q.estimated_reset_at && (
                    <div style={{ color: 'var(--warning)', marginTop: '2px' }}>
                      {t('dashboard.estimatedReset')}: {new Date(q.estimated_reset_at).toLocaleTimeString(i18n.language)}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Recent Failover Events Section (Phase 8.3) */}
      <div className="admin-section" style={{ marginTop: '24px', padding: '16px', background: 'var(--surface)', borderRadius: '8px', border: '1px solid var(--hairline)' }}>
        <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Activity size={14} /> 
          {t('dashboard.recentFailoversTitle')}
        </h4>
        <p style={{ margin: '0 0 16px 0', fontSize: '12.5px', color: 'var(--muted)' }}>
          {t('dashboard.recentFailoversDesc')}
        </p>

        {failovers.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '20px', color: 'var(--muted-soft)', fontSize: '13px' }}>
            {t('dashboard.noFailovers')}
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--hairline)', textAlign: 'left', color: 'var(--muted)' }}>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('dashboard.tableDate')}</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('dashboard.tableModelOriginal')}</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('dashboard.tableModelDest')}</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('dashboard.tableReason')}</th>
                  <th style={{ padding: '8px 12px', fontWeight: 600 }}>{t('dashboard.tableChatId')}</th>
                </tr>
              </thead>
              <tbody>
                {failovers.map((f) => (
                  <tr key={f.id} style={{ borderBottom: '1px solid var(--hairline)', color: 'var(--ink)' }}>
                    <td style={{ padding: '10px 12px', color: 'var(--muted)' }}>
                      {f.created_at ? new Date(f.created_at).toLocaleString(i18n.language) : '-'}
                    </td>
                    <td style={{ padding: '10px 12px', fontWeight: 500, color: 'var(--error)' }}>
                      {f.fallback_from_model_id}
                    </td>
                    <td style={{ padding: '10px 12px', fontWeight: 500, color: 'var(--cyan)' }}>
                      {f.model_id}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span style={{ background: 'var(--surface-soft)', padding: '2px 6px', borderRadius: '4px', fontSize: '11px', textTransform: 'capitalize' }}>
                        {f.fallback_reason === 'rate_limit' ? t('dashboard.rateLimitReason') : f.fallback_reason || t('dashboard.timeoutReason')}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px', color: 'var(--muted)' }}>
                      {f.conversation_id ? f.conversation_id.substring(0, 8) + '...' : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
