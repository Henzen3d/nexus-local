import React, { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import { useStore } from '../../store/useStore'
import type { ControlsBlock } from '../../types'
import { evaluateSafeFormula } from '../lib/safeMath'

interface Props {
  block: ControlsBlock
}

export function ControlsCard({ block }: Props) {
  const { t } = useTranslation()
  const { sendMessage } = useChatContext()
  const { models, selectModel } = useStore()
  const { title, submit_label, fields, action, computed } = block

  // Inicializa estado dos campos
  const [formValues, setFormValues] = useState<Record<string, string | number>>(() => {
    const initial: Record<string, string | number> = {}
    for (const f of fields) {
      if (f.kind === 'number' || f.kind === 'range') {
        initial[f.id] = f.default !== undefined ? f.default : f.min ?? 0
      } else if (f.kind === 'select') {
        initial[f.id] = f.options && f.options.length > 0 ? f.options[0].value : ''
      } else {
        initial[f.id] = ''
      }
    }
    return initial
  })

  const [submitted, setSubmitted] = useState(false)

  // Cálculo reativo em tempo real
  const computedResult = useMemo(() => {
    if (!computed || !computed.formula) return null
    const numericVars: Record<string, number> = {}
    for (const [k, v] of Object.entries(formValues)) {
      numericVars[k] = typeof v === 'number' ? v : parseFloat(String(v)) || 0
    }
    return evaluateSafeFormula(computed.formula, numericVars)
  }, [computed, formValues])

  const computedBadgeText = useMemo(() => {
    if (!computed || computedResult === null) return null
    return computed.template.replace('{resultado}', String(computedResult))
  }, [computed, computedResult])

  const handleFieldChange = (id: string, val: string | number) => {
    setFormValues((prev) => ({ ...prev, [id]: val }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (submitted) return

    if (action.name === 'send_message' && action.template) {
      let msg = action.template
      for (const [k, v] of Object.entries(formValues)) {
        msg = msg.split(`{${k}}`).join(String(v))
      }
      if (computedResult !== null) {
        msg = msg.split('{resultado}').join(String(computedResult))
      }
      if (sendMessage) {
        sendMessage(msg)
        setSubmitted(true)
      }
    } else if (action.name === 'set_model' && action.field) {
      const selectedModelVal = String(formValues[action.field] || '')
      const matched = models.find((m) => m.id === selectedModelVal)
      if (matched && selectModel) {
        selectModel(matched.id, matched.provider_id)
        setSubmitted(true)
      }
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        marginTop: '12px',
        padding: '14px 16px',
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '10px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
          {title}
        </h4>
        {computedBadgeText && (
          <span
            style={{
              fontSize: '12px',
              fontWeight: 600,
              padding: '3px 8px',
              borderRadius: '6px',
              backgroundColor: 'var(--surface-soft)',
              color: 'var(--primary)',
              border: '1px solid var(--hairline)',
            }}
          >
            {computedBadgeText}
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {fields.map((field) => {
          const val = formValues[field.id]

          if (field.kind === 'text') {
            return (
              <div key={field.id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '12px', color: 'var(--body)' }}>{field.label}</label>
                <input
                  type="text"
                  value={String(val || '')}
                  placeholder={field.placeholder}
                  disabled={submitted}
                  onChange={(e) => handleFieldChange(field.id, e.target.value)}
                  style={{
                    height: '36px',
                    padding: '6px 10px',
                    fontSize: '13px',
                    borderRadius: '6px',
                    border: '1px solid var(--hairline)',
                    backgroundColor: 'var(--canvas, #1f1f1e)',
                    color: 'var(--ink)',
                    outline: 'none',
                  }}
                />
              </div>
            )
          }

          if (field.kind === 'number') {
            return (
              <div key={field.id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '12px', color: 'var(--body)' }}>{field.label}</label>
                <input
                  type="number"
                  min={field.min}
                  max={field.max}
                  step={field.step ?? 1}
                  value={typeof val === 'number' ? val : ''}
                  disabled={submitted}
                  onChange={(e) => handleFieldChange(field.id, parseFloat(e.target.value) || 0)}
                  style={{
                    height: '36px',
                    padding: '6px 10px',
                    fontSize: '13px',
                    borderRadius: '6px',
                    border: '1px solid var(--hairline)',
                    backgroundColor: 'var(--canvas, #1f1f1e)',
                    color: 'var(--ink)',
                    outline: 'none',
                  }}
                />
              </div>
            )
          }

          if (field.kind === 'range') {
            return (
              <div key={field.id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--body)' }}>
                  <span>{field.label}</span>
                  <strong>{val}</strong>
                </div>
                <input
                  type="range"
                  min={field.min}
                  max={field.max}
                  step={field.step ?? 1}
                  value={typeof val === 'number' ? val : field.min}
                  disabled={submitted}
                  onChange={(e) => handleFieldChange(field.id, parseFloat(e.target.value) || 0)}
                  style={{
                    width: '100%',
                    accentColor: 'var(--primary)',
                    cursor: submitted ? 'default' : 'pointer',
                  }}
                />
              </div>
            )
          }

          if (field.kind === 'select') {
            return (
              <div key={field.id} style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <label style={{ fontSize: '12px', color: 'var(--body)' }}>{field.label}</label>
                <select
                  value={String(val || '')}
                  disabled={submitted}
                  onChange={(e) => handleFieldChange(field.id, e.target.value)}
                  style={{
                    height: '36px',
                    padding: '6px 10px',
                    fontSize: '13px',
                    borderRadius: '6px',
                    border: '1px solid var(--hairline)',
                    backgroundColor: 'var(--canvas, #1f1f1e)',
                    color: 'var(--ink)',
                    outline: 'none',
                    cursor: submitted ? 'default' : 'pointer',
                  }}
                >
                  {field.options?.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            )
          }

          return null
        })}
      </div>

      <button
        type="submit"
        disabled={submitted}
        style={{
          minHeight: '44px',
          padding: '8px 16px',
          fontSize: '13px',
          fontWeight: 600,
          borderRadius: '8px',
          border: 'none',
          backgroundColor: submitted ? 'var(--hairline)' : 'var(--primary)',
          color: submitted ? 'var(--body)' : '#ffffff',
          cursor: submitted ? 'not-allowed' : 'pointer',
          transition: 'all 0.15s ease',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {submitted ? '✓' : submit_label || t('intelligentUi.controlsSubmitDefault') || 'Executar'}
      </button>
    </form>
  )
}

export default ControlsCard
