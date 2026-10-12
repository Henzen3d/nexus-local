import React, { Suspense } from 'react'
import { parseUiEnvelope } from '../lib/nexusUi'
import type { UiEnvelope } from '../types'

const ProgressCard = React.lazy(() => import('./components/ProgressCard'))
const ChecklistCard = React.lazy(() => import('./components/ChecklistCard'))
const ImageCard = React.lazy(() => import('./components/ImageCard'))
const ChartCard = React.lazy(() => import('./components/ChartCard'))
const ControlsCard = React.lazy(() => import('./components/ControlsCard'))
const SandboxCard = React.lazy(() => import('./components/SandboxCard'))

interface Props {
  envelope?: UiEnvelope | null
}

export function DynamicRenderer({ envelope }: Props) {
  if (!envelope) return null

  const validEnvelope = parseUiEnvelope(envelope)
  if (!validEnvelope || validEnvelope.blocks.length === 0) {
    return null
  }

  return (
    <div className="nexus-ui-container" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <Suspense fallback={null}>
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
