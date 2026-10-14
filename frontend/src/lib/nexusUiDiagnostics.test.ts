import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { diagnoseUiText, parseUiEnvelopeWithDiagnostics, UI_ERROR_CODES } from './nexusUi.ts'
const cases = JSON.parse(readFileSync(new URL('../../../backend/tests/fixtures/ui-errors.json', import.meta.url), 'utf8'))
for (const fixture of cases) {
  test(`shared Python/TS diagnostics: ${fixture.name}`, () => {
    const before = structuredClone(fixture.raw)
    const report = parseUiEnvelopeWithDiagnostics(fixture.raw)
    assert.deepEqual(report.errors.map((e) => e.code), fixture.codes)
    assert.equal(report.dropped, fixture.dropped)
    const raw = typeof fixture.raw === 'string' ? fixture.raw : JSON.stringify(fixture.raw)
    const fenced = diagnoseUiText('prose\n```nexus-ui\n' + raw + '\n```')
    assert.deepEqual(fenced.errors, report.errors)
    assert.equal(fenced.dropped, report.dropped)
    assert.deepEqual(fixture.raw, before)
    assert.ok(report.errors.every((e) => e.message.length <= 160 && UI_ERROR_CODES.includes(e.code)))
  })
}
test('image host policy is explicit and error text does not include raw data', () => {
  const raw = { blocks: [{ type: 'card', image: { url: 'https://trusted.test/secret', alt: 'private' } }] }
  assert.deepEqual(parseUiEnvelopeWithDiagnostics(raw, ['trusted.test']).errors, [])
  const errors = parseUiEnvelopeWithDiagnostics(raw).errors
  assert.equal(errors[0].code, 'unsafe_url')
  assert.doesNotMatch(JSON.stringify(errors), /secret|private/)
})

test('open fences, inline mentions and last fence match backend extraction', () => {
  assert.equal(diagnoseUiText('prose\n```nexus-ui\n{').errors[0].code, 'fence_unclosed')
  assert.deepEqual(diagnoseUiText('inline ```nexus-ui mention').errors, [])
  const text = '```nexus-ui\n{\n```\ntext\n```nexus-ui\n{"blocks":[{"type":"callout","body":"ok"}]}\n```'
  assert.deepEqual(diagnoseUiText(text).errors, [])
  assert.deepEqual(diagnoseUiText('```ui\n{"blocks":[{"type":"video"}]}\n```').errors.map((e) => e.code), ['unknown_type'])
})
