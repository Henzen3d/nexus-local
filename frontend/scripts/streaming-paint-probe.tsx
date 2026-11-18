import React, { Profiler } from 'react'
import TestRenderer, { act } from 'react-test-renderer'
import { performance } from 'node:perf_hooks'
import '../src/i18n'
import { ChatProvider } from '../src/context/ChatContext'
import { ChatWindow } from '../src/components/ChatWindow'
import { useStore } from '../src/store/useStore'
import { AdapterRegistry } from '../src/adapters/AdapterRegistry'
import { markdownComponents } from '../src/components/markdownComponents'
import type { ProcessStep, UiEnvelope } from '../src/types'

type ProbeGlobals = typeof globalThis & {
  __NEXUS_PROBE_ENV__?: string
  __NEXUS_RENDER_PROBE__?: boolean
  __NEXUS_BUBBLE_RENDERS__?: number
  __NEXUS_CHATWINDOW_RENDERS__?: number
  __NEXUS_STREAMING_BUBBLE_RENDERS__?: number
  __NEXUS_MARKDOWN_RENDERS__?: number
}

const g = globalThis as ProbeGlobals
const probeEnv = g.__NEXUS_PROBE_ENV__ ?? (process.env.NODE_ENV === 'production' ? 'production' : 'development')

g.__NEXUS_RENDER_PROBE__ = true
g.__NEXUS_BUBBLE_RENDERS__ = 0
g.__NEXUS_CHATWINDOW_RENDERS__ = 0
g.__NEXUS_STREAMING_BUBBLE_RENDERS__ = 0
g.__NEXUS_MARKDOWN_RENDERS__ = 0

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

// ─── Instrumentation spies (identical before & after optimization) ───────────

let adapterGetCalls = 0
let adapterParseCalls = 0
const origGetAdapter = AdapterRegistry.getAdapter.bind(AdapterRegistry)
AdapterRegistry.getAdapter = (modelId: string | null, providerId: string | null) => {
  adapterGetCalls += 1
  const adapter = origGetAdapter(modelId, providerId)
  const origParse = adapter.parse.bind(adapter)
  adapter.parse = (content: string) => {
    adapterParseCalls += 1
    return origParse(content)
  }
  return adapter
}

// Each deterministic sample contains exactly ONE `# Heading` (h1), so counting
// `markdownComponents.h1` calls gives exact ReactMarkdown execution count before & after.
let markdownH1Calls = 0
const origH1 = markdownComponents.h1
markdownComponents.h1 = (props) => {
  markdownH1Calls += 1
  if (typeof origH1 === 'function') {
    return origH1(props)
  }
  const { children } = props
  return React.createElement('h1', null, children)
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function roundMs(value: number): number {
  return Math.round(value * 1000) / 1000
}

async function flushUpdate(fn: () => void | Promise<void>) {
  if (probeEnv === 'production') {
    await fn()
    await new Promise<void>((r) => setImmediate(r))
    await new Promise<void>((r) => setImmediate(r))
  } else {
    await act(async () => {
      await fn()
    })
  }
}

function summarizeMs(values: number[]) {
  if (values.length === 0) {
    return { total: 0, mean: 0, p50: 0, p95: 0, max: 0 }
  }
  const sorted = [...values].sort((a, b) => a - b)
  const total = values.reduce((acc, v) => acc + v, 0)
  const pick = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p))]
  return {
    total: roundMs(total),
    mean: roundMs(total / values.length),
    p50: roundMs(pick(0.5)),
    p95: roundMs(pick(0.95)),
    max: roundMs(sorted[sorted.length - 1]),
  }
}

function splitDeterministicChunks(text: string, chunkCount: number): string[] {
  const chunks: string[] = []
  const size = Math.max(1, Math.ceil(text.length / chunkCount))
  for (let i = 0; i < text.length; i += size) {
    chunks.push(text.slice(i, i + size))
  }
  return chunks
}

function extractTreeText(node: TestRenderer.ReactTestRendererJSON | TestRenderer.ReactTestRendererJSON[] | string | null): string {
  if (node == null) return ''
  if (typeof node === 'string') return node
  if (Array.isArray(node)) return node.map(extractTreeText).join('')
  return (node.children ?? []).map((c) => extractTreeText(c as TestRenderer.ReactTestRendererJSON | string)).join('')
}

// ─── Fixed deterministic samples ─────────────────────────────────────────────

const SAMPLE_LONG_TEXT = [
  '# Relatorio Tecnico de Arquitetura',
  '',
  'Este documento consolida a avaliacao de desempenho do feed de mensagens em streaming, preservando a integridade de listas, tabelas e blocos de codigo sem cortes arbitrarios.',
  '',
  ...Array.from({ length: 8 }, (_, idx) => [
    `## Secao ${idx + 1}: Analise do Subsistema ${idx + 1}`,
    '',
    `No ciclo ${idx + 1}, o fluxo de tokens chega em rajadas controladas por quadro de animacao. Cada paragrafo valida que o parser de Markdown mantem a renderizacao consistente com **enfase forte**, *enfase simples* e codigo inline \`stream_frame_${idx + 1}\` sem degradação perceptivel de latencia no navegador.`,
    '',
    `- Etapa ${idx + 1}.1: consolidar leitura de metadados e manter isolamento de bolhas antigas.`,
    `- Etapa ${idx + 1}.2: evitar varredura repetida de fences quando apenas o estado de execucao muda.`,
    `- Etapa ${idx + 1}.3: garantir que a ancoragem manual do usuario ao subir a tela seja preservada.`,
    '',
  ].join('\n')),
  '## Tabela Comparativa de Metricas',
  '',
  '| Cenario | Frames | Status | Integridade |',
  '| --- | ---: | ---: | --- |',
  '| Texto longo | 24 | 6 | OK |',
  '| Codigo fenced | 20 | 4 | OK |',
  '| Raciocinio think | 26 | 4 | OK |',
  '| Blocos nexus-ui | 24 | 4 | OK |',
  '',
  'Conclusao final: todas as secoes foram preservadas integralmente.',
].join('\n')

const SAMPLE_FENCED_CODE = [
  '# Implementacao do Pipeline de Stream',
  '',
  'Abaixo estao os tres blocos de codigo usados para validar o realce e o isolamento de fences durante o streaming progressivo.',
  '',
  '```typescript',
  'export interface StreamFrame {',
  '  readonly turnId: string',
  '  readonly seq: number',
  '  readonly delta: string',
  '}',
  '',
  'export function mergeStreamFrames(frames: readonly StreamFrame[]): string {',
  '  let output = ""',
  '  for (const frame of frames) {',
  '    if (!frame.delta) continue',
  '    output += frame.delta',
  '  }',
  '  return output',
  '}',
  '```',
  '',
  'Em seguida, o consumidor Python garante cancelamento seguro e contabilizacao deterministica:',
  '',
  '```python',
  'from dataclasses import dataclass',
  '',
  '@dataclass(frozen=True)',
  'class StreamMetrics:',
  '    frames: int',
  '    chars: int',
  '',
  'def summarize_stream(chunks: list[str]) -> StreamMetrics:',
  '    total_chars = sum(len(chunk) for chunk in chunks)',
  '    return StreamMetrics(frames=len(chunks), chars=total_chars)',
  '```',
  '',
  'Por fim, o manifesto JSON de configuracao:',
  '',
  '```json',
  '{',
  '  "mode": "streaming",',
  '  "preserveScrollAnchor": true,',
  '  "thresholdPx": 180,',
  '  "features": ["memoized-markdown", "stable-props", "adapter-cache"]',
  '}',
  '```',
  '',
  'Todos os fences foram fechados corretamente.',
].join('\n')

const THINK_BODY = Array.from(
  { length: 12 },
  (_, i) => `Passo de raciocinio ${i + 1}: verificando dependencias de memoizacao e impacto em commits do React para o quadro ${i + 1}.`,
).join('\n')

const THINK_ANSWER = [
  '# Resumo da Analise de Raciocinio',
  '',
  'Depois de avaliar o raciocinio interno, o plano confirma tres pontos objetivos:',
  '',
  '1. O texto de pensamento nao precisa reexecutar o parser de Markdown da resposta enquanto a resposta visivel nao mudou.',
  '2. A bolha ativa deve memoizar `adapter.parse(content)` por modelo, provedor e conteudo.',
  '3. Atualizacoes de `processSteps` e `streamingUiBlocks` nao devem provocar nova varredura de fences nem novo parse de Markdown.',
  '',
  'Resultado verificado ao encerrar o raciocinio.',
].join('\n')

const SAMPLE_NEXUS_UI_PROSE = [
  '# Painel Operacional de Latencia',
  '',
  'Os indicadores abaixo consolidam o comportamento da fila de renderizacao durante o envio progressivo de blocos `nexus-ui`.',
  '',
  '- Bolhas historicas permanecem intactas.',
  '- O texto acima do fence nao muda enquanto o JSON visual chega.',
  '',
].join('\n')

const SAMPLE_NEXUS_UI_FENCE = [
  '```nexus-ui',
  JSON.stringify(
    {
      v: 1,
      blocks: [
        {
          id: 'metrics_stream',
          type: 'metric',
          title: 'Resumo de Renderizacao',
          items: [
            { label: 'Bolhas antigas', value: '0 renders' },
            { label: 'ChatWindow', value: '0 commits' },
          ],
        },
        {
          id: 'callout_status',
          type: 'callout',
          kind: 'success',
          title: 'Isolamento Ativo',
          body: 'Os blocos visuais foram extraidos sem repintar o Markdown anterior.',
        },
      ],
    },
    null,
    2,
  ),
  '```',
  '',
  'Bloco visual concluido com sucesso.',
].join('\n')

// ─── Shared scroll mocks ─────────────────────────────────────────────────────

const scrollState = {
  scrollHeight: 2000,
  scrollTop: 1200,
  clientHeight: 800,
  scrollIntoViewCalls: [] as Array<{ behavior?: ScrollBehavior; block?: ScrollLogicalPosition }>,
}

const messagesAreaMock = {
  get scrollHeight() { return scrollState.scrollHeight },
  set scrollHeight(v: number) { scrollState.scrollHeight = v },
  get scrollTop() { return scrollState.scrollTop },
  set scrollTop(v: number) { scrollState.scrollTop = v },
  get clientHeight() { return scrollState.clientHeight },
  set clientHeight(v: number) { scrollState.clientHeight = v },
  scrollTo({ top }: { top?: number }) {
    if (typeof top === 'number') scrollState.scrollTop = top
  },
  style: {},
  focus() {},
  addEventListener() {},
  removeEventListener() {},
  contains() { return false },
}

const sentinelMock = {
  scrollIntoView(opts?: ScrollIntoViewOptions) {
    scrollState.scrollIntoViewCalls.push({
      behavior: opts?.behavior,
      block: opts?.block,
    })
    scrollState.scrollTop = Math.max(0, scrollState.scrollHeight - scrollState.clientHeight)
  },
  style: {},
}

const genericNodeMock = {
  scrollIntoView() {},
  scrollHeight: 0,
  scrollTop: 0,
  clientHeight: 800,
  style: {},
  focus() {},
  addEventListener() {},
  removeEventListener() {},
  contains() { return false },
}

const createNodeMock = (element: React.ReactElement) => {
  const props = (element.props ?? {}) as { className?: string; style?: { height?: number }; 'aria-hidden'?: string }
  if (props.className === 'messages-area') {
    return messagesAreaMock
  }
  if (props['aria-hidden'] === 'true' && props.style?.height === 0) {
    return sentinelMock
  }
  return genericNodeMock
}

// ─── Mount ChatWindow with 50 historical messages ────────────────────────────

const messages = Array.from({ length: 50 }, (_, i) => ({
  id: `m${i}`,
  role: (i % 2 === 0 ? 'user' : 'assistant') as 'user' | 'assistant',
  content: 'oi',
}))

useStore.setState({
  messages,
  isStreaming: true,
  isGenerating: true,
  streamingContent: '',
  processSteps: [],
  processStartedAt: Date.now(),
  streamingUiBlocks: null,
  intelligentUiConfig: { enabled: false, image_hosts: [], allow_private_http: false, source: 'probe' },
  selectedModelId: 'generic-model',
  selectedProviderId: 'openrouter',
  token: null,
})

let renderer: TestRenderer.ReactTestRenderer | null = null
let chatWindowCommits = 0
let seenChatWindowRenders = 0
const phases: string[] = []
let activeProfilerDurations: number[] = []

function onRender(_id: string, phase: string, actualDuration: number) {
  phases.push(phase)
  activeProfilerDurations.push(actualDuration)
  const renders = g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0
  if (renders !== seenChatWindowRenders) {
    chatWindowCommits += 1
    seenChatWindowRenders = renders
  }
}

await flushUpdate(async () => {
  renderer = TestRenderer.create(
    <ChatProvider>
      <Profiler id="ChatWindow" onRender={onRender}>
        <ChatWindow />
      </Profiler>
    </ChatProvider>,
    { createNodeMock },
  )
})

const commitsAfterMount = phases.length
const bubblesAfterMount = g.__NEXUS_BUBBLE_RENDERS__ ?? 0
const chatWindowCommitsAfterMount = chatWindowCommits
const chatWindowRendersAfterMount = g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0

// ─── 1. Legacy 20-token compatibility check ──────────────────────────────────

for (let i = 0; i < 20; i++) {
  await flushUpdate(async () => {
    useStore.setState((s) => ({ streamingContent: s.streamingContent + 'x' }))
  })
}

const commitsDuringTokens = phases.length - commitsAfterMount
const bubblesDuringTokens = (g.__NEXUS_BUBBLE_RENDERS__ ?? 0) - bubblesAfterMount
const chatWindowCommitsDuringTokens = chatWindowCommits - chatWindowCommitsAfterMount
const chatWindowRendersDuringTokens = (g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0) - chatWindowRendersAfterMount

// ─── 2. Multi-frame deterministic scenario runner ────────────────────────────

interface ScenarioConfig {
  name: string
  modelId: string
  providerId: string
  intelligentUiEnabled: boolean
  chunks: string[]
  statusInjectAtFrames: number[]
  statusKind: 'processSteps' | 'streamingUiBlocks'
  verifySubstring: string
}

async function runScenario(cfg: ScenarioConfig) {
  // Reset streaming turn cleanly before measuring
  await flushUpdate(async () => {
    useStore.setState({
      isStreaming: false,
      streamingContent: '',
      processSteps: [],
      processStartedAt: null,
      streamingUiBlocks: null,
      selectedModelId: cfg.modelId,
      selectedProviderId: cfg.providerId,
      intelligentUiConfig: {
        enabled: cfg.intelligentUiEnabled,
        image_hosts: [],
        allow_private_http: false,
        source: 'probe',
      },
    })
  })

  await flushUpdate(async () => {
    useStore.setState({
      isStreaming: true,
      streamingContent: '',
      processSteps: [{ id: 'thinking', type: 'think', title: 'Preparando', status: 'running' }],
      processStartedAt: Date.now(),
      streamingUiBlocks: null,
    })
  })

  const startCommits = phases.length
  const startChatCommits = chatWindowCommits
  const startChatRenders = g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0
  const startOlderBubbles = g.__NEXUS_BUBBLE_RENDERS__ ?? 0
  const startActiveBubbles = g.__NEXUS_STREAMING_BUBBLE_RENDERS__ ?? 0
  const startMarkdownH1 = markdownH1Calls
  const startAdapterGet = adapterGetCalls
  const startAdapterParse = adapterParseCalls
  activeProfilerDurations = []

  const frameLatencies: number[] = []
  const statusLatencies: number[] = []
  let markdownOnContent = 0
  let markdownOnStatus = 0
  let adapterParseOnContent = 0
  let adapterParseOnStatus = 0

  const statusSet = new Set(cfg.statusInjectAtFrames)
  let statusIdx = 0

  for (let idx = 0; idx < cfg.chunks.length; idx++) {
    const chunk = cfg.chunks[idx]
    const mdBefore = markdownH1Calls
    const parseBefore = adapterParseCalls
    const t0 = performance.now()
    await flushUpdate(async () => {
      useStore.setState((s) => ({ streamingContent: s.streamingContent + chunk }))
    })
    frameLatencies.push(performance.now() - t0)
    markdownOnContent += markdownH1Calls - mdBefore
    adapterParseOnContent += adapterParseCalls - parseBefore

    if (statusSet.has(idx + 1)) {
      statusIdx += 1
      const mdSBefore = markdownH1Calls
      const parseSBefore = adapterParseCalls
      const st0 = performance.now()
      await flushUpdate(async () => {
        if (cfg.statusKind === 'processSteps') {
          const steps: ProcessStep[] = [
            { id: 'triage-1', type: 'tool', title: `Etapa ${statusIdx}`, status: 'done' },
            { id: `step-${statusIdx}`, type: 'search', title: `Consultando fonte ${statusIdx}`, status: 'running' },
          ]
          useStore.setState({ processSteps: steps })
        } else {
          const hostUi: UiEnvelope = {
            v: 1,
            blocks: [
              {
                id: 'host_progress',
                type: 'progress',
                label: `Progresso do servidor (${statusIdx}/${cfg.statusInjectAtFrames.length})`,
                value: statusIdx * 25,
                max: 100,
              },
            ],
          }
          useStore.setState({ streamingUiBlocks: hostUi })
        }
      })
      statusLatencies.push(performance.now() - st0)
      markdownOnStatus += markdownH1Calls - mdSBefore
      adapterParseOnStatus += adapterParseCalls - parseSBefore
    }
  }

  const finalTreeText = extractTreeText(renderer!.toJSON())
  const finalVerified = finalTreeText.includes(cfg.verifySubstring)

  const activeBubbleDelta = (g.__NEXUS_STREAMING_BUBBLE_RENDERS__ ?? 0) - startActiveBubbles

  return {
    name: cfg.name,
    frames: cfg.chunks.length,
    statusUpdates: statusIdx,
    chatWindowCommits: chatWindowCommits - startChatCommits,
    chatWindowRenders: (g.__NEXUS_CHATWINDOW_RENDERS__ ?? 0) - startChatRenders,
    olderBubbleRenders: (g.__NEXUS_BUBBLE_RENDERS__ ?? 0) - startOlderBubbles,
    profilerCommits: phases.length - startCommits,
    activeBubbleRenders: activeBubbleDelta > 0 ? activeBubbleDelta : null,
    markdownRendersTotal: markdownH1Calls - startMarkdownH1,
    markdownRendersOnContent: markdownOnContent,
    markdownRendersOnStatus: markdownOnStatus,
    adapterGetCalls: adapterGetCalls - startAdapterGet,
    adapterParseCallsTotal: adapterParseCalls - startAdapterParse,
    adapterParseCallsOnContent: adapterParseOnContent,
    adapterParseCallsOnStatus: adapterParseOnStatus,
    profilerDurationMs: summarizeMs(activeProfilerDurations),
    frameLatencyMs: summarizeMs(frameLatencies),
    statusUpdateLatencyMs: summarizeMs(statusLatencies),
    finalVerified,
  }
}

const thinkChunks = [
  ...splitDeterministicChunks(`<think>\n${THINK_BODY}\n</think>\n\n`, 12),
  ...splitDeterministicChunks(THINK_ANSWER, 14),
]

const nexusUiChunks = [
  ...splitDeterministicChunks(SAMPLE_NEXUS_UI_PROSE, 6),
  ...splitDeterministicChunks(SAMPLE_NEXUS_UI_FENCE, 18),
]

const scenarios = [
  await runScenario({
    name: 'long_text',
    modelId: 'generic-model',
    providerId: 'openrouter',
    intelligentUiEnabled: false,
    chunks: splitDeterministicChunks(SAMPLE_LONG_TEXT, 24),
    statusInjectAtFrames: [4, 8, 12, 16, 20, 23],
    statusKind: 'processSteps',
    verifySubstring: 'Conclusao final: todas as secoes foram preservadas integralmente.',
  }),
  await runScenario({
    name: 'fenced_code',
    modelId: 'generic-model',
    providerId: 'openrouter',
    intelligentUiEnabled: false,
    chunks: splitDeterministicChunks(SAMPLE_FENCED_CODE, 20),
    statusInjectAtFrames: [5, 10, 15, 19],
    statusKind: 'processSteps',
    verifySubstring: 'Todos os fences foram fechados corretamente.',
  }),
  await runScenario({
    name: 'reasoning_think',
    modelId: 'deepseek-r1',
    providerId: 'openrouter',
    intelligentUiEnabled: false,
    chunks: thinkChunks,
    statusInjectAtFrames: [4, 9, 16, 22],
    statusKind: 'processSteps',
    verifySubstring: 'Resultado verificado ao encerrar o raciocinio.',
  }),
  await runScenario({
    name: 'nexus_ui',
    modelId: 'generic-model',
    providerId: 'openrouter',
    intelligentUiEnabled: true,
    chunks: nexusUiChunks,
    statusInjectAtFrames: [5, 10, 15, 20],
    statusKind: 'streamingUiBlocks',
    verifySubstring: 'Bloco visual concluido com sucesso.',
  }),
]

// ─── 3. Scroll-up preservation & auto-follow verification ────────────────────

await flushUpdate(async () => {
  useStore.setState({
    isStreaming: false,
    streamingContent: '',
    processSteps: [],
    streamingUiBlocks: null,
    selectedModelId: 'generic-model',
    selectedProviderId: 'openrouter',
    intelligentUiConfig: { enabled: false, image_hosts: [], allow_private_http: false, source: 'probe' },
  })
})
await flushUpdate(async () => {
  useStore.setState({ isStreaming: true, streamingContent: '# Scroll Check\n\n' })
})

scrollState.scrollHeight = 2000
scrollState.clientHeight = 800
scrollState.scrollTop = 1180 // distance = 20 (< 180)
scrollState.scrollIntoViewCalls = []

// Phase A: near bottom -> auto-follow
for (let i = 0; i < 5; i++) {
  scrollState.scrollHeight += 120
  await flushUpdate(async () => {
    useStore.setState((s) => ({ streamingContent: s.streamingContent + `Linha near-bottom ${i + 1}\n` }))
  })
}
const autoFollowCallsNearBottom = scrollState.scrollIntoViewCalls.length
const autoFollowAllAuto = scrollState.scrollIntoViewCalls.every((c) => c.behavior === 'auto')
const distanceAfterNearBottom = scrollState.scrollHeight - scrollState.scrollTop - scrollState.clientHeight

// Phase B: user scrolls up -> must NOT yank scrollTop down
scrollState.scrollTop = 400
const distanceWhenScrolledUpStart = scrollState.scrollHeight - scrollState.scrollTop - scrollState.clientHeight
const messagesAreaNode = renderer!.root.findByProps({ className: 'messages-area' })
const mdBeforeScrollEvent = markdownH1Calls
const bubblesBeforeScrollUp = g.__NEXUS_BUBBLE_RENDERS__ ?? 0
await flushUpdate(async () => {
  messagesAreaNode.props.onScroll()
})
const markdownRendersOnScrollUpEvent = markdownH1Calls - mdBeforeScrollEvent

const callsBeforeUpStream = scrollState.scrollIntoViewCalls.length
const scrollTopBeforeUpStream = scrollState.scrollTop
for (let i = 0; i < 10; i++) {
  scrollState.scrollHeight += 120
  await flushUpdate(async () => {
    useStore.setState((s) => ({ streamingContent: s.streamingContent + `Linha scrolled-up ${i + 1}\n` }))
  })
}
const scrollCallsWhileUp = scrollState.scrollIntoViewCalls.length - callsBeforeUpStream
const scrollTopAfterUpStream = scrollState.scrollTop
const distanceWhenScrolledUpEnd = scrollState.scrollHeight - scrollState.scrollTop - scrollState.clientHeight
const olderBubblesDuringScrollUp = (g.__NEXUS_BUBBLE_RENDERS__ ?? 0) - bubblesBeforeScrollUp

// Phase C: user returns near bottom -> auto-follow resumes
scrollState.scrollTop = scrollState.scrollHeight - scrollState.clientHeight - 40
await flushUpdate(async () => {
  messagesAreaNode.props.onScroll()
})
const callsBeforeResume = scrollState.scrollIntoViewCalls.length
for (let i = 0; i < 3; i++) {
  scrollState.scrollHeight += 120
  await flushUpdate(async () => {
    useStore.setState((s) => ({ streamingContent: s.streamingContent + `Linha resumed ${i + 1}\n` }))
  })
}
const autoFollowResumedCalls = scrollState.scrollIntoViewCalls.length - callsBeforeResume
const distanceAfterResume = scrollState.scrollHeight - scrollState.scrollTop - scrollState.clientHeight

const scrollPreservation = {
  autoFollowCallsNearBottom,
  autoFollowAllAuto,
  distanceAfterNearBottom,
  distanceWhenScrolledUpStart,
  distanceWhenScrolledUpEnd,
  scrollTopBeforeUpStream,
  scrollTopAfterUpStream,
  scrollTopPreservedWhileUp: scrollTopBeforeUpStream === scrollTopAfterUpStream,
  scrollCallsWhileUp,
  olderBubblesDuringScrollUp,
  markdownRendersOnScrollUpEvent,
  autoFollowResumedCalls,
  distanceAfterResume,
}

const totals = {
  frames: scenarios.reduce((a, s) => a + s.frames, 0),
  statusUpdates: scenarios.reduce((a, s) => a + s.statusUpdates, 0),
  chatWindowCommits: scenarios.reduce((a, s) => a + s.chatWindowCommits, 0),
  chatWindowRenders: scenarios.reduce((a, s) => a + s.chatWindowRenders, 0),
  olderBubbleRenders: scenarios.reduce((a, s) => a + s.olderBubbleRenders, 0),
  profilerCommits: scenarios.reduce((a, s) => a + s.profilerCommits, 0),
  markdownRendersTotal: scenarios.reduce((a, s) => a + s.markdownRendersTotal, 0),
  markdownRendersOnContent: scenarios.reduce((a, s) => a + s.markdownRendersOnContent, 0),
  markdownRendersOnStatus: scenarios.reduce((a, s) => a + s.markdownRendersOnStatus, 0),
  adapterGetCalls: scenarios.reduce((a, s) => a + s.adapterGetCalls, 0),
  adapterParseCallsTotal: scenarios.reduce((a, s) => a + s.adapterParseCallsTotal, 0),
  adapterParseCallsOnStatus: scenarios.reduce((a, s) => a + s.adapterParseCallsOnStatus, 0),
  profilerDurationTotalMs: roundMs(scenarios.reduce((a, s) => a + s.profilerDurationMs.total, 0)),
  frameLatencyTotalMs: roundMs(scenarios.reduce((a, s) => a + s.frameLatencyMs.total, 0)),
  statusUpdateLatencyTotalMs: roundMs(scenarios.reduce((a, s) => a + s.statusUpdateLatencyMs.total, 0)),
  allFinalVerified: scenarios.every((s) => s.finalVerified),
}

console.log(JSON.stringify({
  head: 'probe',
  env: probeEnv,
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
  scenarios,
  scrollPreservation,
  totals,
}))
process.exit(0)
