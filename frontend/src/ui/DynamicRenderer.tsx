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
const SceneCard = React.lazy(() => import('./components/SceneCard'))
const MetricCard = React.lazy(() => import('./components/MetricCard'))
const TableCard = React.lazy(() => import('./components/TableCard'))
const OptionsCard = React.lazy(() => import('./components/OptionsCard'))
const CalloutCard = React.lazy(() => import('./components/CalloutCard'))
const FollowUpCard = React.lazy(() => import('./components/FollowUpCard'))

interface Props {
  envelope?: UiEnvelope | null
  streaming?: boolean
  pendingType?: string | null
  messageId?: string
  onRuntimeError?: (title: string, message: string) => void
}

/**
 * Altura mínima reservada por bloco enquanto o chunk do cartão carrega
 * (spec §7, "Zero CLS"): a bolha não salta quando o lazy resolve.
 * Valores batem com o tamanho real dos cartões do plano 11 (casca `UiCard`:
 * cabeçalho ≈ 34 px, corpo com 12/14 px de respiro; gráfico = 220 px de desenho).
 */
function reservedHeight(block: { type: string; [k: string]: any }): number {
  switch (block.type) {
    case 'progress': {
      const hasValue = block.value !== undefined && block.max !== undefined
      const steps = Array.isArray(block.steps) ? block.steps.length : 0
      return (hasValue || steps === 0 ? 88 : 0) + (steps > 0 ? 60 + steps * 32 : 0)
    }
    case 'card': {
      const facts = Array.isArray(block.facts) && block.facts.length > 0 ? 64 : 0
      return (block.image ? 124 : 72) + facts
    }
    case 'chart':
      return 280
    case 'controls': {
      const count = Array.isArray(block.fields) ? block.fields.length : 2
      return 128 + count * 62
    }
    case 'sandbox':
      return (block.initial_height || (block.kind === 'scene' ? 320 : 300)) + 44
    case 'metric': {
      const itemsCount = Array.isArray(block.items) ? block.items.length : 2
      return (block.title ? 34 : 0) + 14 + 70 * (itemsCount > 2 ? 2 : 1)
    }
    case 'table': {
      const rowCount = Array.isArray(block.rows) ? block.rows.length : 4
      return 56 + 36 * Math.min(rowCount, 11)
    }
    case 'options': {
      const count = Array.isArray(block.options) ? block.options.length : 3
      return 56 + Math.ceil(count / 2) * 58
    }
    case 'callout': {
      const len = typeof block.body === 'string' ? block.body.length : 60
      return 56 + 20 * Math.ceil(len / 80)
    }
    case 'follow_up': {
      const items = Array.isArray(block.items) ? block.items.length : 3
      return 28 + items * 40
    }
    default:
      return 120
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

export function DynamicRenderer({ envelope, streaming, pendingType, messageId, onRuntimeError }: Props) {
  // Flag desligada (ou ainda não carregada): nada é pintado, mesmo com payload.
  const enabled = useIntelligentUiEnabled()
  if (!enabled || (!envelope && !pendingType)) return null

  const validEnvelope = envelope ? parseUiEnvelope(envelope) : null
  const blocks = validEnvelope?.blocks || []
  if (blocks.length === 0 && !pendingType) {
    return null
  }

  return (
    <div className="nexus-ui-container">
      <Suspense fallback={<BlockSkeleton blocks={blocks} />}>
        {blocks.map((block) => {
          if (block.type === 'progress') {
            const hasValue = block.value !== undefined && block.max !== undefined
            const hasSteps = Array.isArray(block.steps) && block.steps.length > 0

            return (
              <React.Fragment key={block.id}>
                {hasValue && <ProgressCard block={block} messageId={messageId} />}
                {hasSteps && <ChecklistCard block={block} />}
              </React.Fragment>
            )
          }

          if (block.type === 'card') {
            return <ImageCard key={block.id} block={block} />
          }

          if (block.type === 'chart') {
            return <ChartCard key={block.id} block={block} messageId={messageId} />
          }

          if (block.type === 'controls') {
            return <ControlsCard key={block.id} block={block} streaming={streaming} messageId={messageId} />
          }

          if (block.type === 'sandbox') {
            if (block.kind === 'scene') {
              return (
                <SceneCard
                  key={block.id}
                  block={block}
                  streaming={streaming}
                  messageId={messageId}
                  onRuntimeError={onRuntimeError}
                />
              )
            }
            return <SandboxCard key={block.id} block={block} streaming={streaming} onRuntimeError={onRuntimeError} />
          }

          if (block.type === 'metric') {
            return <MetricCard key={block.id} block={block} messageId={messageId} />
          }

          if (block.type === 'table') {
            return <TableCard key={block.id} block={block} messageId={messageId} />
          }

          if (block.type === 'options') {
            return <OptionsCard key={block.id} block={block} streaming={streaming} />
          }

          if (block.type === 'callout') {
            return <CalloutCard key={block.id} block={block} />
          }

          if (block.type === 'follow_up') {
            return <FollowUpCard key={block.id} block={block} streaming={streaming} />
          }

          return null
        })}
        {pendingType && (
          <div
            className="nexus-ui-card nexus-ui-skeleton"
            style={{ minHeight: reservedHeight({ type: pendingType, id: '__pending__' }) }}
            aria-hidden="true"
          />
        )}
      </Suspense>
    </div>
  )
}

export default DynamicRenderer
