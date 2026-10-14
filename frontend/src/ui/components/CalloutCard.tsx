import React from 'react'
import { CircleCheck, Info, OctagonAlert, TriangleAlert } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { CalloutBlock } from '../../types'

interface Props {
  block: CalloutBlock
}

const ICONS = {
  info: Info,
  success: CircleCheck,
  warning: TriangleAlert,
  danger: OctagonAlert,
} as const

const KIND_LABEL_KEYS = {
  info: 'intelligentUi.calloutInfo',
  success: 'intelligentUi.calloutSuccess',
  warning: 'intelligentUi.calloutWarning',
  danger: 'intelligentUi.calloutDanger',
} as const

/**
 * Bloco `callout` (plano 12 §2.2): faixa com borda esquerda na cor do tipo e ícone.
 * Não usa a casca `UiCard` (não tem cabeçalho/ações): é um aviso, não um painel.
 * `role="note"` em todos os tipos — o `danger` do modelo é conteúdo, não um alerta
 * do sistema, então não interrompe o leitor de tela (spec §7).
 */
export function CalloutCard({ block }: Props) {
  const { t } = useTranslation()
  const Icon = ICONS[block.kind] ?? Info
  const kindLabel = t(KIND_LABEL_KEYS[block.kind] ?? KIND_LABEL_KEYS.info)

  return (
    <aside className="nexus-ui-callout" data-kind={block.kind} role="note">
      <span className="nexus-ui-callout__icon" aria-hidden="true">
        <Icon size={16} />
      </span>
      <div className="nexus-ui-callout__content">
        {block.title ? (
          <p className="nexus-ui-callout__title">
            <span className="nexus-ui-sr-only">{kindLabel}: </span>
            {block.title}
          </p>
        ) : (
          <span className="nexus-ui-sr-only">{kindLabel}: </span>
        )}
        <p className="nexus-ui-callout__body">{block.body}</p>
      </div>
    </aside>
  )
}

export default CalloutCard
