export type TalkMode = 'off' | 'once' | 'loop'
export type TalkPhase = 'idle' | 'listening' | 'waiting_reply' | 'speaking'
export type TalkState = { mode: TalkMode; phase: TalkPhase }

export type TalkDecision =
  | { type: 'send'; text: string; next: TalkState }
  | { type: 'listen'; next: TalkState }
  | { type: 'exit'; next: TalkState }
  | { type: 'ignore'; next: TalkState }

const idle: TalkState = { mode: 'off', phase: 'idle' }

export function isStopPhrase(text: string): boolean {
  const n = text.trim().toLowerCase().replace(/[.!?…]+$/u, '').trim()
  return n === 'parar' || n === 'stop' || n === 'chega'
}

export function onFinalTranscript(state: TalkState, text: string): TalkDecision {
  const trimmed = text.trim()
  if (state.mode === 'once') {
    if (!trimmed) return { type: 'ignore', next: idle }
    return { type: 'send', text: trimmed, next: idle }
  }
  if (state.mode === 'loop') {
    if (isStopPhrase(trimmed)) return { type: 'exit', next: idle }
    if (!trimmed) return { type: 'listen', next: { mode: 'loop', phase: 'listening' } }
    return { type: 'send', text: trimmed, next: { mode: 'loop', phase: 'waiting_reply' } }
  }
  return { type: 'ignore', next: state }
}

export function onTtsEnded(state: TalkState): TalkDecision {
  if (state.mode === 'loop' && state.phase === 'speaking') {
    return { type: 'listen', next: { mode: 'loop', phase: 'listening' } }
  }
  if (state.mode === 'off') return { type: 'ignore', next: idle }
  return { type: 'ignore', next: { mode: state.mode, phase: state.phase } }
}

export function onSpeakStarted(state: TalkState): TalkState {
  if (state.mode === 'loop' && state.phase === 'waiting_reply') {
    return { mode: 'loop', phase: 'speaking' }
  }
  return state
}

export function onMicTap(state: TalkState): TalkDecision {
  if (state.mode === 'loop') return { type: 'exit', next: idle }
  if (state.phase === 'listening') return { type: 'exit', next: idle }
  if (state.mode === 'off' && state.phase === 'idle') {
    return { type: 'listen', next: { mode: 'once', phase: 'listening' } }
  }
  return { type: 'ignore', next: state }
}

export function onTalkToggle(state: TalkState): TalkDecision {
  if (state.mode === 'loop') return { type: 'exit', next: idle }
  return { type: 'listen', next: { mode: 'loop', phase: 'listening' } }
}

type SpeechResult = { isFinal: boolean; 0: { transcript: string } }
type SpeechRec = {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((ev: { results: ArrayLike<SpeechResult> }) => void) | null
  onerror: ((ev: { error: string }) => void) | null
  onend: (() => void) | null
  start: () => void
  abort: () => void
}

export type SpeechHandlers = {
  onInterim: (text: string) => void
  onFinal: (text: string) => void
  onError: (code: string) => void
  onEnd: () => void
}

export function createSpeechSession(
  Recognition: new () => SpeechRec,
  handlers: SpeechHandlers,
  lang = 'pt-BR',
) {
  const recognition = new Recognition()
  recognition.lang = lang
  recognition.continuous = false
  recognition.interimResults = true
  let aborted = false
  recognition.onresult = (ev) => {
    const list = Array.from(ev.results)
    const last = list[list.length - 1]
    const text = last?.[0]?.transcript ?? ''
    if (last?.isFinal) handlers.onFinal(text)
    else handlers.onInterim(text)
  }
  recognition.onerror = (ev) => handlers.onError(ev?.error || 'error')
  recognition.onend = () => {
    if (!aborted) handlers.onEnd()
  }
  return {
    recognition,
    start() {
      recognition.start()
    },
    abort() {
      aborted = true
      recognition.onend = null
      recognition.abort()
    },
  }
}

export function speechRecognitionCtor(scope: typeof globalThis = globalThis): (new () => SpeechRec) | null {
  const w = scope as typeof globalThis & {
    SpeechRecognition?: new () => SpeechRec
    webkitSpeechRecognition?: new () => SpeechRec
  }
  return w.SpeechRecognition || w.webkitSpeechRecognition || null
}

type Snap = TalkState & { epoch: number }
const listeners = new Set<() => void>()
let snap: Snap = { mode: 'off', phase: 'idle', epoch: 0 }

export function getTalk() {
  return snap
}

export function subscribeTalk(fn: () => void) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

function emit(next: TalkState, force = false) {
  if (!force && next.mode === snap.mode && next.phase === snap.phase) return
  snap = { ...next, epoch: snap.epoch + 1 }
  listeners.forEach((fn) => fn())
}

export function applyDecision(decision: TalkDecision) {
  emit(decision.next, decision.type === 'listen')
  return decision
}

export function noteSpeaking() {
  emit(onSpeakStarted(snap))
}
