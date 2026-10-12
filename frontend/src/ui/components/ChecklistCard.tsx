import React from 'react'
import type { ProgressBlock } from '../../types'

interface Props {
  block: ProgressBlock
}

export function ChecklistCard({ block }: Props) {
  const { label, steps } = block

  if (!steps || steps.length === 0) {
    return null
  }

  const getStateIcon = (state: string) => {
    switch (state) {
      case 'done':
        return (
          <span
            style={{
              color: 'var(--success)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '16px',
              height: '16px',
            }}
          >
            ✓
          </span>
        )
      case 'active':
        return (
          <span
            style={{
              display: 'inline-block',
              width: '10px',
              height: '10px',
              borderRadius: '50%',
              backgroundColor: 'var(--primary)',
              boxShadow: '0 0 6px var(--primary)',
            }}
          />
        )
      case 'error':
        return (
          <span
            style={{
              color: 'var(--error)',
              fontWeight: 'bold',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '16px',
              height: '16px',
            }}
          >
            ✕
          </span>
        )
      default: // pending
        return (
          <span
            style={{
              display: 'inline-block',
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: 'var(--hairline)',
              border: '1px solid var(--body)',
            }}
          />
        )
    }
  }

  return (
    <div
      style={{
        marginTop: '12px',
        padding: '12px 16px',
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '10px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
      }}
    >
      {label && (
        <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)', marginBottom: '8px' }}>
          {label}
        </div>
      )}

      <ul
        role="list"
        style={{
          listStyle: 'none',
          padding: 0,
          margin: 0,
          display: 'flex',
          flexDirection: 'column',
          gap: '6px',
        }}
      >
        {steps.map((step) => (
          <li
            key={step.id}
            role="listitem"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '13px',
              color: step.state === 'done' ? 'var(--body)' : 'var(--ink)',
              textDecoration: step.state === 'done' ? 'none' : 'none',
            }}
          >
            <div style={{ width: '16px', display: 'flex', justifyContent: 'center' }}>
              {getStateIcon(step.state)}
            </div>
            <span
              style={{
                fontWeight: step.state === 'active' ? 600 : 400,
                color: step.state === 'active' ? 'var(--primary)' : undefined,
              }}
            >
              {step.label}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default ChecklistCard
