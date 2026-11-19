import React, { useEffect, useState } from 'react'
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
 * Bloco `follow_up` (plano 12 §2.3 / perguntas-adicionais §1):
 * Ações agrupadas em estilo chip no rodapé da resposta com fundo e borda discretos.
 * Permite quebra de linha em desktop e empilhamento em telas estreitas.
 * Clique = `sendMessage(texto)` — somente marca o item quando sendMessage retornar true.
 * Se retornar false, mantém o bloco utilizável para nova tentativa.
 */
export function FollowUpCard({ block, streaming }: Props) {
  const { t } = useTranslation()
  const { sendMessage } = useChatContext()
  const isStreaming = useStore((s) => s.isStreaming)
  const [chosen, setChosen] = useState<string | null>(null)
  const [pendingText, setPendingText] = useState<string | null>(null)
  const isDisabled = isStreaming || Boolean(streaming) || Boolean(pendingText)

  // Ao encerrar geração, reseta o estado pending para permitir novas tentativas ou seleções
  useEffect(() => {
    if (!isStreaming && !streaming) {
      setPendingText(null)
    }
  }, [isStreaming, streaming])

  const handleClick = (text: string) => {
    if (isDisabled) return
    setPendingText(text)
    const accepted = sendMessage(text)
    if (accepted) {
      setChosen(text)
    } else {
      setPendingText(null)
    }
  }

  return (
    <nav className="nexus-ui-followups" aria-label={t('intelligentUi.followUpTitle')}>
      <ul className="nexus-ui-followups__list">
        {block.items.map((text) => {
          const isChosen = chosen === text
          return (
            <li key={text} className="nexus-ui-followups__item">
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
                <CornerDownRight size={13} aria-hidden="true" className="nexus-ui-followup__icon" />
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}

export default FollowUpCard
