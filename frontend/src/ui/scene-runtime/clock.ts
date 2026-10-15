export const MAX_STEP = 0.05

export function createClock() {
  let time = 0
  let last: number | null = null
  return {
    get time() {
      return time
    },
    tick(now: number): number {
      const step = last === null ? 0 : Math.min(Math.max(now - last, 0) / 1000, MAX_STEP)
      last = now
      time += step
      return step
    },
    hold() {
      last = null
    },
  }
}
