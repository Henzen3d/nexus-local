import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import Renderer, { act } from 'react-test-renderer'
import { TableCard } from '../../src/ui/components/TableCard'
import { ChartCard } from '../../src/ui/components/ChartCard'
import type { TableBlock, ChartBlock } from '../../src/types'

test('TableCard renders semantic table, handles sorting and expands rows', () => {
  const block: TableBlock = {
    id: 'tbl_1',
    type: 'table',
    title: 'Ranking de Vendas',
    columns: [
      { key: 'nome', label: 'Nome', kind: 'text' },
      { key: 'vendas', label: 'Vendas', kind: 'number', unit: 'un' },
      { key: 'data', label: 'Data', kind: 'date' },
    ],
    rows: Array.from({ length: 12 }, (_, i) => ({
      nome: `Vendedor ${String.fromCharCode(65 + i)}`,
      vendas: (i + 1) * 10,
      data: `2026-10-${String(i + 1).padStart(2, '0')}`,
    })),
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<TableCard block={block} />)
  })

  const root = view!.root
  const table = root.findByType('table')
  assert.ok(table)

  // Verifica que inicialmente apenas 10 linhas são exibidas (colapso)
  const tbody = root.findByType('tbody')
  const initialRows = tbody.findAllByType('tr')
  assert.equal(initialRows.length, 10)

  // Botão de expandir visível
  const toggleBtn = root.findByProps({ className: 'nexus-ui-table-toggle-btn' })
  assert.ok(toggleBtn)

  // Ao clicar no botão de expandir, todas as 12 linhas aparecem
  act(() => {
    toggleBtn.props.onClick()
  })
  const expandedRows = tbody.findAllByType('tr')
  assert.equal(expandedRows.length, 12)

  // Ao clicar para ordenar por vendas
  const headers = root.findAllByProps({ className: 'nexus-ui-table-header-btn' })
  const vendasHeader = headers[1]
  act(() => {
    vendasHeader.props.onClick()
  })

  // Alterna direção
  act(() => {
    vendasHeader.props.onClick()
  })

  act(() => {
    view!.unmount()
  })
})

test('ChartCard renders pie and stacked chart blocks with sr-only table', () => {
  const pieBlock: ChartBlock = {
    id: 'pie_1',
    type: 'chart',
    kind: 'pie',
    title: 'Distribuição de Recursos',
    unit: '%',
    x_key: 'item',
    series: [{ key: 'pct', label: 'Porcentagem' }],
    rows: [
      { item: 'CPU', pct: 40 },
      { item: 'Memória', pct: 35 },
      { item: 'Disco', pct: 25 },
    ],
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ChartCard block={pieBlock} />)
  })

  // Deve possuir tabela sr-only acessível
  const srTable = view!.root.findByProps({ className: 'nexus-ui-sr-only' })
  assert.ok(srTable)
  const rows = srTable.findByType('tbody').findAllByType('tr')
  assert.equal(rows.length, 3)

  act(() => {
    view!.unmount()
  })

  const stackedBlock: ChartBlock = {
    id: 'compare_1',
    type: 'chart',
    kind: 'compare',
    stacked: true,
    title: 'Comparativo Empilhado',
    x_key: 'mes',
    series: [
      { key: 'a', label: 'Série A' },
      { key: 'b', label: 'Série B' },
    ],
    rows: [
      { mes: 'Jan', a: 10, b: 20 },
      { mes: 'Fev', a: 15, b: 25 },
    ],
  }

  act(() => {
    view = Renderer.create(<ChartCard block={stackedBlock} />)
  })
  assert.ok(view!.root.findByProps({ className: 'nexus-ui-sr-only' }))

  act(() => {
    view!.unmount()
  })
})

test('ChartCard renders bar chart with title and accessible sr-only table containing model data', () => {
  const barBlock: ChartBlock = {
    id: 'costs_bar',
    type: 'chart',
    kind: 'bar',
    title: 'Custo por 1M tokens',
    x_key: 'modelo',
    series: [{ key: 'custo', label: 'Custo (US$)' }],
    rows: [
      { modelo: 'Groq 8B', custo: 0.05 },
      { modelo: 'GPT-4o mini', custo: 0.15 },
    ],
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ChartCard block={barBlock} />)
  })

  // Título renderizado
  const cardTitle = view!.root.findByProps({ className: 'nexus-ui-card__title' })
  assert.equal(cardTitle.children[0], 'Custo por 1M tokens')

  // Tabela acessível contém Groq 8B e 0.05
  const srTable = view!.root.findByProps({ className: 'nexus-ui-sr-only' })
  assert.ok(srTable)
  const rows = srTable.findByType('tbody').findAllByType('tr')
  assert.equal(rows.length, 2)
  const firstRowCells = rows[0].findAllByType('td')
  assert.equal(firstRowCells[0].children[0], 'Groq 8B')
  assert.ok(String(firstRowCells[1].children[0]).includes('0'))

  act(() => {
    view!.unmount()
  })
})
