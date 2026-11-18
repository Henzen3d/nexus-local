import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { decodeChatFrame, isStreamEndFailure, isStreamEndSuccess } from './chatProtocol.ts'
import { StreamDraftBuffer } from './streamDraftBuffer.ts'

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

test('Os 4 encerramentos permitidos centralizam descarte do rascunho e finalizam o turno', () => {
  const source = readFileSync(
    new URL('../hooks/useChat.ts', import.meta.url),
    'utf8'
  )

  // 1. stream_end
  const streamEndMatch = source.match(/case 'stream_end':[\s\S]*?break/)
  assert.ok(streamEndMatch)
  assert.ok(streamEndMatch[0].includes('isGeneratingRef.current = false'))
  assert.ok(streamEndMatch[0].includes('isStreamEndSuccess(msg)'))
  assert.ok(streamEndMatch[0].includes('s.discardStreamDraft()'))

  // 2. error
  const errorMatch = source.match(/case 'error':[\s\S]*?break/)
  assert.ok(errorMatch)
  assert.ok(errorMatch[0].includes('isGeneratingRef.current = false'))
  assert.ok(errorMatch[0].includes('s.discardStreamDraft()'), 'error fatal deve usar ação centralizada discardStreamDraft')

  // 3. onclose (cobre queda antes ou depois de stream_start)
  const oncloseMatch = source.match(/ws\.onclose = \([\s\S]*?clearHeartbeat\(\)[\s\S]*?isGeneratingRef\.current = false[\s\S]*?st\.discardStreamDraft\(\)/)
  assert.ok(oncloseMatch, 'onclose do WebSocket deve descartar rascunho e destravar isGeneratingRef')

  // 4. stopStream
  const stopStreamMatch = source.match(/const stopStream = useCallback\(\(\) => {[\s\S]*?isGeneratingRef\.current = false[\s\S]*?flushStreamDraft\(\)/)
  assert.ok(stopStreamMatch, 'stopStream explícito deve dar flush síncrono e encerrar isGeneratingRef')
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

test('T2.4: decodeChatFrame valida todas as fixtures canônicas compartilhadas com Python', () => {
  const fixtureRaw = readFileSync(
    new URL('../../../backend/tests/fixtures/chat_ws_contract.json', import.meta.url),
    'utf8'
  )
  const fixture = JSON.parse(fixtureRaw) as {
    valid_frames: Array<{ name: string; payload: Record<string, unknown>; expect_kind: string }>
    invalid_raw_frames: string[]
    incomplete_success_frame: Record<string, unknown>
  }

  for (const entry of fixture.valid_frames) {
    const decoded = decodeChatFrame(JSON.stringify(entry.payload))
    assert.ok(decoded, `fixture válida deveria decodificar: ${entry.name}`)
    if (entry.expect_kind === 'stream_end_success') {
      assert.equal(isStreamEndSuccess(decoded), true, `esperado stream_end_success em ${entry.name}`)
      assert.equal(isStreamEndFailure(decoded), false)
    } else if (entry.expect_kind === 'stream_end_failure') {
      assert.equal(isStreamEndFailure(decoded), true, `esperado stream_end_failure em ${entry.name}`)
      assert.equal(isStreamEndSuccess(decoded), false)
    } else if (entry.expect_kind === 'proactive') {
      assert.ok(decoded.type.startsWith('proactive_'))
    } else {
      assert.equal(decoded.type, entry.expect_kind)
    }
  }

  for (const badRaw of fixture.invalid_raw_frames) {
    assert.equal(decodeChatFrame(badRaw), null, `frame inválido deveria retornar null: ${badRaw}`)
  }

  // Frame stream_end de sucesso SEM message_id nunca pode criar bolha de sucesso
  const incompleteDecoded = decodeChatFrame(JSON.stringify(fixture.incomplete_success_frame))
  assert.ok(incompleteDecoded)
  assert.equal(isStreamEndSuccess(incompleteDecoded), false)
  assert.equal(isStreamEndFailure(incompleteDecoded), true)
})

test('T2.3: StreamDraftBuffer isola turnos, impede commit de frame antigo após reset/clear e suporta aba oculta', () => {
  const commits: Array<{ text: string; turnId: string | null }> = []
  let nextFrameId = 1
  const scheduledFrames = new Map<number, () => void>()
  let hidden = false

  const buf = new StreamDraftBuffer({
    onCommit: (text, turnId) => commits.push({ text, turnId }),
    flushThresholdChars: 20,
    maxBufferChars: 40,
    hiddenFlushMs: 10,
    scheduler: {
      requestFrame: (cb) => {
        const id = nextFrameId++
        scheduledFrames.set(id, cb)
        return id
      },
      cancelFrame: (id) => {
        scheduledFrames.delete(id)
      },
      isHidden: () => hidden,
    },
  })

  // 1. Token antes do frame + flush síncrono no final/Parar não perde cauda
  buf.bindTurn('turn-A')
  buf.append('Olá ', 'turn-A')
  buf.append('mundo', 'turn-A')
  assert.equal(commits.length, 0)
  buf.flushSync()
  assert.deepEqual(commits, [{ text: 'Olá mundo', turnId: 'turn-A' }])

  // 2. Token de turno antigo é ignorado quando turno novo já está ativo
  commits.length = 0
  buf.bindTurn('turn-B')
  const acceptedStale = buf.append('token-velho', 'turn-A')
  assert.equal(acceptedStale, false)
  buf.append('token-novo', 'turn-B')
  buf.flushSync()
  assert.deepEqual(commits, [{ text: 'token-novo', turnId: 'turn-B' }])

  // 3. Reset/clear/logout cancela frame pendente e impede commit mesmo se callback RAF disparar atrasado
  commits.length = 0
  buf.bindTurn('turn-C')
  buf.append('parcial', 'turn-C')
  const capturedCallbacks = [...scheduledFrames.values()]
  buf.discard()
  for (const cb of capturedCallbacks) cb()
  assert.equal(commits.length, 0, 'callback de frame antigo nunca pode commitar após discard')

  // 4. Aba oculta + limite de memória descarrega automaticamente sem perder dados
  commits.length = 0
  hidden = true
  buf.bindTurn('turn-D')
  buf.append('1234567890123456789012345', 'turn-D') // >= flushThresholdChars (20) -> flush imediato
  assert.deepEqual(commits, [{ text: '1234567890123456789012345', turnId: 'turn-D' }])
})
