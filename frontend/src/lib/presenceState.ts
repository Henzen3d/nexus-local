/**
 * Máquina de presença do cliente (assistente proativo — F3.4).
 *
 * Regras (contrato §3.1 / 01-decisao §2.2):
 *  - `hidden`  → aba oculta (`document.visibilityState === 'hidden'`);
 *  - `idle`    → aba visível, mas sem atividade (teclado/ponteiro/toque) há ≥ 5 min;
 *  - `active`  → caso contrário.
 *  - Transição **para** `active` é enviada imediatamente; as demais com debounce de 2 s.
 *  - `conversation_id` só vai quando a tela é o chat (nas outras telas vai `null`).
 *
 * Módulo puro (sem DOM) para ser testável com `node:test`.
 */

export type PresenceState = 'active' | 'idle' | 'hidden'

export const IDLE_AFTER_MS = 5 * 60_000
export const PRESENCE_DEBOUNCE_MS = 2_000
/** Com que frequência reavaliamos "idle" sem eventos do usuário. */
export const IDLE_POLL_MS = 30_000

export interface PresenceInput {
  /** `document.visibilityState === 'visible'` */
  visible: boolean
  /** Último sinal de atividade do usuário (ms epoch). */
  lastActivityAt: number
  now: number
  idleAfterMs?: number
}

export function computePresenceState({ visible, lastActivityAt, now, idleAfterMs = IDLE_AFTER_MS }: PresenceInput): PresenceState {
  if (!visible) return 'hidden'
  if (now - lastActivityAt >= idleAfterMs) return 'idle'
  return 'active'
}

export interface PresenceFrame {
  type: 'presence'
  state: PresenceState
  conversation_id: string | null
  view: string
}

export function buildPresenceFrame(state: PresenceState, view: string, activeConversationId: string | null): PresenceFrame {
  return {
    type: 'presence',
    state,
    conversation_id: view === 'chat' ? activeConversationId || null : null,
    view: view || 'chat',
  }
}

/**
 * Atraso antes de enviar a transição `prev → next`.
 * Voltar a ficar ativo (ou o primeiro relato) é imediato — é o sinal que destrava
 * a entrega das pendências; sair (idle/hidden) espera o debounce para ignorar
 * alt-tabs rápidos.
 */
export function presenceDelay(prev: PresenceState | null, next: PresenceState, debounceMs: number = PRESENCE_DEBOUNCE_MS): number {
  if (prev === null) return 0
  if (next === 'active') return 0
  return debounceMs
}

export function sameFrame(a: PresenceFrame | null, b: PresenceFrame): boolean {
  return !!a && a.state === b.state && a.conversation_id === b.conversation_id && a.view === b.view
}
