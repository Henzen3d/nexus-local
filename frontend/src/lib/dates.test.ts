import assert from 'node:assert/strict'
import { test } from 'node:test'
import { getConversationDateGroup, parseUtc } from './dates.ts'

function inTimezone(timezone: string, run: () => void) {
  const previousTimezone = process.env.TZ
  process.env.TZ = timezone
  try {
    run()
  } finally {
    if (previousTimezone === undefined) delete process.env.TZ
    else process.env.TZ = previousTimezone
  }
}

test('parses suffixless timestamps as UTC and respects explicit offsets', () => {
  inTimezone('America/Sao_Paulo', () => {
    const expected = Date.UTC(2026, 10, 20, 1, 15)
    assert.equal(parseUtc('2026-11-20 01:15:00'), expected)
    assert.equal(parseUtc('2026-11-20T01:15:00'), expected)
    assert.equal(parseUtc('2026-11-20T01:15:00Z'), expected)
    assert.equal(parseUtc('2026-11-19T22:15:00-03:00'), expected)
    assert.equal(parseUtc('2026-11-19 22:15:00-03:00'), expected)
    assert.equal(parseUtc(null), null)
    assert.equal(parseUtc('invalid'), null)
  })
})

test('groups conversations by the local date, including when UTC has rolled over', () => {
  inTimezone('America/Sao_Paulo', () => {
    const now = new Date('2026-11-20T11:33:00Z')
    assert.equal(getConversationDateGroup('2026-11-19 23:41:00', now), 'yesterday')
    assert.equal(getConversationDateGroup('2026-11-20 01:15:00', now), 'yesterday')
    assert.equal(getConversationDateGroup('2026-11-20 02:59:59', now), 'yesterday')
    assert.equal(getConversationDateGroup('2026-11-20 03:00:00', now), 'today')
    assert.equal(getConversationDateGroup('2026-11-13 03:00:00', now), 'last7Days')
    assert.equal(getConversationDateGroup('2026-11-13 02:59:59', now), 'older')
  })
})

test('yesterday starts at local midnight on 23- and 25-hour days', () => {
  inTimezone('America/New_York', () => {
    const spring = new Date('2026-03-09T16:00:00Z')
    assert.equal(getConversationDateGroup('2026-03-08 04:59:59', spring), 'last7Days')
    assert.equal(getConversationDateGroup('2026-03-08 05:00:00', spring), 'yesterday')

    const fall = new Date('2026-11-02T17:00:00Z')
    assert.equal(getConversationDateGroup('2026-11-01 03:59:59', fall), 'last7Days')
    assert.equal(getConversationDateGroup('2026-11-01 04:00:00', fall), 'yesterday')
  })
})
