import { useEffect, useState } from 'react'
import { AlertTriangle, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import type { ProactiveAdminStats, ProactiveStatus } from '../types'
import { compact } from './ProactiveAdminSettings'

// ─── ProactiveDashboardSection — cards do assistente proativo no dashboard (F5.2.4/F5.2.5) ──
// Insights/dia por status (barras empilhadas), taxa "saiba mais", taxa de bloqueio,
// p95 do pipeline e custo estimado em tokens. Badge de alarme quando
// `failed/total > 50 %` nas últimas 24 h (com amostra mínima). Só agregados — nunca
// o texto da conversa nem o texto sintetizado.

const MAX_DAYS = 90

/** Status que aparecem no gráfico (ordem = ordem de empilhamento). */
const CHART_STATUSES: Array<{ status: ProactiveStatus; color: string }> = [
  { status: 'delivered', color: 'var(--primary)' },
  { status: 'seen', color: 'var(--cyan, #06b6d4)' },
  { status: 'dismissed', color: 'var(--muted)' },
  { status: 'blocked', color: 'var(--warning, #d97706)' },
  { status: 'expired', color: 'var(--muted-soft, #94a3b8)' },
  { status: 'failed', color: 'var(--error, #c64545)' },
  { status: 'ready', color: 'var(--accent, #6366f1)' },
]

function pct(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

function ms(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return value >= 1000 ? `${(value / 1000).toFixed(1)} s` : `${Math.round(value)} ms`
}

const cardStyle = {
  background: 'var(--surface-soft)',
  padding: '14px',
  borderRadius: '8px',
  border: '1px solid var(--hairline)',
} as const
const cardLabelStyle = {
  fontSize: '11px',
  color: 'var(--muted)',
  fontWeight: 600,
  textTransform: 'uppercase',
  marginBottom: '6px',
} as const
const cardValueStyle = { fontSize: '22px', fontWeight: 700, color: 'var(--ink)' } as const
const cardSubStyle = { fontSize: '11px', color: 'var(--muted)', marginTop: '2px' } as const

export function ProactiveDashboardSection({ days }: { days: number }) {
  const { t } = useTranslation()
  const [stats, setStats] = useState<ProactiveAdminStats | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    api
      .getProactiveAdminStats(Math.max(1, Math.min(days, MAX_DAYS)))
      .then((data) => {
        if (!cancelled) {
          setStats(data)
          setError(false)
        }
      })
      .catch((e) => {
        console.warn('[proactive-dashboard] stats:', e)
        if (!cancelled) setError(true)
      })
    return () => {
      cancelled = true
    }
  }, [days])

  if (error || !stats) return null

  const w24 = stats.windows['24h']
  const w7 = stats.windows['7d']
  const daily = stats.daily ?? []
  const periodTotal = daily.reduce((acc, d) => acc + d.total, 0)
  const periodTokens = daily.reduce((acc, d) => acc + d.tokens_in + d.tokens_out, 0)
  const alert = stats.alert

  return (
    <div
      className="admin-section proactive-dashboard"
      data-testid="proactive-dashboard"
      style={{ marginTop: '24px', padding: '20px', background: 'var(--surface)', borderRadius: '10px', border: '1px solid var(--hairline)' }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
        <h4 style={{ margin: 0, fontSize: '15px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sparkles size={16} className="text-primary" />
          {t('proactive.dashboard.title')}
        </h4>
        {alert?.active ? (
          <span
            className="proactive-admin-alert"
            role="alert"
            data-testid="proactive-dashboard-alert"
            style={{ margin: 0, padding: '4px 10px', fontSize: '12px' }}
          >
            <AlertTriangle size={14} aria-hidden="true" />
            {t('proactive.dashboard.alertBadge', { pct: Math.round((alert.ratio ?? 0) * 100) })}
          </span>
        ) : (
          <span style={{ fontSize: '12px', padding: '3px 8px', borderRadius: '6px', background: 'var(--surface-soft)', color: 'var(--muted)', fontWeight: 600 }}>
            {t('proactive.dashboard.usersEnabled', { n: stats.users_enabled })}
          </span>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: '14px', marginBottom: '20px' }}>
        <div style={cardStyle}>
          <div style={cardLabelStyle}>{t('proactive.dashboard.insights24h')}</div>
          <div style={cardValueStyle}>{w24.total}</div>
          <div style={cardSubStyle}>{t('proactive.dashboard.insightsPeriod', { n: periodTotal, days: stats.days ?? daily.length })}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabelStyle}>{t('proactive.dashboard.knowMoreRate')}</div>
          <div style={{ ...cardValueStyle, color: 'var(--success, #10b981)' }}>{pct(w7.know_more_rate)}</div>
          <div style={cardSubStyle}>{t('proactive.dashboard.knowMoreSub', { n: w7.know_more, delivered: w7.delivered })}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabelStyle}>{t('proactive.dashboard.blockedRate')}</div>
          <div style={{ ...cardValueStyle, color: (w7.blocked_rate ?? 0) > 0.2 ? 'var(--error, #c64545)' : 'var(--ink)' }}>{pct(w7.blocked_rate)}</div>
          <div style={cardSubStyle}>{t('proactive.dashboard.blockedSub', { n: w7.blocked })}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabelStyle}>{t('proactive.dashboard.failureRate')}</div>
          <div style={{ ...cardValueStyle, color: alert?.active ? 'var(--error, #c64545)' : 'var(--ink)' }}>{pct(w24.failure_rate)}</div>
          <div style={cardSubStyle}>{t('proactive.dashboard.failureSub', { failed: alert?.failed ?? w24.by_status.failed, total: w24.total })}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabelStyle}>{t('proactive.dashboard.p95')}</div>
          <div style={cardValueStyle}>{ms(stats.latency.total_p95_ms)}</div>
          <div style={cardSubStyle}>{t('proactive.dashboard.p95Sub', { research: ms(stats.latency.research_p95_ms), synth: ms(stats.latency.synth_p95_ms) })}</div>
        </div>
        <div style={cardStyle}>
          <div style={cardLabelStyle}>{t('proactive.dashboard.tokens')}</div>
          <div style={{ ...cardValueStyle, color: 'var(--cyan, #06b6d4)' }}>~{compact(periodTokens)}</div>
          <div style={cardSubStyle}>
            {t('proactive.dashboard.tokensSub', {
              day: compact(stats.tokens ? stats.tokens['24h'].tokens_in + stats.tokens['24h'].tokens_out : 0),
            })}
          </div>
        </div>
      </div>

      <h5 style={{ margin: '0 0 10px 0', fontSize: '13px', fontWeight: 600, color: 'var(--muted)' }}>{t('proactive.dashboard.dailyTitle')}</h5>
      <div style={{ height: '220px', width: '100%' }}>
        {periodTotal > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={daily} margin={{ top: 5, right: 5, left: -20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" vertical={false} />
              <XAxis
                dataKey="day"
                stroke="var(--muted)"
                fontSize={11}
                tickMargin={8}
                tickFormatter={(val: string) => {
                  const [, m, d] = String(val).split('-')
                  return m && d ? `${Number(d)}/${Number(m)}` : String(val)
                }}
              />
              <YAxis stroke="var(--muted)" fontSize={11} tickMargin={8} allowDecimals={false} />
              <RechartsTooltip
                contentStyle={{ background: 'var(--surface-card)', border: '1px solid var(--hairline)', borderRadius: '6px', fontSize: '12px' }}
                labelStyle={{ fontWeight: 600, marginBottom: '4px' }}
              />
              <Legend wrapperStyle={{ fontSize: '11px' }} />
              {CHART_STATUSES.map(({ status, color }) => (
                <Bar key={status} dataKey={status} stackId="insights" name={t(`proactive.admin.status.${status}`)} fill={color} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--muted-soft)', fontSize: '12.5px' }}>
            {t('proactive.dashboard.empty')}
          </div>
        )}
      </div>
    </div>
  )
}
