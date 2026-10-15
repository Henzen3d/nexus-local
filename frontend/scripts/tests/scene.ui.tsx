import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import Renderer, { act } from 'react-test-renderer'
import { SceneCard } from '../../src/ui/components/SceneCard'
import { controls, reset } from './uiStubs'
import { orbitFixture, pendulumFixture } from '../../src/ui/scene/__fixtures__/fixtures'
import type { SandboxBlock } from '../../src/types'

test('SceneCard: renders 3D orbit scene with controls, iframe, actions and readout', () => {
  reset()

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<SceneCard block={orbitFixture} />)
  })

  const root = view!.root

  // Verifica se o iframe está presente com sandbox allow-scripts e srcDoc
  const iframe = root.findByType('iframe')
  assert.ok(iframe)
  assert.equal(iframe.props.sandbox, 'allow-scripts')
  assert.equal(iframe.props.title, 'Órbita Planetária')
  assert.ok(iframe.props.srcDoc.includes('NexusScene.setup('))
  assert.ok(iframe.props.srcDoc.includes("default-src 'none'"))

  // Verifica parâmetro de range
  const rangeInput = root.findByProps({ type: 'range' })
  assert.ok(rangeInput)
  assert.equal(rangeInput.props.min, 0.2)
  assert.equal(rangeInput.props.max, 3)
  assert.equal(rangeInput.props.value, 1)

  // Verifica tabela de acessibilidade sr-only para o readout
  const table = root.findByType('table')
  assert.ok(table)
  assert.equal(table.props.className, 'sr-only')
})

test('SceneCard: renders 2D pendulum scene with multiple parameters and updates value', () => {
  reset()

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<SceneCard block={pendulumFixture} />)
  })

  const root = view!.root

  // Dois parâmetros de range (comprimento e gravidade)
  const ranges = root.findAllByProps({ type: 'range' })
  assert.equal(ranges.length, 2)
  assert.equal(ranges[0].props.value, 200)
  assert.equal(ranges[1].props.value, 9.8)

  // Mudança de valor de parâmetro atualiza o slider
  act(() => {
    ranges[0].props.onChange({ target: { value: '250' } })
  })

  const updatedRanges = root.findAllByProps({ type: 'range' })
  assert.equal(updatedRanges[0].props.value, 250)
})

test('SceneCard: handles runtime error and sends correction prompt', () => {
  reset()

  const listeners: Record<string, Function> = {}
  const hostWindow = {
    addEventListener: (type: string, cb: Function) => {
      listeners[type] = cb
    },
    removeEventListener: (type: string) => {
      delete listeners[type]
    },
  }
  Object.assign(globalThis, { window: hostWindow })

  const frameWindow = { postMessage: () => {} }
  let errorReported = false

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(
      <SceneCard
        block={orbitFixture}
        onRuntimeError={(title, msg) => {
          assert.equal(title, 'Órbita Planetária')
          assert.ok(msg.includes('THREE is not defined'))
          errorReported = true
        }}
      />,
      {
        createNodeMock: (node) => (node.type === 'iframe' ? { contentWindow: frameWindow } : {}),
      }
    )
  })

  const root = view!.root
  const iframe = root.findByType('iframe')
  assert.ok(iframe)

  // Simula erro de runtime vindo do iframe
  act(() => {
    if (listeners['message']) {
      listeners['message']({
        source: frameWindow,
        data: {
          type: '__nexus_scene_error',
          message: 'ReferenceError: THREE is not defined',
        },
      })
    }
  })

  assert.equal(errorReported, true)

  // Erro visível no alerta
  const errorAlert = root.findByProps({ role: 'alert' })
  assert.ok(errorAlert)

  // Botão "Pedir correção" clica e dispara sendMessage
  const fixBtn = errorAlert.findByType('button')
  assert.ok(fixBtn)

  act(() => {
    fixBtn.props.onClick()
  })

  assert.equal(controls.sent.length, 1)
  const sentText = String(controls.sent[0][0])
  assert.ok(sentText.includes('Órbita Planetária'))
  assert.ok(sentText.includes('ReferenceError: THREE is not defined'))
})
