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

test('normalizeComparableUrl normalizes host, default port and empty path only', () => {
  assert.equal(
    normalizeComparableUrl('HTTPS://WWW.Example.com:443/Path/?year=2026#Notes'),
    'https://www.example.com/Path/?year=2026#Notes',
  )
  assert.equal(normalizeComparableUrl('http://example.com:80'), 'http://example.com/')
  assert.equal(normalizeComparableUrl('http://example.com:8080'), 'http://example.com:8080/')
  assert.equal(normalizeComparableUrl('https://example.com/a/../b'), 'https://example.com/a/../b')
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

test('stripDuplicateTrailingSources removes an inline terminal citation', () => {
  for (const heading of ['Fontes:', '**Fontes**:', '## **Fontes:**', 'Fuentes:', 'Sources:']) {
    const input = `Texto [1].\r\n\r\n${heading} [1] https://site.org/a\r\n`
    assert.equal(stripDuplicateTrailingSources(input, [{ title: 'Fonte', url: 'https://site.org/a' }]), 'Texto [1].')
  }
})

test('stripDuplicateTrailingSources preserves references with a different query, fragment or path', () => {
  const sources: WebSearchSource[] = [{ title: 'Fonte', url: 'https://www.site.org/Dados/?ano=2025#jan' }]
  for (const url of [
    'https://www.site.org/Dados/?ano=2026#jan',
    'https://www.site.org/Dados/?ano=2025#feb',
    'https://www.site.org/dados/?ano=2025#jan',
    'https://www.site.org/Dados?ano=2025#jan',
    'https://site.org/Dados/?ano=2025#jan',
    'http://www.site.org/Dados/?ano=2025#jan',
  ]) {
    const input = `Texto.\n\nFontes: [1] ${url}`
    assert.equal(stripDuplicateTrailingSources(input, sources), input)
  }
})

test('stripDuplicateTrailingSources preserves substantive list items and text beside known links', () => {
  const sources: WebSearchSource[] = [{ title: 'Fonte', url: 'https://site.org/a' }]
  for (const line of [
    '- Nota que explica por que a estimativa é provisória.',
    '- [1] https://site.org/a — os números são provisórios',
    '2. [Dados](https://site.org/a) se referem a 2025.',
    '- Leia a ressalva em https://site.org/a antes de decidir.',
  ]) {
    const input = `Texto.\n\nFontes:\n- https://site.org/a\n${line}`
    assert.equal(stripDuplicateTrailingSources(input, sources), input)
  }
})

test('stripDuplicateTrailingSources preserves code blocks and removes only a citation after a closed block', () => {
  const sources: WebSearchSource[] = [{ title: 'Fonte', url: 'https://site.org/a' }]
  for (const fence of ['~~~', '\x60\x60\x60\x60']) {
    const openExample = `Texto.\n\n${fence}markdown\nFontes:\n- https://site.org/a`
    const closedExample = `${openExample}\n${fence}`
    assert.equal(stripDuplicateTrailingSources(openExample, sources), openExample)
    assert.equal(stripDuplicateTrailingSources(closedExample, sources), closedExample)
    assert.equal(stripDuplicateTrailingSources(`${closedExample}\n\nFontes: [1] https://site.org/a`, sources), closedExample)
  }
  const indentedCode = 'Texto.\n\nFontes:\n\n    https://site.org/a'
  assert.equal(stripDuplicateTrailingSources(indentedCode, sources), indentedCode)
})
