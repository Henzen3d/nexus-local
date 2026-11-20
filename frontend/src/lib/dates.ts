/** SQLite timestamps without a timezone are stored in UTC. */
export function parseUtc(timestamp: string | null | undefined): number | null {
  if (!timestamp) return null
  const iso = timestamp.trim().replace(' ', 'T')
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(iso)
  const time = Date.parse(hasTimezone ? iso : iso + 'Z')
  return Number.isNaN(time) ? null : time
}

export function differenceInLocalDays(date: Date, now: Date): number {
  // Compare local calendar dates as UTC midnights so 23- and 25-hour days count once.
  const dateDay = Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  const currentDay = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())
  return (currentDay - dateDay) / 86_400_000
}

export function getConversationDateGroup(updatedAt: string, now: Date) {
  const time = parseUtc(updatedAt)
  if (time === null) return 'older'
  const daysAgo = differenceInLocalDays(new Date(time), now)

  if (daysAgo <= 0) return 'today'
  if (daysAgo === 1) return 'yesterday'
  if (daysAgo <= 7) return 'last7Days'
  return 'older'
}
