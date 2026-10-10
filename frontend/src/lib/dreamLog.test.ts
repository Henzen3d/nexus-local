import assert from 'node:assert/strict'
import { test } from 'node:test'
import { describeDreamLog, dreamStepState } from './dreamLog.ts'

test('falha com facts_after 0 não vira 100% de ruído', () => {
  const view = describeDreamLog({
    status: 'failed',
    facts_before: 72,
    facts_after: 0,
    error_message: 'Provider error 413',
    can_rollback: false,
    snapshot_id: 'snap-1',
  })
  assert.equal(view.showNoise, false)
  assert.equal(view.pill, 'failed')
  assert.match(view.headline, /413/)
  assert.doesNotMatch(view.headline, /100%/)
})

test('trava de segurança não mostra reversão bloqueada', () => {
  const view = describeDreamLog({
    status: 'aborted_safety',
    facts_before: 72,
    facts_after: 0,
    error_message: 'ID inexistente referenciado em keep: fbebb04f',
    can_rollback: false,
    snapshot_id: 'snap-1',
  })
  assert.equal(view.pill, 'failed')
  assert.equal(view.showNoise, false)
  assert.match(view.headline, /fbebb04f/)
})

test('sucesso com snapshot libera rollback; sucesso antigo fica bloqueado', () => {
  const latest = describeDreamLog({
    status: 'success',
    facts_before: 72,
    facts_after: 40,
    can_rollback: true,
    snapshot_id: 'snap-1',
  })
  assert.equal(latest.showNoise, true)
  assert.equal(latest.noisePct, 44)
  assert.equal(latest.pill, 'rollback')

  const older = describeDreamLog({
    status: 'success',
    facts_before: 72,
    facts_after: 40,
    can_rollback: false,
    snapshot_id: 'snap-0',
  })
  assert.equal(older.pill, 'blocked')
})

test('60% no passo reasoning não marca a transação flash como ativa', () => {
  assert.equal(dreamStepState(2, 'reasoning'), 'active')
  assert.equal(dreamStepState(3, 'reasoning'), 'pending')
  assert.equal(dreamStepState(3, 'validating'), 'pending')
  assert.equal(dreamStepState(3, 'persisting'), 'active')
  assert.equal(dreamStepState(2, 'persisting'), 'done')
})
