import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

test('useChat handlers intermediários nunca encerram o turno (isGeneratingRef permanece true)', () => {
  const source = readFileSync(
    new URL('../hooks/useChat.ts', import.meta.url),
    'utf8'
  )

  const intermediateCases = [
    'stream_start',
    'stream_clear',
    'token',
    'ui_progress',
    'search_start',
    'process_step_start',
    'process_step_update',
    'process_step_end',
    'auto_route_decision',
    'failover_notice',
    'fusion_start',
    'fusion_phase',
    'fusion_status',
    'fusion_judge_start',
    'fusion_grounding',
    'fusion_refined_prompt',
  ]

  for (const caseName of intermediateCases) {
    const regex = new RegExp(`case '${caseName}':[\\s\\S]*?break`)
    const match = source.match(regex)
    assert.ok(match, `case '${caseName}' deve existir no switch de mensagens`)
    assert.equal(
      match[0].includes('isGeneratingRef.current = false'),
      false,
      `case '${caseName}' é intermediário e NUNCA pode setar isGeneratingRef.current = false`
    )
  }
})

test('Os 4 encerramentos permitidos finalizam o ciclo de vida do turno', () => {
  const source = readFileSync(
    new URL('../hooks/useChat.ts', import.meta.url),
    'utf8'
  )

  // 1. stream_end
  const streamEndMatch = source.match(/case 'stream_end':[\s\S]*?break/)
  assert.ok(streamEndMatch)
  assert.ok(streamEndMatch[0].includes('isGeneratingRef.current = false'))

  // 2. error
  const errorMatch = source.match(/case 'error':[\s\S]*?break/)
  assert.ok(errorMatch)
  assert.ok(errorMatch[0].includes('isGeneratingRef.current = false'))
  assert.ok(errorMatch[0].includes('s.clearStreamDraft()'), 'error fatal deve limpar o rascunho de stream')

  // 3. onclose
  const oncloseMatch = source.match(/ws\.onclose = \([\s\S]*?clearHeartbeat\(\)[\s\S]*?isGeneratingRef\.current = false/)
  assert.ok(oncloseMatch, 'onclose do WebSocket deve setar isGeneratingRef.current = false')

  // 4. stopStream
  const stopStreamMatch = source.match(/const stopStream = useCallback\(\(\) => {[\s\S]*?isGeneratingRef\.current = false/)
  assert.ok(stopStreamMatch, 'stopStream explícito deve setar isGeneratingRef.current = false')
})

test('clearStreamDraft zera streamingContent e streamingUiBlocks sem criar mensagem prematura', () => {
  const storeSource = readFileSync(
    new URL('../store/useStore.ts', import.meta.url),
    'utf8'
  )

  const clearMatch = storeSource.match(/clearStreamDraft:\s*\(\)\s*=>\s*\{[\s\S]*?\}/)
  assert.ok(clearMatch, 'clearStreamDraft deve ser declarado na store')
  assert.ok(clearMatch[0].includes("streamingContent: ''"), 'deve zerar streamingContent')
  assert.ok(clearMatch[0].includes('streamingUiBlocks: null'), 'deve zerar streamingUiBlocks')
  assert.equal(clearMatch[0].includes('finalizeStream'), false, 'não pode finalizar a mensagem prematuramente no clear')

  const chatSource = readFileSync(
    new URL('../hooks/useChat.ts', import.meta.url),
    'utf8'
  )
  const streamClearCase = chatSource.match(/case 'stream_clear':[\s\S]*?break/)
  assert.ok(streamClearCase, "case 'stream_clear' deve existir")
  assert.ok(streamClearCase[0].includes('s.clearStreamDraft()'), 'deve chamar clearStreamDraft ao receber stream_clear')
  assert.equal(streamClearCase[0].includes('isGeneratingRef.current = false'), false, 'stream_clear não pode encerrar o turno')
})

test('Smart Scroll Anchor e botão flutuante em ChatWindow', () => {
  const chatSource = readFileSync(
    new URL('../components/ChatWindow.tsx', import.meta.url),
    'utf8'
  )

  // ChatWindow não assina streamingContent diretamente
  assert.equal(chatSource.includes('streamingContent'), false)

  // Botão flutuante existe e usa a chave i18n correta
  assert.ok(chatSource.includes('scroll-to-bottom-btn'))
  assert.ok(chatSource.includes('scrollToBottom'))
  assert.ok(chatSource.includes("t('chat.scrollToBottom'"))
  assert.ok(chatSource.includes('ChevronDown'))
  assert.ok(chatSource.includes('handleScroll'))
  assert.ok(chatSource.includes('onScroll={handleScroll}'))
})
