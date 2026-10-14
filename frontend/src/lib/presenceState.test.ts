import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  IDLE_AFTER_MS,
  PRESENCE_DEBOUNCE_MS,
  buildPresenceFrame,
  computePresenceState,
  presenceDelay,
  sameFrame,
} from './presenceState.ts'

test('aba oculta é hidden independentemente da atividade', () => {
  const now = 1_000_000
  assert.equal(computePresenceState({ visible: false, lastActivityAt: now, now }), 'hidden')
})

test('visível + atividade recente = active; ≥ 5 min sem atividade = idle', () => {
  const now = 10_000_000
  assert.equal(computePresenceState({ visible: true, lastActivityAt: now - 1_000, now }), 'active')
  assert.equal(computePresenceState({ visible: true, lastActivityAt: now - IDLE_AFTER_MS + 1, now }), 'active')
  assert.equal(computePresenceState({ visible: true, lastActivityAt: now - IDLE_AFTER_MS, now }), 'idle')
  assert.equal(computePresenceState({ visible: true, lastActivityAt: now - 60_000, now, idleAfterMs: 30_000 }), 'idle')
})

test('conversation_id só vai na tela de chat', () => {
  assert.deepEqual(buildPresenceFrame('active', 'chat', 'c1'), {
    type: 'presence', state: 'active', conversation_id: 'c1', view: 'chat',
  })
  assert.deepEqual(buildPresenceFrame('active', 'admin', 'c1'), {
    type: 'presence', state: 'active', conversation_id: null, view: 'admin',
  })
  assert.equal(buildPresenceFrame('hidden', 'chat', null).conversation_id, null)
  assert.equal(buildPresenceFrame('hidden', '', null).view, 'chat')
})

test('→active e primeiro relato são imediatos; sair espera o debounce', () => {
  assert.equal(presenceDelay(null, 'hidden'), 0)
  assert.equal(presenceDelay('hidden', 'active'), 0)
  assert.equal(presenceDelay('idle', 'active'), 0)
  assert.equal(presenceDelay('active', 'hidden'), PRESENCE_DEBOUNCE_MS)
  assert.equal(presenceDelay('active', 'idle', 500), 500)
})

test('sameFrame compara estado, conversa e tela', () => {
  const a = buildPresenceFrame('active', 'chat', 'c1')
  assert.equal(sameFrame(null, a), false)
  assert.equal(sameFrame(a, buildPresenceFrame('active', 'chat', 'c1')), true)
  assert.equal(sameFrame(a, buildPresenceFrame('active', 'chat', 'c2')), false)
  assert.equal(sameFrame(a, buildPresenceFrame('idle', 'chat', 'c1')), false)
})
