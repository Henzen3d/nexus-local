import React, { useId, useMemo, useState } from 'react'
import { Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import { useStore } from '../../store/useStore'
import type { ControlsBlock } from '../../types'
import { formatNumber } from '../lib/chartFormat'
import { evaluateSafeFormula } from '../lib/safeMath'
import { UiCard } from './UiCard'

interface Props {
  block: ControlsBlock
}

/** Spec §4.4: `text` tem teto de 200 caracteres no cliente, declare o modelo ou não. */
const TEXT_MAX_LENGTH = 200

/** Separador do valor interno do select de `set_model` (ids podem repetir entre provedores). */
const MODEL_KEY_SEP = '::'
const modelKey = (providerId: string, id: string) => `${providerId}${MODEL_KEY_SEP}${id}`

/** Corta um número para dentro de [min, max] (spec §4.4: "o host corta o valor para dentro do intervalo"). */
function clampNumber(raw: number, min?: number, max?: number): number {
  let n = Number.isFinite(raw) ? raw : (min ?? 0)
  if (typeof min === 'number' && n < min) n = min
  if (typeof max === 'number' && n > max) n = max
  return n
}

export function ControlsCard({ block }: Props) {
  const { t, i18n } = useTranslation()
  const { sendMessage } = useChatContext()
  // Seletores pontuais: a bolha não pode re-renderizar a cada token do store
  const models = useStore((s) => s.models)
  const selectModel = useStore((s) => s.selectModel)
  const selectedModelId = useStore((s) => s.selectedModelId)
  const selectedProviderId = useStore((s) => s.selectedProviderId)
  const { title, submit_label, fields, action, computed } = block
  const uid = useId()
  const fieldDomId = (fieldId: string) => `${uid}-${fieldId}`
  const locale = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  const isSetModel = action.name === 'set_model'
  const modelField = isSetModel ? action.field : undefined

  // Inicializa estado dos campos
  const [formValues, setFormValues] = useState<Record<string, string | number>>(() => {
    const initial: Record<string, string | number> = {}
    for (const f of fields) {
      if (f.kind === 'number' || f.kind === 'range') {
        initial[f.id] = clampNumber(f.default !== undefined ? f.default : (f.min ?? 0), f.min, f.max)
      } else if (f.kind === 'select') {
        if (isSetModel && f.id === modelField) {
          // set_model: pré-seleciona o modelo atual do usuário; options do JSON são ignoradas
          const current =
            selectedModelId && selectedProviderId ? modelKey(selectedProviderId, selectedModelId) : ''
          initial[f.id] = models.some((m) => modelKey(m.provider_id, m.id) === current)
            ? current
            : models.length > 0
              ? modelKey(models[0].provider_id, models[0].id)
              : ''
        } else {
          initial[f.id] = f.options && f.options.length > 0 ? f.options[0].value : ''
        }
      } else {
        initial[f.id] = ''
      }
    }
    return initial
  })

  const [submitted, setSubmitted] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  // Spec §4.4: sem modelos na lista do usuário, o bloco set_model não aparece.
  if (isSetModel && models.length === 0) return null

  const handleFieldChange = (id: string, val: string | number) => {
    setError(null)
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
      } else {
        setError(t('intelligentUi.controlsError'))
      }
      return
    }

    if (action.name === 'set_model' && action.field) {
      // Só muda se o id existir na lista do usuário. Id inventado: erro curto, nada acontece.
      const key = String(formValues[action.field] || '')
      const matched = models.find((m) => modelKey(m.provider_id, m.id) === key)
      if (matched && selectModel) {
        selectModel(matched.id, matched.provider_id)
        setSubmitted(true)
      } else {
        setError(t('intelligentUi.modelNotInList'))
      }
    }
  }

  const errorId = `${uid}-error`
  const titleId = `${uid}-title`
  const doneLabel = t('intelligentUi.controlsDone') || 'Enviado'

  return (
    <UiCard
      as="form"
      className="nexus-ui-controls"
      title={title}
      titleId={titleId}
      onSubmit={handleSubmit}
      aria-labelledby={titleId}
      aria-describedby={error ? errorId : undefined}
      data-submitted={submitted || undefined}
      actions={
        computed ? (
          <span
            className="nexus-ui-chip nexus-ui-chip--accent"
            aria-live="polite"
            aria-atomic="true"
            data-empty={computedBadgeText ? undefined : 'true'}
          >
            {computedBadgeText ?? ' '}
          </span>
        ) : undefined
      }
      footer={
        <>
          {error && (
            <p id={errorId} role="alert" className="nexus-ui-error">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitted}
            className="nexus-ui-button nexus-ui-button--primary"
            data-done={submitted || undefined}
            aria-label={submitted ? doneLabel : undefined}
          >
            {submitted ? (
              <>
                <Check size={16} aria-hidden="true" /> {doneLabel}
              </>
            ) : (
              submit_label || t('intelligentUi.controlsSubmitDefault') || 'Executar'
            )}
          </button>
        </>
      }
    >
      <div className="nexus-ui-fields">
        {fields.map((field) => {
          const val = formValues[field.id]
          const domId = fieldDomId(field.id)

          if (field.kind === 'text') {
            return (
              <div key={field.id} className="nexus-ui-field" data-kind="text">
                <label htmlFor={domId} className="nexus-ui-field__label">
                  {field.label}
                </label>
                <input
                  id={domId}
                  name={field.id}
                  type="text"
                  className="nexus-ui-input"
                  value={String(val || '')}
                  placeholder={field.placeholder}
                  maxLength={TEXT_MAX_LENGTH}
                  disabled={submitted}
                  onChange={(e) => handleFieldChange(field.id, e.target.value.slice(0, TEXT_MAX_LENGTH))}
                />
              </div>
            )
          }

          if (field.kind === 'number') {
            return (
              <div key={field.id} className="nexus-ui-field" data-kind="number">
                <label htmlFor={domId} className="nexus-ui-field__label">
                  {field.label}
                </label>
                <input
                  id={domId}
                  name={field.id}
                  type="number"
                  inputMode="decimal"
                  className="nexus-ui-input"
                  min={field.min}
                  max={field.max}
                  step={field.step ?? 1}
                  value={typeof val === 'number' ? val : ''}
                  disabled={submitted}
                  onChange={(e) => handleFieldChange(field.id, parseFloat(e.target.value) || 0)}
                  onBlur={(e) =>
                    handleFieldChange(field.id, clampNumber(parseFloat(e.target.value), field.min, field.max))
                  }
                />
              </div>
            )
          }

          if (field.kind === 'range') {
            const rangeVal = typeof val === 'number' ? val : (field.min ?? 0)
            const min = field.min ?? 0
            const max = field.max ?? 100
            const pct = max > min ? Math.min(100, Math.max(0, ((rangeVal - min) / (max - min)) * 100)) : 0
            return (
              <div key={field.id} className="nexus-ui-field" data-kind="range">
                <div className="nexus-ui-field__row">
                  <label htmlFor={domId} className="nexus-ui-field__label">
                    {field.label}
                  </label>
                  <output htmlFor={domId} aria-live="off" className="nexus-ui-chip">
                    {formatNumber(rangeVal, locale, false)}
                  </output>
                </div>
                <input
                  id={domId}
                  name={field.id}
                  type="range"
                  className="nexus-ui-range"
                  min={field.min}
                  max={field.max}
                  step={field.step ?? 1}
                  value={rangeVal}
                  aria-valuemin={field.min}
                  aria-valuemax={field.max}
                  aria-valuenow={rangeVal}
                  disabled={submitted}
                  style={{ ['--nexus-ui-range-pct' as string]: `${pct}%` }}
                  onChange={(e) =>
                    handleFieldChange(field.id, clampNumber(parseFloat(e.target.value), field.min, field.max))
                  }
                />
                <div className="nexus-ui-field__bounds" aria-hidden="true">
                  <span>{formatNumber(min, locale)}</span>
                  <span>{formatNumber(max, locale)}</span>
                </div>
              </div>
            )
          }

          if (field.kind === 'select') {
            const isModelPicker = isSetModel && field.id === modelField
            return (
              <div key={field.id} className="nexus-ui-field" data-kind="select">
                <label htmlFor={domId} className="nexus-ui-field__label">
                  {field.label}
                </label>
                <select
                  id={domId}
                  name={field.id}
                  className="nexus-ui-select"
                  value={String(val || '')}
                  disabled={submitted}
                  aria-invalid={isModelPicker && error ? true : undefined}
                  onChange={(e) => handleFieldChange(field.id, e.target.value)}
                >
                  {isModelPicker
                    ? // Opções do modelo são ignoradas: a lista é a do usuário (store)
                      models.map((m) => (
                        <option key={modelKey(m.provider_id, m.id)} value={modelKey(m.provider_id, m.id)}>
                          {m.display_name}
                          {m.provider_name ? ` · ${m.provider_name}` : ''}
                        </option>
                      ))
                    : field.options?.map((opt) => (
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
    </UiCard>
  )
}

export default ControlsCard
