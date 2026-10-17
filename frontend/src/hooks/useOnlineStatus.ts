/**
 * Hook que escuta online/offline e espelha no estado do app.
 * Exibe banner quando offline; some automaticamente ao reconectar.
 */
import { useEffect } from 'react'
import { useStore } from '../store/useStore'

export function useOnlineStatus() {
  const setIsOnline = useStore((s) => s.setIsOnline)
  const isOnline = useStore((s) => s.isOnline)

  useEffect(() => {
    const update = () => {
      const online = navigator.onLine
      if (online !== isOnline) {
        setIsOnline(online)
      }
    }

    update() // estado inicial
    window.addEventListener('online', update)
    window.addEventListener('offline', update)

    return () => {
      window.removeEventListener('online', update)
      window.removeEventListener('offline', update)
    }
  }, [isOnline, setIsOnline])
}
