import assert from 'node:assert/strict'
import { test } from 'node:test'
import { canRequestCorrection } from './correction.ts'

test('correction requires flag, an error and an explicit unconsumed offer', () => {
  assert.equal(canRequestCorrection(false, false, 1, true), false)
  assert.equal(canRequestCorrection(true, false, 0, false), false)
  assert.equal(canRequestCorrection(true, false, 1, false), true)
  assert.equal(canRequestCorrection(true, false, 0, true), true)
  assert.equal(canRequestCorrection(true, true, 1, true), false)
})
