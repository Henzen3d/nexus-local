import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  bubbleContent,
  isExpired,
  isFresh,
  mergePending,
  newIds,
  parseUtc,
  pruneExpired,
  relativeAge,
  toastPreview,
} from './proactivePending.ts'
import type { ProactiveInsight } from '../types'

const NOW = Date.parse('2026-10-14T12:00:00Z')

function insight(id: string, extra: Partial<ProactiveInsight> = {}): ProactiveInsight {
  return {
    id,
    conversation_id: 'conv-' + id,
    message_id: null,
    topic: 'tópico ' + id,
    category: 'event',
    text: 'texto',
    sources: [],
    follow_ups: [],
    status: 'ready',
    language: 'pt-BR',
    ready_at: '2026-10-14 11:00:00',
    expires_at: '2026-10-21 12:00:00',
    ...extra,
  }
}

test('timestamps UTC sem sufixo são lidos como UTC', () => {
  assert.equal(parseUtc('2026-10-14 12:00:00'), NOW)
  assert.equal(parseUtc('2026-10-14T12:00:00Z'), NOW)
  assert.equal(parseUtc('2026-10-14T09:00:00-03:00'), NOW)
  assert.equal(parseUtc(null), null)
  assert.equal(parseUtc('lixo'), null)
})

test('insight vencido nunca entra na fila', () => {
  assert.equal(isExpired(insight('a', { expires_at: '2026-10-14 11:59:59' }), NOW), true)
  assert.equal(isExpired(insight('a', { expires_at: '2026-10-14 12:00:01' }), NOW), false)
  assert.equal(isExpired(insight('a', { expires_at: null }), NOW), false)
  const merged = mergePending([], [insight('old', { expires_at: '2026-10-14 11:00:00' }), insight('ok')], NOW)
  assert.deepEqual(merged.map((i) => i.id), ['ok'])
  const list = [insight('x', { expires_at: '2026-10-14 11:00:00' }), insight('y')]
  assert.deepEqual(pruneExpired(list, NOW).map((i) => i.id), ['y'])
  assert.equal(pruneExpired([insight('y')], NOW).length, 1)
})

test('merge deduplica por id, ordena do mais antigo e corta em 3', () => {
  const current = [insight('b', { ready_at: '2026-10-14 10:00:00' })]
  const incoming = [
    insight('c', { ready_at: '2026-10-14 11:30:00' }),
    insight('a', { ready_at: '2026-10-14 09:00:00' }),
    insight('b', { ready_at: '2026-10-14 10:00:00', text: 'atualizado' }),
    insight('d', { ready_at: '2026-10-14 11:45:00' }),
  ]
  const merged = mergePending(current, incoming, NOW)
  assert.deepEqual(merged.map((i) => i.id), ['a', 'b', 'c'])
  assert.equal(merged[1].text, 'atualizado')
  assert.deepEqual(newIds(current, merged), ['a', 'c'])
})

test('insights que deixaram de estar ready saem da fila', () => {
  const merged = mergePending([insight('a')], [insight('a', { status: 'delivered' })], NOW)
  assert.deepEqual(merged, [])
})

test('título "novidade" só quando o mais novo tem < 10 min', () => {
  assert.equal(isFresh([], NOW), false)
  assert.equal(isFresh([insight('a', { ready_at: '2026-10-14 11:55:00' })], NOW), true)
  assert.equal(isFresh([insight('a', { ready_at: '2026-10-14 11:49:00' })], NOW), false)
  assert.equal(isFresh([insight('a', { ready_at: '2026-10-14 09:00:00' }), insight('b', { ready_at: '2026-10-14 11:58:00' })], NOW), true)
})

test('idade relativa', () => {
  assert.deepEqual(relativeAge('2026-10-14 11:59:40', NOW), { key: 'justNow' })
  assert.deepEqual(relativeAge('2026-10-14 11:45:00', NOW), { key: 'minutes', n: 15 })
  assert.deepEqual(relativeAge('2026-10-14 09:00:00', NOW), { key: 'hours', n: 3 })
  assert.deepEqual(relativeAge('2026-10-13 10:00:00', NOW), { key: 'yesterday' })
  assert.deepEqual(relativeAge('2026-10-10 10:00:00', NOW), { key: 'days', n: 4 })
  assert.deepEqual(relativeAge(null, NOW), { key: 'justNow' })
})

test('prefixo da bolha segue canal e idioma', () => {
  assert.equal(
    bubbleContent({ topic: 'Coldplay', text: 'Show dia 21.', language: 'pt-BR', channel: 'pending_inline' }),
    'Enquanto você estava fora, pesquisei sobre **Coldplay**: Show dia 21.',
  )
  assert.equal(
    bubbleContent({ topic: 'Coldplay', text: 'Show dia 21.', language: 'pt-BR', channel: 'inline' }),
    'Fiquei curioso com **Coldplay** e fui pesquisar: Show dia 21.',
  )
  assert.match(bubbleContent({ topic: 'X', text: 't', language: 'en-GB', channel: 'pending_inline' }), /^While you were away/)
  assert.match(bubbleContent({ topic: 'X', text: 't', language: 'es-419', channel: 'toast' }), /^Me dio curiosidad/)
  assert.match(bubbleContent({ topic: 'X', text: 't', language: 'fr-FR', channel: null }), /^Fiquei curioso/)
})

test('preview do toast remove markdown e corta', () => {
  assert.equal(toastPreview('**a**  b\n c'), 'a b c')
  const long = toastPreview('x'.repeat(200))
  assert.equal(long.length, 140)
  assert.ok(long.endsWith('…'))
})
