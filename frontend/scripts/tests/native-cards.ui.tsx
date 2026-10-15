import React from 'react'
import assert from 'node:assert/strict'
import { test } from 'node:test'
import Renderer, { act } from 'react-test-renderer'
import { controls, reset, useStore } from './uiStubs'
import { ProgressCard } from '../../src/ui/components/ProgressCard'
import { ChecklistCard } from '../../src/ui/components/ChecklistCard'
import { ImageCard } from '../../src/ui/components/ImageCard'
import { ControlsCard } from '../../src/ui/components/ControlsCard'
import { FollowUpCard } from '../../src/ui/components/FollowUpCard'
import { MetricCard } from '../../src/ui/components/MetricCard'
import { CalloutCard } from '../../src/ui/components/CalloutCard'
import type {
  ProgressBlock,
  CardBlock,
  ControlsBlock,
  FollowUpBlock,
  MetricBlock,
  CalloutBlock,
} from '../../src/types'

test('ProgressCard renders progressbar with value, max and fraction', () => {
  const block: ProgressBlock = {
    id: 'seo_progress',
    type: 'progress',
    label: 'Auditoria SEO',
    value: 7,
    max: 10,
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ProgressCard block={block} />)
  })

  const progressbar = view!.root.findByProps({ role: 'progressbar' })
  assert.ok(progressbar)
  assert.equal(progressbar.props['aria-valuenow'], 7)
  assert.equal(progressbar.props['aria-valuemax'], 10)
  assert.equal(progressbar.props['aria-label'], 'Auditoria SEO')

  // Verifica percentual 70%
  const metric = view!.root.findByProps({ className: 'nexus-ui-metric__value' })
  assert.equal(metric.children.join(''), '70%')

  act(() => {
    view!.unmount()
  })
})

test('ChecklistCard renders ordered list with steps, active step and summary', () => {
  const block: ProgressBlock = {
    id: 'steps_1',
    type: 'progress',
    label: 'Pipeline de Deploy',
    steps: [
      { id: 's1', label: 'Compilar frontend', state: 'done' },
      { id: 's2', label: 'Rodar testes', state: 'active' },
      { id: 's3', label: 'Publicar imagem', state: 'pending' },
    ],
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ChecklistCard block={block} />)
  })

  const list = view!.root.findByProps({ role: 'list' })
  assert.ok(list)

  const items = list.findAllByType('li')
  assert.equal(items.length, 3)

  // O passo ativo possui aria-current="step"
  const activeStep = items.find((it) => it.props['aria-current'] === 'step')
  assert.ok(activeStep)
  assert.equal(activeStep.props['data-state'], 'active')

  act(() => {
    view!.unmount()
  })
})

test('ImageCard renders title and facts, omitting img when image is absent', () => {
  const blockWithoutImg: CardBlock = {
    id: 'esp32_card',
    type: 'card',
    title: 'ESP32-S3',
    body: 'Microcontrolador dual-core com Wi-Fi e Bluetooth 5 (LE).',
    facts: [
      { label: 'Flash', value: '8 MB' },
      { label: 'SRAM', value: '512 KB' },
    ],
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ImageCard block={blockWithoutImg} />)
  })

  // Não deve conter tag img
  const imgs = view!.root.findAllByType('img')
  assert.equal(imgs.length, 0)

  // Título e fatos presentes
  const title = view!.root.findByProps({ className: 'nexus-ui-infocard__title' })
  assert.equal(title.children[0], 'ESP32-S3')

  const facts = view!.root.findAllByProps({ className: 'nexus-ui-fact' })
  assert.equal(facts.length, 2)

  act(() => {
    view!.unmount()
  })
})

test('FollowUpCard renders clickable suggestions and respects stream', () => {
  reset()
  const block: FollowUpBlock = {
    id: 'follow_1',
    type: 'follow_up',
    items: ['Comparar com 2025', 'Mostrar por região', 'Exportar como tabela'],
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<FollowUpCard block={block} />)
  })

  const buttons = view!.root.findAllByType('button')
  assert.equal(buttons.length, 3)

  // Ao clicar em uma sugestão, chama sendMessage
  act(() => {
    buttons[0].props.onClick()
  })
  assert.equal(controls.sent.length, 1)
  assert.equal(controls.sent[0][0], 'Comparar com 2025')

  act(() => {
    view!.unmount()
  })

  // No streaming, botões ficam desabilitados
  act(() => {
    view = Renderer.create(<FollowUpCard block={block} streaming={true} />)
  })
  const disabledButtons = view!.root.findAllByType('button')
  assert.equal(disabledButtons[0].props.disabled, true)

  act(() => {
    view!.unmount()
  })
})

test('MetricCard calculates tone from trend and good direction', () => {
  const block: MetricBlock = {
    id: 'kpis',
    type: 'metric',
    title: 'Métricas de Performance',
    items: [
      { label: 'Receita', value: 'R$ 48.200', trend: 'up', good: 'up' }, // good
      { label: 'Custos', value: 'R$ 12.000', trend: 'up', good: 'down' }, // bad
      { label: 'Churn', value: '1.2%', trend: 'down', good: 'down' }, // good
      { label: 'Uptime', value: '99.9%', trend: 'flat' }, // neutral
    ],
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<MetricCard block={block} />)
  })

  const tiles = view!.root.findAllByProps({ className: 'nexus-ui-kpi' })
  assert.equal(tiles.length, 4)

  assert.equal(tiles[0].props['data-tone'], 'good')
  assert.equal(tiles[1].props['data-tone'], 'bad')
  assert.equal(tiles[2].props['data-tone'], 'good')
  assert.equal(tiles[3].props['data-tone'], 'neutral')

  act(() => {
    view!.unmount()
  })
})

test('CalloutCard renders with kind, role note and content', () => {
  const block: CalloutBlock = {
    id: 'aviso_1',
    type: 'callout',
    kind: 'warning',
    title: 'Atenção',
    body: 'A taxa Selic usada é a de outubro de 2026.',
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<CalloutCard block={block} />)
  })

  const callout = view!.root.findByProps({ role: 'note' })
  assert.ok(callout)
  assert.equal(callout.props['data-kind'], 'warning')

  const title = view!.root.findByProps({ className: 'nexus-ui-callout__title' })
  assert.ok(title)

  const body = view!.root.findByProps({ className: 'nexus-ui-callout__body' })
  assert.equal(body.children[0], 'A taxa Selic usada é a de outubro de 2026.')

  act(() => {
    view!.unmount()
  })
})

test('ControlsCard renders fields and handles form submit', () => {
  reset()
  const block: ControlsBlock = {
    id: 'calc_ctrl',
    type: 'controls',
    title: 'Simulação',
    submit_label: 'Calcular Projeção',
    fields: [
      { id: 'meses', label: 'Prazo (meses)', kind: 'range', min: 1, max: 24, default: 12 },
      { id: 'aporte', label: 'Aporte Mensal', kind: 'number', min: 100, max: 10000, default: 500 },
    ],
    action: {
      name: 'send_message',
      template: 'Calcular investimento de {aporte} por {meses} meses',
    },
  }

  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ControlsCard block={block} />)
  })

  const form = view!.root.findByType('form')
  assert.ok(form)

  // Submissão do formulário chama sendMessage interpolado
  act(() => {
    form.props.onSubmit({ preventDefault: () => {} })
  })

  assert.equal(controls.sent.length, 1)
  assert.equal(controls.sent[0][0], 'Calcular investimento de 500 por 12 meses')

  act(() => {
    view!.unmount()
  })
})

test('ControlsCard set_model hides when models empty and changes model when available', () => {
  reset()
  const block: ControlsBlock = {
    id: 'ctrl_model',
    type: 'controls',
    title: 'Trocar Modelo',
    submit_label: 'Confirmar Modelo',
    fields: [
      {
        id: 'target_model',
        label: 'Modelo',
        kind: 'select',
        options: [{ value: 'gpt-fake', label: 'Fake' }],
      },
    ],
    action: {
      name: 'set_model',
      field: 'target_model',
    },
  }

  // 1. Quando models está vazio no store, ControlsCard retorna null
  let view: Renderer.ReactTestRenderer
  act(() => {
    view = Renderer.create(<ControlsCard block={block} />)
  })
  assert.equal(view!.toJSON(), null)
  act(() => {
    view!.unmount()
  })

  // 2. Quando models possui opções reais no store, popula o select a partir do store
  useStore.setState({
    models: [
      { id: 'gpt-4o', provider_id: 'openai', name: 'GPT-4o' },
      { id: 'claude-3-5-sonnet', provider_id: 'anthropic', name: 'Claude 3.5 Sonnet' },
    ],
    selectedModelId: 'gpt-4o',
    selectedProviderId: 'openai',
  })

  act(() => {
    view = Renderer.create(<ControlsCard block={block} />)
  })

  const form = view!.root.findByType('form')
  assert.ok(form)

  const select = view!.root.findByType('select')
  const options = select.findAllByType('option')
  // As options do JSON ('gpt-fake') foram ignoradas; as do store foram renderizadas
  assert.equal(options.length, 2)
  assert.equal(options[0].props.value, 'openai::gpt-4o')
  assert.equal(options[1].props.value, 'anthropic::claude-3-5-sonnet')

  // Ao submeter com o modelo selecionado
  act(() => {
    form.props.onSubmit({ preventDefault: () => {} })
  })

  assert.equal(controls.selectedModels.length, 1)
  assert.deepEqual(controls.selectedModels[0], ['gpt-4o', 'openai'])

  act(() => {
    view!.unmount()
  })
})
