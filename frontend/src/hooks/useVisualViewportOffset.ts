import { useEffect, useState } from 'react'

/**
 * Returns bottom inset (px) to keep fixed/sticky UI above the soft keyboard.
 * Uses visualViewport when available (iOS Safari / Android Chrome).
 */
export function useVisualViewportOffset() {
  const [offset, setOffset] = useState(0)

  useEffect(() => {
    if (typeof window === 'undefined') return
    const vv = window.visualViewport
    if (!vv) return

    const update = () => {
      // Distance between layout viewport bottom and visual viewport bottom
      const keyboardGap = Math.max(0, window.innerHeight - vv.height - vv.offsetTop)
      setOffset(keyboardGap > 40 ? keyboardGap : 0)
    }

    update()
    vv.addEventListener('resize', update)
    vv.addEventListener('scroll', update)
    window.addEventListener('resize', update)
    return () => {
      vv.removeEventListener('resize', update)
      vv.removeEventListener('scroll', update)
      window.removeEventListener('resize', update)
    }
  }, [])

  return offset
}
