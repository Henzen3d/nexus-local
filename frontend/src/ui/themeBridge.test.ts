import assert from 'node:assert/strict'
import { test } from 'node:test'
import { buildSandboxCsp, getThemeBridgeCss, injectThemeTokens, THEME_MESSAGE_TYPE } from './themeBridge.ts'

test('CSP do sandbox fecha tudo e reabre so o necessario', () => {
  const csp = buildSandboxCsp()
  assert.match(csp, /default-src 'none'/)
  assert.match(csp, /script-src 'unsafe-inline' https:\/\/esm\.sh/)
  assert.match(csp, /connect-src https:\/\/esm\.sh/)
  assert.match(csp, /img-src data: blob:(;|$)/)
  assert.match(csp, /frame-src 'none'/)
  assert.match(csp, /form-action 'none'/)
  assert.match(csp, /base-uri 'none'/)
})

test('CSP inclui hosts confiaveis de imagem e ignora lixo', () => {
  const csp = buildSandboxCsp(['img.casa.lan', 'CDN.Exemplo.com', 'javascript:alert(1)', "x' y"])
  assert.match(csp, /img-src data: blob: https:\/\/img\.casa\.lan https:\/\/cdn\.exemplo\.com(;|$)/)
  assert.doesNotMatch(csp, /javascript/)
  assert.doesNotMatch(csp, /x'/)
})

test('bridge traz os dois temas e segue o sistema sem data-theme', () => {
  const css = getThemeBridgeCss()
  assert.match(css, /:root \{[\s\S]*--canvas: #1f1f1e/)
  assert.match(css, /html\[data-theme="light"\] \{[\s\S]*--canvas: #f8f8f6/)
  assert.match(css, /@media \(prefers-color-scheme: light\)/)
  assert.match(css, /--color-background-primary: var\(--canvas\)/)
})

test('injectThemeTokens poe data-theme inicial, tokens ao vivo e receptor de mensagem', () => {
  const doc = '<!DOCTYPE html><html><head><title>x</title></head><body>oi</body></html>'
  const out = injectThemeTokens(doc, false, { '--canvas': '#123456', '--primary': 'rgb(1, 2, 3)' })
  assert.match(out, /<style id="nexus-theme-bridge">/)
  assert.match(out, /setAttribute\('data-theme', "light"\)/)
  assert.match(out, /--canvas: #123456; --primary: rgb\(1, 2, 3\)/)
  assert.ok(out.includes(THEME_MESSAGE_TYPE))
  // injeção fica dentro do <head>
  assert.ok(out.indexOf('nexus-theme-bridge') < out.indexOf('</head>'))
  // documento sem <head> também recebe o bridge
  const semHead = injectThemeTokens('<div>a</div>', true)
  assert.match(semHead, /^\s*<style id="nexus-theme-bridge">/)
  assert.match(semHead, /setAttribute\('data-theme', "dark"\)/)
})
