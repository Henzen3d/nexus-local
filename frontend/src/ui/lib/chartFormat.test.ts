import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  CHART_RAMP,
  PIE_RAMP,
  chartToCsv,
  distributeColors,
  formatNumber,
  looksNumeric,
  pieColors,
  seriesColors,
  tableToCsv,
  tickCountFor,
  truncateLabel,
  yAxisWidthFor,
  yDomainThroughZero,
} from './chartFormat.ts'

describe('distributeColors', () => {
  const ramp = ['a', 'b', 'c', 'd', 'e']

  it('1 série pega a cor do meio; 2 séries pegam vizinhas distintas', () => {
    assert.deepEqual(distributeColors(ramp, 1), ['c'])
    assert.deepEqual(distributeColors(ramp, 2), ['b', 'd'])
  })

  it('n séries saem do meio para fora e repetem a rampa quando faltam cores', () => {
    assert.deepEqual(distributeColors(ramp, 3), ['b', 'c', 'd'])
    assert.deepEqual(distributeColors(ramp, 5), ['a', 'b', 'c', 'd', 'e'])
    assert.equal(distributeColors(ramp, 7).length, 7)
    assert.deepEqual(distributeColors([], 3), [])
    assert.deepEqual(distributeColors(ramp, 0), [])
  })

  it('rampa de 2 cores não repete a mesma cor para 2 séries', () => {
    assert.deepEqual(distributeColors(['x', 'y'], 2), ['x', 'y'])
  })
})

describe('seriesColors', () => {
  it('primeira série é sempre --primary e as demais seguem a rampa', () => {
    assert.deepEqual(seriesColors(1), [CHART_RAMP[0]])
    assert.deepEqual(seriesColors(3), [CHART_RAMP[0], CHART_RAMP[1], CHART_RAMP[2]])
    assert.equal(seriesColors(8).length, 8)
    assert.deepEqual(seriesColors(0), [])
  })
})

describe('tickCountFor', () => {
  it('um tick a cada 40 px, mínimo 2', () => {
    assert.equal(tickCountFor(220), 5)
    assert.equal(tickCountFor(60), 2)
    assert.equal(tickCountFor(0), 2)
    assert.equal(tickCountFor(Number.NaN), 2)
  })
})

describe('yDomainThroughZero', () => {
  const rows = [
    { x: 'a', y: 10, z: -4 },
    { x: 'b', y: 25, z: 'não' },
    { x: 'c', y: -2, z: 7 },
  ]

  it('sem pilha: [min(0, menor), max(0, maior)]', () => {
    assert.deepEqual(yDomainThroughZero(rows, ['y']), [-2, 25])
    assert.deepEqual(yDomainThroughZero(rows, ['y', 'z']), [-4, 25])
    assert.deepEqual(yDomainThroughZero([{ x: 'a', y: 3 }], ['y']), [0, 3])
  })

  it('com pilha: soma positivos e negativos por linha, separadamente', () => {
    assert.deepEqual(yDomainThroughZero(rows, ['y', 'z'], true), [-4, 25])
    assert.deepEqual(yDomainThroughZero([{ y: 5, z: 6 }], ['y', 'z'], true), [0, 11])
  })
})

describe('formatNumber', () => {
  it('usa o locale e limita casas decimais', () => {
    assert.equal(formatNumber(1234.567, 'en-US'), '1,234.57')
    assert.equal(formatNumber(1234.5, 'pt-BR'), '1.234,5')
  })

  it('acima de 10 000 fica compacto; texto não numérico volta como veio', () => {
    assert.equal(formatNumber(1250000, 'en-US'), '1.3M')
    assert.equal(formatNumber(1250000, 'en-US', false), '1,250,000')
    assert.equal(formatNumber('abc', 'en-US'), 'abc')
    assert.equal(formatNumber(undefined, 'en-US'), '')
  })

  it('locale inválido não quebra', () => {
    assert.equal(typeof formatNumber(10, 'xx-INVALIDO-!!'), 'string')
  })
})

describe('truncateLabel / yAxisWidthFor / looksNumeric', () => {
  it('corta com reticências só quando passa do teto', () => {
    assert.equal(truncateLabel('Janeiro'), 'Janeiro')
    assert.equal(truncateLabel('Uma categoria muito longa', 10), 'Uma categ…')
    assert.equal(truncateLabel(undefined), '')
  })

  it('largura do eixo Y cresce com o rótulo e fica entre 32 e 72', () => {
    assert.equal(yAxisWidthFor([0, 5], 'en-US'), 32)
    assert.ok(yAxisWidthFor([0, 1234567890], 'en-US') <= 72)
    assert.ok(yAxisWidthFor([-1234.56, 9876.54], 'pt-BR') > 32)
  })

  it('reconhece valores numéricos de facts', () => {
    assert.equal(looksNumeric('42'), true)
    assert.equal(looksNumeric('R$ 1.200,50'), true)
    assert.equal(looksNumeric('42%'), true)
    assert.equal(looksNumeric('3,5 kg'), true)
    assert.equal(looksNumeric('Alta'), false)
    assert.equal(looksNumeric(''), false)
  })
})

describe('chartToCsv', () => {
  it('cabeçalho com rótulos e células escapadas', () => {
    const csv = chartToCsv(
      'mes',
      [{ key: 'v', label: 'Vendas, R$' }, { key: 'c' }],
      [
        { mes: 'Jan', v: 10, c: 2 },
        { mes: 'Fev "x"', v: 20 },
      ]
    )
    assert.equal(csv, 'mes,"Vendas, R$",c\nJan,10,2\n"Fev ""x""",20,')
  })
})

describe('pieColors', () => {
  it('retorna paleta coerente para fatias de pizza', () => {
    assert.deepEqual(pieColors(0), [])
    assert.deepEqual(pieColors(1), [PIE_RAMP[0]])
    assert.equal(pieColors(4).length, 4)
    assert.equal(pieColors(8).length, 8)
  })
})

describe('tableToCsv', () => {
  it('gera CSV com cabeçalhos de colunas e células escapadas', () => {
    const csv = tableToCsv(
      [
        { key: 'item', label: 'Item / Nome' },
        { key: 'qtd', label: 'Quantidade' },
        { key: 'preco', label: 'Preço, R$' },
      ],
      [
        { item: 'Produto "A"', qtd: 10, preco: 99.5 },
        { item: 'Produto B', qtd: null, preco: 15.0 },
      ]
    )
    assert.equal(
      csv,
      'Item / Nome,Quantidade,"Preço, R$"\n"Produto ""A""",10,99.5\nProduto B,,15'
    )
  })
})
