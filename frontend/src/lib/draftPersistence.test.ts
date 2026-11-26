import assert from 'node:assert/strict'
import test from 'node:test'
import {
  clearAllUserDrafts,
  clearComposerDraft,
  loadComposerDraft,
  loadPendingTurn,
  reconcilePendingTurnWithServer,
  saveComposerDraft,
  savePendingTurn,
  type PendingTurnSnapshot,
  type StorageLike,
} from './draftPersistence.ts'
import type { ChatRequest } from '../types.ts'

function createMemoryStorage(): StorageLike {
  const map = new Map<string, string>()
  return {
    get length() {
      return map.size
    },
    key(index: number) {
      return Array.from(map.keys())[index] ?? null
    },
    getItem(k: string) {
      return map.has(k) ? map.get(k)! : null
    },
    setItem(k: string, v: string) {
      map.set(k, v)
    },
    removeItem(k: string) {
      map.delete(k)
    },
  }
}

function makeReq(overrides: Partial<ChatRequest> = {}): ChatRequest {
  return {
    request_id: 'turn-req-123',
    conversation_id: 'conv-1',
    message: 'Resuma os contratos',
    model_id: 'auto',
    provider_id: 'auto',
    fusion: false,
    web_search: false,
    use_memory: true,
    project_context_debug: false,
    client_timezone_offset: 180,
    ...overrides,
  }
}

test('rascunhos são isolados por (userId, conversationId, projectId) e limpos no logout', () => {
  const st = createMemoryStorage()
  saveComposerDraft('u1', 'conv-a', 'proj-1', { text: 'Texto no projeto 1', attachments: [] }, st)
  saveComposerDraft('u1', 'conv-b', 'proj-2', { text: 'Texto no projeto 2', attachments: [] }, st)
  saveComposerDraft('u2', 'conv-a', 'proj-1', { text: 'Outro usuario', attachments: [] }, st)

  assert.equal(loadComposerDraft('u1', 'conv-a', 'proj-1', st)?.text, 'Texto no projeto 1')
  assert.equal(loadComposerDraft('u1', 'conv-b', 'proj-2', st)?.text, 'Texto no projeto 2')
  assert.equal(loadComposerDraft('u1', null, null, st), null)

  clearComposerDraft('u1', 'conv-a', 'proj-1', st)
  assert.equal(loadComposerDraft('u1', 'conv-a', 'proj-1', st), null)
  assert.equal(loadComposerDraft('u1', 'conv-b', 'proj-2', st)?.text, 'Texto no projeto 2')

  clearAllUserDrafts('u1', st)
  assert.equal(loadComposerDraft('u1', 'conv-b', 'proj-2', st), null)
  // Outro usuário na mesma máquina permanece intacto
  assert.equal(loadComposerDraft('u2', 'conv-a', 'proj-1', st)?.text, 'Outro usuario')
})

test('reconcilePendingTurnWithServer recarrega quando turno concluiu no servidor e preserva parcial quando interrompido', () => {
  const st = createMemoryStorage()
  const snap: PendingTurnSnapshot = {
    request: makeReq({ conversation_id: null }),
    conversationId: 'conv-created',
    projectId: null,
    status: 'streaming',
    partialContent: 'Inicio local',
    updatedAt: Date.now(),
  }
  savePendingTurn('u1', snap, st)
  assert.equal(loadPendingTurn('u1', st)?.request.request_id, 'turn-req-123')

  const completed = reconcilePendingTurnWithServer(snap, {
    found: true,
    request_id: 'turn-req-123',
    status: 'completed',
    conversation_id: 'conv-created',
    partial_content: 'Resposta completa no servidor',
  })
  assert.equal(completed.action, 'completed_reload')
  assert.equal(completed.conversationId, 'conv-created')

  const incomplete = reconcilePendingTurnWithServer(snap, {
    found: true,
    request_id: 'turn-req-123',
    status: 'incomplete',
    conversation_id: 'conv-created',
    partial_content: 'Inicio local + trecho salvo no banco',
  })
  assert.equal(incomplete.action, 'show_incomplete')
  assert.equal(incomplete.status, 'incomplete')
  assert.equal(incomplete.partialContent, 'Inicio local + trecho salvo no banco')

  const stopped = reconcilePendingTurnWithServer(snap, {
    found: true,
    request_id: 'turn-req-123',
    status: 'stopped',
    conversation_id: 'conv-created',
    partial_content: '',
  })
  assert.equal(stopped.action, 'show_incomplete')
  assert.equal(stopped.status, 'stopped')
  assert.equal(stopped.partialContent, 'Inicio local')

  clearAllUserDrafts('u1', st)
  assert.equal(loadPendingTurn('u1', st), null)
})
