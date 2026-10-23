import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'

test('useChat não zera isGeneratingRef ao receber tokens ou etapas de processo', () => {
  const source = readFileSync(
    new URL('../hooks/useChat.ts', import.meta.url),
    'utf8'
  )

  // Extrai o bloco de case 'token':
  const tokenCaseMatch = source.match(/case 'token':[\s\S]*?break/)
  assert.ok(tokenCaseMatch, 'case token deve existir em useChat.ts')
  const tokenCaseCode = tokenCaseMatch[0]

  // isGeneratingRef.current NÃO pode ser setado para false dentro de case 'token':
  // (isso causava o descarte imediato de todos os tokens subsequentes a partir do 2º token)
  assert.equal(
    tokenCaseCode.includes('isGeneratingRef.current = false'),
    false,
    'case token nunca deve setar isGeneratingRef.current = false'
  )
  assert.ok(
    tokenCaseCode.includes('s.appendToken(msg.content)'),
    'case token deve chamar appendToken'
  )

  // Extrai o bloco de case 'search_start':
  const searchCaseMatch = source.match(/case 'search_start':[\s\S]*?break/)
  assert.ok(searchCaseMatch, 'case search_start deve existir em useChat.ts')
  assert.equal(
    searchCaseMatch[0].includes('isGeneratingRef.current = false'),
    false,
    'case search_start nunca deve setar isGeneratingRef.current = false'
  )

  // Extrai o bloco de case 'process_step_start':
  const stepCaseMatch = source.match(/case 'process_step_start':[\s\S]*?break/)
  assert.ok(stepCaseMatch, 'case process_step_start deve existir em useChat.ts')
  assert.equal(
    stepCaseMatch[0].includes('isGeneratingRef.current = false'),
    false,
    'case process_step_start nunca deve setar isGeneratingRef.current = false'
  )

  // isGeneratingRef só deve ser finalizado em stream_end, error, onclose e stopStream
  const streamEndCaseMatch = source.match(/case 'stream_end':[\s\S]*?break/)
  assert.ok(streamEndCaseMatch, 'case stream_end deve existir')
  assert.ok(
    streamEndCaseMatch[0].includes('isGeneratingRef.current = false'),
    'case stream_end deve finalizar isGeneratingRef.current'
  )
})
