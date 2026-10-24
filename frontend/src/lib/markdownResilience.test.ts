import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { highlightCode } from './codeHighlight.ts'

test('highlightCode lida com código vazio e prefixos parciais sem estourar exceção', () => {
  // Código vazio
  assert.equal(highlightCode('', 'typescript'), '')

  // Bloco com string aberta sem fechar (streaming parcial)
  const partialString = 'const msg = "texto que ainda nao fechou aspas'
  const highlighted = highlightCode(partialString, 'typescript')
  assert.ok(highlighted.includes('tok-string') || highlighted.includes('texto que ainda'))

  // Comentário aberto
  const partialComment = '// comentário de uma linha'
  assert.ok(highlightCode(partialComment, 'javascript').includes('tok-comment'))

  // Bloco sem linguagem informada
  const plain = highlightCode('SELECT * FROM users;', '')
  assert.ok(plain.includes('SELECT'))
})

test('CodeBlock possui cabeçalho presente, rótulo neutro de fallback e proteção contra falso sucesso de cópia', () => {
  const codeBlockSource = readFileSync(
    new URL('../components/CodeBlock.tsx', import.meta.url),
    'utf8'
  )

  // Rótulo neutro quando lang ausente
  assert.ok(codeBlockSource.includes("cleanLang || t('chat.code', { defaultValue: 'code' })") || codeBlockSource.includes('cleanLang ||'))

  // Cabeçalho sempre presente
  assert.ok(codeBlockSource.includes('className="code-block-header"'))
  assert.ok(codeBlockSource.includes('className="code-lang"'))

  // Botão de copiar com confirmação de 2000ms
  assert.ok(codeBlockSource.includes('setTimeout(() => setCopied(false), 2000)'))

  // Tratamento de erro na cópia (não exibe falso sucesso se Clipboard API falhar)
  assert.ok(codeBlockSource.includes('.catch('))
})

test('Tabelas GFM e wrapper responsivo com zebra striping no index.css', () => {
  const css = readFileSync(
    new URL('../index.css', import.meta.url),
    'utf8'
  )

  // Wrapper com overflow-x: auto
  assert.ok(css.includes('.markdown-table-wrapper'))
  assert.ok(css.includes('overflow-x: auto'))

  // Zebra striping presente
  assert.ok(css.includes('tr:nth-child(even) td'))

  // Hierarquia tipográfica com h1-h4 calibrados
  assert.ok(css.includes('.assistant-response h1'))
  assert.ok(css.includes('.assistant-response h2'))
  assert.ok(css.includes('.assistant-response h3'))
  assert.ok(css.includes('.assistant-response h4'))

  // Listas aninhadas com espaçamento consistente
  assert.ok(css.includes('.assistant-response ul ul'))
})
