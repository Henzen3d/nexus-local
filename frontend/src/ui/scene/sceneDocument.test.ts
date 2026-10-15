import assert from 'node:assert/strict'
import { test } from 'node:test'
import { embed, escapeScript, sceneDocument } from './sceneDocument.ts'
import { readSceneMessage, SCENE_MSG } from './sceneProtocol.ts'
import type { SceneSetup } from './sceneProtocol.ts'

test('escapeScript escapes </script> and <!-- correctly', () => {
  const code = 'const x = "</script><script>alert(1)</script><!-- comment -->";'
  const escaped = escapeScript(code)
  assert.equal(escaped.includes('</script>'), false)
  assert.equal(escaped.includes('<!--'), false)
  assert.equal(escaped.includes('<\\/script>'), true)
  assert.equal(escaped.includes('<\\!--'), true)
})

test('embed encodes < as \\u003c', () => {
  const obj = { title: '<tag> & "quote"', value: 42 }
  const embedded = embed(obj)
  assert.equal(embedded.includes('<'), false)
  assert.equal(embedded.includes('\\u003c'), true)
})

test('sceneDocument generates strict CSP and valid HTML without network', () => {
  const setup: SceneSetup = {
    title: 'Teste',
    mode: '3d',
    theme: { dark: true, text: '#ffffff', accent: '#cc785c' },
    params: { vel: 1 },
    paused: false,
  }
  const html = sceneDocument(setup, 'console.log("hello");', '/scene/runtime.js', 'pt-BR')
  assert.equal(html.includes("default-src 'none'"), true)
  assert.equal(html.includes("/scene/runtime.js"), true)
  assert.equal(html.includes("NexusScene.setup("), true)
  assert.equal(html.includes("NexusScene.start("), true)
  assert.equal(html.includes('lang="pt-BR"'), true)
})

test('readSceneMessage validates messages according to scene protocol', () => {
  // Mensagem válida de ready
  assert.deepEqual(readSceneMessage({ type: SCENE_MSG.ready }), { type: SCENE_MSG.ready })

  // Mensagem válida de report com chaves válidas
  const reportMsg = readSceneMessage({
    type: SCENE_MSG.report,
    values: { angulo: 1.57, ativo: true, texto: 'ok', invalido: [1, 2, 3] },
  })
  assert.deepEqual(reportMsg, {
    type: SCENE_MSG.report,
    values: { angulo: 1.57, ativo: true, texto: 'ok' },
  })

  // Mensagem válida de error (limitada em MAX_ERROR_TEXT = 500)
  const longError = 'x'.repeat(600)
  const errorMsg = readSceneMessage({ type: SCENE_MSG.error, message: longError })
  assert.equal(errorMsg?.type, SCENE_MSG.error)
  if (errorMsg?.type === SCENE_MSG.error) {
    assert.equal(errorMsg.message.length, 500)
  }

  // Mensagens fora do protocolo devolvem null
  assert.equal(readSceneMessage(null), null)
  assert.equal(readSceneMessage('texto'), null)
  assert.equal(readSceneMessage({ type: 'unknown_type' }), null)
  assert.equal(readSceneMessage({ type: SCENE_MSG.report, values: 'not_an_object' }), null)
})
