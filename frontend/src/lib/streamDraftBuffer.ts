/**
 * Isolated per-turn streaming token buffer with epoch fencing, hidden-tab fallback,
 * synchronous terminal flush, and bounded memory (T2.3).
 */

export interface StreamDraftScheduler {
  requestFrame?: (cb: () => void) => number
  cancelFrame?: (id: number) => void
  setTimer?: (cb: () => void, ms: number) => ReturnType<typeof setTimeout>
  clearTimer?: (id: ReturnType<typeof setTimeout>) => void
  isHidden?: () => boolean
}

export interface StreamDraftBufferOptions {
  onCommit: (chunk: string, turnId: string | null) => void
  flushThresholdChars?: number
  maxBufferChars?: number
  hiddenFlushMs?: number
  scheduler?: StreamDraftScheduler
}

const DEFAULT_FLUSH_THRESHOLD_CHARS = 64_000
const DEFAULT_MAX_BUFFER_CHARS = 512_000
const DEFAULT_HIDDEN_FLUSH_MS = 50

export class StreamDraftBuffer {
  private pending: string[] = []
  private pendingChars = 0
  private epoch = 0
  private activeTurnId: string | null = null
  private cancelScheduled: (() => void) | null = null
  private readonly onCommit: (chunk: string, turnId: string | null) => void
  private readonly flushThresholdChars: number
  private readonly maxBufferChars: number
  private readonly hiddenFlushMs: number
  private readonly scheduler: StreamDraftScheduler

  constructor(opts: StreamDraftBufferOptions) {
    this.onCommit = opts.onCommit
    this.maxBufferChars = Math.max(1, opts.maxBufferChars ?? DEFAULT_MAX_BUFFER_CHARS)
    this.flushThresholdChars = Math.min(this.maxBufferChars, Math.max(1, opts.flushThresholdChars ?? DEFAULT_FLUSH_THRESHOLD_CHARS))
    this.hiddenFlushMs = opts.hiddenFlushMs ?? DEFAULT_HIDDEN_FLUSH_MS
    this.scheduler = opts.scheduler ?? {}
  }

  get currentEpoch(): number {
    return this.epoch
  }

  get currentTurnId(): string | null {
    return this.activeTurnId
  }

  get bufferedLength(): number {
    return this.pendingChars
  }

  bindTurn(turnId: string | null): void {
    this.discard()
    this.activeTurnId = turnId
  }

  append(token: string, turnId?: string | null): boolean {
    if (!token) return false
    if (turnId !== undefined && this.activeTurnId !== null && turnId !== this.activeTurnId) {
      return false
    }
    // Bound queued text without discarding any part of a large frame.
    for (let offset = 0; offset < token.length;) {
      const count = Math.min(token.length - offset, this.maxBufferChars - this.pendingChars)
      this.pending.push(token.slice(offset, offset + count))
      this.pendingChars += count
      offset += count
      if (this.pendingChars >= this.flushThresholdChars) this.flushSync()
    }

    if (this.pendingChars > 0) this.scheduleFlush()
    return true
  }

  flushSync(): void {
    this.cancelScheduled?.()
    this.cancelScheduled = null
    this.commitIfEpoch(this.epoch)
  }

  discard(): void {
    this.epoch += 1
    this.cancelScheduled?.()
    this.cancelScheduled = null
    this.pending = []
    this.pendingChars = 0
  }

  resetTurn(): void {
    this.discard()
    this.activeTurnId = null
  }

  private commitIfEpoch(expectedEpoch: number): void {
    if (expectedEpoch !== this.epoch) return
    if (this.pending.length === 0) return
    const chunk = this.pending.join('')
    const turnId = this.activeTurnId
    this.pending = []
    this.pendingChars = 0
    this.onCommit(chunk, turnId)
  }

  private scheduleFlush(): void {
    if (this.cancelScheduled) return
    const scheduledEpoch = this.epoch

    const isHidden = this.scheduler.isHidden
      ? this.scheduler.isHidden()
      : typeof document !== 'undefined' && document.visibilityState === 'hidden'

    const raf =
      this.scheduler.requestFrame ??
      (typeof requestAnimationFrame === 'function' ? requestAnimationFrame : undefined)
    const caf =
      this.scheduler.cancelFrame ??
      (typeof cancelAnimationFrame === 'function' ? cancelAnimationFrame : undefined)

    const st = this.scheduler.setTimer ?? setTimeout
    const ct = this.scheduler.clearTimer ?? clearTimeout
    let active = true
    const flush = () => {
      if (!active) return
      this.cancelScheduled?.()
      this.cancelScheduled = null
      this.commitIfEpoch(scheduledEpoch)
    }
    const frameId = !isHidden && raf && caf ? raf(flush) : null
    // RAF can already be pending when the tab is hidden. A timer fallback
    // ensures that this batch is still eligible to flush without another token.
    const timerId = st(flush, isHidden || frameId !== null ? this.hiddenFlushMs : 16)
    this.cancelScheduled = () => {
      active = false
      if (frameId !== null) caf?.(frameId)
      ct(timerId)
    }
  }
}
