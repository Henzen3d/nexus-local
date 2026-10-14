import React, { useState } from 'react'
import { isAllowedImageUrl } from '../../lib/nexusUi'
import type { CardBlock } from '../../types'
import { useIntelligentUiConfig } from '../hooks/useIntelligentUi'
import { looksNumeric } from '../lib/chartFormat'
import { UiCard } from './UiCard'

interface Props {
  block: CardBlock
}

/**
 * Cartão com foto confiável, texto e "facts". Facts numéricos viram mini-métricas
 * (valor grande, rótulo pequeno), como o `MetricIndicator` do OpenUI; os demais
 * ficam como pares rótulo/valor na mesma grade.
 */
export function ImageCard({ block }: Props) {
  const { title, body, facts, image } = block
  const [imgError, setImgError] = useState(false)
  // Mesma lista de hosts e mesma flag de rede privada que o servidor usou ao
  // validar o bloco (spec, seção 6): o frontend repete a checagem antes do <img>.
  const { image_hosts, allow_private_http } = useIntelligentUiConfig()

  const isImgValid =
    image &&
    !imgError &&
    isAllowedImageUrl(
      image.url,
      image_hosts,
      typeof window !== 'undefined' ? window.location.host : undefined,
      allow_private_http
    )

  const hasFacts = Boolean(facts && facts.length > 0)

  return (
    <UiCard className="nexus-ui-infocard" data-has-image={isImgValid ? 'true' : undefined}>
      <div className="nexus-ui-infocard__main">
        {isImgValid && (
          <figure className="nexus-ui-infocard__media">
            <img
              src={image.url}
              alt={image.alt}
              loading="lazy"
              decoding="async"
              referrerPolicy="no-referrer"
              onError={() => setImgError(true)}
            />
          </figure>
        )}

        <div className="nexus-ui-infocard__text">
          <h4 className="nexus-ui-infocard__title">{title}</h4>
          {body && <p className="nexus-ui-infocard__body">{body}</p>}
        </div>
      </div>

      {hasFacts && (
        <dl className="nexus-ui-facts">
          {facts!.map((fact, idx) => {
            const numeric = looksNumeric(fact.value)
            return (
              <div key={idx} className="nexus-ui-fact" data-numeric={numeric || undefined}>
                <dt className="nexus-ui-fact__label">{fact.label}</dt>
                <dd className="nexus-ui-fact__value">{fact.value}</dd>
              </div>
            )
          })}
        </dl>
      )}
    </UiCard>
  )
}

export default ImageCard
