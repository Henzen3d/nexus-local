import React from 'react'
import { useTranslation } from 'react-i18next'
import type { ProgressBlock } from '../../types'

interface Props {
  block: ProgressBlock
}

export function ProgressCard({ block }: Props) {
  const { t } = useTranslation()
  const { label, value, max } = block

  if (value === undefined || max === undefined || max <= 0) {
    return null
  }

  const percent = Math.min(100, Math.max(0, Math.round((value / max) * 100)))

  return (
    <div
      style={{
        marginTop: '12px',
        padding: '12px 16px',
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '10px',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>{label}</span>
        <span style={{ fontSize: '12px', color: 'var(--body)' }}>
          {t('intelligentUi.progressOf', { current: value, max }) || `${value} de ${max}`} ({percent}%)
        </span>
      </div>

      <div
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={label}
        style={{
          width: '100%',
          height: '6px',
          backgroundColor: 'var(--hairline)',
          borderRadius: '3px',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <div
          style={{
            width: `${percent}%`,
            height: '100%',
            backgroundColor: 'var(--primary)',
            borderRadius: '3px',
            transition: 'width 0.4s ease',
          }}
        />
      </div>
    </div>
  )
}

export default ProgressCard
