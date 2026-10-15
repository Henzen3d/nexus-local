import React, { Profiler } from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import '../src/i18n'
import { ChatProvider } from '../src/context/ChatContext'
import { ChatWindow } from '../src/components/ChatWindow'
import { useStore } from '../src/store/useStore'

const g = globalThis as typeof globalThis & {
  __NEXUS_RENDER_PROBE__?: boolean
  __NEXUS_BUBBLE_RENDERS__?: number
  __NEXUS_CHATWINDOW_RENDERS__?: number
}

g.__NEXUS_RENDER_PROBE__ = true
g.__NEXUS_BUBBLE_RENDERS__ = 0
g.__NEXUS_CHATWINDOW_RENDERS__ = 0

if (typeof window === 'undefined') {
  ;(globalThis as { window?: typeof globalThis }).window = globalThis
}
const w = globalThis.window as Window & {
  matchMedia?: (q: string) => { matches: boolean; addEventListener: () => void; removeEventListener: () => void }
  addEventListener?: (type: string, fn: EventListener) => void
  removeEventListener?: (type: string, fn: EventListener) => void
}
if (!w.matchMedia) {
  w.matchMedia = () => ({
    matches: false,
    addEventListener() {},
    removeEventListener() {},
  })
}
if (!w.addEventListener) w.addEventListener = () => {}
if (!w.removeEventListener) w.removeEventListener = () => {}

if (!globalThis.WebSocket) {
  globalThis.WebSocket = class {} as unknown as typeof WebSocket
}

if (!globalThis.document) {
  const listeners = new Map<string, Set<(ev: Event) => void>>()
  globalThis.document = {
    addEventListener(type: string, fn: (ev: Event) => void) {
      const set = listeners.get(type) ?? new Set()
      set.add(fn)
      listeners.set(type, set)
    },
    removeEventListener(type: string, fn: (ev: Event) => void) {
      listeners.get(type)?.delete(fn)
    },
    documentElement: { lang: '', setAttribute() {}, classList: { add() {} } },
    visibilityState: 'visible',
    hidden: false,
    getElementById: () => null,
    querySelector: () => null,
    createElement: () => ({ style: {}, setAttribute() {}, appendChild() {} }),
  } as unknown as Document
}

const mem = new Map<string, string>()
if (!globalThis.localStorage) {
  globalThis.localStorage = {
    getItem: (k: string) => mem.get(k) ?? null,
    setItem: (k: string, v: string) => { mem.set(k, String(v)) },
    removeItem: (k: string) => { mem.delete(k) },
    clear: () => { mem.clear() },
    key: () => null,
    get length() { return mem.size },
  }
}
globalThis.fetch = (async () => ({
  ok: true,
  status: 200,
  json: async () => [],
  text: async () => '',
})) as unknown as typeof fetch

const messages = Array.from({ length: 50 }, (_, i) => ({
  id: `m${i}`,
  role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
  content: 'oi',
}))

useStore.setState({
  messages,
  isStreaming: true,
  streamingContent: '',
  token: null,
})

let renderer: { root: { findByType: (type: unknown) => { _fiber?: { actualDuration?: number } } } } | null = null
let chatWindowCommits = 0
let seenChatWindowRenders = 0
const phases: string[] = []
function onRender(_id: string, phase: string) {
  phases.push(phase)
  const renders = g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0
  if (renders !== seenChatWindowRenders) {
    chatWindowCommits += 1
    seenChatWindowRenders = renders
  }
  void renderer
}

const nodeMock = () => ({
  scrollIntoView() {},
  scrollHeight: 0,
  scrollTop: 0,
  clientHeight: 800,
  style: {},
  focus() {},
  addEventListener() {},
  removeEventListener() {},
  contains() {
    return false
  },
})

console.error('probe: creating')
await act(async () => {
  renderer = TestRenderer.create(
    <ChatProvider>
      <Profiler id="ChatWindow" onRender={onRender}>
        <ChatWindow />
      </Profiler>
    </ChatProvider>,
    { createNodeMock: nodeMock },
  )
})
console.error('probe: mounted', phases.length, g.__NEXUS_BUBBLE_RENDERS__)
const commitsAfterMount = phases.length
const bubblesAfterMount = g.__NEXUS_BUBBLE_RENDERS__ ?? 0
const chatWindowCommitsAfterMount = chatWindowCommits
const chatWindowRendersAfterMount = g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0

for (let i = 0; i < 20; i++) {
  await act(async () => {
    useStore.setState((s) => ({ streamingContent: s.streamingContent + 'x' }))
  })
  console.error('probe: token', i + 1, 'commits', phases.length - commitsAfterMount, 'bubbles', (g.__NEXUS_BUBBLE_RENDERS__ ?? 0) - bubblesAfterMount)
}

const commitsDuringTokens = phases.length - commitsAfterMount
const bubblesDuringTokens = (g.__NEXUS_BUBBLE_RENDERS__ ?? 0) - bubblesAfterMount
const chatWindowCommitsDuringTokens = chatWindowCommits - chatWindowCommitsAfterMount
const chatWindowRendersDuringTokens = (g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0) - chatWindowRendersAfterMount

console.log(JSON.stringify({
  head: 'probe',
  messages: 50,
  tokens: 20,
  commitsAfterMount,
  commitsDuringTokens,
  chatWindowCommitsAfterMount,
  chatWindowCommitsDuringTokens,
  chatWindowRendersDuringTokens,
  bubblesAfterMount,
  bubblesDuringTokens,
  bubblesTotal: g.__NEXUS_BUBBLE_RENDERS__ ?? 0,
}))
process.exit(0)
