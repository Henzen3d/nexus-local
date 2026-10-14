import { useEffect, useState } from 'react'
import { getResolvedThemeMode, type ThemeMode } from '../themeBridge'

/**
 * Tema efetivo do app ('dark' | 'light'), reativo.
 * O App.tsx resolve 'system' e grava `data-theme` em `<html>`; aqui observamos esse
 * atributo (MutationObserver) e, por segurança, também o `prefers-color-scheme`.
 */
export function useResolvedTheme(): ThemeMode {
  const [mode, setMode] = useState<ThemeMode>(() => getResolvedThemeMode())

  useEffect(() => {
    if (typeof document === 'undefined') return
    const update = () => setMode(getResolvedThemeMode())
    const observer = new MutationObserver(update)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    const media = typeof window !== 'undefined' ? window.matchMedia?.('(prefers-color-scheme: light)') : undefined
    media?.addEventListener?.('change', update)
    update()
    return () => {
      observer.disconnect()
      media?.removeEventListener?.('change', update)
    }
  }, [])

  return mode
}
