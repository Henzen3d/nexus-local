import assert from 'node:assert/strict'
import { test } from 'node:test'
import { isAllowedImageUrl, parseUiEnvelope, stripUiFences } from './nexusUi.ts'

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

// ── Paridade TS ↔ Python (backend/ui_blocks/validate.py) ─────────────────────

test('v ausente assume 1; v null ou string estranha rejeita', () => {
  assert.notEqual(parseUiEnvelope({ blocks: [{ id: 'p', type: 'progress', label: 'A', value: 1, max: 2 }] }), null)
  assert.notEqual(parseUiEnvelope({ v: '1', blocks: [{ id: 'p', type: 'progress', label: 'A', value: 1, max: 2 }] }), null)
  assert.equal(parseUiEnvelope({ v: null, blocks: [{ id: 'p', type: 'progress', label: 'A', value: 1, max: 2 }] }), null)
  assert.equal(parseUiEnvelope({ v: 'x', blocks: [{ id: 'p', type: 'progress', label: 'A', value: 1, max: 2 }] }), null)
})

test('chart: kind ausente vira bar, kind invalido descarta o bloco', () => {
  const rows = [{ x: 'a', y: 1 }, { x: 'b', y: 2 }]
  const series = [{ key: 'y', label: 'Y' }]
  const semKind = parseUiEnvelope({ v: 1, blocks: [{ id: 'c', type: 'chart', title: 'T', x_key: 'x', series, rows }] })
  assert.equal(semKind?.blocks[0]?.type, 'chart')
  if (semKind?.blocks[0]?.type === 'chart') assert.equal(semKind.blocks[0].kind, 'bar')
  const pizza = parseUiEnvelope({ v: 1, blocks: [{ id: 'c', type: 'chart', kind: 'pie', title: 'T', x_key: 'x', series, rows }] })
  assert.equal(pizza, null)
})

test('controls: action obrigatoria, nomes estritos, sem template inventado, maximo 4 campos', () => {
  const fields = [{ id: 'a', kind: 'number' }, { id: 'b', kind: 'number' }]
  const base = { id: 'ctrl', type: 'controls', title: 'T', fields }
  assert.equal(parseUiEnvelope({ v: 1, blocks: [base] }), null, 'sem action')
  assert.equal(parseUiEnvelope({ v: 1, blocks: [{ ...base, action: { name: 'open_url', template: 'x' } }] }), null, 'action desconhecida')
  assert.equal(parseUiEnvelope({ v: 1, blocks: [{ ...base, action: { name: 'send_message' } }] }), null, 'send_message sem template')
  assert.equal(parseUiEnvelope({ v: 1, blocks: [{ ...base, action: { name: 'set_model' } }] }), null, 'set_model sem select')

  const seis = Array.from({ length: 6 }, (_, i) => ({ id: `f${i + 1}`, kind: 'number' }))
  const out = parseUiEnvelope({
    v: 1,
    blocks: [{ ...base, fields: seis, action: { name: 'send_message', template: 'Soma {f1} {f4}' } }],
  })
  assert.equal(out?.blocks[0]?.type, 'controls')
  if (out?.blocks[0]?.type === 'controls') {
    assert.equal(out.blocks[0].fields.length, 4)
    assert.deepEqual(out.blocks[0].fields.map((f) => f.id), ['f1', 'f2', 'f3', 'f4'])
  }
  // placeholder apontando para campo cortado (5º) invalida o bloco
  assert.equal(
    parseUiEnvelope({ v: 1, blocks: [{ ...base, fields: seis, action: { name: 'send_message', template: '{f5}' } }] }),
    null
  )
})

test('sandbox: limites 12000/4000/8000 e altura tolerante', () => {
  const ok = parseUiEnvelope({ v: 1, blocks: [{ id: 's', type: 'sandbox', html: '<p>x</p>', initial_height: '350.4' }] })
  assert.equal(ok?.blocks[0]?.type, 'sandbox')
  if (ok?.blocks[0]?.type === 'sandbox') assert.equal(ok.blocks[0].initial_height, 350)
  const alta = parseUiEnvelope({ v: 1, blocks: [{ id: 's', type: 'sandbox', html: '<p>x</p>', initial_height: 9000 }] })
  if (alta?.blocks[0]?.type === 'sandbox') assert.equal(alta.blocks[0].initial_height, 300)

  const htmlGrande = parseUiEnvelope({ v: 1, blocks: [{ id: 's', type: 'sandbox', html: 'x'.repeat(12001) }] })
  assert.equal(htmlGrande, null)
  const cssGrande = parseUiEnvelope({
    v: 1,
    blocks: [{ id: 's', type: 'sandbox', html: '<p>x</p>', css: 'a'.repeat(4001), js: 'b'.repeat(8001) }],
  })
  assert.equal(cssGrande?.blocks[0]?.type, 'sandbox')
  if (cssGrande?.blocks[0]?.type === 'sandbox') {
    assert.equal(cssGrande.blocks[0].css, undefined)
    assert.equal(cssGrande.blocks[0].js, undefined)
  }
})

test('stripUiFences: remove fence no inicio da linha, preserva mencao inline', () => {
  const comFence = 'Prosa.\n\n```nexus-ui\n{"v":1,"blocks":[]}\n```'
  assert.equal(stripUiFences(comFence), 'Prosa.')
  const inline = 'Use o fence ```nexus-ui no final, assim: ```nexus-ui {...} ``` e pronto.'
  assert.equal(stripUiFences(inline), inline)
  const indentado = 'Texto.\n   ```nexus-ui\n{"v":1,"blocks":[]}\n   ```'
  assert.equal(stripUiFences(indentado), 'Texto.')
  // fence aberto durante o stream some; menção inline não
  assert.equal(stripUiFences('Texto.\n```nexus-ui\n{"v":1,"blo'), 'Texto.')
  assert.equal(stripUiFences('falando de ```nexus-ui no meio'), 'falando de ```nexus-ui no meio')
})
