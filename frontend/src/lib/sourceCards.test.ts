import assert from 'node:assert/strict'
import test from 'node:test'
import { faviconUrl, pageCountKey, sourceHost } from './sourceCards.ts'

test('host sem www e favicon pelo domínio', () => {
  assert.equal(sourceHost('https://www.fixblu.com.br/blog/a'), 'fixblu.com.br')
  assert.equal(
    faviconUrl('https://fixblu.com.br/x'),
    'https://www.google.com/s2/favicons?domain=fixblu.com.br&sz=64',
  )
})

test('plural de páginas', () => {
  assert.equal(pageCountKey(1), 'chat.pagesCount_one')
  assert.equal(pageCountKey(92), 'chat.pagesCount_other')
})
