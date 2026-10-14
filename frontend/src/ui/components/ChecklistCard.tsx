import React from 'react'
import { Check, X } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ProgressBlock, ProgressStep } from '../../types'
import { UiCard } from './UiCard'

interface Props {
  block: ProgressBlock
}

/**
 * Lista de passos como linha do tempo: círculo com estado + conector vertical + rótulo.
 * Modelo visual: `Steps`/`StepsItem` do OpenUI (Thesys, MIT), reescrito em CSS puro
 * com os tokens do Multi+. Estados da spec §4.1: pending | active | done | error.
 */
export function ChecklistCard({ block }: Props) {
  const { t } = useTranslation()
  const { label, steps } = block

  if (!steps || steps.length === 0) {
    return null
  }

  const done = steps.filter((s) => s.state === 'done').length
  const summary = t('intelligentUi.stepsSummary', { done, total: steps.length }) || `${done}/${steps.length}`

  return (
    <UiCard
      title={label}
      actions={
        <span className="nexus-ui-metric" data-state={done === steps.length ? 'done' : 'active'}>
          <span className="nexus-ui-metric__value nexus-ui-metric__value--small">{summary}</span>
        </span>
      }
    >
      <ol className="nexus-ui-steps" role="list">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className="nexus-ui-step"
            data-state={step.state}
            aria-current={step.state === 'active' ? 'step' : undefined}
          >
            <div className="nexus-ui-step__rail">
              <span className="nexus-ui-step__marker">
                <StepGlyph step={step} index={index} />
              </span>
              <span className="nexus-ui-step__line" aria-hidden="true" />
            </div>
            <div className="nexus-ui-step__content">
              <span className="nexus-ui-step__label">{step.label}</span>
              <span className="nexus-ui-sr-only">{stateLabel(step.state, t)}</span>
            </div>
          </li>
        ))}
      </ol>
    </UiCard>
  )
}

function StepGlyph({ step, index }: { step: ProgressStep; index: number }) {
  switch (step.state) {
    case 'done':
      return <Check size={13} strokeWidth={3} aria-hidden="true" />
    case 'error':
      return <X size={13} strokeWidth={3} aria-hidden="true" />
    case 'active':
      return <span className="nexus-ui-step__pulse" aria-hidden="true" />
    default:
      return <span aria-hidden="true">{index + 1}</span>
  }
}

function stateLabel(state: ProgressStep['state'], t: (key: string) => string): string {
  switch (state) {
    case 'done':
      return t('intelligentUi.stepDone') || 'concluído'
    case 'active':
      return t('intelligentUi.stepActive') || 'em andamento'
    case 'error':
      return t('intelligentUi.stepError') || 'com erro'
    default:
      return t('intelligentUi.stepPending') || 'pendente'
  }
}

export default ChecklistCard
