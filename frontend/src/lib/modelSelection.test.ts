import assert from 'node:assert/strict'
import test from 'node:test'
import {
  pickManualFallback,
  effectivePreferredModel,
  resolveInitialModelSelection,
} from './modelSelection.ts'

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

test('modo simples em perfil limpo resolve auto quando há rota elegível', () => {
  const res = resolveInitialModelSelection({
    models,
    catalogStatus: 'ready',
    uiLevel: 'simple',
    preferredModelId: null,
    preferredProviderId: null,
  })
  assert.deepEqual(res, {
    modelId: 'auto',
    providerId: 'auto',
    routeReady: true,
    reason: 'ok',
  })
})

test('modo simples não inventa rota durante carregamento ou catálogo vazio/esgotado/erro', () => {
  assert.deepEqual(
    resolveInitialModelSelection({ models: [], catalogStatus: 'loading', uiLevel: 'simple' }),
    { modelId: null, providerId: null, routeReady: false, reason: 'loading' },
  )
  assert.deepEqual(
    resolveInitialModelSelection({ models: [], catalogStatus: 'empty', uiLevel: 'simple' }),
    { modelId: null, providerId: null, routeReady: false, reason: 'empty' },
  )
  assert.deepEqual(
    resolveInitialModelSelection({
      models: [{ id: 'm2', provider_id: 'openrouter', quota_status: 'exhausted' }],
      catalogStatus: 'ready',
      uiLevel: 'simple',
    }),
    { modelId: null, providerId: null, routeReady: false, reason: 'all_exhausted' },
  )
  assert.deepEqual(
    resolveInitialModelSelection({ models, catalogStatus: 'error', uiLevel: 'simple' }),
    { modelId: null, providerId: null, routeReady: false, reason: 'error' },
  )
})

test('modo intermediário sem opt-in seleciona primeiro modelo elegível e preserva manual', () => {
  const clean = resolveInitialModelSelection({
    models,
    catalogStatus: 'ready',
    uiLevel: 'intermediate',
    preferredModelId: null,
    autoOptIn: false,
  })
  assert.equal(clean.modelId, 'm1')
  assert.equal(clean.providerId, 'groq')

  const manual = resolveInitialModelSelection({
    models,
    catalogStatus: 'ready',
    uiLevel: 'advanced',
    preferredModelId: 'm3',
    preferredProviderId: 'gemini',
  })
  assert.equal(manual.modelId, 'm3')
  assert.equal(manual.providerId, 'gemini')
})
