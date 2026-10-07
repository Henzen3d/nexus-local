import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { test } from 'node:test'
import { fileURLToPath } from 'node:url'
import { canShowRegisterUserButton, REGISTER_USER_BUTTON_CLASS } from './registerUser.ts'

const here = dirname(fileURLToPath(import.meta.url))

test('botão só para administrador, em qualquer caixa', () => {
  assert.equal(canShowRegisterUserButton('ADMIN'), true)
  assert.equal(canShowRegisterUserButton('admin'), true)
  assert.equal(canShowRegisterUserButton(' Admin '), true)
  assert.equal(canShowRegisterUserButton('user'), false)
  assert.equal(canShowRegisterUserButton(''), false)
  assert.equal(canShowRegisterUserButton(undefined), false)
  assert.equal(canShowRegisterUserButton(null), false)
})

test('regressão visual: botão não pode sumir no layout', () => {
  const css = readFileSync(join(here, '../index.css'), 'utf8')
  const start = css.indexOf(`.${REGISTER_USER_BUTTON_CLASS} {`)
  assert.ok(start >= 0, 'classe do botão ausente no CSS')
  const rule = css.slice(start, css.indexOf('}', start) + 1)
  assert.match(rule, /display:\s*flex\s*!important/)
  assert.match(rule, /min-height:\s*44px/)
  assert.match(rule, /width:\s*100%/)
  assert.match(rule, /background:\s*#cc785c/)
  assert.match(rule, /color:\s*#fff/)
  assert.match(rule, /visibility:\s*visible\s*!important/)
})

test('rótulo pt-BR é Cadastrar Usuário', () => {
  const locale = JSON.parse(readFileSync(join(here, '../i18n/locales/pt-BR.json'), 'utf8'))
  assert.equal(locale.settings.registerUser, 'Cadastrar Usuário')
})
