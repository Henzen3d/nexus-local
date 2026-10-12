import assert from 'node:assert/strict'
import test from 'node:test'
import { mergeProcessTree } from './processTree.ts'

const labels = { searching: 'Pesquisando na web', reading: 'Lendo' }

test('mantém os passos de busca quando já existe um passo de raciocínio', () => {
  const steps = mergeProcessTree(
    [
      { id: 'search-step-0', type: 'search', title: 'Pesquisado na web por: clima', detail: 'clima', status: 'completed' },
      { id: 'thinking', type: 'think', title: 'Raciocinando', status: 'completed' },
    ],
    { used: true, query: 'clima', sources: [{ title: 'Fonte', url: 'https://exemplo.test' }] },
    labels,
  )
  assert.equal(steps.filter((step) => step.type === 'search').length, 1)
  assert.equal(steps.some((step) => step.type === 'think'), true)
  assert.equal(steps[0].detail, 'clima')
})

test('recompõe a busca a partir das fontes quando a árvore só tem raciocínio', () => {
  const steps = mergeProcessTree(
    [{ id: 'thinking', type: 'think', title: 'Raciocinando', status: 'completed' }],
    {
      used: true,
      query: 'previsão blumenau',
      sources: [{ title: 'Climatempo', url: 'https://exemplo.test/clima' }],
    },
    labels,
  )
  assert.equal(steps[0].type, 'search')
  assert.equal(steps[0].detail, 'previsão blumenau')
  assert.equal(steps.some((step) => step.detail === 'https://exemplo.test/clima'), true)
  assert.equal(steps.some((step) => step.type === 'think'), true)
})

test('não inventa busca quando não houve pesquisa', () => {
  const steps = mergeProcessTree(
    [{ id: 'thinking', type: 'think', title: 'Raciocinando', status: 'completed' }],
    undefined,
    labels,
  )
  assert.equal(steps.length, 1)
  assert.equal(steps[0].type, 'think')
})
