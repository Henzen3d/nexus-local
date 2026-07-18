import { useCallback } from 'react'
import { useStore } from '../store/useStore'

/** Fire a short vibration only when the user has haptics enabled. */
export function useHaptic() {
  const hapticFeedback = useStore((s) => s.hapticFeedback)

  return useCallback(
    (ms = 12) => {
      if (!hapticFeedback) return
      if (typeof navigator === 'undefined' || !navigator.vibrate) return
      try {
        navigator.vibrate(ms)
      } catch {
        /* ignore */
      }
    },
    [hapticFeedback]
  )
}

/** Imperative helper for non-hook call sites (e.g. timeout callbacks). */
export function triggerHapticIfEnabled(enabled: boolean, ms = 12) {
  if (!enabled) return
  if (typeof navigator === 'undefined' || !navigator.vibrate) return
  try {
    navigator.vibrate(ms)
  } catch {
    /* ignore */
  }
}
