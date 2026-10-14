import { useCallback, useEffect, useRef, type MutableRefObject } from 'react'
import { useStore } from '../store/useStore'
import {
  IDLE_POLL_MS,
  PRESENCE_DEBOUNCE_MS,
  buildPresenceFrame,
  computePresenceState,
  presenceDelay,
  sameFrame,
  type PresenceFrame,
  type PresenceState,
} from '../lib/presenceState'

/** Eventos que contam como "atividade" (só atualizam um timestamp — nada de re-render). */
const ACTIVITY_EVENTS: Array<keyof WindowEventMap> = ['keydown', 'pointerdown', 'mousemove', 'touchstart', 'wheel']

/**
 * F3.4 — presença do cliente: `active | idle | hidden` + conversa/tela atual.
 *
 * - envia `{type:"presence"}` pelo socket passado em `wsRef`;
 * - transição **para** `active` (voltou) é imediata; sair tem debounce de 2 s;
 * - troca de conversa/tela é imediata (sinal que entrega pendências na origem);
 * - `idle` = 5 min sem teclado/ponteiro com a aba visível (reavaliado a cada 30 s);
 * - nunca repete o mesmo frame; `resendPresence()` zera o cache após (re)conectar.
 */
export function usePresence(wsRef: MutableRefObject<WebSocket | null>) {
  const activeConversationId = useStore((s) => s.activeConversationId)
  const view = useStore((s) => s.view)

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastFrameRef = useRef<PresenceFrame | null>(null)
  const lastStateRef = useRef<PresenceState | null>(null)
  const lastActivityRef = useRef(Date.now())

  const currentState = useCallback((): PresenceState => {
    const visible = typeof document === 'undefined' || document.visibilityState !== 'hidden'
    return computePresenceState({ visible, lastActivityAt: lastActivityRef.current, now: Date.now() })
  }, [])

  const sendPresence = useCallback((immediate = false) => {
    const fire = () => {
      timerRef.current = null
      const ws = wsRef.current
      if (!ws || ws.readyState !== WebSocket.OPEN) return
      const st = useStore.getState()
      const frame = buildPresenceFrame(currentState(), st.view, st.activeConversationId)
      if (sameFrame(lastFrameRef.current, frame)) return
      lastFrameRef.current = frame
      lastStateRef.current = frame.state
      try {
        ws.send(JSON.stringify(frame))
      } catch {
        /* ignore — onclose cuidará do reconnect */
      }
    }
    if (timerRef.current) clearTimeout(timerRef.current)
    const delay = immediate ? 0 : presenceDelay(lastStateRef.current, currentState(), PRESENCE_DEBOUNCE_MS)
    if (delay === 0) fire()
    else timerRef.current = setTimeout(fire, delay)
  }, [wsRef, currentState])

  /** Após `ready` de um socket novo: o backend não conhece o estado anterior. */
  const resendPresence = useCallback(() => {
    lastFrameRef.current = null
    lastStateRef.current = null
    sendPresence(true)
  }, [sendPresence])

  // Troca de conversa/tela → imediato
  useEffect(() => {
    sendPresence(true)
  }, [activeConversationId, view, sendPresence])

  // Visibilidade/foco → com debounce ao sair, imediato ao voltar
  useEffect(() => {
    const onVis = () => sendPresence()
    document.addEventListener('visibilitychange', onVis)
    window.addEventListener('focus', onVis)
    window.addEventListener('blur', onVis)
    window.addEventListener('pageshow', onVis)
    return () => {
      document.removeEventListener('visibilitychange', onVis)
      window.removeEventListener('focus', onVis)
      window.removeEventListener('blur', onVis)
      window.removeEventListener('pageshow', onVis)
    }
  }, [sendPresence])

  // Atividade do usuário → idle ⇄ active
  useEffect(() => {
    const onActivity = () => {
      lastActivityRef.current = Date.now()
      if (lastStateRef.current === 'idle') sendPresence(true)
    }
    for (const evt of ACTIVITY_EVENTS) window.addEventListener(evt, onActivity, { passive: true })
    const poll = setInterval(() => {
      if (lastStateRef.current !== null && lastStateRef.current !== currentState()) sendPresence()
    }, IDLE_POLL_MS)
    return () => {
      for (const evt of ACTIVITY_EVENTS) window.removeEventListener(evt, onActivity)
      clearInterval(poll)
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [sendPresence, currentState])

  return { sendPresence, resendPresence }
}
