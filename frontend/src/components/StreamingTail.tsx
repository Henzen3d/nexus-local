import { useEffect, type RefObject } from 'react'
import { useStore } from '../store/useStore'
import { StreamingBubble } from './MessageBubble'
import { streamScrollBehavior } from '../lib/scrollPolicy'

const scrollBehavior = streamScrollBehavior(true)

export function StreamingTail({
  sentinelRef,
  messagesAreaRef,
}: {
  sentinelRef: RefObject<HTMLDivElement | null>
  messagesAreaRef: RefObject<HTMLDivElement | null>
}) {
  const streamingContent = useStore((s) => s.streamingContent)
  const isStreaming = useStore((s) => s.isStreaming)

  useEffect(() => {
    if (!streamingContent) return
    const container = messagesAreaRef.current
    if (!container) return
    const threshold = 180
    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < threshold
    if (!isNearBottom) return
    const node = sentinelRef.current
    if (!node || typeof node.scrollIntoView !== 'function') return
    node.scrollIntoView({
      behavior: scrollBehavior,
      block: 'end',
    })
  }, [streamingContent, sentinelRef, messagesAreaRef])

  if (!isStreaming) return null
  return <StreamingBubble content={streamingContent} />
}
