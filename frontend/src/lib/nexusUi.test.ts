import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isAllowedImageUrl, parseUiEnvelope } from './nexusUi.ts'

test('rejeita versao errada', () => {
  assert.equal(parseUiEnvelope('{"v":2,"blocks":[]}'), null)
})

test('progress valido', () => {
  const raw = '{"v":1,"blocks":[{"id":"seo","type":"progress","label":"Auditoria SEO","value":7,"max":10}]}'
  const out = parseUiEnvelope(raw)
  assert.notEqual(out, null)
  assert.equal(out?.blocks[0]?.type, 'progress')
  if (out?.blocks[0]?.type === 'progress') {
    assert.equal(out.blocks[0].value, 7)
    assert.equal(out.blocks[0].max, 10)
  }
})

test('bloco ruim nao derruba o bom', () => {
  const raw = '{"v":1,"blocks":[{"id":"ok","type":"progress","label":"A","value":1,"max":2},{"id":"ruim","type":"chart","kind":"pizza"}]}'
  const out = parseUiEnvelope(raw)
  assert.notEqual(out, null)
  assert.deepEqual(
    out?.blocks.map((b) => b.id),
    ['ok']
  )
})

test('filtro de imagens segue regras de seguranca', () => {
  // URLs relativas permitidas
  assert.equal(isAllowedImageUrl('/attachments/foto.png'), true)

  // Host atual permitido
  assert.equal(isAllowedImageUrl('https://meusite.com/img.jpg', [], 'meusite.com'), true)

  // Host na lista branca
  assert.equal(isAllowedImageUrl('https://cdn.exemplo.com/img.jpg', ['cdn.exemplo.com']), true)

  // Host externo nao autorizado
  assert.equal(isAllowedImageUrl('https://hacker.com/img.jpg', []), false)

  // Protocolos perigosos
  assert.equal(isAllowedImageUrl('javascript:alert(1)'), false)
  assert.equal(isAllowedImageUrl('data:image/png;base64,123'), false)

  // IP privado com flag desligada
  assert.equal(isAllowedImageUrl('http://192.168.1.50/cam.jpg', [], undefined, false), false)
  // IP privado com flag ligada
  assert.equal(isAllowedImageUrl('http://192.168.1.50/cam.jpg', [], undefined, true), true)
})

test('chart bar line e compare', () => {
  const rawBar = {
    v: 1,
    blocks: [
      {
        id: 'c1',
        type: 'chart',
        title: 'Custo',
        kind: 'bar',
        x_key: 'mod',
        series: [{ key: 'usd', label: 'USD' }],
        rows: [{ mod: 'A', usd: 10 }],
      },
    ],
  }
  const out = parseUiEnvelope(rawBar)
  assert.notEqual(out, null)
  assert.equal(out?.blocks[0]?.type, 'chart')
})

test('controls com formula e template', () => {
  const rawControls = {
    v: 1,
    blocks: [
      {
        id: 'ctrl',
        type: 'controls',
        title: 'Calcular',
        submit_label: 'Enviar',
        fields: [
          { id: 'total', kind: 'number', min: 1, max: 1000 },
          { id: 'opcao', kind: 'select', options: [{ value: 'a', label: 'Op A' }, { value: 'b', label: 'Op B' }] },
        ],
        computed: { template: 'Total: {resultado}', formula: '{total} * 2' },
        action: { name: 'send_message', template: 'Escolhido: {opcao}. Res: {resultado}' },
      },
    ],
  }
  const out = parseUiEnvelope(rawControls)
  assert.notEqual(out, null)
  assert.equal(out?.blocks[0]?.type, 'controls')
})

test('sandbox com initial_height', () => {
  const rawSb = {
    v: 1,
    blocks: [
      {
        id: 'sb',
        type: 'sandbox',
        title: 'Simulador',
        initial_height: 400,
        html: '<div>ok</div>',
        standalone_download: true,
      },
    ],
  }
  const out = parseUiEnvelope(rawSb)
  assert.notEqual(out, null)
  assert.equal(out?.blocks[0]?.type, 'sandbox')
  if (out?.blocks[0]?.type === 'sandbox') {
    assert.equal(out.blocks[0].initial_height, 400)
  }
})
