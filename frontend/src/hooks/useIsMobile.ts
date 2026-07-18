import { useState, useEffect } from 'react'

/** Mobile breakpoint — keep in sync with CSS `@media (max-width: 768px)`. */
export const MOBILE_BREAKPOINT = 768
export const MOBILE_MQ = `(max-width: ${MOBILE_BREAKPOINT}px)`

export function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(MOBILE_MQ).matches : false
  )

  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia(MOBILE_MQ)
    const listener = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])

  return isMobile
}
