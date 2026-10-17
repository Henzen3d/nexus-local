import { test } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'
import {
  isExpression,
  validateExpression,
  evaluateExpression,
  checkDependencyCycles,
  MAX_EXPR_LENGTH,
  MAX_EXPR_TOKENS,
} from './safeMath.ts'

test('expressions parity against backend shared fixtures', () => {
  const fixturePath = new URL(
    '../../../../backend/tests/fixtures/expressions.json',
    import.meta.url
  ).pathname
  const fixtureContent = fs.readFileSync(fixturePath, 'utf-8')
  const cases = JSON.parse(fixtureContent)

  for (const c of cases) {
    const expr = c.expr
    const expectedValid = c.valid
    const res = validateExpression(expr)

    assert.strictEqual(
      res.valid,
      expectedValid,
      `Expr: ${expr} expected valid=${expectedValid}, got ${res.valid} (error=${res.error})`
    )

    if (expectedValid) {
      assert.strictEqual(res.error, undefined)
      if (c.variables) {
        assert.deepStrictEqual(
          new Set(res.variables),
          new Set(c.variables),
          `Variables mismatch for ${expr}: ${res.variables} vs ${c.variables}`
        )
      }
      if (c.sample_vars && c.expected_result !== undefined) {
        const evalRes = evaluateExpression(expr, c.sample_vars)
        assert(evalRes !== null, `Failed to evaluate valid expression ${expr}`)
        const diff = Math.abs(evalRes - c.expected_result)
        assert(diff < 0.001, `Evaluation of ${expr} got ${evalRes}, expected ${c.expected_result}`)
      }
    } else {
      assert(res.error !== undefined, `Expected error for invalid expression ${expr}`)
      if (c.error) {
        assert.strictEqual(res.error, c.error, `Error mismatch for ${expr}: ${res.error} vs ${c.error}`)
      }
    }
  }
})

test('known_ids validation', () => {
  const expr = '={x} + {y}'
  const resValid = validateExpression(expr, new Set(['x', 'y', 'z']))
  assert.strictEqual(resValid.valid, true)

  const resInvalid = validateExpression(expr, new Set(['x']))
  assert.strictEqual(resInvalid.valid, false)
  assert.strictEqual(resInvalid.error, 'unknown_identifier')
})

test('length and token limits', () => {
  const longExpr = '=' + '1 + '.repeat(50) + '1'
  assert(longExpr.length > MAX_EXPR_LENGTH)
  const resLong = validateExpression(longExpr)
  assert.strictEqual(resLong.valid, false)
  assert.strictEqual(resLong.error, 'limit_exceeded')

  const manyTokensExpr = '=1' + '+1'.repeat(30)
  assert(manyTokensExpr.length <= MAX_EXPR_LENGTH)
  const resTokens = validateExpression(manyTokensExpr)
  assert.strictEqual(resTokens.valid, false)
  assert.strictEqual(resTokens.error, 'limit_exceeded')
})

test('checkDependencyCycles topological ordering and cycle detection', () => {
  const fieldIds = new Set(['preco', 'desconto'])

  // 1. Encadeamento linear
  const linear = [
    { id: 'subtotal', formula: '{preco} - {desconto}' },
    { id: 'total', formula: '{subtotal} * 1.1' },
  ]
  const resLinear = checkDependencyCycles(linear, fieldIds)
  assert.strictEqual(resLinear.valid, true)
  assert.deepStrictEqual(resLinear.order, ['subtotal', 'total'])

  // 2. Ciclo
  const cycle = [
    { id: 'a', formula: '{b} + 1' },
    { id: 'b', formula: '{a} * 2' },
  ]
  const resCycle = checkDependencyCycles(cycle, fieldIds)
  assert.strictEqual(resCycle.valid, false)
  assert.strictEqual(resCycle.error, 'cycle_detected')

  // 3. Duplicate id
  const dup = [{ id: 'preco', formula: '100' }]
  const resDup = checkDependencyCycles(dup, fieldIds)
  assert.strictEqual(resDup.valid, false)
  assert.strictEqual(resDup.error, 'duplicate_id')

  // 4. Unknown id
  const unk = [{ id: 'total', formula: '{inexistente} * 2' }]
  const resUnk = checkDependencyCycles(unk, fieldIds)
  assert.strictEqual(resUnk.valid, false)
  assert.strictEqual(resUnk.error, 'unknown_identifier')
})
