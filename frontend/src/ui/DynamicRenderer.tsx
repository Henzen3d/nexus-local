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
const MetricCard = React.lazy(() => import('./components/MetricCard'))
const CalloutCard = React.lazy(() => import('./components/CalloutCard'))
const FollowUpCard = React.lazy(() => import('./components/FollowUpCard'))

interface Props {
  envelope?: UiEnvelope | null
  onRuntimeError?: (title: string, message: string) => void
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
    case 'metric':
      // Plano 12 §2.1: cabeçalho + uma linha de tiles (duas quando há mais de 2 itens em bolha estreita)
      return (block.title ? 34 : 0) + 14 + 70 * (block.items.length > 2 ? 2 : 1)
    case 'callout':
      return 56 + 20 * Math.ceil(block.body.length / 80)
    case 'follow_up':
      return 28 + block.items.length * 40
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

export function DynamicRenderer({ envelope, onRuntimeError }: Props) {
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
            return <SandboxCard key={block.id} block={block} onRuntimeError={onRuntimeError} />
          }

          if (block.type === 'metric') {
            return <MetricCard key={block.id} block={block} />
          }

          if (block.type === 'callout') {
            return <CalloutCard key={block.id} block={block} />
          }

          if (block.type === 'follow_up') {
            return <FollowUpCard key={block.id} block={block} />
          }

          return null
        })}
      </Suspense>
    </div>
  )
}

export default DynamicRenderer
