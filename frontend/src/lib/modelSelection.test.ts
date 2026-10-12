import assert from 'node:assert/strict'
import test from 'node:test'
import { pickManualFallback, effectivePreferredModel } from './modelSelection.ts'

const models = [
  { id: 'm1', provider_id: 'groq', quota_status: 'available' },
  { id: 'm2', provider_id: 'openrouter', quota_status: 'exhausted' },
  { id: 'm3', provider_id: 'gemini', quota_status: 'available' },
]

test('lista vazia não inventa modelo — o toggle não pode desligar no vazio', () => {
  assert.equal(pickManualFallback([], '', ''), null)
})

test('restaura o último manual se ainda existe e não está esgotado', () => {
  assert.equal(pickManualFallback(models, 'm3', 'gemini')?.id, 'm3')
})

test('ignora último manual esgotado e cai no primeiro disponível', () => {
  assert.equal(pickManualFallback(models, 'm2', 'openrouter')?.id, 'm1')
})

test('auto gravado sem opt-in não é o padrão', () => {
  assert.equal(effectivePreferredModel('auto', false), null)
})

test('auto com opt-in permanece', () => {
  assert.equal(effectivePreferredModel('auto', true), 'auto')
})

test('modelo manual não depende do opt-in', () => {
  assert.equal(effectivePreferredModel('m3', false), 'm3')
})

test('sem histórico, não devolve id auto', () => {
  const picked = pickManualFallback(
    [{ id: 'auto', provider_id: 'auto' }, ...models],
    '',
    '',
  )
  assert.equal(picked?.id, 'm1')
})
