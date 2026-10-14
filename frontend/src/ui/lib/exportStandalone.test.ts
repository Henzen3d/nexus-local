import assert from 'node:assert/strict'
import { test } from 'node:test'
import { assembleStandaloneHtml } from './exportStandalone.ts'

test('standalone leva lang do i18n, tema do momento e os dois conjuntos de tokens', () => {
  const html = assembleStandaloneHtml('Calculadora', '<p>x</p>', 'p{color:red}', 'console.log(1)', false, 'en-US')
  assert.match(html, /<html lang="en-US" data-theme="light">/)
  assert.match(html, /html\[data-theme="light"\]/)
  assert.match(html, /@media \(prefers-color-scheme: light\)/)
  assert.match(html, /<title>Calculadora<\/title>/)
  assert.match(html, /"three":"https:\/\/esm\.sh\/three"/)
  assert.match(html, /p\{color:red\}/)
  assert.match(html, /console\.log\(1\)/)
})

test('standalone escapa titulo e nao deixa o bloco fechar script/style', () => {
  const html = assembleStandaloneHtml('<b>"t"</b>', '<p>x</p>', 'a{}</style><script>alert(1)</script>', 'x</script><img src=x onerror=alert(1)>', true)
  assert.match(html, /<title>&lt;b&gt;&quot;t&quot;&lt;\/b&gt;<\/title>/)
  assert.doesNotMatch(html, /a\{\}<\/style>/)
  assert.match(html, /x<\\\/script>/)
  assert.match(html, /<html lang="pt-BR" data-theme="dark">/)
})

test('lang invalido cai para pt-BR', () => {
  const html = assembleStandaloneHtml('t', '<p>x</p>', '', '', true, '"><script>')
  assert.match(html, /<html lang="pt-BR"/)
})
