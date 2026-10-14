import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import Renderer, { act } from 'react-test-renderer'
import { ControlsCard } from '../../src/ui/components/ControlsCard'
import { FollowUpCard } from '../../src/ui/components/FollowUpCard'
import { SandboxCard } from '../../src/ui/components/SandboxCard'
import { DynamicRenderer } from '../../src/ui/DynamicRenderer'
import { controls, reset } from './uiStubs'
import type { ControlsBlock, FollowUpBlock, SandboxBlock } from '../../src/types'

test('stream UI: progressive rendering disables interactions and reserves skeleton', async () => {
  reset()

  // 1. ControlsCard: disabled while streaming
  const controlsBlock: ControlsBlock = {
    id: 'ctrl_1',
    type: 'controls',
    title: 'Ajustes',
    fields: [
      { id: 'q', label: 'Quantidade', kind: 'number', min: 1, max: 10, default: 5 },
      { id: 'obs', label: 'Observação', kind: 'text', placeholder: 'Digite aqui' },
    ],
    action: { name: 'send_message', template: 'qtd: {q}' },
  }

  let ctrlView: Renderer.ReactTestRenderer
  act(() => {
    ctrlView = Renderer.create(<ControlsCard block={controlsBlock} streaming={true} />)
  })

  const submitBtn = ctrlView!.root.findByProps({ type: 'submit' })
  assert.equal(submitBtn.props.disabled, true)

  const numInput = ctrlView!.root.findByProps({ name: 'q' })
  assert.equal(numInput.props.disabled, true)

  const textInput = ctrlView!.root.findByProps({ name: 'obs' })
  assert.equal(textInput.props.disabled, true)

  // Submissão não dispara envio
  act(() => {
    ctrlView!.root.findByType('form').props.onSubmit({ preventDefault: () => {} })
  })
  assert.equal(controls.sent.length, 0)

  // 2. FollowUpCard: disabled while streaming
  const followUpBlock: FollowUpBlock = {
    id: 'fup_1',
    type: 'follow_up',
    items: ['Sugestão 1', 'Sugestão 2'],
  }

  let followView: Renderer.ReactTestRenderer
  act(() => {
    followView = Renderer.create(<FollowUpCard block={followUpBlock} streaming={true} />)
  })

  const followButtons = followView!.root.findAllByType('button')
  assert.equal(followButtons.length, 2)
  assert.equal(followButtons[0].props.disabled, true)
  assert.equal(followButtons[1].props.disabled, true)

  act(() => {
    followButtons[0].props.onClick()
  })
  assert.equal(controls.sent.length, 0)

  // 3. SandboxCard: deferred iframe mounting & disabled actions during stream
  const sandboxBlock: SandboxBlock = {
    id: 'sbx_1',
    type: 'sandbox',
    title: 'Visualizador',
    html: '<p>Teste</p>',
  }

  let sbxView: Renderer.ReactTestRenderer
  act(() => {
    sbxView = Renderer.create(<SandboxCard block={sandboxBlock} streaming={true} />)
  })

  // Iframe NÃO monta enquanto streaming=true
  assert.equal(sbxView!.root.findAllByType('iframe').length, 0)
  const placeholder = sbxView!.root.findByProps({ className: 'nexus-ui-sandbox__placeholder' })
  assert.ok(placeholder)

  // Botões de ação estão disabled
  const actionButtons = sbxView!.root.findAllByProps({ className: 'nexus-ui-action' })
  assert.ok(actionButtons.length >= 2)
  for (const btn of actionButtons) {
    assert.equal(btn.props.disabled, true)
  }

  // 4. DynamicRenderer with pendingType renders skeleton
  let dynView: Renderer.ReactTestRenderer
  await act(async () => {
    dynView = Renderer.create(
      <DynamicRenderer
        envelope={{ v: 1, blocks: [followUpBlock] }}
        streaming={true}
        pendingType="chart"
      />
    )
  })

  // Contém o esqueleto do bloco pendente
  const skeletons = dynView!.root.findAllByProps({ className: 'nexus-ui-card nexus-ui-skeleton' })
  assert.ok(skeletons.length >= 1)
})
