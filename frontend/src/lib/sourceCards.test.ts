import test from 'node:test'
import assert from 'node:assert/strict'
import {
  sourceHost,
  pageCountKey,
  stripDuplicateTrailingSources,
  normalizeComparableUrl,
} from './sourceCards.ts'
import type { WebSearchSource } from '../types.ts'

test('sourceHost extracts domain correctly', () => {
  assert.equal(sourceHost('https://www.google.com/search?q=test'), 'google.com')
  assert.equal(sourceHost('http://noticias.uol.com.br/artigo/1'), 'noticias.uol.com.br')
  assert.equal(sourceHost('invalid-url'), 'invalid-url')
})

test('pageCountKey formats singular and plural keys', () => {
  assert.equal(pageCountKey(1), 'chat.pagesCount_one')
  assert.equal(pageCountKey(2), 'chat.pagesCount_other')
  assert.equal(pageCountKey(5), 'chat.pagesCount_other')
})

test('normalizeComparableUrl strips protocol, www, trailing slash and lowercase', () => {
  assert.equal(
    normalizeComparableUrl('https://WWW.Example.com/path/'),
    'example.com/path',
  )
  assert.equal(
    normalizeComparableUrl('http://example.com/path'),
    'example.com/path',
  )
})

test('stripDuplicateTrailingSources removes terminal section when all links exist in sources', () => {
  const sources: WebSearchSource[] = [
    { index: 1, title: 'Google', url: 'https://www.google.com/search', was_read: true },
    { index: 2, title: 'UOL', url: 'https://noticias.uol.com.br/item', was_read: false },
  ]

  const input = `Aqui está o resultado conforme apurado [1] e complementado por [2].

### Fontes:
1. [Google](https://www.google.com/search)
2. [UOL](https://noticias.uol.com.br/item)`

  const cleaned = stripDuplicateTrailingSources(input, sources)
  assert.equal(cleaned, 'Aqui está o resultado conforme apurado [1] e complementado por [2].')
})

test('stripDuplicateTrailingSources handles bulleted lists with bold headers', () => {
  const sources: WebSearchSource[] = [
    { index: 1, title: 'Fonte 1', url: 'https://site.org/a' },
    { index: 2, title: 'Fonte 2', url: 'https://site.org/b' },
  ]

  const input = `Texto com dados importantes.

**Fontes consultadas:**
- [1] https://site.org/a
- [2] https://site.org/b`

  const cleaned = stripDuplicateTrailingSources(input, sources)
  assert.equal(cleaned, 'Texto com dados importantes.')
})

test('stripDuplicateTrailingSources preserves content when a link is novel (not in sources)', () => {
  const sources: WebSearchSource[] = [
    { index: 1, title: 'Fonte 1', url: 'https://site.org/a' },
  ]

  const input = `Texto.

### Fontes:
1. https://site.org/a
2. https://novel-site.org/untracked`

  const cleaned = stripDuplicateTrailingSources(input, sources)
  assert.equal(cleaned, input, 'Não deve remover se contiver link inédito intencional')
})

test('stripDuplicateTrailingSources preserves content when inside code fences', () => {
  const sources: WebSearchSource[] = [
    { index: 1, title: 'Fonte 1', url: 'https://site.org/a' },
  ]

  const input = `Exemplo de markdown gerado:
\`\`\`markdown
### Fontes:
- https://site.org/a
\`\`\``

  const cleaned = stripDuplicateTrailingSources(input, sources)
  assert.equal(cleaned, input, 'Não deve remover dentro de blocos de código')
})

test('stripDuplicateTrailingSources preserves content when section contains substantive text', () => {
  const sources: WebSearchSource[] = [
    { index: 1, title: 'Fonte 1', url: 'https://site.org/a' },
  ]

  const input = `Texto.

### Fontes:
- https://site.org/a

Conclusão analítica fundamental que não pode ser descartada de forma alguma.`

  const cleaned = stripDuplicateTrailingSources(input, sources)
  assert.equal(cleaned, input, 'Não deve remover se contiver parágrafo substantivo após os links')
})

test('stripDuplicateTrailingSources returns unchanged if sources is empty or null', () => {
  const input = `Texto.\n\n### Fontes:\n1. https://site.org/a`
  assert.equal(stripDuplicateTrailingSources(input, []), input)
  assert.equal(stripDuplicateTrailingSources(input, null), input)
})
