import assert from 'node:assert/strict'
import { test } from 'node:test'
import { evaluateSafeFormula } from './safeMath.ts'

test('operacoes basicas e precedencia', () => {
  assert.equal(evaluateSafeFormula('2 + 3 * 4', {}), 14)
  assert.equal(evaluateSafeFormula('(2 + 3) * 4', {}), 20)
  assert.equal(evaluateSafeFormula('10 / 2 + 5', {}), 10)
  assert.equal(evaluateSafeFormula('100 - 20 * 2', {}), 60)
})

test('substituicao de variaveis numericas', () => {
  const vars = { total: 100, gorjeta: 10, pessoas: 2 }
  // ({total} * (1 + {gorjeta} / 100)) / {pessoas}
  const formula = '({total} * (1 + {gorjeta} / 100)) / {pessoas}'
  assert.equal(evaluateSafeFormula(formula, vars), 55)
})

test('rejeita caracteres perigosos ou nao aritmeticos', () => {
  assert.equal(evaluateSafeFormula('console.log(1)', {}), null)
  assert.equal(evaluateSafeFormula('2 + alert(1)', {}), null)
  assert.equal(evaluateSafeFormula('process.exit()', {}), null)
  assert.equal(evaluateSafeFormula('', {}), null)
})

test('trata divisao por zero com seguranca', () => {
  assert.equal(evaluateSafeFormula('10 / 0', {}), 0)
})
