import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

test('ArtifactPanel possui fullscreen, escape handler e restauração de foco', () => {
  const panelSource = readFileSync(
    new URL('../components/ArtifactPanel.tsx', import.meta.url),
    'utf8'
  )

  // Suporte a tela cheia (Maximize2 / Minimize2)
  assert.ok(panelSource.includes('Maximize2'))
  assert.ok(panelSource.includes('Minimize2'))
  assert.ok(panelSource.includes('isFullscreen'))
  assert.ok(panelSource.includes('setIsFullscreen'))
  assert.ok(panelSource.includes('artifact-panel--fullscreen'))

  // Restauração de foco ao fechar
  assert.ok(panelSource.includes('lastFocusedElementRef'))
  assert.ok(panelSource.includes('lastFocusedElementRef.current.focus()'))

  // Tecla Escape fecha primeiro fullscreen ou o painel
  assert.ok(panelSource.includes("e.key === 'Escape'"))
  assert.ok(panelSource.includes('setIsFullscreen(false)'))
})

test('index.css contém regras de tela cheia para ArtifactPanel e animação em Intelligent UI cards', () => {
  const css = readFileSync(
    new URL('../index.css', import.meta.url),
    'utf8'
  )

  // Fullscreen overlay do ArtifactPanel
  assert.ok(css.includes('.artifact-panel.artifact-panel--fullscreen'))
  assert.ok(css.includes('z-index: 1000;'))

  // Animação de entrada e prefers-reduced-motion em Intelligent UI
  assert.ok(css.includes('nexusUiCardIn'))
  assert.ok(css.includes('@keyframes nexusUiCardIn'))
  assert.ok(css.includes('.nexus-ui-card {') && css.includes('animation: nexusUiCardIn'))
  assert.ok(css.includes('@media (prefers-reduced-motion: reduce)'))
})

test('FollowUpCard e OptionsCard possuem proteção ativa contra duplo-clique', () => {
  const followUpSource = readFileSync(
    new URL('../ui/components/FollowUpCard.tsx', import.meta.url),
    'utf8'
  )
  assert.ok(followUpSource.includes('pendingText'))
  assert.ok(followUpSource.includes('Boolean(pendingText)'))

  const optionsSource = readFileSync(
    new URL('../ui/components/OptionsCard.tsx', import.meta.url),
    'utf8'
  )
  assert.ok(optionsSource.includes('setSubmitted(true)'))
})
