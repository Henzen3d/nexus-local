import React, { useMemo, useState } from 'react'
import { Check, Copy } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
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
  pieColors,
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
  unit,
}: {
  active?: boolean
  label?: unknown
  payload?: TooltipEntry[]
  locale: string
  unit?: string
}) {
  if (!active || !payload || payload.length === 0) return null
  return (
    <div className="nexus-ui-chart-tooltip" role="status">
      <div className="nexus-ui-chart-tooltip__label">{String(label ?? '')}</div>
      <ul className="nexus-ui-chart-tooltip__list">
        {payload.map((entry, idx) => {
          const formatted = formatNumber(entry.value, locale, false)
          const valWithUnit = unit ? `${formatted} ${unit}` : formatted
          return (
            <li key={`${String(entry.dataKey ?? idx)}`} className="nexus-ui-chart-tooltip__item">
              <span className="nexus-ui-chart-tooltip__dot" style={{ background: entry.color }} aria-hidden="true" />
              <span className="nexus-ui-chart-tooltip__name">{entry.name}</span>
              <span className="nexus-ui-chart-tooltip__value">{valWithUnit}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function PieTooltipContent({
  active,
  payload,
  locale,
  unit,
  total,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  locale: string
  unit?: string
  total: number
}) {
  if (!active || !payload || payload.length === 0) return null
  const entry = payload[0]
  const val = typeof entry.value === 'number' ? entry.value : Number(entry.value || 0)
  const pct = total > 0 ? ((val / total) * 100).toFixed(1) : '0'
  const formatted = formatNumber(val, locale, false)
  const valWithUnit = unit ? `${formatted} ${unit}` : formatted

  return (
    <div className="nexus-ui-chart-tooltip" role="status">
      <div className="nexus-ui-chart-tooltip__label">{String(entry.name ?? '')}</div>
      <div className="nexus-ui-chart-tooltip__item">
        <span className="nexus-ui-chart-tooltip__dot" style={{ background: entry.color }} aria-hidden="true" />
        <span className="nexus-ui-chart-tooltip__value">
          {valWithUnit} ({pct}%)
        </span>
      </div>
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
  const { title, kind, x_key, series, rows, unit, x_label, y_label, stacked } = block
  const reducedMotion = useReducedMotion()
  const [copied, setCopied] = useState(false)
  const locale = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  const keys = useMemo(() => (series || []).map((s) => s.key), [series])
  const isStacked = Boolean(kind === 'compare' && stacked)
  const colors = useMemo(() => seriesColors(keys.length), [keys.length])
  const piePalette = useMemo(() => pieColors((rows || []).length), [(rows || []).length])
  const extent = useMemo(() => yDomainThroughZero(rows || [], keys, isStacked), [rows, keys, isStacked])
  const yWidth = useMemo(() => yAxisWidthFor(extent, locale), [extent, locale])
  const ticks = tickCountFor(CHART_HEIGHT)

  const pieTotal = useMemo(() => {
    if (kind !== 'pie' || !rows || !series || series.length === 0) return 0
    const sKey = series[0].key
    return rows.reduce((acc, r) => acc + (Number(r[sKey]) || 0), 0)
  }, [kind, rows, series])

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
      /* clipboard indisponível */
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
        label={
          x_label
            ? {
                value: x_label,
                position: 'insideBottom',
                offset: -4,
                fill: 'var(--muted)',
                fontSize: 11,
              }
            : undefined
        }
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
        label={
          y_label || unit
            ? {
                value: y_label || unit,
                angle: -90,
                position: 'insideLeft',
                fill: 'var(--muted)',
                fontSize: 11,
              }
            : undefined
        }
      />
      <Tooltip
        cursor={kind === 'line' ? { stroke: GRID_STROKE } : { fill: CURSOR_FILL }}
        content={<ChartTooltipContent locale={locale} unit={unit} />}
        isAnimationActive={false}
      />
      {multi && <Legend content={<ChartLegendContent />} />}
    </>
  )

  const margin = { top: 8, right: 8, left: 0, bottom: x_label ? 16 : 0 }

  const renderChart = () => {
    if (kind === 'pie') {
      const sKey = series[0].key
      return (
        <PieChart margin={{ top: 8, right: 8, bottom: 8, left: 8 }}>
          <Pie
            data={rows}
            dataKey={sKey}
            nameKey={x_key}
            cx="50%"
            cy="50%"
            innerRadius="50%"
            outerRadius="75%"
            paddingAngle={2}
            isAnimationActive={animate}
          >
            {rows.map((_, index) => (
              <Cell key={`cell-${index}`} fill={piePalette[index % piePalette.length]} />
            ))}
          </Pie>
          <Tooltip
            content={<PieTooltipContent locale={locale} unit={unit} total={pieTotal} />}
            isAnimationActive={false}
          />
          <Legend content={<ChartLegendContent />} />
        </PieChart>
      )
    }

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

    // bar (1 série) e compare (barras agrupadas ou empilhadas)
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
            radius={isStacked ? [0, 0, 0, 0] : [4, 4, 0, 0]}
            stackId={isStacked ? 'nexus-ui-stack' : undefined}
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
                <td key={s.key}>
                  {formatNumber(row[s.key], locale, false)}
                  {unit ? ` ${unit}` : ''}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </UiCard>
  )
}

export default ChartCard
