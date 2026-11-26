import { useEffect, useRef, useCallback } from 'react'
import i18n from '../i18n'
import { useStore } from '../store/useStore'
import { useShallow } from 'zustand/react/shallow'
import { getTalk } from '../lib/talkLoop'
import { usePresence } from './usePresence'
import { decodeChatFrame, isStreamEndSuccess, isTurnProgressFrame } from '../lib/chatProtocol'
import type { WSMessage, Attachment, ChatRequest } from '../types'

const AUTH_CLOSE_CODE = 4001
const MAX_RETRY_MS = 30_000
const BASE_RETRY_MS = 1_000
/** Keepalive em ambos os sentidos — evita idle-timeout do Cloudflare Tunnel (~100s) */
const HEARTBEAT_MS = 25_000

let turnCounter = 0
function nextTurnId(): string {
  if (globalThis.crypto?.randomUUID) return `turn-${globalThis.crypto.randomUUID()}`
  turnCounter += 1
  return `turn-${Date.now()}-${turnCounter}`
}

let lastPartialPersistAt = 0

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
  const activeTurnIdRef = useRef<string | null>(null)
  const activeTurnSocketRef = useRef<WebSocket | null>(null)
  const activeTurnConvIdRef = useRef<string | null>(null)
  const watchdogTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearWatchdog = useCallback(() => {
    if (watchdogTimerRef.current != null) {
      clearTimeout(watchdogTimerRef.current)
      watchdogTimerRef.current = null
    }
  }, [])

  const clearTurnBinding = useCallback(() => {
    activeTurnIdRef.current = null
    activeTurnSocketRef.current = null
    activeTurnConvIdRef.current = null
  }, [])

  const resetWatchdog = useCallback(() => {
    clearWatchdog()
    if (!isGeneratingRef.current) return
    const boundTurnId = activeTurnIdRef.current
    watchdogTimerRef.current = setTimeout(() => {
      if (!isGeneratingRef.current || activeTurnIdRef.current !== boundTurnId) return
      const stalledSocket = activeTurnSocketRef.current
      isGeneratingRef.current = false
      clearTurnBinding()
      const s = useStore.getState()
      const hadActivity = s.activeStreamTurnId === boundTurnId
      s.discardStreamDraft()
      // A server that does not echo turn IDs can still be running this turn.
      // Retire the socket before allowing another request.
      stalledSocket?.close()
      if (hadActivity) {
        const timeoutMsg = i18n.t('chat.streamTimeout', {
          defaultValue: 'Tempo limite de resposta excedido. O modelo não respondeu.',
        })
        s.showToast(timeoutMsg, 'error')
        s.addErrorMessage(timeoutMsg)
      }
    }, 90000)
  }, [clearWatchdog, clearTurnBinding])

  const sendTurn = useCallback((request: ChatRequest) => {
    const socket = wsRef.current
    if (isGeneratingRef.current || !socket || socket.readyState !== WebSocket.OPEN) return false

    const turnId = nextTurnId()
    const store = useStore.getState()
    store.beginStreamTurn(turnId, request.conversation_id)
    activeTurnIdRef.current = turnId
    activeTurnSocketRef.current = socket
    activeTurnConvIdRef.current = request.conversation_id
    isGeneratingRef.current = true
    resetWatchdog()
    try {
      socket.send(JSON.stringify({ ...request, turn_id: turnId }))
      store.setLastUserMessage(request)
      store.setPendingTurn({
        request,
        userDisplayText: request.message,
        conversationId: request.conversation_id ?? null,
        projectId: request.project_id ?? null,
        status: 'sending',
        partialContent: '',
        updatedAt: Date.now(),
      })
      return true
    } catch {
      clearWatchdog()
      isGeneratingRef.current = false
      clearTurnBinding()
      store.discardStreamDraft()
      return false
    }
  }, [resetWatchdog, clearWatchdog, clearTurnBinding])

  const retryMessage = useCallback((reasoningEffort?: string, expectedRequestId?: string) => {
    const { lastUserMessage, pendingTurn, activeConversationId } = useStore.getState()
    const targetReq =
      lastUserMessage && activeConversationId === lastUserMessage.conversation_id
        ? lastUserMessage
        : pendingTurn &&
          (!pendingTurn.conversationId || pendingTurn.conversationId === activeConversationId) &&
          (!expectedRequestId || pendingTurn.request.request_id === expectedRequestId)
        ? pendingTurn.request
        : null
    if (!targetReq) return false
    if (expectedRequestId && targetReq.request_id !== expectedRequestId) return false
    return sendTurn(reasoningEffort ? { ...targetReq, reasoning_effort: reasoningEffort } : targetReq)
  }, [sendTurn])

  const {
    selectedModelId,
    selectedProviderId,
    fusionMode,
    addUserMessage,
    token,
    webSearchActive,
    activeProjectId,
  } = useStore(useShallow((s) => ({
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

    const retryOptionsFor = (requestId?: string) => requestId ? {
      durationMs: 15000,
      action: {
        label: i18n.t('chat.retry', { defaultValue: 'Tentar novamente' }),
        onClick: () => {
          if (retryMessage(undefined, requestId)) useStore.getState().hideToast()
        },
      },
    } : undefined

    const handleMessage = (ws: WebSocket, e: MessageEvent) => {
      if (disposed || socket !== ws) return

      const msg: WSMessage | null = decodeChatFrame(typeof e.data === 'string' ? e.data : '')
      if (!msg) {
        console.warn('[WS] ignored invalid or malformed frame')
        return
      }

      // Heartbeat / handshake — não mexe no estado do chat
      if (msg.type === 'ready') {
        // Socket novo: o backend perdeu o estado anterior → reenvia presença (F3.4.2) e reconcilia turno pendente
        resendPresence()
        void useStore.getState().reconcilePendingTurn()
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

      // Isolamento por turno e socket: descarta frames de turnos/sockets antigos
      const incomingTurnId = 'turn_id' in msg ? msg.turn_id : undefined
      if (incomingTurnId && activeTurnIdRef.current && incomingTurnId !== activeTurnIdRef.current) {
        return
      }
      if (activeTurnSocketRef.current && activeTurnSocketRef.current !== ws) {
        return
      }

      const isTurnProgress = isTurnProgressFrame(msg.type)
      if (!isGeneratingRef.current && (isTurnProgress || msg.type === 'stream_end' || msg.type === 'conversation_created')) {
        return
      }

      // Lê actions frescas do store (evita recriar o socket a cada re-render).
      const s = useStore.getState()
      const boundConvId = activeTurnConvIdRef.current
      const ownsDraft = s.activeStreamTurnId !== null && s.activeStreamTurnId === activeTurnIdRef.current
      const isViewingTurnConversation = ownsDraft && s.activeConversationId === boundConvId
      const retryRequestId = isViewingTurnConversation ? s.lastUserMessage?.request_id : undefined
      if (isTurnProgress && boundConvId && 'conversation_id' in msg &&
          msg.conversation_id && msg.conversation_id !== boundConvId) return
      if (isTurnProgress && !isViewingTurnConversation) {
        // Keep the transport alive while the user is looking at another chat,
        // but never restart a draft whose prefix was discarded on navigation.
        resetWatchdog()
        return
      }

      switch (msg.type) {
        case 'request_ack': {
          if (activeTurnConvIdRef.current === null) {
            activeTurnConvIdRef.current = msg.conversation_id
          }
          if (s.lastUserMessage && s.lastUserMessage.request_id === msg.request_id && s.lastUserMessage.conversation_id === null) {
            s.setLastUserMessage({ ...s.lastUserMessage, conversation_id: msg.conversation_id })
          }
          if (s.pendingTurn && (!msg.request_id || s.pendingTurn.request.request_id === msg.request_id)) {
            s.setPendingTurn({
              ...s.pendingTurn,
              conversationId: msg.conversation_id,
              userMessageId: msg.user_message_id,
              status: 'streaming',
              request: { ...s.pendingTurn.request, conversation_id: msg.conversation_id },
              updatedAt: Date.now(),
            })
          }
          break
        }
        case 'conversation_created':
          if (activeTurnConvIdRef.current === null) {
            activeTurnConvIdRef.current = msg.conversation_id
            if (s.lastUserMessage?.conversation_id === null) {
              s.setLastUserMessage({ ...s.lastUserMessage, conversation_id: msg.conversation_id })
            }
          }
          if (isViewingTurnConversation) {
            s.setConversationCreated(msg.conversation_id, msg.title)
          } else {
            s.loadConversations()
          }
          break
        case 'stream_start':
          resetWatchdog()
          if (activeTurnConvIdRef.current === null) {
            activeTurnConvIdRef.current = msg.conversation_id
          }
          if (isViewingTurnConversation) {
            s.beginProcess(i18n.t('chat.generatingResponse', { defaultValue: 'Gerando resposta…' }))
            s.setIsGenerating(false)
          }
          break
        case 'stream_clear':
          // Failover mid-stream: o modelo anterior já emitiu tokens e falhou;
          // limpa apenas o rascunho do candidato atual para o próximo modelo não misturar respostas.
          if (isViewingTurnConversation) {
            s.clearStreamDraft()
          }
          break
        case 'token':
          resetWatchdog()
          if (isViewingTurnConversation) {
            if (s.isGenerating) {
              s.setIsGenerating(false)
            }
            s.appendToken(msg.content, msg.turn_id ?? activeTurnIdRef.current)
            const nowMs = Date.now()
            if (s.pendingTurn && nowMs - lastPartialPersistAt >= 750) {
              lastPartialPersistAt = nowMs
              s.setPendingTurn({
                ...s.pendingTurn,
                status: 'streaming',
                partialContent: `${s.streamingContent || s.pendingTurn.partialContent || ''}${msg.content}`,
                updatedAt: nowMs,
              })
            }
          }
          break
        case 'stream_end':
          clearWatchdog()
          isGeneratingRef.current = false
          clearTurnBinding()
          if (!isStreamEndSuccess(msg)) {
            const capturedPartial = msg.partial_content ?? s.streamingContent ?? s.pendingTurn?.partialContent ?? ''
            // Terminal de falha/vazio/timeout: destrava compositor e descarta rascunho sem criar bolha sem ID
            s.discardStreamDraft()
            if (s.pendingTurn) {
              s.setPendingTurn({
                ...s.pendingTurn,
                conversationId: msg.conversation_id ?? s.pendingTurn.conversationId,
                status: msg.outcome === 'cancelled' || msg.turn_status === 'stopped' ? 'stopped' : 'failed',
                partialContent: capturedPartial,
                errorMessage: msg.message ?? s.pendingTurn.errorMessage ?? null,
                updatedAt: Date.now(),
              })
            }
            s.loadConversations()
            const persistedPartial = msg.reason === 'judge_partial_timeout' && msg.conversation_id
            if (persistedPartial && s.activeConversationId === msg.conversation_id) {
              void s.loadConversation(persistedPartial).catch(() => {})
            }
            if (isViewingTurnConversation && msg.message) {
              s.showToast(msg.message, 'error', retryOptionsFor(retryRequestId))
              if (!persistedPartial) s.addErrorMessage(msg.message)
            }
            break
          }
          if (!isViewingTurnConversation || (s.activeConversationId && msg.conversation_id !== s.activeConversationId)) {
            s.discardStreamDraft()
            s.setPendingTurn(null)
            if (s.activeConversationId === msg.conversation_id) {
              // The user returned before completion and only saw persisted turns.
              void s.loadConversation(msg.conversation_id).catch(() => {})
            }
            s.loadConversations()
            break
          }
          if (msg.finish_reason === 'image_pending' || msg.finish_reason === 'already_completed') {
            // image_pending already inserted the placeholder with this ID.
            s.discardStreamDraft()
            s.setPendingTurn(null)
            if (msg.finish_reason === 'already_completed' || !s.messages.some((message) => message.id === msg.message_id)) {
              void s.loadConversation(msg.conversation_id).catch(() => {})
            }
            s.loadConversations()
            break
          }
          useStore.getState().setIsGenerating(false)
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
            msg.attempt_count,
            msg.memory_used,
            msg.memory_none_relevant,
            msg.relay_status
          )
          s.hideToast('failover-notice')
          s.loadConversations()
          break
        case 'ui_progress':
          s.handleUiProgress(msg.block)
          break
        case 'triage_decision':
          // Decisão de triagem rápida do Pré-Router (< 200ms)
          break
        case 'auto_route_decision':
          s.setAutoRouteDecision(msg)
          break
        case 'failover_notice': {
          resetWatchdog()
          const reasonKey = msg.reason || 'error'
          const defaultReason = reasonKey === 'rate_limit'
            ? 'limite de requisições excedido'
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
            : reasonKey === 'quota_exhausted' || reasonKey === 'quota' || reasonKey === 'credit_gate' || reasonKey === 'insufficient_user_quota'
            ? 'crédito indisponível no provedor'
            : reasonKey === 'model_unavailable' || reasonKey === 'unavailable'
            ? 'modelo temporariamente indisponível'
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
            'info',
            { id: 'failover-notice' }
          )
          break
        }
        case 'search_start':
          if (s.isGenerating) {
            s.setIsGenerating(false)
          }
          // Só inicia a etapa sintética se ainda não existirem etapas de busca específicas por consulta (T3.3)
          if (!s.processSteps.some((st) => st.type === 'search' && st.id !== 'web-search')) {
            s.startProcessStep({
              id: 'web-search',
              type: 'search',
              title: i18n.t('chat.processSearching'),
              detail: msg.query,
              status: 'running',
            })
          }
          break
        case 'tool_executing': {
          if (s.isGenerating) {
            s.setIsGenerating(false)
          }
          const famTitle = i18n.t(`chat.toolFamily.${msg.family}`, {
            defaultValue: msg.family,
          })
          if (!s.processSteps.some((st) => st.id === `tool-${msg.family}`)) {
            s.startProcessStep({
              id: `tool-${msg.family}`,
              type: 'tool',
              title: famTitle,
              detail: msg.action,
              status: 'running',
            })
          }
          break
        }
        case 'tool_executed': {
          const metaParts: string[] = []
          if (msg.provider) metaParts.push(msg.provider)
          if (msg.cached) metaParts.push('cache')
          if (msg.fallback) metaParts.push('fallback')
          s.updateProcessStep(`tool-${msg.family}`, {
            status: 'completed',
            ...(metaParts.length > 0 ? { detail: metaParts.join(' · ') } : {}),
          })
          break
        }
        case 'tool_failed':
          s.updateProcessStep(`tool-${msg.family}`, {
            status: 'failed',
            detail: i18n.t('chat.toolFailedDetail', {
              defaultValue: 'Não foi possível consultar esta ferramenta',
            }),
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
          clearTurnBinding()
          console.error('[WS error]', msg.message)
          s.discardStreamDraft()
          s.showToast(
            msg.message,
            'error',
            retryOptionsFor(retryRequestId)
          )
          if (isViewingTurnConversation) s.addErrorMessage(msg.message)
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
        if (disposed || socket !== ws) return
        attempt = 0
        startHeartbeat(ws)
        // Presença é reenviada ao receber `ready` (socket registrado no backend)
      }

      ws.onmessage = (ev) => handleMessage(ws, ev)

      ws.onerror = () => {
        if (disposed || socket !== ws) return
        // onclose always follows; keep logging light to avoid console spam.
        if (attempt === 0) {
          console.warn('[WS] connection error')
        }
      }

      ws.onclose = (ev) => {
        if (socket !== ws) return
        clearWatchdog()
        clearHeartbeat()
        isGeneratingRef.current = false
        clearTurnBinding()
        if (wsRef.current === ws) wsRef.current = null
        if (socket === ws) socket = null

        // Nunca deixar a UI presa em "Fusion ativo" / streaming / isGenerating (mesmo antes do stream_start)
        const st = useStore.getState()
        const hadActiveTurn = st.fusionActive || st.isStreaming || st.isGenerating
        const dropPartial = st.streamingContent || st.pendingTurn?.partialContent || ''
        st.discardStreamDraft()
        if (hadActiveTurn) {
          if (st.pendingTurn) {
            st.setPendingTurn({
              ...st.pendingTurn,
              status: 'incomplete',
              partialContent: dropPartial,
              updatedAt: Date.now(),
            })
          }
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
      isGeneratingRef.current = false
      clearTurnBinding()
      useStore.getState().discardStreamDraft()
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
  }, [token, resendPresence, clearWatchdog, clearTurnBinding, resetWatchdog, retryMessage])

  const stopStream = useCallback(() => {
    clearWatchdog()
    isGeneratingRef.current = false
    clearTurnBinding()
    const s = useStore.getState()
    if (!s.isStreaming && !s.isGenerating && !s.fusionActive) return

    // Inclui tokens ainda agrupados no próximo frame antes de decidir se há
    // uma resposta parcial para preservar.
    s.flushStreamDraft()
    const current = useStore.getState()
    const stopTurnId = activeTurnIdRef.current
    const stopReqId = current.lastUserMessage?.request_id || current.pendingTurn?.request.request_id

    // Interrompe imediatamente a geração no backend avisando parada e fechando o socket ativo;
    // o handler de onclose reconecta automaticamente com estado limpo.
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      try {
        if (stopTurnId || stopReqId) {
          wsRef.current.send(JSON.stringify({ type: 'stop_turn', turn_id: stopTurnId, request_id: stopReqId }))
        }
        wsRef.current.close()
      } catch {
        /* ignore */
      }
    }

    if (current.pendingTurn) {
      current.setPendingTurn({
        ...current.pendingTurn,
        status: 'stopped',
        partialContent: current.streamingContent || current.pendingTurn.partialContent || '',
        updatedAt: Date.now(),
      })
    }

    if (current.streamingContent.trim()) {
      // Preserva a resposta parcial gerada até o momento da parada
      current.finalizeStream(
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
        current.processStartedAt ? Date.now() - current.processStartedAt : undefined
      )
    } else {
      // Nenhum texto não-vazio gerado ainda — descarta rascunho completo via ação única
      current.discardStreamDraft()
    }
  }, [clearWatchdog, clearTurnBinding])

  const sendMessage = useCallback(
    (
      text: string,
      displayText?: string,
      attachmentIds?: string[],
      attachments?: Attachment[],
      voiceMode?: boolean,
      uiCorrectionMessageId?: string,
    ) => {
      if (isGeneratingRef.current) return false
      const socket = wsRef.current
      if (!socket || socket.readyState !== WebSocket.OPEN) {
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

      const safeAttachmentIds = (attachmentIds ?? []).filter(
        (id): id is string => typeof id === 'string' && id.length > 0
      )

      const activeEffort = useStore.getState().getActiveReasoningEffort()
      const isVoiceMode = voiceMode !== undefined ? voiceMode : getTalk().mode === 'loop'

      if (!sendTurn({
          request_id: nextTurnId(),
          conversation_id: useStore.getState().activeConversationId,
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
      })) return false
      addUserMessage(displayText ?? text, attachments)
      return true
    },
    [
      selectedModelId,
      selectedProviderId,
      fusionMode,
      addUserMessage,
      webSearchActive,
      activeProjectId,
      sendTurn,
    ]
  )

  return { sendMessage, stopStream, retryMessage }
}
