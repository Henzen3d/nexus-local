import React, { useId, useState } from 'react'
import { Check, Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import type { OptionsBlock } from '../../types'
import { UiCard } from './UiCard'

interface Props {
  block: OptionsBlock
  streaming?: boolean
}

const TEXT_MAX_LENGTH = 200

export function OptionsCard({ block, streaming }: Props) {
  const { t } = useTranslation()
  const { sendMessage } = useChatContext()
  const uid = useId()
  const { question, mode = 'single', options, allow_other, action } = block

  const [selectedValues, setSelectedValues] = useState<string[]>([])
  const [otherText, setOtherText] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [submittedChoiceText, setSubmittedChoiceText] = useState('')

  const isMultiple = mode === 'multiple'
  const isDisabled = submitted || Boolean(streaming)

  const handleSelectOption = (value: string, label: string) => {
    if (isDisabled) return

    if (!isMultiple) {
      // No modo single sem allow_other: um clique envia na hora (spec §7)
      if (!allow_other) {
        const choiceText = label || value
        let msg = action.template.replace('{choice}', choiceText)
        if (msg.includes('{other}')) {
          msg = msg.replace('{other}', '')
        }
        setSubmitted(true)
        setSelectedValues([value])
        setSubmittedChoiceText(choiceText)
        sendMessage(msg)
        return
      }

      // Se allow_other é true: seleciona a opção e limpa texto livre
      setSelectedValues([value])
      setOtherText('')
      return
    }

    // Modo multiple: alterna seleção
    setSelectedValues((prev) =>
      prev.includes(value) ? prev.filter((v) => v !== value) : [...prev, value]
    )
  }

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (isDisabled) return

    const selectedLabels = options
      .filter((o) => selectedValues.includes(o.value))
      .map((o) => o.label || o.value)

    if (otherText.trim()) {
      selectedLabels.push(otherText.trim())
    }

    if (selectedLabels.length === 0) return

    setSubmitted(true)
    const choiceText = selectedLabels.join(', ')
    let msg = action.template.replace('{choice}', choiceText)
    if (msg.includes('{other}')) {
      msg = msg.replace('{other}', otherText.trim())
    }

    setSubmittedChoiceText(choiceText)
    sendMessage(msg)
  }

  const subtitle = isMultiple
    ? t('intelligentUi.optionsMultipleHint')
    : allow_other
      ? t('intelligentUi.optionsMultipleHint')
      : t('intelligentUi.optionsSingleHint')

  const titleId = `${uid}-title`
  const hasSelection = selectedValues.length > 0 || otherText.trim().length > 0

  return (
    <UiCard
      as="section"
      className="nexus-ui-options"
      title={question}
      titleId={titleId}
      subtitle={submitted ? undefined : subtitle}
      actions={
        submitted ? (
          <span className="nexus-ui-chip nexus-ui-chip--accent" aria-live="polite">
            <Check size={14} aria-hidden="true" />{' '}
            {t('intelligentUi.optionsAnswered', { choice: submittedChoiceText })}
          </span>
        ) : undefined
      }
      footer={
        (isMultiple || allow_other) && !submitted ? (
          <button
            type="button"
            className="nexus-ui-button nexus-ui-button--primary"
            onClick={handleSubmit}
            disabled={isDisabled || !hasSelection}
          >
            <Send size={14} aria-hidden="true" /> {t('intelligentUi.optionsSubmit')}
          </button>
        ) : undefined
      }
    >
      <div
        className="nexus-ui-options__grid"
        role={isMultiple ? 'group' : 'radiogroup'}
        aria-labelledby={titleId}
      >
        {options.map((opt) => {
          const isSelected = selectedValues.includes(opt.value)
          return (
            <button
              key={opt.value}
              type="button"
              className="nexus-ui-option-card"
              role={isMultiple ? 'checkbox' : 'radio'}
              aria-checked={isSelected}
              data-selected={isSelected || undefined}
              disabled={isDisabled}
              onClick={() => handleSelectOption(opt.value, opt.label)}
            >
              <div
                className={`nexus-ui-option-card__indicator ${isMultiple ? 'nexus-ui-option-card__indicator--checkbox' : ''}`}
                aria-hidden="true"
              >
                {isSelected && <Check size={12} />}
              </div>
              <div className="nexus-ui-option-card__content">
                <span className="nexus-ui-option-card__label">{opt.label}</span>
                {opt.description && (
                  <span className="nexus-ui-option-card__desc">{opt.description}</span>
                )}
              </div>
            </button>
          )
        })}
      </div>

      {allow_other && !submitted && (
        <div className="nexus-ui-options__other">
          <input
            type="text"
            className="nexus-ui-input"
            value={otherText}
            placeholder={t('intelligentUi.optionsOther')}
            maxLength={TEXT_MAX_LENGTH}
            disabled={isDisabled}
            onChange={(e) => {
              if (isDisabled) return
              setOtherText(e.target.value.slice(0, TEXT_MAX_LENGTH))
              if (!isMultiple && e.target.value.trim()) {
                setSelectedValues([])
              }
            }}
          />
        </div>
      )}
    </UiCard>
  )
}

export default OptionsCard
