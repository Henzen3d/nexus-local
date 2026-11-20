import assert from 'node:assert/strict'
import React from 'react'
import Renderer, { act } from 'react-test-renderer'
import { api } from '../../src/api/client'
import { useChat } from '../../src/hooks/useChat'
import { useStore } from '../../src/store/useStore'
import type { ConversationDetail, Message } from '../../src/types'

class TestSocket {
  static OPEN = 1
  static CONNECTING = 0
  static connections: TestSocket[] = []
  readyState = TestSocket.OPEN
  sent: Array<Record<string, unknown>> = []
  onmessage?: (event: { data: string }) => void
  onclose?: (event: { code: number; reason: string }) => void

  constructor() {
    TestSocket.connections.push(this)
  }

  receive(frame: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(frame) })
  }

  send(data: string) {
    this.sent.push(JSON.parse(data))
  }

  close() {
    this.readyState = 3
    queueMicrotask(() => this.onclose?.({ code: 1000, reason: 'closed' }))
  }
}

function conversation(id: string, messages: Message[]): ConversationDetail {
  return { id, title: id, message_count: messages.length, messages, created_at: '', updated_at: '' }
}

export async function runChatSocketProbe() {
  // Components mount against a synthetic DOM and no real socket, storage or API.
  const global = globalThis as unknown as Record<string, unknown>
  global.window = Object.assign(new EventTarget(), { location: { protocol: 'http:', host: 'localhost' } })
  global.document = Object.assign(new EventTarget(), { visibilityState: 'visible' })
  global.WebSocket = TestSocket
  global.requestAnimationFrame = () => 1
  global.cancelAnimationFrame = () => {}
  const oldA: Message = { id: 'old-A', role: 'assistant', content: 'A', created_at: '' }
  const oldB: Message = { id: 'old-B', role: 'assistant', content: 'B', created_at: '' }
  const conversations = { A: conversation('A', [oldA]), B: conversation('B', [oldB]) }
  api.getConversation = async (id) => conversations[id as keyof typeof conversations]
  api.getConversations = async () => []
  api.getArtifacts = async () => []
  useStore.setState({
    token: 'test',
    selectedModelId: 'test-model',
    selectedProviderId: 'test-provider',
    activeConversationId: 'A',
    messages: [oldA],
  })

  let client: ReturnType<typeof useChat>
  function Probe() {
    client = useChat()
    return null
  }
  let render: Renderer.ReactTestRenderer
  await act(async () => { render = Renderer.create(<Probe />) })
  try {
    const socket = TestSocket.connections[0]!
    const state = useStore.getState
    act(() => { assert.equal(client.sendMessage('novo', undefined, undefined, undefined, false), true) })
    const turn = socket.sent.at(-1)?.turn_id
    act(() => {
      socket.receive({ type: 'stream_start', conversation_id: 'A', turn_id: turn })
      socket.receive({ type: 'token', content: 'prefixo ', conversation_id: 'A', turn_id: turn })
    })
    await act(async () => { await state().loadConversation('B') })
    act(() => {
      assert.equal(client.sendMessage('não deve iniciar', undefined, undefined, undefined, false), false)
      socket.receive({
        type: 'ui_progress', turn_id: turn, conversation_id: 'A',
        block: { id: 'step', type: 'progress', label: 'A only' },
      })
      socket.receive({ type: 'process_step_start', id: 'step', step_type: 'tool', title: 'A only', turn_id: turn })
    })
    assert.deepEqual(state().messages, [oldB])
    assert.equal(state().processSteps.length, 0)
    await act(async () => { await state().loadConversation('A') })
    const restored: Message = { id: 'complete', role: 'assistant', content: 'prefixo sufixo', created_at: '' }
    conversations.A = conversation('A', [oldA, restored])
    await act(async () => {
      socket.receive({ type: 'token', content: 'sufixo', conversation_id: 'A', turn_id: turn })
      socket.receive({ type: 'stream_end', outcome: 'success', conversation_id: 'A', message_id: 'complete', turn_id: turn })
    })
    assert.deepEqual(state().messages, [oldA, restored], 'returning during the turn rehydrates the full answer')

    act(() => {
      assert.equal(client.sendMessage('normal', undefined, undefined, undefined, false), true)
      socket.receive({ type: 'token', content: 'obsoleto', turn_id: turn })
      socket.receive({ type: 'stream_start', conversation_id: 'A' })
      socket.receive({ type: 'token', content: 'última cauda' })
      socket.receive({ type: 'stream_end', conversation_id: 'A', message_id: 'normal' })
    })
    assert.equal(state().messages.at(-1)?.content, 'última cauda', 'legacy terminal flushes the last scheduled batch')

    act(() => {
      state().setReasoningEffortAuto('high')
      useStore.setState({ selectedModelId: 'auto', selectedProviderId: 'auto' })
      assert.equal(client.sendMessage('Leia o PDF', undefined, ['att-pdf'], undefined, true, 'source-msg'), true)
      const { turn_id: originalTurn, ...original } = socket.sent.at(-1)!
      assert.deepEqual(original.attachment_ids, ['att-pdf'])
      assert.equal(original.reasoning_effort, 'high')
      assert.equal(original.voice_mode, true)
      assert.ok(original.request_id)

      socket.receive({ type: 'error', message: 'Falha simulada', turn_id: originalTurn, conversation_id: 'A' })
      const retry = state().toasts.at(-1)?.action
      assert.ok(retry)
      const userMessages = state().messages.filter((message) => message.role === 'user').length
      retry.onClick()
      const { turn_id: newTurn, ...replayed } = socket.sent.at(-1)!
      assert.notEqual(newTurn, originalTurn)
      assert.deepEqual(replayed, original)
      assert.equal(state().messages.filter((message) => message.role === 'user').length, userMessages)
      socket.receive({ type: 'token', content: 'Resposta do PDF', turn_id: newTurn })
      socket.receive({ type: 'stream_end', outcome: 'success', conversation_id: 'A', message_id: 'retried', turn_id: newTurn })
      useStore.setState({ selectedModelId: 'test-model', selectedProviderId: 'test-provider' })
    })

    act(() => {
      assert.equal(client.sendMessage('/imagem teste', undefined, undefined, undefined, false), true)
      const imageTurn = socket.sent.at(-1)?.turn_id
      socket.receive({ type: 'image_pending', conversation_id: 'A', message_id: 'image', task_id: '1', prompt: 'teste', turn_id: imageTurn })
      socket.receive({
        type: 'stream_end', outcome: 'success', conversation_id: 'A', message_id: 'image',
        finish_reason: 'image_pending', turn_id: imageTurn,
      })
    })
    assert.equal(state().messages.filter((message) => message.id === 'image').length, 1)
    assert.equal(state().isStreaming, false)
    assert.equal(state().isGenerating, false)

    await act(async () => {
      assert.equal(client.sendMessage('conexão cai', undefined, undefined, undefined, false), true)
      assert.equal(state().isGenerating, true)
      socket.close()
    })
    assert.equal(state().isGenerating, false, 'socket closure unlocks even before stream_start')

    // Simulate the reconnect timer firing without spending real time in the
    // watchdog, then deliver an uncorrelated frame from the retired socket.
    const realTimeout = globalThis.setTimeout
    let reconnect: (() => void) | undefined
    let watchdog: (() => void) | undefined
    globalThis.setTimeout = ((fn: () => void, delay?: number) => {
      if (delay === 90000) {
        watchdog = fn
        return realTimeout(() => {}, 0)
      }
      if (delay === 1000) {
        reconnect = fn
        return realTimeout(() => {}, 0)
      }
      return realTimeout(fn, delay)
    }) as typeof setTimeout
    try {
      // Drive a separate mount so previous retry timers don't need to tick.
      await act(async () => { render!.unmount() })
      await act(async () => { render = Renderer.create(<Probe />) })
      const current = TestSocket.connections.at(-1)!
      await act(async () => {
        assert.equal(client.sendMessage('expira', undefined, undefined, undefined, false), true)
        assert.ok(watchdog)
        watchdog()
      })
      assert.equal(current.readyState, 3)
      assert.equal(state().isGenerating, false)
      await act(async () => { reconnect?.() })
      const next = TestSocket.connections.at(-1)!
      assert.notEqual(next, current)
      act(() => {
        assert.equal(client.sendMessage('seguinte', undefined, undefined, undefined, false), true)
        current.receive({ type: 'token', content: 'socket antigo' })
        next.receive({ type: 'stream_start', conversation_id: 'A' })
        next.receive({ type: 'token', content: 'socket atual' })
        client.stopStream()
      })
      assert.equal(state().messages.at(-1)?.content, 'socket atual', 'Parar flushes the latest active draft only')
    } finally {
      globalThis.setTimeout = realTimeout
    }
  } finally {
    act(() => { render!.unmount() })
  }
}
