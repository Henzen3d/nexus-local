import React from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ChartBlock } from '../../types'

interface Props {
  block: ChartBlock
}

const PALETTE = [
  'var(--primary, #cc785c)',
  'var(--cyan, #5db8a6)',
  'var(--warning, #d4a017)',
  'var(--success, #5db872)',
]

export function ChartCard({ block }: Props) {
  const { title, kind, x_key, series, rows } = block

  if (!rows || rows.length === 0 || !series || series.length === 0) {
    return null
  }

  const renderChart = () => {
    if (kind === 'bar') {
      const s = series[0]
      return (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={rows} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
            <XAxis dataKey={x_key} stroke="var(--body)" fontSize={11} tickLine={false} />
            <YAxis stroke="var(--body)" fontSize={11} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--surface-card)',
                borderColor: 'var(--hairline)',
                borderRadius: '8px',
                color: 'var(--ink)',
                fontSize: '12px',
              }}
            />
            <Bar dataKey={s.key} name={s.label || s.key} fill={PALETTE[0]} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      )
    }

    if (kind === 'line') {
      return (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={rows} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
            <XAxis dataKey={x_key} stroke="var(--body)" fontSize={11} tickLine={false} />
            <YAxis stroke="var(--body)" fontSize={11} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--surface-card)',
                borderColor: 'var(--hairline)',
                borderRadius: '8px',
                color: 'var(--ink)',
                fontSize: '12px',
              }}
            />
            {series.length > 1 && <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '6px' }} />}
            {series.map((s, idx) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label || s.key}
                stroke={PALETTE[idx % PALETTE.length]}
                strokeWidth={2}
                dot={{ r: 3 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )
    }

    if (kind === 'compare') {
      return (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={rows} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--hairline)" />
            <XAxis dataKey={x_key} stroke="var(--body)" fontSize={11} tickLine={false} />
            <YAxis stroke="var(--body)" fontSize={11} tickLine={false} />
            <Tooltip
              contentStyle={{
                backgroundColor: 'var(--surface-card)',
                borderColor: 'var(--hairline)',
                borderRadius: '8px',
                color: 'var(--ink)',
                fontSize: '12px',
              }}
            />
            <Legend wrapperStyle={{ fontSize: '11px', paddingTop: '6px' }} />
            {series.map((s, idx) => (
              <Bar
                key={s.key}
                dataKey={s.key}
                name={s.label || s.key}
                fill={PALETTE[idx % PALETTE.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      )
    }

    return null
  }

  return (
    <div
      style={{
        marginTop: '12px',
        padding: '14px 16px',
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '10px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
      }}
    >
      <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)', marginBottom: '12px' }}>
        {title}
      </div>

      {renderChart()}

      {/* Tabela acessível para leitores de tela */}
      <table
        style={{
          position: 'absolute',
          width: '1px',
          height: '1px',
          padding: 0,
          margin: '-1px',
          overflow: 'hidden',
          clip: 'rect(0, 0, 0, 0)',
          whiteSpace: 'nowrap',
          border: 0,
        }}
      >
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>{x_key}</th>
            {series.map((s) => (
              <th key={s.key}>{s.label || s.key}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => (
            <tr key={rIdx}>
              <td>{String(row[x_key])}</td>
              {series.map((s) => (
                <td key={s.key}>{String(row[s.key])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default ChartCard
