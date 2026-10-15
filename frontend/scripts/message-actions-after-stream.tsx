import React from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import '../src/i18n'
import { ChatProvider } from '../src/context/ChatContext'
import { ChatWindow } from '../src/components/ChatWindow'
import { useStore } from '../src/store/useStore'

const OLD_ID = 'old-user'
const OLD_TEXT = 'CONTEUDO-ANTIGO-42'
const EDITED_TEXT = 'CONTEUDO-EDITADO-99'

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
    body: { appendChild() {}, removeChild() {} },
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

const copied: string[] = []
const nav = globalThis.navigator as Navigator & { clipboard?: { writeText: (text: string) => Promise<void> } }
nav.clipboard = {
  writeText: async (text: string) => {
    copied.push(text)
  },
}

globalThis.fetch = (async () => ({
  ok: true,
  status: 200,
  json: async () => [],
  text: async () => '',
})) as unknown as typeof fetch

useStore.setState({
  messages: [
    { id: OLD_ID, role: 'user' as const, content: OLD_TEXT },
    { id: 'old-assistant', role: 'assistant' as const, content: 'resposta antiga' },
  ],
  isStreaming: true,
  streamingContent: '',
  token: null,
})

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

let renderer: TestRenderer.ReactTestRenderer
await act(async () => {
  renderer = TestRenderer.create(
    <ChatProvider>
      <ChatWindow />
    </ChatProvider>,
    { createNodeMock: nodeMock },
  )
})

for (let i = 0; i < 5; i++) {
  await act(async () => {
    useStore.setState((s) => ({ streamingContent: s.streamingContent + 'x' }))
  })
}

type Node = TestRenderer.ReactTestInstance

function classNameOf(node: Node): string {
  const value = node.props?.className
  return typeof value === 'string' ? value : ''
}

function textOf(node: Node): string {
  return node.children.map((child) => (typeof child === 'string' ? child : textOf(child))).join('')
}

function labelOf(node: Node): string {
  const bits = [
    node.props?.['aria-label'],
    node.props?.['data-tooltip'],
    node.props?.title,
    textOf(node),
  ]
  return bits.filter((bit) => typeof bit === 'string').join(' ')
}

const ACTION = /\b(editar|edit|regenerar|regenerate|excluir|apagar|delete)\b/i

function findOldBubble(): Node {
  const bubble = renderer.root.findAll((node) => classNameOf(node) === 'message user')
    .find((node) => textOf(node).includes(OLD_TEXT) || textOf(node).includes(EDITED_TEXT))
  if (!bubble) throw new Error('bolha da mensagem antiga sumiu antes da ação')
  return bubble
}

function clickCopy(bubble: Node) {
  const button = bubble.findAll((node) => classNameOf(node).includes('meta-copy-btn') && typeof node.props.onClick === 'function')[0]
  if (!button) throw new Error('botão de copiar ausente na mensagem antiga')
  button.props.onClick()
}

const oldBubble = findOldBubble()
await act(async () => {
  clickCopy(oldBubble)
})

await act(async () => {
  useStore.setState((s) => ({
    messages: s.messages.map((message) => (
      message.id === OLD_ID ? { ...message, content: EDITED_TEXT } : message
    )),
  }))
})

const editedBubble = findOldBubble()
const visibleAfterEdit = textOf(editedBubble).includes(EDITED_TEXT) && !textOf(editedBubble).includes(OLD_TEXT)
await act(async () => {
  clickCopy(editedBubble)
})

await act(async () => {
  useStore.setState((s) => ({
    messages: s.messages.filter((message) => message.id !== OLD_ID),
  }))
})

const goneAfterDelete = !renderer.root.findAll((node) => textOf(node) === EDITED_TEXT || textOf(node) === OLD_TEXT)
  .some((node) => classNameOf(node) === 'message user')

const controls = renderer.root.findAll((node) => typeof node.props?.onClick === 'function')
  .map((node) => labelOf(node))
  .filter((label) => ACTION.test(label))

console.log(JSON.stringify({
  copyAfterStream: copied[0] ?? null,
  copyAfterEdit: copied[1] ?? null,
  visibleAfterEdit,
  goneAfterDelete,
  staleActionControls: controls,
}))
process.exit(0)
