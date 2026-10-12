import { useEffect, useRef, useCallback } from 'react'
import i18n from '../i18n'
import { useStore } from '../store/useStore'
import type { WSMessage, Attachment } from '../types'

const AUTH_CLOSE_CODE = 4001
const MAX_RETRY_MS = 30_000
const BASE_RETRY_MS = 1_000
/** Keepalive em ambos os sentidos — evita idle-timeout do Cloudflare Tunnel (~100s) */
const HEARTBEAT_MS = 25_000

function buildWsUrl(token: string | null | undefined): string {
  const tokenQuery = token ? `?token=${encodeURIComponent(token)}` : ''
  const wsUrl = import.meta.env.VITE_WS_URL as string | undefined

  if (wsUrl) {
    const base = wsUrl.endsWith('/ws/chat') ? wsUrl : `${wsUrl}/ws/chat`
    return base + tokenQuery
  }

  // Recomendado em produção: mesmo host do front (proxy Nginx → backend)
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws/chat${tokenQuery}`
}

export function useChat() {
  const wsRef = useRef<WebSocket | null>(null)
  const isGeneratingRef = useRef(false)
  const {
    activeConversationId,
    selectedModelId,
    selectedProviderId,
    fusionMode,
    addUserMessage,
    token,
    webSearchActive,
    activeProjectId,
  } = useStore()

  // Single long-lived socket; reconnect only when token changes or the link drops.
  useEffect(() => {
    // Sem token não há o que autenticar — evita loop de "Autenticação requerida".
    if (!token) {
      wsRef.current?.close()
      wsRef.current = null
      return
    }

    let disposed = false
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    let heartbeatTimer: ReturnType<typeof setInterval> | null = null
    let attempt = 0
    let socket: WebSocket | null = null

    const clearRetry = () => {
      if (retryTimer != null) {
        clearTimeout(retryTimer)
        retryTimer = null
      }
    }

    const clearHeartbeat = () => {
      if (heartbeatTimer != null) {
        clearInterval(heartbeatTimer)
        heartbeatTimer = null
      }
    }

    const startHeartbeat = (ws: WebSocket) => {
      clearHeartbeat()
      heartbeatTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          try {
            ws.send(JSON.stringify({ type: 'ping' }))
          } catch {
            /* ignore — onclose cuidará do reconnect */
          }
        }
      }, HEARTBEAT_MS)
    }

    const handleMessage = (e: MessageEvent) => {
      let msg: WSMessage
      try {
        msg = JSON.parse(e.data)
      } catch {
        console.warn('[WS] invalid JSON frame')
        return
      }

      // Heartbeat / handshake — não mexe no estado do chat
      if (msg.type === 'ready' || msg.type === 'pong') {
        return
      }
      if (msg.type === 'ping') {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          try {
            wsRef.current.send(JSON.stringify({ type: 'pong' }))
          } catch {
            /* ignore */
          }
        }
        return
      }

      // Se a geração foi interrompida localmente pelo usuário, ignora frames parciais
      if (!isGeneratingRef.current && (
        msg.type === 'token' ||
        msg.type === 'stream_start' ||
        msg.type === 'ui_progress' ||
        msg.type === 'process_step_start' ||
        msg.type === 'process_step_update' ||
        msg.type === 'process_step_end' ||
        msg.type === 'fusion_start' ||
        msg.type === 'fusion_phase' ||
        msg.type === 'fusion_status' ||
        msg.type === 'fusion_judge_start' ||
        msg.type === 'fusion_grounding' ||
        msg.type === 'fusion_refined_prompt' ||
        msg.type === 'image_pending' ||
        msg.type === 'image_ready' ||
        msg.type === 'image_failed'
      )) {
        return
      }

      if (!isGeneratingRef.current && msg.type === 'stream_end') {
        return
      }

      // Lê actions frescas do store (evita recriar o socket a cada re-render).
      const s = useStore.getState()

      switch (msg.type) {
        case 'conversation_created':
          s.setConversationCreated(msg.conversation_id, msg.title)
          break
        case 'stream_start':
          s.beginProcess(i18n.t('chat.processThinking'))
          break
        case 'token':
          s.appendToken(msg.content)
          break
        case 'stream_end':
          isGeneratingRef.current = false
          s.setFusionActive(false)
          s.finalizeStream(
            msg.message_id,
            msg.artifact_id && msg.artifact_type && msg.artifact_title
              ? { id: msg.artifact_id, type: msg.artifact_type, title: msg.artifact_title }
              : undefined,
            msg.artifacts,
            msg.relay_used,
            msg.relay_model,
            msg.web_search_used,
            msg.web_search_query,
            msg.web_search_sources,
            msg.was_fallback,
            msg.ui_blocks,
            msg.process_duration_ms
          )
          s.loadConversations()
          break
        case 'ui_progress':
          s.handleUiProgress(msg.block)
          break
        case 'auto_route_decision':
          s.setAutoRouteDecision(msg)
          break
        case 'failover_notice':
          s.showToast(
            `Failover: ${msg.original_model} esgotado. Alternando para ${msg.fallback_model}...`,
            'info'
          )
          break
        case 'search_start':
          s.startProcessStep({
            id: 'web-search',
            type: 'search',
            title: i18n.t('chat.processSearching'),
            detail: msg.query,
            status: 'running',
          })
          break
        case 'process_step_start':
          s.startProcessStep({
            id: msg.id,
            type: msg.step_type,
            title: msg.step_type === 'search' ? i18n.t('chat.processSearching') : msg.title,
            detail: msg.detail,
            status: 'running',
          })
          break
        case 'process_step_update':
          s.updateProcessStep(msg.id, { detail: msg.detail, subSteps: msg.sub_steps })
          break
        case 'process_step_end':
          s.updateProcessStep(msg.id, { status: msg.status, subSteps: msg.sub_steps })
          break
        case 'artifact':
          s.handleArtifactEvent(msg)
          break
        case 'fusion_start':
          // Marca streaming cedo para bloquear reenvio e mostrar estado de ocupado
          // (antes o isStreaming só ligava no juiz — proposers pareciam "travados").
          s.setStreaming(true)
          s.setFusionActive(true)
          s.setFusionStatuses(
            msg.models.map((m) => ({ model_id: m, provider_id: '', status: 'pending' as const }))
          )
          break
        case 'fusion_phase':
          // Refining, proposers, grounding and judge stay in the inline timeline.
          s.startProcessStep({
            id: `fusion-${msg.phase}`,
            type: msg.phase === 'grounding' ? 'search' : 'tool',
            title: i18n.t(`chat.processFusion.${msg.phase}`, { defaultValue: msg.phase }),
            status: 'running',
          })
          break
        case 'fusion_status':
          s.updateFusionStatus(msg.model_id, msg.status, msg.response, msg.confidence, msg.confidence_reason)
          break
        case 'fusion_judge_start':
          s.setFusionJudgeModelId(msg.model_id)
          break
        case 'fusion_grounding':
          s.updateFusionGrounding(msg.status, msg.queries, msg.found)
          if (msg.queries?.length) {
            s.updateProcessStep('fusion-grounding', { subSteps: msg.queries })
          }
          break
        case 'fusion_refined_prompt':
          s.setFusionRefinedPrompt(msg.prompt)
          break
        case 'image_pending':
          s.handleImagePending(msg)
          break
        case 'image_ready':
          s.handleImageReady(msg)
          break
        case 'image_failed':
          s.handleImageFailed(msg)
          break
        case 'effort_dropped': {
          let dropText = i18n.t('chat.effortDroppedUnsupported', {
            defaultValue: 'O modelo selecionado não suporta controle de esforço.',
          })
          if (msg.reason === 'failover') {
            dropText = i18n.t('chat.effortDroppedFailover', {
              defaultValue: 'O modelo reserva não suporta controle de esforço; resposta gerada no padrão.',
            })
          } else if (msg.reason === 'provider_rejected') {
            dropText = i18n.t('chat.effortDroppedProvider', {
              defaultValue: 'O provedor rejeitou o parâmetro de esforço; retentando sem ele.',
            })
          }
          s.showToast(dropText, 'info')
          break
        }
        case 'error':
          if (!isGeneratingRef.current) return
          isGeneratingRef.current = false
          console.error('[WS error]', msg.message)
          s.setStreaming(false)
          s.setFusionActive(false)
          s.showToast(msg.message, 'error')
          s.addErrorMessage(msg.message)
          break
      }
    }

    const scheduleReconnect = (reason: string) => {
      if (disposed) return
      clearRetry()
      const delay = Math.min(MAX_RETRY_MS, BASE_RETRY_MS * 2 ** attempt)
      attempt += 1
      if (attempt <= 3 || attempt % 5 === 0) {
        console.warn(`[WS] reconnect in ${delay}ms (attempt ${attempt}): ${reason}`)
      }
      retryTimer = setTimeout(connect, delay)
    }

    const connect = () => {
      if (disposed) return

      // Evita sockets órfãos se connect for chamado enquanto ainda CONNECTING/OPEN.
      if (
        socket &&
        (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)
      ) {
        return
      }

      let ws: WebSocket
      try {
        ws = new WebSocket(buildWsUrl(token))
      } catch (err) {
        console.error('[WS] failed to construct socket', err)
        scheduleReconnect('constructor error')
        return
      }

      socket = ws
      wsRef.current = ws

      ws.onopen = () => {
        attempt = 0
        startHeartbeat(ws)
      }

      ws.onmessage = handleMessage

      ws.onerror = () => {
        // onclose always follows; keep logging light to avoid console spam.
        if (attempt === 0) {
          console.warn('[WS] connection error')
        }
      }

      ws.onclose = (ev) => {
        clearHeartbeat()
        isGeneratingRef.current = false
        if (wsRef.current === ws) wsRef.current = null
        if (socket === ws) socket = null

        // Nunca deixar a UI presa em "Fusion ativo" / streaming se o socket caiu
        const st = useStore.getState()
        if (st.fusionActive || st.isStreaming) {
          st.setStreaming(false)
          st.setFusionActive(false)
          st.showToast(
            i18n.t('chat.wsDroppedDuringStream', {
              defaultValue: 'Conexão interrompida durante a resposta. Tente novamente.',
            }),
            'error'
          )
        }

        if (disposed) return

        // Auth reject: não adianta martelar reconexão com o mesmo token inválido.
        if (ev.code === AUTH_CLOSE_CODE) {
          console.warn('[WS] auth rejected — faça login novamente')
          useStore.getState().showToast(
            i18n.t('chat.wsAuthFailed', { defaultValue: 'Sessão expirada. Faça login novamente.' }),
            'error'
          )
          return
        }

        scheduleReconnect(`code=${ev.code} reason=${ev.reason || 'closed'}`)
      }
    }

    connect()

    // Reconecta ao voltar online ou ao focar a aba (útil após sleep/túnel Cloudflare)
    const onOnline = () => {
      if (disposed) return
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        attempt = 0
        clearRetry()
        connect()
      }
    }
    const onVisibility = () => {
      if (document.visibilityState === 'visible') onOnline()
    }
    window.addEventListener('online', onOnline)
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      disposed = true
      clearRetry()
      clearHeartbeat()
      window.removeEventListener('online', onOnline)
      document.removeEventListener('visibilitychange', onVisibility)
      // Fecha sem disparar reconnect (flag disposed).
      if (socket) {
        socket.onclose = null
        socket.onerror = null
        socket.onmessage = null
        socket.onopen = null
        try {
          socket.close()
        } catch {
          /* ignore */
        }
      }
      socket = null
      if (wsRef.current) wsRef.current = null
    }
  }, [token])

  const stopStream = useCallback(() => {
    isGeneratingRef.current = false
    const s = useStore.getState()
    if (!s.isStreaming && !s.fusionActive) return

    if (s.streamingContent.trim()) {
      // Preserva a resposta parcial gerada até o momento da parada
      s.finalizeStream(
        `msg-stop-${Date.now()}`,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        undefined,
        s.processStartedAt ? Date.now() - s.processStartedAt : undefined
      )
    } else {
      // Nenhum texto gerado ainda — cancela os estados de ocupado e reseta passos
      useStore.setState({
        isStreaming: false,
        streamingContent: '',
        fusionActive: false,
        processSteps: [],
        processStartedAt: null,
      })
    }
  }, [])

  const sendMessage = useCallback(
    (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[]) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        console.warn('WebSocket not ready')
        useStore.getState().showToast(
          i18n.t('chat.wsNotReady', {
            defaultValue: 'Conexão em tempo real indisponível. Aguarde ou recarregue a página.',
          }),
          'error'
        )
        return
      }
      if (!selectedModelId || !selectedProviderId) {
        console.warn('No model selected')
        return
      }

      isGeneratingRef.current = true

      // displayText: versão curta exibida no chat (ex: "✏️ Dashboard: adicionar dark mode")
      // text: prompt completo enviado ao modelo (inclui conteúdo do artifact)
      addUserMessage(displayText ?? text, attachments)

      const safeAttachmentIds = (attachmentIds ?? []).filter(
        (id): id is string => typeof id === 'string' && id.length > 0
      )

      const activeEffort = useStore.getState().getActiveReasoningEffort()

      wsRef.current.send(
        JSON.stringify({
          conversation_id: activeConversationId,
          message: text,
          model_id: selectedModelId,
          provider_id: selectedProviderId,
          reasoning_effort: activeEffort || undefined,
          fusion: fusionMode,
          attachment_ids: safeAttachmentIds.length > 0 ? safeAttachmentIds : undefined,
          web_search: webSearchActive,
          // Always request memory; backend honors global profile.memory_enabled
          use_memory: true,
          // Bind new turns / new chats to active project workspace (RAG)
          project_id: activeProjectId || undefined,
          project_context_debug: !!(import.meta.env.DEV),
          client_timezone_offset: new Date().getTimezoneOffset(),
        })
      )
    },
    [
      activeConversationId,
      selectedModelId,
      selectedProviderId,
      fusionMode,
      addUserMessage,
      webSearchActive,
      activeProjectId,
    ]
  )

  return { sendMessage, stopStream }
}
