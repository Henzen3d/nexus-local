import { useEffect, useRef, useCallback } from 'react'
import i18n from '../i18n'
import { useStore } from '../store/useStore'
import { useShallow } from 'zustand/react/shallow'
import { getTalk } from '../lib/talkLoop'
import { usePresence } from './usePresence'
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
  // Flag de turno ativo (controla se o socket aceita frames do assistente).
  // Permanece true durante todo o turno. Só vai para false no fim (stream_end),
  // em erro fatal (error), fechamento do socket (onclose) ou cancelamento do usuário (stopStream).
  // NUNCA zerar ao receber tokens parciais ou etapas, pois causaria o descarte do restante do stream.
  const isGeneratingRef = useRef(false)
  const watchdogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearWatchdog = useCallback(() => {
    if (watchdogTimerRef.current != null) {
      clearTimeout(watchdogTimerRef.current)
      watchdogTimerRef.current = null
    }
  }, [])

  const resetWatchdog = useCallback(() => {
    clearWatchdog()
    if (!isGeneratingRef.current) return
    watchdogTimerRef.current = setTimeout(() => {
      if (!isGeneratingRef.current) return
      isGeneratingRef.current = false
      const s = useStore.getState()
      if (s.isStreaming || s.fusionActive) {
        s.setStreaming(false)
        s.setIsGenerating(false)
        s.setFusionActive(false)
        const timeoutMsg = i18n.t('chat.streamTimeout', {
          defaultValue: 'Tempo limite de resposta excedido. O modelo não respondeu.',
        })
        s.showToast(timeoutMsg, 'error')
        s.addErrorMessage(timeoutMsg)
      }
    }, 90000)
  }, [clearWatchdog])

  const {
    activeConversationId,
    selectedModelId,
    selectedProviderId,
    fusionMode,
    addUserMessage,
    token,
    webSearchActive,
    activeProjectId,
  } = useStore(useShallow((s) => ({
    activeConversationId: s.activeConversationId,
    selectedModelId: s.selectedModelId,
    selectedProviderId: s.selectedProviderId,
    fusionMode: s.fusionMode,
    addUserMessage: s.addUserMessage,
    token: s.token,
    webSearchActive: s.webSearchActive,
    activeProjectId: s.activeProjectId,
  })))

  // ── Presença (assistente proativo, F3.4) ───────────────────────────────────
  // active | idle | hidden + conversa/tela atual → backend decide inline × toast × pendente
  // e entrega as pendências quando o usuário volta.
  const { resendPresence } = usePresence(wsRef)

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
      if (msg.type === 'ready') {
        // Socket novo: o backend perdeu o estado anterior → reenvia presença (F3.4.2)
        resendPresence()
        return
      }
      if (msg.type === 'pong') {
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

      // Eventos do assistente proativo — chegam fora do ciclo de geração
      if (msg.type === 'proactive_status') {
        useStore.getState().handleProactiveStatus(msg)
        return
      }
      if (msg.type === 'proactive_insight') {
        useStore.getState().handleProactiveInsight(msg)
        return
      }
      if (msg.type === 'proactive_pending') {
        // F3.5: fila de pendentes → cartão (tela inicial), toast agrupado + badge (outras telas)
        useStore.getState().handleProactivePending(msg)
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
        msg.type === 'fusion_refined_prompt'
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
          resetWatchdog()
          s.beginProcess(i18n.t('chat.generatingResponse', { defaultValue: 'Gerando resposta…' }))
          s.setIsGenerating(false)
          break
        case 'stream_clear':
          // Failover mid-stream: o modelo anterior já emitiu tokens e falhou;
          // limpa o rascunho para o próximo modelo não misturar respostas.
          s.clearStreamDraft()
          break
        case 'token':
          resetWatchdog()
          if (s.isGenerating) {
            s.setIsGenerating(false)
          }
          s.appendToken(msg.content)
          break
        case 'stream_end':
          clearWatchdog()
          isGeneratingRef.current = false
          useStore.getState().setIsGenerating(false)
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
            msg.process_duration_ms,
            msg.process_steps,
            msg.ui_errors,
            msg.ui_dropped,
            msg.final_model_id,
            msg.final_model_name,
            msg.final_provider_id,
            msg.requested_model,
            msg.served_by,
            msg.failover_tier,
            msg.spliced,
            msg.outcome,
            msg.attempt_count
          )
          s.loadConversations()
          break
        case 'ui_progress':
          s.handleUiProgress(msg.block)
          break
        case 'auto_route_decision':
          s.setAutoRouteDecision(msg)
          break
        case 'failover_notice': {
          resetWatchdog()
          const reasonKey = msg.reason || 'error'
          const defaultReason = reasonKey === 'rate_limit'
            ? 'esgotado'
            : reasonKey === 'invalid_request'
            ? 'requisição incompatível'
            : reasonKey === 'upstream'
            ? 'instabilidade no serviço'
            : reasonKey === 'timeout'
            ? 'tempo limite esgotado'
            : reasonKey === 'connection'
            ? 'falha de conexão'
            : reasonKey === 'auth'
            ? 'falha de autenticação'
            : 'indisponível'
          const reasonLabel = i18n.t(`chat.failoverReason.${reasonKey}`, {
            defaultValue: defaultReason
          })
          s.showToast(
            i18n.t('chat.failoverNotice', {
              model: msg.original_model,
              fallback: msg.fallback_model,
              reason: reasonLabel,
              defaultValue: `Failover: ${msg.original_model} (${reasonLabel}). Alternando para ${msg.fallback_model}...`
            }),
            'info'
          )
          break
        }
        case 'search_start':
          if (s.isGenerating) {
            s.setIsGenerating(false)
          }
          s.startProcessStep({
            id: 'web-search',
            type: 'search',
            title: i18n.t('chat.processSearching'),
            detail: msg.query,
            status: 'running',
          })
          break
        case 'process_step_start':
          if (s.isGenerating) {
            s.setIsGenerating(false)
          }
          s.startProcessStep({
            id: msg.id,
            type: msg.step_type,
            title: msg.title || (msg.step_type === 'search' ? i18n.t('chat.processSearching') : msg.step_type),
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
          s.setIsGenerating(false)
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
          s.updateFusionStatus(msg.model_id, msg.status, msg.response, msg.confidence, msg.confidence_reason, (msg as any).original_model_id)
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
        case 'history_trimmed':
          s.showToast(
            i18n.t('chat.historyTrimmed', {
              defaultValue: 'Parte antiga da conversa ficou de fora para caber no modelo.',
            }),
            'info'
          )
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
          clearWatchdog()
          if (!isGeneratingRef.current) return
          isGeneratingRef.current = false
          useStore.getState().setIsGenerating(false)
          console.error('[WS error]', msg.message)
          s.clearStreamDraft()
          s.setStreaming(false)
          s.setFusionActive(false)
          // Toast com ação de retry
          const retryAction = s.lastUserMessage
            ? {
                label: i18n.t('chat.retry', { defaultValue: 'Tentar novamente' }),
                onClick: () => {
                  s.hideToast()
                  // Re-envia a última mensagem via WebSocket
                  if (wsRef.current?.readyState === WebSocket.OPEN) {
                    isGeneratingRef.current = true
                    useStore.getState().setIsGenerating(true)
                    resetWatchdog()
                    wsRef.current.send(JSON.stringify({
                      conversation_id: s.lastUserMessage!.conversationId,
                      message: s.lastUserMessage!.text,
                      model_id: s.lastUserMessage!.modelId,
                      provider_id: s.lastUserMessage!.providerId,
                      fusion: s.lastUserMessage!.fusionMode,
                      web_search: s.lastUserMessage!.webSearchActive,
                      project_id: s.lastUserMessage!.projectId || undefined,
                      use_memory: true,
                      client_timezone_offset: new Date().getTimezoneOffset(),
                    }))
                  }
                },
              }
            : undefined
          s.showToast(
            msg.message,
            'error',
            retryAction ? { action: retryAction, durationMs: 15000 } : undefined
          )
          const errorDetail = (msg as any).details || msg.message
          s.addErrorMessage(errorDetail)
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
        // Presença é reenviada ao receber `ready` (socket registrado no backend)
      }

      ws.onmessage = handleMessage

      ws.onerror = () => {
        // onclose always follows; keep logging light to avoid console spam.
        if (attempt === 0) {
          console.warn('[WS] connection error')
        }
      }

      ws.onclose = (ev) => {
        clearWatchdog()
        clearHeartbeat()
        isGeneratingRef.current = false
        if (wsRef.current === ws) wsRef.current = null
        if (socket === ws) socket = null

        // Nunca deixar a UI presa em "Fusion ativo" / streaming se o socket caiu
        const st = useStore.getState()
        if (st.fusionActive || st.isStreaming) {
          st.setStreaming(false)
          st.setIsGenerating(false)
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
      clearWatchdog()
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
  }, [token, resendPresence])

  const stopStream = useCallback(() => {
    clearWatchdog()
    isGeneratingRef.current = false
    const s = useStore.getState()
    if (!s.isStreaming && !s.fusionActive) return

    // Interrompe imediatamente a geração no backend fechando o socket ativo;
    // o handler de onclose reconecta automaticamente com estado limpo.
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.close()
      } catch {
        /* ignore */
      }
    }

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
        isGenerating: false,
        streamingContent: '',
        fusionActive: false,
        processSteps: [],
        processStartedAt: null,
      })
    }
  }, [])

  const sendMessage = useCallback(
    (
      text: string,
      displayText?: string,
      attachmentIds?: string[],
      attachments?: Attachment[],
      voiceMode?: boolean,
      uiCorrectionMessageId?: string,
    ) => {
      if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
        console.warn('WebSocket not ready')
        useStore.getState().showToast(
          i18n.t('chat.wsNotReady', {
            defaultValue: 'Conexão em tempo real indisponível. Aguarde ou recarregue a página.',
          }),
          'error'
        )
        return false
      }
      if (!selectedModelId || !selectedProviderId) {
        console.warn('No model selected')
        return false
      }

      isGeneratingRef.current = true
      useStore.getState().setIsGenerating(true)
      resetWatchdog()

      // displayText: versão curta exibida no chat (ex: "✏️ Dashboard: adicionar dark mode")
      // text: prompt completo enviado ao modelo (inclui conteúdo do artifact)
      addUserMessage(displayText ?? text, attachments)

      // Armazena a última mensagem para retry
      useStore.getState().setLastUserMessage({
        text: displayText ?? text,
        conversationId: activeConversationId,
        modelId: selectedModelId,
        providerId: selectedProviderId,
        fusionMode: fusionMode,
        webSearchActive: webSearchActive,
        projectId: activeProjectId || null,
      })

      const safeAttachmentIds = (attachmentIds ?? []).filter(
        (id): id is string => typeof id === 'string' && id.length > 0
      )

      const activeEffort = useStore.getState().getActiveReasoningEffort()
      const isVoiceMode = voiceMode !== undefined ? voiceMode : getTalk().mode === 'loop'

      wsRef.current.send(
        JSON.stringify({
          conversation_id: activeConversationId,
          message: text,
          ui_correction_message_id: uiCorrectionMessageId,
          model_id: selectedModelId,
          provider_id: selectedProviderId,
          reasoning_effort: activeEffort || undefined,
          fusion: fusionMode,
          voice_mode: isVoiceMode ? true : undefined,
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
      return true
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
