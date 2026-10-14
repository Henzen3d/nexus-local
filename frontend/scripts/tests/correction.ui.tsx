import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { runInNewContext } from 'node:vm'
import Renderer, { act } from 'react-test-renderer'
import { CorrectionNotice } from '../../src/ui/components/CorrectionNotice'
import { SandboxCard } from '../../src/ui/components/SandboxCard'
import { controls, reset, useStore } from './uiStubs'

const error = { code: 'missing_required' as const, block_id: 'visual', path: 'body', message: 'missing_required: body', hint: 'callout: body' }
const props = { messageId: 'm', errors: [error], dropped: 1 }

test('real correction component: flag, streaming, explicit click, retry and shared one-shot state', async () => {
  reset()
  controls.enabled = false
  let view: Renderer.ReactTestRenderer
  act(() => { view = Renderer.create(<CorrectionNotice {...props} />) })
  assert.equal(view!.toJSON(), null)
  assert.equal(controls.sent.length, 0)
  controls.enabled = true
  act(() => { view!.update(<CorrectionNotice {...props} />) })
  assert.equal(controls.sent.length, 0) // mounting never sends
  act(() => { useStore.setState({ isStreaming: true }) })
  assert.equal(view!.root.findByType('button').props.disabled, true)
  act(() => { view!.root.findByType('button').props.onClick() })
  assert.equal(controls.sent.length, 0)
  act(() => { useStore.setState({ isStreaming: false }) })
  controls.sendSuccess = false
  await act(async () => { view!.root.findByType('button').props.onClick() })
  assert.equal(view!.root.findAllByType('button').length, 1) // offline send is retryable
  controls.sendSuccess = true
  await act(async () => {
    const click = view!.root.findByType('button').props.onClick
    click(); click() // double click is consumed only once
  })
  assert.equal(controls.sent.length, 2) // failed attempt + successful retry
  assert.equal(controls.sent[1][5], 'm')
  assert.equal(view!.toJSON(), null)
  act(() => { view!.unmount(); view = Renderer.create(<CorrectionNotice {...props} runtime={{ title: 'tool', message: 'error' }} />) })
  assert.equal(view!.toJSON(), null) // remount / second sandbox cannot request again
  act(() => view!.unmount())
})

test('sandbox bootstrap catches error/rejection, bounds text, checks source and shares correction offer', async () => {
  reset()
  const listeners: Record<string, Function> = {}
  const hostWindow = { addEventListener: (type: string, cb: Function) => { listeners[type] = cb }, removeEventListener: (type: string) => { delete listeners[type] } }
  Object.assign(globalThis, { window: hostWindow })
  const frameWindow = { postMessage: () => {} }
  const runtime: { title: string; message: string }[] = []
  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<SandboxCard block={{ id: 's', type: 'sandbox', title: 'tool', html: '<p>safe</p>', js: 'throw new Error("boom")' }} onRuntimeError={(title, message) => runtime.push({ title, message })} />, {
      createNodeMock: (node) => node.type === 'iframe' ? { contentWindow: frameWindow } : {},
    })
  })
  const iframe = view!.root.findByType('iframe')
  assert.equal(iframe.props.sandbox, 'allow-scripts allow-forms')
  const script = iframe.props.srcDoc.match(/<script>\s*([\s\S]*?)<\/script>/)[1]
  const frameListeners: Record<string, Function> = {}
  const posted: any[] = []
  runInNewContext(script, {
    window: { addEventListener: (type: string, cb: Function) => { frameListeners[type] = cb } },
    parent: { postMessage: (data: unknown) => posted.push(data) },
    ResizeObserver: class { observe() {} }, setTimeout: () => {},
  })
  frameListeners.error({ message: '<img onerror=evil>' + 'x'.repeat(600) })
  frameListeners.unhandledrejection({ reason: new Error('rejected') })
  assert.equal(posted[0].type, '__nexus_ogui_error')
  assert.equal(posted[0].message.length, 500)
  assert.equal(posted[1].message, 'rejected')
  act(() => listeners.message({ source: {}, data: posted[0] }))
  assert.equal(runtime.length, 0)
  act(() => listeners.message({ source: frameWindow, data: posted[0] }))
  assert.equal(runtime.length, 1)
  assert.equal(runtime[0].message.length, 500)
  assert.equal(controls.sent.length, 0)
  act(() => view!.unmount())
  act(() => { view = Renderer.create(<CorrectionNotice messageId="m" runtime={runtime[0]} />) })
  assert.ok(controls.offers.includes('m'))
  assert.equal(controls.sent.length, 0)
  await act(async () => { view!.root.findByType('button').props.onClick() })
  assert.equal(controls.sent.length, 1)
  assert.equal(view!.toJSON(), null)
  act(() => view!.unmount())
})
