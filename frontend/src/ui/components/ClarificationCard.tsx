import React, { useId, useMemo, useState } from 'react'
import { Check, Send } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import { useStore } from '../../store/useStore'
import type { ClarificationBlock } from '../../types'
import { UiCard } from './UiCard'

interface Props {
  block: ClarificationBlock
  streaming?: boolean
  messageId?: string
}

const OTHER_TEXT_MAX_LENGTH = 200

/**
 * Bloco `clarification` (plano perguntas-adicionais §2/§3):
 * Quadro agrupado de perguntas com seleção única por pergunta e confirmação explícita.
 * Envia exatamente uma mensagem comum no chat formatada com as perguntas e escolhas.
 */
export function ClarificationCard({ block, streaming, messageId }: Props) {
  const { t } = useTranslation()
  const { sendMessage } = useChatContext()
  const uid = useId()
  const { questions, submit_label } = block

  const isGlobalStreaming = useStore((s) => s.isStreaming)
  const activeConversationId = useStore((s) => s.activeConversationId)

  // O quadro só fica interativo na mensagem que fechou o último turno da conversa ativa
  const isLatestAssistantMessage = useStore((s) => {
    if (!messageId || messageId === '__streaming__') return false
    const msgs = s.messages
    if (!msgs || msgs.length === 0) return true
    const lastMsg = msgs[msgs.length - 1]
    return lastMsg.id === messageId
  })

  const [selections, setSelections] = useState<Record<string, string>>({})
  const [otherTexts, setOtherTexts] = useState<Record<string, string>>({})
  const [submitted, setSubmitted] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const isReadOnly = !isLatestAssistantMessage || submitted
  const isDisabled = isReadOnly || isGlobalStreaming || Boolean(streaming) || isSubmitting

  const handleSelectOption = (questionId: string, optionId: string) => {
    if (isDisabled) return
    setSelections((prev) => ({
      ...prev,
      [questionId]: optionId,
    }))
  }

  const handleOtherTextChange = (questionId: string, text: string) => {
    if (isDisabled) return
    const trimmed = text.slice(0, OTHER_TEXT_MAX_LENGTH)
    setOtherTexts((prev) => ({
      ...prev,
      [questionId]: trimmed,
    }))
  }

  // Validação: todas as perguntas devem ter uma resposta válida selecionada
  const allAnswered = useMemo(() => {
    if (!questions || questions.length === 0) return false
    return questions.every((q) => {
      const selected = selections[q.id]
      if (!selected) return false
      if (selected === '__other__') {
        const otherVal = otherTexts[q.id]
        return Boolean(otherVal && otherVal.trim().length > 0)
      }
      return q.options.some((opt) => opt.id === selected)
    })
  }, [questions, selections, otherTexts])

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (isDisabled || !allAnswered) return

    // Valida se a conversa continua ativa
    const currentActiveConv = useStore.getState().activeConversationId
    if (activeConversationId && currentActiveConv !== activeConversationId) {
      return
    }

    // Monta o texto legível na ordem das perguntas
    const parts = questions.map((q) => {
      const sel = selections[q.id]
      let choiceText = ''
      if (sel === '__other__') {
        choiceText = (otherTexts[q.id] || '').trim()
      } else {
        const found = q.options.find((o) => o.id === sel)
        choiceText = found ? found.label : sel
      }
      return `${q.label} — ${choiceText}`
    })

    let messageText = parts.join('. ')
    if (messageText && !messageText.endsWith('.')) {
      messageText += '.'
    }

    setIsSubmitting(true)
    const accepted = sendMessage(messageText)

    if (accepted) {
      setSubmitted(true)
      setIsSubmitting(false)
    } else {
      // Se envio foi recusado, preserva escolhas e libera nova tentativa
      setIsSubmitting(false)
    }
  }

  const cardTitleId = `${uid}-title`
  const submitButtonLabel = submit_label || t('intelligentUi.clarificationSubmit')

  return (
    <UiCard
      as="section"
      className="nexus-ui-clarification"
      title={t('intelligentUi.clarificationTitle')}
      titleId={cardTitleId}
      actions={
        submitted ? (
          <span className="nexus-ui-chip nexus-ui-chip--accent" aria-live="polite">
            <Check size={14} aria-hidden="true" /> {t('intelligentUi.clarificationAnswered')}
          </span>
        ) : !isLatestAssistantMessage ? (
          <span className="nexus-ui-chip" aria-live="polite">
            {t('intelligentUi.clarificationReadOnly')}
          </span>
        ) : undefined
      }
      footer={
        !isReadOnly ? (
          <button
            type="submit"
            form={`${uid}-form`}
            className="nexus-ui-button nexus-ui-button--primary"
            disabled={isDisabled || !allAnswered}
          >
            <Send size={14} aria-hidden="true" /> {submitButtonLabel}
          </button>
        ) : undefined
      }
    >
      <form id={`${uid}-form`} onSubmit={handleSubmit} className="nexus-ui-clarification__form">
        <div className="nexus-ui-clarification__groups">
          {questions.map((q) => {
            const groupName = `${uid}-${q.id}`
            const selectedOptId = selections[q.id]

            return (
              <fieldset
                key={q.id}
                className="nexus-ui-clarification__group"
                disabled={isDisabled}
              >
                <legend className="nexus-ui-clarification__legend">{q.label}</legend>
                <div
                  className="nexus-ui-clarification__options"
                  role="radiogroup"
                  aria-label={q.label}
                >
                  {q.options.map((opt) => {
                    const isSelected = selectedOptId === opt.id
                    const radioId = `${uid}-${q.id}-${opt.id}`

                    return (
                      <label
                        key={opt.id}
                        htmlFor={radioId}
                        className="nexus-ui-clarification__option"
                        data-selected={isSelected || undefined}
                      >
                        <input
                          type="radio"
                          id={radioId}
                          name={groupName}
                          value={opt.id}
                          checked={isSelected}
                          disabled={isDisabled}
                          onChange={() => handleSelectOption(q.id, opt.id)}
                          className="nexus-ui-clarification__radio"
                        />
                        <span className="nexus-ui-clarification__indicator" aria-hidden="true">
                          {isSelected && <Check size={11} strokeWidth={3} />}
                        </span>
                        <span className="nexus-ui-clarification__option-label">{opt.label}</span>
                      </label>
                    )
                  })}

                  {q.allow_other && (
                    <div className="nexus-ui-clarification__other-wrapper">
                      <label
                        htmlFor={`${uid}-${q.id}-other`}
                        className="nexus-ui-clarification__option nexus-ui-clarification__option--other"
                        data-selected={selectedOptId === '__other__' || undefined}
                      >
                        <input
                          type="radio"
                          id={`${uid}-${q.id}-other`}
                          name={groupName}
                          value="__other__"
                          checked={selectedOptId === '__other__'}
                          disabled={isDisabled}
                          onChange={() => handleSelectOption(q.id, '__other__')}
                          className="nexus-ui-clarification__radio"
                        />
                        <span className="nexus-ui-clarification__indicator" aria-hidden="true">
                          {selectedOptId === '__other__' && <Check size={11} strokeWidth={3} />}
                        </span>
                        <span className="nexus-ui-clarification__option-label">
                          {t('intelligentUi.clarificationOther')}
                        </span>
                      </label>

                      {selectedOptId === '__other__' && !submitted && (
                        <input
                          type="text"
                          className="nexus-ui-input nexus-ui-clarification__other-input"
                          value={otherTexts[q.id] || ''}
                          placeholder={t('intelligentUi.clarificationOtherPlaceholder')}
                          maxLength={OTHER_TEXT_MAX_LENGTH}
                          disabled={isDisabled}
                          aria-label={t('intelligentUi.clarificationOtherLabel', { question: q.label })}
                          onChange={(e) => handleOtherTextChange(q.id, e.target.value)}
                          autoFocus
                        />
                      )}
                    </div>
                  )}
                </div>
              </fieldset>
            )
          })}
        </div>
      </form>
    </UiCard>
  )
}

export default ClarificationCard
