import { useEffect, useRef, useCallback } from 'react'
import i18n from '../i18n'
import { useStore } from '../store/useStore'
import type { WSMessage, Attachment } from '../types'

export function useChat() {
  const wsRef = useRef<WebSocket | null>(null)
  const {
    activeConversationId,
    selectedModelId,
    selectedProviderId,
    fusionMode,
    addUserMessage,
    appendToken,
    finalizeStream,
    setStreaming,
    setConversationCreated,
    loadConversations,
    setFusionActive,
    setFusionStatuses,
    updateFusionStatus,
    setFusionJudgeModelId,
    updateFusionGrounding,
    handleArtifactEvent,
    token,
    showToast,
    addErrorMessage,
    webSearchActive,
  } = useStore()
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    const wsUrl = import.meta.env.VITE_WS_URL
    let ws: WebSocket
    const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : ''
    
    if (wsUrl) {
      const url = wsUrl.endsWith('/ws/chat') ? wsUrl : `${wsUrl}/ws/chat`
      ws = new WebSocket(url + tokenQuery)
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      ws = new WebSocket(`${protocol}//${window.location.host}/ws/chat${tokenQuery}`)
    }

    ws.onmessage = (e) => {
      const msg: WSMessage = JSON.parse(e.data)
      switch (msg.type) {
        case 'conversation_created':
          setConversationCreated(msg.conversation_id, msg.title)
          break
        case 'stream_start':
          setStreaming(true)
          break
        case 'token':
          appendToken(msg.content)
          break
        case 'stream_end':
          setFusionActive(false)
          // Repassa metadados do(s) artifact(s) para aparecerem na mensagem
          finalizeStream(
            msg.message_id,
            msg.artifact_id && msg.artifact_type && msg.artifact_title
              ? { id: msg.artifact_id, type: msg.artifact_type, title: msg.artifact_title }
              : undefined,
            msg.artifacts,
            msg.relay_used,
            msg.relay_model,
            msg.web_search_used,
            msg.web_search_query,
            msg.web_search_sources
          )
          loadConversations()
          break
        case 'search_start':
          showToast(i18n.t('chat.searchingWeb', { query: msg.query }), 'info')
          break
        case 'artifact':
          // Dispara o fetch do artifact e abre o painel lateralmente.
          // handleArtifactEvent protege contra race conditions internamente.
          handleArtifactEvent(msg)
          break
        case 'fusion_start':
          setFusionActive(true)
          setFusionStatuses(
            msg.models.map((m) => ({ model_id: m, provider_id: '', status: 'pending' as const }))
          )
          break
        case 'fusion_status':
          updateFusionStatus(msg.model_id, msg.status, msg.response, msg.confidence, msg.confidence_reason)
          break
        case 'fusion_judge_start':
          setFusionJudgeModelId(msg.model_id)
          break
        case 'fusion_grounding':
          updateFusionGrounding(msg.status, msg.queries, msg.found)
          break
        case 'fusion_refined_prompt':
          useStore.getState().setFusionRefinedPrompt(msg.prompt)
          break
        case 'error':
          console.error('[WS error]', msg.message)
          setStreaming(false)
          setFusionActive(false)
          showToast(msg.message, 'error')
          addErrorMessage(msg.message)
          break
      }
    }

    ws.onclose = () => {
      wsRef.current = null
      // Reconnect after 2s
      setTimeout(connect, 2000)
    }

    wsRef.current = ws
  }, [appendToken, finalizeStream, setStreaming, setConversationCreated, loadConversations, setFusionActive, setFusionStatuses, updateFusionStatus, setFusionJudgeModelId, updateFusionGrounding, handleArtifactEvent, showToast, addErrorMessage])

  useEffect(() => {
    connect()
    return () => wsRef.current?.close()
  }, [connect])

  const sendMessage = useCallback(
    (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[]) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        console.warn('WebSocket not ready')
        return
      }
      if (!selectedModelId || !selectedProviderId) {
        console.warn('No model selected')
        return
      }

      // displayText: versão curta exibida no chat (ex: "✏️ Dashboard: adicionar dark mode")
      // text: prompt completo enviado ao modelo (inclui conteúdo do artifact)
      addUserMessage(displayText ?? text, attachments)

      wsRef.current.send(
        JSON.stringify({
          conversation_id: activeConversationId,
          message: text,
          model_id: selectedModelId,
          provider_id: selectedProviderId,
          fusion: fusionMode,
          attachment_ids: attachmentIds,
          web_search: webSearchActive,
        })
      )
    },
    [activeConversationId, selectedModelId, selectedProviderId, fusionMode, addUserMessage, webSearchActive]
  )

  return { sendMessage }
}
