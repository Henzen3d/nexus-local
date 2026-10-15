import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import Renderer, { act } from 'react-test-renderer'
import { ControlsCard } from '../../src/ui/components/ControlsCard'
import { MetricCard } from '../../src/ui/components/MetricCard'
import { ProgressCard } from '../../src/ui/components/ProgressCard'
import { TableCard } from '../../src/ui/components/TableCard'
import { useMessageUiStore } from '../../src/ui/state/messageUiState'
import { controls, reset } from './uiStubs'
import type { ControlsBlock, MetricBlock, ProgressBlock, TableBlock } from '../../src/types'

test('Shared state and reactive expressions between ControlsCard, MetricCard, ProgressCard and TableCard', () => {
  reset()
  const msgId = 'msg_test_reactive'
  useMessageUiStore.getState().clearMessage(msgId)

  const controlsBlock: ControlsBlock = {
    id: 'ctrl_1',
    type: 'controls',
    title: 'Simulador Financeiro',
    submit_label: 'Aplicar',
    fields: [
      { id: 'f_slider', label: 'Investimento', kind: 'range', default: 20, min: 0, max: 100, step: 1 },
      { id: 'f_taxa', label: 'Taxa Fixa', kind: 'number', default: 5, min: 0, max: 50 },
    ],
    computed: [
      { id: 'c_total', template: 'Total: {c_total}', formula: '{f_slider} * 2 + {f_taxa}' },
    ],
    action: { name: 'send_message', template: 'Investindo {f_slider} gera {c_total}' },
  }

  const metricBlock: MetricBlock = {
    id: 'met_1',
    type: 'metric',
    title: 'Indicadores',
    items: [
      { label: 'Total', value: '={c_total}', unit: 'k' },
    ],
  }

  const progressBlock: ProgressBlock = {
    id: 'prog_1',
    type: 'progress',
    label: 'Meta',
    value: '={f_slider}',
    max: 100,
  }

  const tableBlock: TableBlock = {
    id: 'tbl_1',
    type: 'table',
    title: 'Previsão',
    columns: [
      { key: 'ano', label: 'Ano', kind: 'text' },
      { key: 'projecao', label: 'Projeção', kind: 'number' },
    ],
    rows: [
      { ano: '2026', projecao: '={f_slider} * 3' },
    ],
  }

  let ctrlView: Renderer.ReactTestRenderer
  let metView: Renderer.ReactTestRenderer
  let progView: Renderer.ReactTestRenderer
  let tblView: Renderer.ReactTestRenderer

  act(() => {
    ctrlView = Renderer.create(<ControlsCard block={controlsBlock} messageId={msgId} />)
    metView = Renderer.create(<MetricCard block={metricBlock} messageId={msgId} />)
    progView = Renderer.create(<ProgressCard block={progressBlock} messageId={msgId} />)
    tblView = Renderer.create(<TableCard block={tableBlock} messageId={msgId} />)
  })

  // Estado inicial publicado pelo ControlsCard: f_slider=20, f_taxa=5, c_total = 20*2 + 5 = 45
  const storeState = useMessageUiStore.getState().states[msgId]
  assert.ok(storeState)
  assert.equal(storeState.f_slider, 20)
  assert.equal(storeState.f_taxa, 5)
  assert.equal(storeState.c_total, 45)

  // MetricCard inicial deve exibir 45
  let metricVal = metView!.root.findByProps({ className: 'nexus-ui-kpi__value' })
  assert.ok(metricVal.props.children.includes('45'))

  // ProgressCard inicial deve ter aria-valuenow=20
  let progressBar = progView!.root.findByProps({ role: 'progressbar' })
  assert.equal(progressBar.props['aria-valuenow'], 20)

  // TableCard inicial com célula computada = 20 * 3 = 60
  let tableNum = tblView!.root.findByProps({ className: 'nexus-ui-table__num' })
  assert.equal(tableNum.props.children, '60')

  // Altera slider para 40 via input slider do ControlsCard
  const sliderInput = ctrlView!.root.findByProps({ type: 'range' })
  act(() => {
    sliderInput.props.onChange({ target: { value: '40' } })
  })

  // Estado atualizado: f_slider=40, c_total = 40*2 + 5 = 85
  const updatedState = useMessageUiStore.getState().states[msgId]
  assert.equal(updatedState.f_slider, 40)
  assert.equal(updatedState.c_total, 85)

  // Re-renderização reativa dos componentes conectados
  metricVal = metView!.root.findByProps({ className: 'nexus-ui-kpi__value' })
  assert.ok(metricVal.props.children.includes('85'))

  progressBar = progView!.root.findByProps({ role: 'progressbar' })
  assert.equal(progressBar.props['aria-valuenow'], 40)

  tableNum = tblView!.root.findByProps({ className: 'nexus-ui-table__num' })
  assert.equal(tableNum.props.children, '120')

  // Submissão do ControlsCard com campos e computeds interpolados
  const form = ctrlView!.root.findByType('form')
  act(() => {
    form.props.onSubmit({ preventDefault: () => {} })
  })

  assert.equal(controls.sent.length, 1)
  assert.deepEqual(controls.sent[0], ['Investindo 40 gera 85'])

  act(() => {
    ctrlView!.unmount()
    metView!.unmount()
    progView!.unmount()
    tblView!.unmount()
  })
})
