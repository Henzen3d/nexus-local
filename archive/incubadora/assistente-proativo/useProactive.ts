import { useEffect } from 'react'
import { useStore } from '../store/useStore'

/** Reavaliação local da validade (`expires_at`) — nunca mostrar insight vencido. */
const PRUNE_EVERY_MS = 60_000

/**
 * F3.5.1 — ciclo de vida da fila de pendentes no app:
 *  - no boot (ou ao trocar de usuário) puxa `GET /api/proactive/pending`;
 *  - a cada 60 s descarta localmente o que venceu;
 *  - ao voltar para a aba, repete a poda (o relógio pode ter andado em segundo plano).
 * A chegada ao vivo (`proactive_pending` pelo WS) é tratada em `useChat`.
 */
export function useProactive() {
  const token = useStore((s) => s.token)

  useEffect(() => {
    if (!token) {
      useStore.setState({ pendingInsights: [], proactiveSettings: null })
      return
    }
    void useStore.getState().loadPendingInsights()
    const timer = setInterval(() => useStore.getState().prunePendingInsights(), PRUNE_EVERY_MS)
    const onVis = () => {
      if (document.visibilityState === 'visible') useStore.getState().prunePendingInsights()
    }
    document.addEventListener('visibilitychange', onVis)
    return () => {
      clearInterval(timer)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [token])
}
