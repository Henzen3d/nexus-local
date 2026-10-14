import React, { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { UiError } from '../../lib/nexusUi'
import { useStore } from '../../store/useStore'
import { api } from '../../api/client'
import { useChatContext } from '../../context/ChatContext'
import { useIntelligentUiEnabled } from '../hooks/useIntelligentUi'
import { canRequestCorrection } from '../lib/correction'

interface Props {
  messageId: string
  errors?: UiError[]
  dropped?: number
  runtime?: { title: string; message: string } | null
}

/** One explicit request per message, shared by validation and all sandbox failures. */
export function CorrectionNotice({ messageId, errors = [], dropped = 0, runtime }: Props) {
  const { t } = useTranslation()
  const enabled = useIntelligentUiEnabled()
  const { sendMessage } = useChatContext()
  const streaming = useStore((s) => s.isStreaming)
  const requested = useStore((s) => !!s.uiCorrectionRequested[messageId])
  const [busy, setBusy] = useState(false)
  const lock = useRef(false)

  useEffect(() => {
    if (enabled && runtime && !requested) void api.offerUiCorrection(messageId).catch(() => {})
  }, [enabled, runtime, requested, messageId])

  if (!canRequestCorrection(enabled, requested, errors.length, !!runtime)) return null

  const request = async () => {
    if (streaming || lock.current || useStore.getState().uiCorrectionRequested[messageId]) return
    lock.current = true
    setBusy(true)
    try {
      if (runtime) await api.offerUiCorrection(messageId)
      if (useStore.getState().uiCorrectionRequested[messageId] || useStore.getState().isStreaming) return
      const error = errors[0]
      const text = runtime
        ? t('intelligentUi.correctionRuntimePrompt', { title: runtime.title.slice(0, 80), message: runtime.message.slice(0, 500) })
        : t('intelligentUi.correctionPrompt', {
          id: error?.block_id || messageId, path: error?.path || 'envelope',
          message: error?.message || '', hint: error?.hint || '',
        })
      // Failure to send (offline / no model) keeps the offer retryable.
      if (sendMessage(text, undefined, undefined, undefined, false, messageId)) {
        useStore.setState((state) => ({ uiCorrectionRequested: { ...state.uiCorrectionRequested, [messageId]: true } }))
      }
    } catch {
      useStore.getState().showToast(t('intelligentUi.correctionUnavailable'), 'error')
    } finally {
      lock.current = false
      setBusy(false)
    }
  }

  return (
    <div className="nexus-ui-correction" role="status">
      <span>{t('intelligentUi.correctionNotice', { count: Math.max(1, dropped) })}</span>
      <span aria-hidden="true"> · </span>
      <button type="button" onClick={() => void request()} disabled={streaming || busy}>
        {t('intelligentUi.requestCorrection')}
      </button>
    </div>
  )
}
