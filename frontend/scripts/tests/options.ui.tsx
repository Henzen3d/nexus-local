import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import Renderer, { act } from 'react-test-renderer'
import { OptionsCard } from '../../src/ui/components/OptionsCard'
import { controls, reset } from './uiStubs'
import type { OptionsBlock } from '../../src/types'

test('OptionsCard: single mode sends immediately on click and locks', () => {
  reset()

  const block: OptionsBlock = {
    id: 'opt_1',
    type: 'options',
    question: 'Qual estilo de viagem prefere?',
    mode: 'single',
    options: [
      { value: 'praia', label: 'Praia e descanso', description: 'Litoral calmo' },
      { value: 'trilha', label: 'Natureza e aventura' },
    ],
    action: { name: 'send_message', template: 'Prefiro: {choice}' },
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<OptionsCard block={block} />)
  })

  const root = view!.root
  const buttons = root.findAllByProps({ role: 'radio' })
  assert.equal(buttons.length, 2)
  assert.equal(buttons[0].props['aria-checked'], false)

  // Clique em "Praia e descanso" envia na hora (spec §7)
  act(() => {
    buttons[0].props.onClick()
  })

  assert.equal(controls.sent.length, 1)
  assert.deepEqual(controls.sent[0], ['Prefiro: Praia e descanso'])

  // Bloqueio após envio: mostra chip respondido e desabilita opções
  const chip = root.findByProps({ className: 'nexus-ui-chip nexus-ui-chip--accent' })
  assert.ok(chip)

  // Segundo clique não envia nada
  act(() => {
    buttons[1].props.onClick()
  })
  assert.equal(controls.sent.length, 1)
})

test('OptionsCard: multiple mode allows multi-selection and submits via button', () => {
  reset()

  const block: OptionsBlock = {
    id: 'opt_multi',
    type: 'options',
    question: 'Selecione suas stacks:',
    mode: 'multiple',
    options: [
      { value: 'react', label: 'React' },
      { value: 'node', label: 'Node.js' },
      { value: 'python', label: 'Python' },
    ],
    action: { name: 'send_message', template: 'Habilidades: {choice}' },
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<OptionsCard block={block} />)
  })

  const root = view!.root
  const checkboxes = root.findAllByProps({ role: 'checkbox' })
  assert.equal(checkboxes.length, 3)

  const submitBtn = root.findByProps({ className: 'nexus-ui-button nexus-ui-button--primary' })
  assert.equal(submitBtn.props.disabled, true) // desabilitado sem seleção

  // Seleciona React e Python
  act(() => {
    checkboxes[0].props.onClick()
    checkboxes[2].props.onClick()
  })

  assert.equal(checkboxes[0].props['aria-checked'], true)
  assert.equal(checkboxes[1].props['aria-checked'], false)
  assert.equal(checkboxes[2].props['aria-checked'], true)
  assert.equal(submitBtn.props.disabled, false)

  // Clique no botão de envio
  act(() => {
    submitBtn.props.onClick()
  })

  assert.equal(controls.sent.length, 1)
  assert.deepEqual(controls.sent[0], ['Habilidades: React, Python'])
})

test('OptionsCard: allow_other field and streaming disabled', () => {
  reset()

  const block: OptionsBlock = {
    id: 'opt_other',
    type: 'options',
    question: 'Qual seu framework favorito?',
    mode: 'single',
    options: [
      { value: 'vue', label: 'Vue' },
      { value: 'angular', label: 'Angular' },
    ],
    allow_other: true,
    action: { name: 'send_message', template: 'Escolha: {choice}' },
  }

  // Com streaming=true
  let streamView: Renderer.ReactTestRenderer
  act(() => {
    streamView = Renderer.create(<OptionsCard block={block} streaming={true} />)
  })

  const radios = streamView!.root.findAllByProps({ role: 'radio' })
  assert.equal(radios[0].props.disabled, true)
  const input = streamView!.root.findByProps({ className: 'nexus-ui-input' })
  assert.equal(input.props.disabled, true)

  // Sem streaming: digita em outro e submete
  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<OptionsCard block={block} />)
  })

  const otherInput = view!.root.findByProps({ className: 'nexus-ui-input' })
  act(() => {
    otherInput.props.onChange({ target: { value: 'Svelte' } })
  })

  const submitBtn = view!.root.findByProps({ className: 'nexus-ui-button nexus-ui-button--primary' })
  assert.equal(submitBtn.props.disabled, false)

  act(() => {
    submitBtn.props.onClick()
  })

  assert.equal(controls.sent.length, 1)
  assert.deepEqual(controls.sent[0], ['Escolha: Svelte'])
})
