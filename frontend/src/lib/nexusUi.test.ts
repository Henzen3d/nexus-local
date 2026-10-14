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
  const radar = parseUiEnvelope({ v: 1, blocks: [{ id: 'c', type: 'chart', kind: 'radar', title: 'T', x_key: 'x', series, rows }] })
  assert.equal(radar, null)
  const pizza = parseUiEnvelope({ v: 1, blocks: [{ id: 'c', type: 'chart', kind: 'pie', title: 'T', x_key: 'x', series, rows }] })
  assert.equal(pizza?.blocks[0]?.type, 'chart')
  if (pizza?.blocks[0]?.type === 'chart') assert.equal(pizza.blocks[0].kind, 'pie')
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

// ─── Plano 12 — metric, callout, follow_up; teto 6 e subtetos (espelho do Python) ───

test('metric: limites, unit so com numero, NaN cai', () => {
  const out = parseUiEnvelope({
    v: 1,
    blocks: [
      {
        id: 'kpis',
        type: 'metric',
        title: 'Este mês',
        items: [
          { label: 'Receita', value: 48200, unit: 'R$', delta: '+8,1%', trend: 'up', hint: 'vs. mês anterior' },
          { label: 'Churn', value: '1,8%', delta: '-0,3 p.p.', trend: 'down', good: 'down' },
          { label: 'Texto com unidade', value: 'alto', unit: '%' },
          { label: 'Sem valor' },
          { label: 'NaN', value: Number.NaN },
          { label: 'Quinto', value: 5 },
          { label: 'Sexto', value: 6 },
        ],
      },
    ],
  })
  assert.equal(out?.blocks[0]?.type, 'metric')
  if (out?.blocks[0]?.type === 'metric') {
    const block = out.blocks[0]
    assert.equal(block.title, 'Este mês')
    assert.deepEqual(
      block.items.map((i) => i.label),
      ['Receita', 'Churn', 'Texto com unidade', 'Quinto']
    )
    assert.deepEqual(block.items[0], {
      label: 'Receita', value: 48200, unit: 'R$', delta: '+8,1%', trend: 'up', hint: 'vs. mês anterior',
    })
    assert.equal(block.items[1].good, 'down')
    assert.equal(block.items[2].unit, undefined)
  }
  assert.equal(parseUiEnvelope({ v: 1, blocks: [{ type: 'metric', items: [] }] }), null)
  assert.equal(parseUiEnvelope({ v: 1, blocks: [{ type: 'metric', items: [{ label: 'x', value: true }] }] }), null)
})

test('callout: kind tolerante, body obrigatorio', () => {
  const out = parseUiEnvelope({
    v: 1,
    blocks: [
      { type: 'callout', kind: 'warn', title: 'Atenção', body: 'A Selic usada é a de outubro.' },
      { type: 'callout', kind: 'pizza', body: 'Vira info.' },
      { type: 'callout', kind: 'error', body: 'Vira danger.' },
      { type: 'callout', kind: 'danger', title: 'Sem corpo' },
    ],
  })
  assert.deepEqual(
    out?.blocks.map((b) => (b.type === 'callout' ? [b.kind, b.title] : null)),
    [['warning', 'Atenção'], ['info', undefined], ['danger', undefined]]
  )
})

test('follow_up: vai para o fim, so um por envelope, teto 4', () => {
  const out = parseUiEnvelope({
    v: 1,
    blocks: [
      { type: 'follow_up', items: ['Comparar com 2025', 'Mostrar por região', 'x', 'comparar com 2025', { label: 'Exportar' }, 'Quinto item'] },
      { type: 'progress', label: 'A', value: 1, max: 2 },
      { type: 'follow_up', items: ['Segundo bloco cai'] },
    ],
  })
  assert.deepEqual(out?.blocks.map((b) => b.type), ['progress', 'follow_up'])
  if (out?.blocks[1]?.type === 'follow_up') {
    assert.deepEqual(out.blocks[1].items, ['Comparar com 2025', 'Mostrar por região', 'Exportar', 'Quinto item'])
  }
  assert.equal(parseUiEnvelope({ v: 1, blocks: [{ type: 'follow_up', items: ['ab'] }] }), null)
})

test('teto de seis blocos com subtetos por tipo', () => {
  const chart = { type: 'chart', kind: 'bar', x_key: 'x', series: [{ key: 'y', label: 'Y' }], rows: [{ x: 'a', y: 1 }] }
  const sandbox = { type: 'sandbox', title: 'S', html: '<div></div>' }
  const out = parseUiEnvelope({
    v: 1,
    blocks: [
      { ...chart, id: 'c1' }, { ...chart, id: 'c2' }, { ...chart, id: 'c3' },
      { ...sandbox, id: 's1' }, { ...sandbox, id: 's2' },
      { id: 'm', type: 'metric', items: [{ label: 'a', value: 1 }] },
      { id: 'setimo', type: 'callout', body: 'fora da janela de 6' },
    ],
  })
  assert.deepEqual(out?.blocks.map((b) => b.id), ['c1', 'c2', 's1', 'm'])
})

test('inferencia de tipo dos blocos novos', () => {
  const out = parseUiEnvelope({
    v: 1,
    blocks: [
      { items: ['Primeira sugestão', 'Segunda sugestão'] },
      { items: [{ label: 'Receita', value: 10 }] },
      { kind: 'danger', body: 'Cuidado.' },
      { title: 'Só título' },
    ],
  })
  assert.deepEqual(out?.blocks.map((b) => b.type), ['metric', 'callout', 'card', 'follow_up'])
  assert.equal(parseUiEnvelope({ items: ['Uma sugestão válida'] })?.blocks[0]?.type, 'follow_up')
  assert.equal(
    parseUiEnvelope({
      columns: [{ key: 'a' }, { key: 'b' }],
      rows: [{ a: '1', b: '2' }],
    })?.blocks[0]?.type,
    'table'
  )
})

test('table: valida colunas tipadas, limites e ordenacao', () => {
  const envelope = {
    v: 1,
    blocks: [
      {
        id: 't1',
        type: 'table',
        title: 'Tabela Financeira',
        columns: [
          { key: 'produto', label: 'Produto', kind: 'text' },
          { key: 'valor', label: 'Valor', kind: 'number', unit: 'R$' },
          { key: 'data', label: 'Data', kind: 'date' },
        ],
        rows: [
          { produto: 'Nexus Pro', valor: 1500, data: '2026-10-14' },
          { produto: 'Nexus Lite', valor: 'invalido', data: 'data-errada' },
        ],
        sort: { key: 'valor', dir: 'desc' },
      },
    ],
  }
  const parsed = parseUiEnvelope(envelope)
  assert.notEqual(parsed, null)
  assert.equal(parsed?.blocks[0]?.type, 'table')
  if (parsed?.blocks[0]?.type === 'table') {
    assert.equal(parsed.blocks[0].columns.length, 3)
    assert.equal(parsed.blocks[0].columns[1].unit, 'R$')
    assert.equal(parsed.blocks[0].rows.length, 2)
    assert.equal(parsed.blocks[0].rows[0].valor, 1500)
    assert.equal(parsed.blocks[0].rows[0].data, '2026-10-14')
    // Célula inválida tratada como null (tolerância)
    assert.equal(parsed.blocks[0].rows[1].valor, null)
    assert.equal(parsed.blocks[0].rows[1].data, null)
    assert.deepEqual(parsed.blocks[0].sort, { key: 'valor', dir: 'desc' })
  }

  // Menos de 2 colunas válidas deve descartar
  assert.equal(
    parseUiEnvelope({
      v: 1,
      blocks: [
        {
          type: 'table',
          columns: [{ key: 'apenas_uma' }],
          rows: [{ apenas_uma: 'x' }],
        },
      ],
    }),
    null
  )
})

test('chart: pie agrupa excedente em Outros e suporta stacked, unit e labels', () => {
  const pieData = {
    v: 1,
    blocks: [
      {
        id: 'p1',
        type: 'chart',
        kind: 'pie',
        title: 'Participação',
        unit: '%',
        x_key: 'item',
        series: [{ key: 'share', label: 'Fatia' }, { key: 'descartada' }],
        rows: Array.from({ length: 10 }, (_, i) => ({
          item: `Item ${i + 1}`,
          share: 10,
        })),
      },
    ],
  }
  const parsedPie = parseUiEnvelope(pieData)
  assert.notEqual(parsedPie, null)
  if (parsedPie?.blocks[0]?.type === 'chart') {
    assert.equal(parsedPie.blocks[0].kind, 'pie')
    assert.equal(parsedPie.blocks[0].unit, '%')
    assert.equal(parsedPie.blocks[0].series.length, 1) // pie só tem 1 série
    assert.equal(parsedPie.blocks[0].rows.length, 8) // max 8 rows
    assert.equal(parsedPie.blocks[0].rows[7].item, 'Outros')
    assert.equal(parsedPie.blocks[0].rows[7].share, 30) // soma dos itens 8, 9, 10 (10+10+10)
  }

  const stackedData = {
    v: 1,
    blocks: [
      {
        id: 'c1',
        type: 'chart',
        kind: 'compare',
        title: 'Comparativo Empilhado',
        stacked: true,
        unit: 'kg',
        x_label: 'Meses',
        y_label: 'Peso',
        x_key: 'mes',
        series: [{ key: 'a' }, { key: 'b' }],
        rows: [{ mes: 'Jan', a: 10, b: 20 }],
      },
    ],
  }
  const parsedStacked = parseUiEnvelope(stackedData)
  assert.notEqual(parsedStacked, null)
  if (parsedStacked?.blocks[0]?.type === 'chart') {
    assert.equal(parsedStacked.blocks[0].stacked, true)
    assert.equal(parsedStacked.blocks[0].unit, 'kg')
    assert.equal(parsedStacked.blocks[0].x_label, 'Meses')
    assert.equal(parsedStacked.blocks[0].y_label, 'Peso')
  }
})

test('options: valida single, multiple, allow_other, limites e action com {choice}', () => {
  const raw = {
    v: 1,
    blocks: [
      {
        id: 'opt_1',
        type: 'options',
        question: 'Qual o destino da sua viagem?',
        mode: 'single',
        options: [
          { value: 'praia', label: 'Praia e Sol', description: 'Litoral' },
          { value: 'serra', label: 'Serra e Frio' },
          { value: 'campo', label: 'Campo e Natureza' },
        ],
        allow_other: true,
        action: { name: 'send_message', template: 'Destino escolhido: {choice}' },
      },
    ],
  }
  const parsed = parseUiEnvelope(raw)
  assert.notEqual(parsed, null)
  if (parsed?.blocks[0]?.type === 'options') {
    const b = parsed.blocks[0]
    assert.equal(b.question, 'Qual o destino da sua viagem?')
    assert.equal(b.mode, 'single')
    assert.equal(b.options.length, 3)
    assert.equal(b.options[0].value, 'praia')
    assert.equal(b.options[0].description, 'Litoral')
    assert.equal(b.allow_other, true)
    assert.equal(b.action.template, 'Destino escolhido: {choice}')
  }

  // Multiple e limite de 6 opções
  const manyOpts = {
    v: 1,
    blocks: [
      {
        type: 'options',
        question: 'Selecione suas preferências:',
        mode: 'multiple',
        options: Array.from({ length: 10 }, (_, i) => ({ value: `v_${i}`, label: `Opção ${i}` })),
        action: { name: 'send_message', template: 'Preferências: {choice}' },
      },
    ],
  }
  const parsedMany = parseUiEnvelope(manyOpts)
  assert.notEqual(parsedMany, null)
  if (parsedMany?.blocks[0]?.type === 'options') {
    assert.equal(parsedMany.blocks[0].mode, 'multiple')
    assert.equal(parsedMany.blocks[0].options.length, 6)
  }
})

test('options: rejeições estritas, auto-healing e inferência', () => {
  // Menos de 2 opções -> rejeita
  assert.equal(
    parseUiEnvelope({
      v: 1,
      blocks: [
        {
          type: 'options',
          question: 'Q?',
          options: [{ value: 'a', label: 'A' }],
          action: { name: 'send_message', template: '{choice}' },
        },
      ],
    }),
    null
  )

  // Sem {choice} no template -> rejeita
  assert.equal(
    parseUiEnvelope({
      v: 1,
      blocks: [
        {
          type: 'options',
          question: 'Q?',
          options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
          action: { name: 'send_message', template: 'Sem token' },
        },
      ],
    }),
    null
  )

  // Action inválida -> rejeita
  assert.equal(
    parseUiEnvelope({
      v: 1,
      blocks: [
        {
          type: 'options',
          question: 'Q?',
          options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
          action: { name: 'set_model', field: 'f' },
        },
      ],
    }),
    null
  )

  // Inferência automática e auto-healing de values
  const inferred = parseUiEnvelope({
    v: 1,
    blocks: [
      {
        question: 'Qual cor?',
        mode: 'desconhecido',
        options: [
          { label: 'Azul' },
          { value: 'vermelho', label: 'Vermelho' },
        ],
        action: { name: 'send_message', template: 'Cor: {choice}' },
      },
    ],
  })
  assert.notEqual(inferred, null)
  if (inferred?.blocks[0]?.type === 'options') {
    assert.equal(inferred.blocks[0].mode, 'single')
    assert.equal(inferred.blocks[0].options[0].value, 'opt_1')
    assert.equal(inferred.blocks[0].options[1].value, 'vermelho')
  }
})
