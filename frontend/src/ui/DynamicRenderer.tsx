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
 * Valores batem com o tamanho real dos cartões (chart = 220 de gráfico + cabeçalho).
 */
function reservedHeight(block: UiBlock): number {
  switch (block.type) {
    case 'progress': {
      const hasValue = block.value !== undefined && block.max !== undefined
      const steps = Array.isArray(block.steps) ? block.steps.length : 0
      return (hasValue ? 56 : 0) + (steps > 0 ? 40 + steps * 28 : 0)
    }
    case 'card':
      return block.image ? 220 : 72
    case 'chart':
      return 280
    case 'controls':
      return 72 + block.fields.length * 58 + 44
    case 'sandbox':
      return (block.initial_height || 300) + 48
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
          className="nexus-ui-skeleton"
          style={{
            minHeight: reservedHeight(block),
            marginTop: '12px',
            borderRadius: '10px',
            border: '1px solid var(--hairline)',
            backgroundColor: 'var(--surface-card)',
            opacity: 0.6,
          }}
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
    <div className="nexus-ui-container" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
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
