import React, { Suspense } from 'react'
import { parseUiEnvelope } from '../lib/nexusUi'
import type { UiBlock, UiEnvelope } from '../types'
import { useIntelligentUiEnabled } from './hooks/useIntelligentUi'

const ProgressCard = React.lazy(() => import('./components/ProgressCard'))
const ChecklistCard = React.lazy(() => import('./components/ChecklistCard'))
const ImageCard = React.lazy(() => import('./components/ImageCard'))
const ChartCard = React.lazy(() => import('./components/ChartCard'))
const ControlsCard = React.lazy(() => import('./components/ControlsCard'))
const SandboxCard = React.lazy(() => import('./components/SandboxCard'))

interface Props {
  envelope?: UiEnvelope | null
}

/**
 * Altura mínima reservada por bloco enquanto o chunk do cartão carrega
 * (spec §7, "Zero CLS"): a bolha não salta quando o lazy resolve.
 * Valores batem com o tamanho real dos cartões do plano 11 (casca `UiCard`:
 * cabeçalho ≈ 34 px, corpo com 12/14 px de respiro; gráfico = 220 px de desenho).
 */
function reservedHeight(block: UiBlock): number {
  switch (block.type) {
    case 'progress': {
      const hasValue = block.value !== undefined && block.max !== undefined
      const steps = Array.isArray(block.steps) ? block.steps.length : 0
      return (hasValue ? 88 : 0) + (steps > 0 ? 60 + steps * 32 : 0)
    }
    case 'card': {
      const facts = Array.isArray(block.facts) && block.facts.length > 0 ? 64 : 0
      return (block.image ? 124 : 72) + facts
    }
    case 'chart':
      return 280
    case 'controls':
      return 128 + block.fields.length * 62
    case 'sandbox':
      return (block.initial_height || 300) + 44
    default:
      return 0
  }
}

function BlockSkeleton({ blocks }: { blocks: UiBlock[] }) {
  return (
    <>
      {blocks.map((block) => (
        <div
          key={block.id}
          aria-hidden="true"
          className="nexus-ui-card nexus-ui-skeleton"
          style={{ minHeight: reservedHeight(block) }}
        />
      ))}
    </>
  )
}

export function DynamicRenderer({ envelope }: Props) {
  // Flag desligada (ou ainda não carregada): nada é pintado, mesmo com payload.
  const enabled = useIntelligentUiEnabled()
  if (!enabled || !envelope) return null

  const validEnvelope = parseUiEnvelope(envelope)
  if (!validEnvelope || validEnvelope.blocks.length === 0) {
    return null
  }

  return (
    <div className="nexus-ui-container">
      <Suspense fallback={<BlockSkeleton blocks={validEnvelope.blocks} />}>
        {validEnvelope.blocks.map((block) => {
          if (block.type === 'progress') {
            const hasValue = block.value !== undefined && block.max !== undefined
            const hasSteps = Array.isArray(block.steps) && block.steps.length > 0

            return (
              <React.Fragment key={block.id}>
                {hasValue && <ProgressCard block={block} />}
                {hasSteps && <ChecklistCard block={block} />}
              </React.Fragment>
            )
          }

          if (block.type === 'card') {
            return <ImageCard key={block.id} block={block} />
          }

          if (block.type === 'chart') {
            return <ChartCard key={block.id} block={block} />
          }

          if (block.type === 'controls') {
            return <ControlsCard key={block.id} block={block} />
          }

          if (block.type === 'sandbox') {
            return <SandboxCard key={block.id} block={block} />
          }

          return null
        })}
      </Suspense>
    </div>
  )
}

export default DynamicRenderer
