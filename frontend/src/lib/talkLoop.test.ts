import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import {
  createSpeechSession,
  isStopPhrase,
  onFinalTranscript,
  onMicTap,
  onTalkToggle,
  onTtsEnded,
  type TalkState,
} from './talkLoop.ts'

const here = dirname(fileURLToPath(import.meta.url))
const idle: TalkState = { mode: 'off', phase: 'idle' }
const onceListening: TalkState = { mode: 'once', phase: 'listening' }
const loopListening: TalkState = { mode: 'loop', phase: 'listening' }
const loopSpeaking: TalkState = { mode: 'loop', phase: 'speaking' }

test('parar exato sai da conversa, frase comum não', () => {
  assert.equal(isStopPhrase('parar'), true)
  assert.equal(isStopPhrase('  Parar. '), true)
  assert.equal(isStopPhrase('stop'), true)
  assert.equal(isStopPhrase('chega!'), true)
  assert.equal(isStopPhrase('parar agora'), false)
  assert.equal(isStopPhrase('me conta uma história'), false)
})

test('toque único manda o texto e não reabre o microfone', () => {
  const sent = onFinalTranscript(onceListening, '  oi, tudo bem?  ')
  assert.equal(sent.type, 'send')
  if (sent.type !== 'send') return
  assert.equal(sent.text, 'oi, tudo bem?')
  assert.deepEqual(sent.next, { mode: 'off', phase: 'idle' })
})

test('transcrição vazia no toque único não manda', () => {
  const empty = onFinalTranscript(onceListening, '   ')
  assert.equal(empty.type, 'ignore')
  assert.deepEqual(empty.next, { mode: 'off', phase: 'idle' })
})

test('modo conversa manda e espera a leitura antes de ouvir de novo', () => {
  const sent = onFinalTranscript(loopListening, 'conta uma piada')
  assert.equal(sent.type, 'send')
  assert.deepEqual(sent.next, { mode: 'loop', phase: 'waiting_reply' })

  const stillWaiting = onTtsEnded({ mode: 'loop', phase: 'waiting_reply' })
  assert.equal(stillWaiting.type, 'ignore')

  const again = onTtsEnded(loopSpeaking)
  assert.equal(again.type, 'listen')
  assert.deepEqual(again.next, { mode: 'loop', phase: 'listening' })
})

test('leitura fora do modo conversa não reabre o microfone', () => {
  const ended = onTtsEnded({ mode: 'off', phase: 'speaking' })
  assert.equal(ended.type, 'ignore')
  assert.deepEqual(ended.next, { mode: 'off', phase: 'idle' })
})

test('parar ou toque no microfone sai, sem ouvir enquanto a voz fala', () => {
  const stopped = onFinalTranscript(loopListening, 'Parar.')
  assert.equal(stopped.type, 'exit')
  assert.deepEqual(stopped.next, idle)

  const tapped = onMicTap(loopSpeaking)
  assert.equal(tapped.type, 'exit')
  assert.deepEqual(tapped.next, idle)
})

test('vazio na conversa ouve de novo, sem mandar', () => {
  const again = onFinalTranscript(loopListening, '  ')
  assert.equal(again.type, 'listen')
  assert.deepEqual(again.next, loopListening)
})

test('botão conversar liga e desliga o loop', () => {
  const on = onTalkToggle(idle)
  assert.equal(on.type, 'listen')
  assert.deepEqual(on.next, loopListening)

  const off = onTalkToggle(loopListening)
  assert.equal(off.type, 'exit')
  assert.deepEqual(off.next, idle)
})

test('toque no microfone parado começa uma escuta só', () => {
  const started = onMicTap(idle)
  assert.equal(started.type, 'listen')
  assert.deepEqual(started.next, onceListening)
})

class FakeRecognition {
  lang = ''
  continuous = true
  interimResults = false
  onresult: ((ev: { results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null = null
  onerror: ((ev: { error: string }) => void) | null = null
  onend: (() => void) | null = null
  started = 0
  aborted = 0
  start() { this.started += 1 }
  abort() { this.aborted += 1 }
}

test('sessão de voz pede pt-BR e separa parcial de final', () => {
  const partials: string[] = []
  const finals: string[] = []
  const session = createSpeechSession(FakeRecognition, {
    onInterim: (text) => partials.push(text),
    onFinal: (text) => finals.push(text),
    onError: () => {},
    onEnd: () => {},
  })
  session.start()
  const rec = session.recognition as FakeRecognition
  assert.equal(rec.lang, 'pt-BR')
  assert.equal(rec.continuous, false)
  assert.equal(rec.interimResults, true)
  assert.equal(rec.started, 1)

  rec.onresult?.({ results: [{ isFinal: false, 0: { transcript: 'con' } }] })
  rec.onresult?.({ results: [{ isFinal: true, 0: { transcript: 'conta uma piada' } }] })
  assert.deepEqual(partials, ['con'])
  assert.deepEqual(finals, ['conta uma piada'])

  session.abort()
  assert.equal(rec.aborted, 1)
})

test('composer tem microfone e modo conversa', () => {
  const src = readFileSync(join(here, '../components/MessageInput.tsx'), 'utf8')
  assert.match(src, /aria-label=\{t\('chat\.mic'/)
  assert.match(src, /aria-label=\{t\('chat\.talkLoop'/)
  assert.match(src, /createSpeechSession/)
})
