import React, { useState } from 'react'
import { CornerDownRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import { useStore } from '../../store/useStore'
import type { FollowUpBlock } from '../../types'

interface Props {
  block: FollowUpBlock
  streaming?: boolean
}

/**
 * Bloco `follow_up` (plano 12 §2.3): lista vertical de sugestões de próxima pergunta,
 * no desenho dos FollowUps do Open WebUI (linhas finas, texto à esquerda, ícone de
 * "continuar"). Clique = `sendMessage(texto)` — gesto do usuário, sem auto-envio
 * (spec §7). O item escolhido fica marcado; os outros continuam clicáveis, e a
 * lista permanece no histórico como estava.
 */
export function FollowUpCard({ block, streaming }: Props) {
  const { t } = useTranslation()
  const { sendMessage } = useChatContext()
  const isStreaming = useStore((s) => s.isStreaming)
  const [chosen, setChosen] = useState<string | null>(null)
  const [pendingText, setPendingText] = useState<string | null>(null)
  const isDisabled = isStreaming || Boolean(streaming) || Boolean(pendingText)

  const handleClick = (text: string) => {
    if (isDisabled) return
    setPendingText(text)
    setChosen(text)
    sendMessage(text)
  }

  return (
    <nav className="nexus-ui-followups" aria-label={t('intelligentUi.followUpTitle')}>
      <p className="nexus-ui-followups__title" aria-hidden="true">
        {t('intelligentUi.followUpTitle')}
      </p>
      <ul className="nexus-ui-followups__list">
        {block.items.map((text) => {
          const isChosen = chosen === text
          return (
            <li key={text}>
              <button
                type="button"
                className="nexus-ui-followup"
                onClick={() => handleClick(text)}
                disabled={isDisabled}
                aria-label={t('intelligentUi.followUpHint', { text })}
                aria-pressed={isChosen}
                data-chosen={isChosen || undefined}
              >
                <span className="nexus-ui-followup__text">{text}</span>
                <CornerDownRight size={14} aria-hidden="true" className="nexus-ui-followup__icon" />
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export default FollowUpCard
