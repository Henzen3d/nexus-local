import { useEffect, type RefObject } from 'react'
import { useStore } from '../store/useStore'
import { StreamingBubble } from './MessageBubble'
import { streamScrollBehavior } from '../lib/scrollPolicy'

const scrollBehavior = streamScrollBehavior(true)

export function StreamingTail({
  sentinelRef,
}: {
  sentinelRef: RefObject<HTMLDivElement | null>
}) {
  const streamingContent = useStore((s) => s.streamingContent)
  const isStreaming = useStore((s) => s.isStreaming)

  useEffect(() => {
    if (!streamingContent) return
    const node = sentinelRef.current
    if (!node || typeof node.scrollIntoView !== 'function') return
    node.scrollIntoView({
      behavior: scrollBehavior,
      block: 'end',
    })
  }, [streamingContent, sentinelRef])

  if (!isStreaming) return null
  return <StreamingBubble content={streamingContent} />
}
