import React from 'react'
import { Activity, Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { MetricBlock, MetricItem } from '../../types'
import { formatNumber } from '../lib/chartFormat'
import { useResolvedValue } from '../state/messageUiState'
import { UiCard } from './UiCard'

interface Props {
  block: MetricBlock
  messageId?: string
}

/**
 * Bloco `metric` (plano 12 §2.1): 1 a 4 indicadores em grade, cada um no desenho do
 * `MetricIndicator` do OpenUI (valor pesado, delta ao lado com seta, rótulo em cima,
 * dica embaixo). A cor do delta depende de `trend` × `good`: a direção boa é
 * `--success`, a ruim é `--error`, `flat` é neutro. Só tokens do Multi+.
 */
export function MetricCard({ block, messageId }: Props) {
  const { t, i18n } = useTranslation()
  const locale = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  return (
    <UiCard className="nexus-ui-kpis" icon={<Activity size={16} />} title={block.title}>
      <dl className="nexus-ui-kpis__grid" data-count={block.items.length}>
        {block.items.map((item, idx) => (
          <MetricTile key={idx} item={item} locale={locale} t={t} messageId={messageId} />
        ))}
      </dl>
    </UiCard>
  )
}

function toneFor(item: MetricItem): 'good' | 'bad' | 'neutral' {
  if (!item.trend || item.trend === 'flat') return 'neutral'
  const good = item.good ?? 'up'
  return item.trend === good ? 'good' : 'bad'
}

function MetricTile({
  item,
  locale,
  t,
  messageId,
}: {
  item: MetricItem
  locale: string
  t: (key: string, opts?: Record<string, unknown>) => string
  messageId?: string
}) {
  const resolvedValue = useResolvedValue(messageId, item.value)
  const numeric = typeof resolvedValue === 'number'
  // Valor numérico formatado por locale; sem notação compacta para o KPI não virar "48 mil"
  // quando o modelo mandou 48200 (a tile tem espaço; o eixo do gráfico não tinha).
  const valueText = numeric
    ? formatNumber(resolvedValue, locale, false)
    : resolvedValue !== null && resolvedValue !== undefined
      ? String(resolvedValue)
      : '—'
  const tone = toneFor(item)
  const TrendIcon = item.trend === 'up' ? TrendingUp : item.trend === 'down' ? TrendingDown : Minus
  const trendLabel =
    item.trend === 'up'
      ? t('intelligentUi.metricUp')
      : item.trend === 'down'
        ? t('intelligentUi.metricDown')
        : item.trend === 'flat'
          ? t('intelligentUi.metricFlat')
          : ''

  return (
    <div className="nexus-ui-kpi" data-tone={tone}>
      <dt className="nexus-ui-kpi__label">{item.label}</dt>
      <dd className="nexus-ui-kpi__value-row">
        <span className="nexus-ui-kpi__value" data-numeric={numeric || undefined}>
          {valueText}
          {numeric && item.unit && <span className="nexus-ui-kpi__unit">{item.unit}</span>}
        </span>
        {(item.delta || item.trend) && (
          <span className="nexus-ui-kpi__delta">
            {item.trend && (
              <TrendIcon size={13} aria-hidden="true" className="nexus-ui-kpi__trend-icon" />
            )}
            {item.delta && <span>{item.delta}</span>}
            {trendLabel && <span className="nexus-ui-sr-only">{trendLabel}</span>}
          </span>
        )}
      </dd>
      {item.hint && <dd className="nexus-ui-kpi__hint">{item.hint}</dd>}
    </div>
  )
}

export default MetricCard
