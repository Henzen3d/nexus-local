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
    this.flushThresholdChars = opts.flushThresholdChars ?? DEFAULT_FLUSH_THRESHOLD_CHARS
    this.maxBufferChars = opts.maxBufferChars ?? DEFAULT_MAX_BUFFER_CHARS
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
    // Enforce hard memory cap on queued buffer
    const remainingCap = this.maxBufferChars - this.pendingChars
    if (remainingCap <= 0) {
      this.flushSync()
    }
    const bounded = token.length > this.maxBufferChars ? token.slice(0, this.maxBufferChars) : token
    this.pending.push(bounded)
    this.pendingChars += bounded.length

    if (this.pendingChars >= this.flushThresholdChars) {
      this.flushSync()
      return true
    }

    this.scheduleFlush()
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

    if (!isHidden && raf && caf) {
      const frameId = raf(() => {
        this.cancelScheduled = null
        this.commitIfEpoch(scheduledEpoch)
      })
      this.cancelScheduled = () => caf(frameId)
      return
    }

    const st = this.scheduler.setTimer ?? setTimeout
    const ct = this.scheduler.clearTimer ?? clearTimeout
    const delay = isHidden ? this.hiddenFlushMs : 16
    const timerId = st(() => {
      this.cancelScheduled = null
      this.commitIfEpoch(scheduledEpoch)
    }, delay)
    this.cancelScheduled = () => ct(timerId)
  }
}
