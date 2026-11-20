import { useEffect, useState } from 'react'

/** Refresh calendar labels at local midnight and when returning to the app. */
export function useLocalDate(): Date {
  const [, setDay] = useState(() => new Date().setHours(0, 0, 0, 0))

  useEffect(() => {
    let timer: number
    const schedule = () => {
      window.clearTimeout(timer)
      const now = new Date()
      setDay(new Date(now).setHours(0, 0, 0, 0))
      const nextDay = new Date(now).setHours(24, 0, 0, 0)
      timer = window.setTimeout(schedule, nextDay - now.getTime())
    }
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') schedule()
    }

    schedule()
    window.addEventListener('focus', schedule)
    document.addEventListener('visibilitychange', onVisibilityChange)
    return () => {
      window.clearTimeout(timer)
      window.removeEventListener('focus', schedule)
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }, [])

  return new Date()
}
