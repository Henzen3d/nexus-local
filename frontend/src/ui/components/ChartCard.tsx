import React, { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'
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
import { useTranslation } from 'react-i18next'
import type { ChartBlock } from '../../types'
import { useReducedMotion } from '../hooks/useMotionAndViewport'
import {
  CHART_HEIGHT,
  chartToCsv,
  formatNumber,
  seriesColors,
  tickCountFor,
  truncateLabel,
  yAxisWidthFor,
  yDomainThroughZero,
} from '../lib/chartFormat'
import { UiCard, UiCardAction } from './UiCard'

interface Props {
  block: ChartBlock
}

const AXIS_STYLE = { fill: 'var(--muted)', fontSize: 11 }
const GRID_STROKE = 'var(--hairline)'
const CURSOR_FILL = 'color-mix(in srgb, var(--ink) 6%, transparent)'

type TooltipEntry = { name?: string; value?: unknown; color?: string; dataKey?: string | number }

/** Tooltip no estilo do OpenUI: caixa pequena, rótulo em cima, uma linha por série com o ponto da cor. */
function ChartTooltipContent({
  active,
  label,
  payload,
  locale,
}: {
  active?: boolean
  label?: unknown
  payload?: TooltipEntry[]
  locale: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="nexus-ui-chart-tooltip" role="status">
      <div className="nexus-ui-chart-tooltip__label">{String(label ?? '')}</div>
      <ul className="nexus-ui-chart-tooltip__list">
        {payload.map((entry, idx) => (
          <li key={`${String(entry.dataKey ?? idx)}`} className="nexus-ui-chart-tooltip__item">
            <span className="nexus-ui-chart-tooltip__dot" style={{ background: entry.color }} aria-hidden="true" />
            <span className="nexus-ui-chart-tooltip__name">{entry.name}</span>
            <span className="nexus-ui-chart-tooltip__value">{formatNumber(entry.value, locale, false)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ChartLegendContent({ payload }: { payload?: { value?: string; color?: string }[] }) {
  if (!payload || payload.length === 0) return null
  return (
    <ul className="nexus-ui-chart-legend">
      {payload.map((entry, idx) => (
        <li key={`${entry.value}-${idx}`} className="nexus-ui-chart-legend__item">
          <span className="nexus-ui-chart-legend__swatch" style={{ background: entry.color }} aria-hidden="true" />
          {entry.value}
        </li>
      ))}
    </ul>
  )
}

export function ChartCard({ block }: Props) {
  const { t, i18n } = useTranslation()
  const { title, kind, x_key, series, rows } = block
  const reducedMotion = useReducedMotion()
  const [copied, setCopied] = useState(false)
  const locale = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  const keys = useMemo(() => (series || []).map((s) => s.key), [series])
  const colors = useMemo(() => seriesColors(keys.length), [keys.length])
  const extent = useMemo(() => yDomainThroughZero(rows || [], keys), [rows, keys])
  const yWidth = useMemo(() => yAxisWidthFor(extent, locale), [extent, locale])
  const ticks = tickCountFor(CHART_HEIGHT)
  // Eixo ancorado em zero: com dados só positivos o piso é 0; com negativos o Recharts
  // escolhe os ticks "redondos" sozinho (e o zero entra no meio). Domínio fixo nos dois
  // extremos daria ticks feios (6 250, 12 500…), por isso o teto fica em 'auto'.
  const yDomain: [number | 'auto', 'auto'] = [extent[0] < 0 ? 'auto' : 0, 'auto']

  if (!rows || rows.length === 0 || !series || series.length === 0) {
    return null
  }

  const multi = series.length > 1
  const fmt = (v: unknown) => formatNumber(v, locale)
  const animate = !reducedMotion

  const handleCopy = async () => {
    const csv = chartToCsv(x_key, series, rows)
    try {
      await navigator.clipboard.writeText(csv)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1600)
    } catch {
      /* clipboard indisponível (http sem contexto seguro): nada a fazer */
    }
  }

  const axes = (
    <>
      <CartesianGrid vertical={false} stroke={GRID_STROKE} strokeDasharray="3 3" />
      <XAxis
        dataKey={x_key}
        tick={AXIS_STYLE}
        tickLine={false}
        axisLine={{ stroke: GRID_STROKE }}
        interval="preserveStartEnd"
        minTickGap={12}
        tickFormatter={(v) => truncateLabel(v)}
      />
      <YAxis
        tick={AXIS_STYLE}
        tickLine={false}
        axisLine={false}
        width={yWidth}
        tickCount={ticks}
        domain={yDomain}
        allowDecimals
        tickFormatter={fmt}
      />
      <Tooltip
        cursor={kind === 'line' ? { stroke: GRID_STROKE } : { fill: CURSOR_FILL }}
        content={<ChartTooltipContent locale={locale} />}
        isAnimationActive={false}
      />
      {multi && <Legend content={<ChartLegendContent />} />}
    </>
  )

  const margin = { top: 8, right: 8, left: 0, bottom: 0 }

  const renderChart = () => {
    if (kind === 'line') {
      return (
        <LineChart data={rows} margin={margin}>
          {axes}
          {series.map((s, idx) => (
            <Line
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label || s.key}
              stroke={colors[idx]}
              strokeWidth={2}
              dot={{ r: 3, strokeWidth: 0, fill: colors[idx] }}
              activeDot={{ r: 5, strokeWidth: 0 }}
              isAnimationActive={animate}
            />
          ))}
        </LineChart>
      )
    }

    // bar (1 série) e compare (barras agrupadas)
    const drawn = kind === 'bar' ? series.slice(0, 1) : series
    return (
      <BarChart data={rows} margin={margin} barCategoryGap="22%" barGap={3} maxBarSize={48}>
        {axes}
        {drawn.map((s, idx) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label || s.key}
            fill={colors[idx]}
            radius={[4, 4, 0, 0]}
            isAnimationActive={animate}
          />
        ))}
      </BarChart>
    )
  }

  return (
    <UiCard
      title={title}
      actions={
        <UiCardAction
          icon={copied ? <Check size={14} /> : <Copy size={14} />}
          label={t('intelligentUi.copyData') || 'Copiar dados'}
          pressedLabel={t('intelligentUi.copied') || 'Copiado'}
          pressed={copied}
          onClick={handleCopy}
          hideLabel
        />
      }
    >
      <div className="nexus-ui-chart" style={{ height: CHART_HEIGHT }}>
        <ResponsiveContainer width="100%" height="100%">
          {renderChart()}
        </ResponsiveContainer>
      </div>

      {/* Tabela acessível para leitores de tela (spec §7) */}
      <table className="nexus-ui-sr-only">
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">{x_key}</th>
            {series.map((s) => (
              <th key={s.key} scope="col">
                {s.label || s.key}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => (
            <tr key={rIdx}>
              <td>{String(row[x_key])}</td>
              {series.map((s) => (
                <td key={s.key}>{formatNumber(row[s.key], locale, false)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </UiCard>
  )
}

export default ChartCard
