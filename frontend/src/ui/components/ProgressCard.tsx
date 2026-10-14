import React from 'react'
import { useTranslation } from 'react-i18next'
import type { ProgressBlock } from '../../types'
import { formatNumber } from '../lib/chartFormat'
import { UiCard } from './UiCard'

interface Props {
  block: ProgressBlock
}

export function ProgressCard({ block }: Props) {
  const { t, i18n } = useTranslation()
  const { label, value, max } = block

  if (value === undefined || max === undefined || max <= 0) {
    return null
  }

  const locale = i18n.resolvedLanguage || i18n.language || 'pt-BR'
  const percent = Math.min(100, Math.max(0, Math.round((value / max) * 100)))
  const ofText =
    t('intelligentUi.progressOf', { current: formatNumber(value, locale), max: formatNumber(max, locale) }) ||
    `${value} de ${max}`
  const state = percent >= 100 ? 'done' : percent === 0 ? 'empty' : 'active'

  return (
    <UiCard
      title={label}
      actions={
        <span className="nexus-ui-metric" data-state={state}>
          <span className="nexus-ui-metric__value">{percent}%</span>
        </span>
      }
    >
      <div
        role="progressbar"
        className="nexus-ui-progress"
        data-state={state}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuetext={`${ofText} (${percent}%)`}
        aria-label={label}
      >
        <div className="nexus-ui-progress__fill nexus-ui-progress-fill" style={{ width: `${percent}%` }} />
      </div>
      <p className="nexus-ui-progress__caption">{ofText}</p>
    </UiCard>
  )
}

export default ProgressCard
