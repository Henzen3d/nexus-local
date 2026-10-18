import { useEffect, useState } from 'react'
import { useStore } from '../store/useStore'

/**
 * Skeleton/Loading screen shown while the app initializes.
 * Disappears once conversations and models are loaded.
 */
export function LoadingScreen() {
  const conversations = useStore((s) => s.conversations)
  const models = useStore((s) => s.models)
  const [visible, setVisible] = useState(true)

  useEffect(() => {
    // Show loading until at least one data source is populated
    const hasData = (conversations?.length ?? 0) > 0 || (models?.length ?? 0) > 0
    if (hasData) {
      // Minimum display time for smoothness
      const timer = setTimeout(() => setVisible(false), 800)
      return () => clearTimeout(timer)
    }
  }, [conversations, models])

  if (!visible) return null

  return (
    <div className="loading-screen" aria-busy="true" aria-label="Carregando NexusLocal">
      <div className="loading-spinner" />
      <p className="loading-text">Carregando NexusLocal…</p>
    </div>
  )
}
