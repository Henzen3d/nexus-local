import type { Attachment, ChatRequest, TurnStatusResponse } from '../types'

export interface ComposerDraft {
  text: string
  attachments: Attachment[]
  updatedAt: number
}

export interface PendingTurnSnapshot {
  request: ChatRequest
  userDisplayText?: string
  attachments?: Attachment[]
  conversationId: string | null
  projectId: string | null
  userMessageId?: string | null
  status: 'sending' | 'streaming' | 'stopped' | 'incomplete' | 'failed'
  partialContent: string
  errorMessage?: string | null
  updatedAt: number
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
  key?(index: number): string | null
  readonly length?: number
}

const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

function getDefaultStorage(): StorageLike | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function draftStorageKey(
  userId: string,
  conversationId: string | null | undefined,
  projectId: string | null | undefined,
): string {
  const convSeg = conversationId && conversationId.trim() ? conversationId.trim() : 'new'
  const projSeg = projectId && projectId.trim() ? projectId.trim() : 'none'
  return `nexuslocal_draft_${userId}_${convSeg}_${projSeg}`
}

export function pendingTurnStorageKey(userId: string): string {
  return `nexuslocal_pending_turn_${userId}`
}

export function saveComposerDraft(
  userId: string | null | undefined,
  conversationId: string | null | undefined,
  projectId: string | null | undefined,
  draft: { text: string; attachments: Attachment[]; updatedAt?: number },
  storage: StorageLike | null = getDefaultStorage(),
): void {
  if (!storage || !userId) return
  const key = draftStorageKey(userId, conversationId, projectId)
  const hasContent = Boolean(draft.text && draft.text.length > 0) || (draft.attachments?.length ?? 0) > 0
  try {
    if (!hasContent) {
      storage.removeItem(key)
      return
    }
    const payload: ComposerDraft = {
      text: draft.text,
      attachments: draft.attachments || [],
      updatedAt: draft.updatedAt ?? Date.now(),
    }
    storage.setItem(key, JSON.stringify(payload))
  } catch {
    /* ignore storage quota errors */
  }
}

export function loadComposerDraft(
  userId: string | null | undefined,
  conversationId: string | null | undefined,
  projectId: string | null | undefined,
  storage: StorageLike | null = getDefaultStorage(),
  now: number = Date.now(),
): ComposerDraft | null {
  if (!storage || !userId) return null
  const key = draftStorageKey(userId, conversationId, projectId)
  try {
    const raw = storage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ComposerDraft>
    if (!parsed || typeof parsed !== 'object') return null
    if (typeof parsed.updatedAt === 'number' && now - parsed.updatedAt > DRAFT_MAX_AGE_MS) {
      storage.removeItem(key)
      return null
    }
    const text = typeof parsed.text === 'string' ? parsed.text : ''
    const attachments = Array.isArray(parsed.attachments) ? parsed.attachments : []
    if (!text && attachments.length === 0) return null
    return {
      text,
      attachments,
      updatedAt: typeof parsed.updatedAt === 'number' ? parsed.updatedAt : now,
    }
  } catch {
    return null
  }
}

export function clearComposerDraft(
  userId: string | null | undefined,
  conversationId: string | null | undefined,
  projectId: string | null | undefined,
  storage: StorageLike | null = getDefaultStorage(),
): void {
  if (!storage || !userId) return
  try {
    storage.removeItem(draftStorageKey(userId, conversationId, projectId))
  } catch {
    /* ignore */
  }
}

export function savePendingTurn(
  userId: string | null | undefined,
  snapshot: PendingTurnSnapshot | null,
  storage: StorageLike | null = getDefaultStorage(),
): void {
  if (!storage || !userId) return
  const key = pendingTurnStorageKey(userId)
  try {
    if (!snapshot) {
      storage.removeItem(key)
      return
    }
    storage.setItem(key, JSON.stringify(snapshot))
  } catch {
    /* ignore */
  }
}

export function loadPendingTurn(
  userId: string | null | undefined,
  storage: StorageLike | null = getDefaultStorage(),
  now: number = Date.now(),
): PendingTurnSnapshot | null {
  if (!storage || !userId) return null
  const key = pendingTurnStorageKey(userId)
  try {
    const raw = storage.getItem(key)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<PendingTurnSnapshot>
    if (!parsed || typeof parsed !== 'object' || !parsed.request || !parsed.request.request_id) {
      return null
    }
    if (typeof parsed.updatedAt === 'number' && now - parsed.updatedAt > DRAFT_MAX_AGE_MS) {
      storage.removeItem(key)
      return null
    }
    return {
      request: parsed.request,
      userDisplayText: parsed.userDisplayText,
      attachments: Array.isArray(parsed.attachments) ? parsed.attachments : undefined,
      conversationId: parsed.conversationId ?? parsed.request.conversation_id ?? null,
      projectId: parsed.projectId ?? parsed.request.project_id ?? null,
      userMessageId: parsed.userMessageId ?? null,
      status: parsed.status || 'incomplete',
      partialContent: typeof parsed.partialContent === 'string' ? parsed.partialContent : '',
      errorMessage: typeof parsed.errorMessage === 'string' ? parsed.errorMessage : null,
      updatedAt: typeof parsed.updatedAt === 'number' ? parsed.updatedAt : now,
    }
  } catch {
    return null
  }
}

export function clearPendingTurn(
  userId: string | null | undefined,
  expectedRequestId?: string,
  storage: StorageLike | null = getDefaultStorage(),
): void {
  if (!storage || !userId) return
  const key = pendingTurnStorageKey(userId)
  try {
    if (expectedRequestId) {
      const existing = loadPendingTurn(userId, storage)
      if (existing && existing.request.request_id !== expectedRequestId) return
    }
    storage.removeItem(key)
  } catch {
    /* ignore */
  }
}

export function clearAllUserDrafts(
  userId: string | null | undefined,
  storage: StorageLike | null = getDefaultStorage(),
): void {
  if (!storage || !userId) return
  const draftPrefix = `nexuslocal_draft_${userId}_`
  const pendingKey = pendingTurnStorageKey(userId)
  try {
    const keysToDelete: string[] = [pendingKey]
    if (typeof storage.key === 'function' && typeof storage.length === 'number') {
      for (let i = 0; i < storage.length; i++) {
        const k = storage.key(i)
        if (k && k.startsWith(draftPrefix)) {
          keysToDelete.push(k)
        }
      }
    }
    for (const k of keysToDelete) {
      storage.removeItem(k)
    }
  } catch {
    /* ignore */
  }
}

export interface ReconciledTurnAction {
  action: 'completed_reload' | 'show_incomplete'
  conversationId: string | null
  status: PendingTurnSnapshot['status']
  partialContent: string
  errorMessage?: string | null
}

export function reconcilePendingTurnWithServer(
  snapshot: PendingTurnSnapshot,
  serverStatus: TurnStatusResponse | null,
): ReconciledTurnAction {
  const localPartial = snapshot.partialContent || ''
  if (!serverStatus || !serverStatus.found || serverStatus.status === 'unknown') {
    return {
      action: 'show_incomplete',
      conversationId: snapshot.conversationId,
      status: snapshot.status === 'stopped' ? 'stopped' : 'incomplete',
      partialContent: localPartial,
      errorMessage: snapshot.errorMessage ?? null,
    }
  }

  const convId = serverStatus.conversation_id ?? snapshot.conversationId
  const bestPartial =
    serverStatus.partial_content && serverStatus.partial_content.length >= localPartial.length
      ? serverStatus.partial_content
      : localPartial

  if (serverStatus.status === 'completed') {
    return {
      action: 'completed_reload',
      conversationId: convId,
      status: 'streaming',
      partialContent: bestPartial,
      errorMessage: null,
    }
  }

  const mappedStatus: PendingTurnSnapshot['status'] =
    serverStatus.status === 'stopped'
      ? 'stopped'
      : serverStatus.status === 'failed'
      ? 'failed'
      : serverStatus.status === 'streaming' || serverStatus.status === 'accepted'
      ? 'streaming'
      : 'incomplete'

  return {
    action: 'show_incomplete',
    conversationId: convId,
    status: mappedStatus,
    partialContent: bestPartial,
    errorMessage: serverStatus.error_message ?? snapshot.errorMessage ?? null,
  }
}
