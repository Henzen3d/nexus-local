import { useState, useRef, useEffect, useSyncExternalStore } from 'react'
import { Square, Mic, AudioLines, AlertCircle, Settings, RefreshCw, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { hasEligibleRoute } from '../lib/modelSelection'
import { clearComposerDraft, loadComposerDraft, saveComposerDraft } from '../lib/draftPersistence'
import { ModelSelector } from './ModelSelector'
import { SimpleModeSelector } from './SimpleModeSelector'
import { PlusActionMenu } from './PlusActionMenu'
import { AttachmentChip } from './AttachmentChip'
import { useIsMobile } from '../hooks/useIsMobile'
import { useVisualViewportOffset } from '../hooks/useVisualViewportOffset'
import type { Attachment } from '../types'
import { api } from '../api/client'
import {
  applyDecision,
  createSpeechSession,
  getTalk,
  onFinalTranscript,
  onMicTap,
  onTalkToggle,
  speechRecognitionCtor,
  subscribeTalk,
} from '../lib/talkLoop'
import { stopSpeech } from '../lib/ttsPlayer'

interface Props {
  onSend: (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[], voiceMode?: boolean) => boolean | void
  onStop?: () => void
  isEmpty?: boolean
}

export function MessageInput({ onSend, onStop, isEmpty = false }: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [enhancing, setEnhancing] = useState(false)
  const [enhancerEnabled, setEnhancerEnabled] = useState(true)
  const [enhancerConfigured, setEnhancerConfigured] = useState(false)
  const [enhanceFlash, setEnhanceFlash] = useState(false)
  const [enhanceError, setEnhanceError] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [isMultiline, setIsMultiline] = useState(false)
  const [resolvingRoute, setResolvingRoute] = useState(false)

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const photoInputRef = useRef<HTMLInputElement>(null)
  const cameraInputRef = useRef<HTMLInputElement>(null)

  const {
    isStreaming,
    selectedModelId,
    models,
    modelsStatus,
    loadModels,
    openSettings,
    user,
    showToast,
    activeConversationId,
    activeProjectId,
    composerPrefill,
    setComposerPrefill,
    noteTyping,
    uiLevel,
  } = useStore()

  // Persistência e restauração de rascunho por (userId, conversationId, projectId)
  const draftStateRef = useRef({
    userId: user?.id ?? null,
    convId: activeConversationId ?? null,
    projId: activeProjectId ?? null,
    text: '',
    attachments: [] as Attachment[],
  })

  useEffect(() => {
    const uid = user?.id ?? null
    const restored = loadComposerDraft(uid, activeConversationId, activeProjectId)
    if (restored) {
      setText(restored.text)
      setAttachments(restored.attachments)
    } else if (!useStore.getState().composerPrefill) {
      setText('')
      setAttachments([])
    }
    draftStateRef.current = {
      userId: uid,
      convId: activeConversationId ?? null,
      projId: activeProjectId ?? null,
      text: restored?.text ?? '',
      attachments: restored?.attachments ?? [],
    }
  }, [user?.id, activeConversationId, activeProjectId])

  useEffect(() => {
    draftStateRef.current = {
      userId: user?.id ?? null,
      convId: activeConversationId ?? null,
      projId: activeProjectId ?? null,
      text,
      attachments,
    }
    const timer = setTimeout(() => {
      saveComposerDraft(user?.id, activeConversationId, activeProjectId, { text, attachments })
    }, 150)
    return () => clearTimeout(timer)
  }, [text, attachments, user?.id, activeConversationId, activeProjectId])

  useEffect(() => {
    const flushNow = () => {
      const cur = draftStateRef.current
      saveComposerDraft(cur.userId, cur.convId, cur.projId, {
        text: cur.text,
        attachments: cur.attachments,
      })
    }
    window.addEventListener('beforeunload', flushNow)
    window.addEventListener('pagehide', flushNow)
    return () => {
      window.removeEventListener('beforeunload', flushNow)
      window.removeEventListener('pagehide', flushNow)
      flushNow()
    }
  }, [])

  // Pré-preenchimento vindo do assistente proativo ("Quero saber mais")
  useEffect(() => {
    if (!composerPrefill) return
    setText(composerPrefill)
    setComposerPrefill(null)
    requestAnimationFrame(() => {
      const ta = textareaRef.current
      if (!ta) return
      ta.focus()
      ta.setSelectionRange(ta.value.length, ta.value.length)
    })
  }, [composerPrefill, setComposerPrefill])

  const isMobile = useIsMobile()
  const keyboardOffset = useVisualViewportOffset()
  const talk = useSyncExternalStore(subscribeTalk, getTalk)
  const onSendRef = useRef(onSend)
  onSendRef.current = onSend
  const seenConv = useRef(activeConversationId)

  const isCompact = !isEmpty
  const isListening = talk.phase === 'listening'
  const hasContent = text.trim().length > 0 || attachments.length > 0
  const enhancerReady = enhancerEnabled && enhancerConfigured
  const catalogExhausted = modelsStatus === 'ready' && !hasEligibleRoute(models)
  const noRouteState: 'loading' | 'error' | 'empty' | 'exhausted' | null =
    modelsStatus === 'error'
      ? 'error'
      : modelsStatus === 'empty'
      ? 'empty'
      : catalogExhausted
      ? 'exhausted'
      : (modelsStatus === 'loading' || resolvingRoute) && !selectedModelId
      ? 'loading'
      : !selectedModelId && modelsStatus === 'ready'
      ? 'exhausted'
      : null
  const canSend = hasContent && !isStreaming && !enhancing && !resolvingRoute

  useEffect(() => {
    const prev = seenConv.current
    seenConv.current = activeConversationId
    if (prev && prev !== activeConversationId) {
      applyDecision({ type: 'exit', next: { mode: 'off', phase: 'idle' } })
    }
  }, [activeConversationId])

  useEffect(() => {
    if (talk.phase !== 'listening') return
    const Ctor = speechRecognitionCtor(window)
    if (!Ctor) {
      showToast(t('chat.micUnsupported', { defaultValue: 'Voz só no Chrome.' }), 'error')
      applyDecision({ type: 'exit', next: { mode: 'off', phase: 'idle' } })
      return
    }
    let gotFinal = false
    const session = createSpeechSession(Ctor, {
      onInterim: (heard) => setText(heard),
      onFinal: (heard) => {
        gotFinal = true
        const cur = getTalk()
        const decision = onFinalTranscript(cur, heard)
        const modelId = useStore.getState().selectedModelId
        if (decision.type === 'send' && !modelId) {
          showToast(t('chat.selectModelPlaceholder'), 'error')
          applyDecision(
            cur.mode === 'loop'
              ? { type: 'listen', next: { mode: 'loop', phase: 'listening' } }
              : { type: 'exit', next: { mode: 'off', phase: 'idle' } },
          )
          setText('')
          return
        }
        if (decision.type === 'send' && useStore.getState().isStreaming) {
          applyDecision({ type: 'exit', next: { mode: 'off', phase: 'idle' } })
          setText('')
          return
        }
        applyDecision(decision)
        setText('')
        if (decision.type === 'send') onSendRef.current(decision.text, undefined, undefined, undefined, cur.mode === 'loop')
      },
      onError: (code) => {
        if (code === 'aborted' || code === 'no-speech') return
        showToast(
          code === 'not-allowed'
            ? t('chat.micDenied', { defaultValue: 'Permita o microfone no Chrome.' })
            : t('chat.micUnsupported', { defaultValue: 'Voz só no Chrome.' }),
          'error',
        )
        applyDecision({ type: 'exit', next: { mode: 'off', phase: 'idle' } })
      },
      onEnd: () => {
        if (gotFinal) return
        const cur = getTalk()
        if (cur.mode === 'loop' && cur.phase === 'listening') {
          applyDecision({ type: 'listen', next: { mode: 'loop', phase: 'listening' } })
          return
        }
        if (cur.phase === 'listening') {
          applyDecision({ type: 'exit', next: { mode: 'off', phase: 'idle' } })
        }
      },
    })
    try {
      session.start()
    } catch {
      showToast(t('chat.micUnsupported', { defaultValue: 'Voz só no Chrome.' }), 'error')
      applyDecision({ type: 'exit', next: { mode: 'off', phase: 'idle' } })
      return
    }
    return () => session.abort()
  }, [talk.epoch, talk.phase, showToast, t])

  // Foco no input ao montar ou trocar de conversa
  useEffect(() => {
    textareaRef.current?.focus()
  }, [activeConversationId, isMobile])

  // Retorna foco quando o streaming termina no desktop
  const prevIsStreaming = useRef(isStreaming)
  const prevEnhancing = useRef(enhancing)

  useEffect(() => {
    const wasBusy = prevIsStreaming.current || prevEnhancing.current
    const isBusy = isStreaming || enhancing

    if (wasBusy && !isBusy) {
      const timer = setTimeout(() => {
        textareaRef.current?.focus()
      }, 50)
      return () => clearTimeout(timer)
    }

    prevIsStreaming.current = isStreaming
    prevEnhancing.current = enhancing
  }, [isStreaming, enhancing])

  useEffect(() => {
    api.getEnhancerConfig().then((cfg) => {
      setEnhancerEnabled(cfg.enhancer_enabled)
      setEnhancerConfigured(!!cfg.enhancer_provider_id && !!cfg.enhancer_model_id)
    }).catch(() => {})
  }, [])

  // Auto-expansão vertical com teto estrito de 200px
  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    const newHeight = Math.min(ta.scrollHeight, 200)
    ta.style.height = `${newHeight}px`
    setIsMultiline(ta.scrollHeight > 200 || (ta.scrollHeight > (isCompact ? 36 : 48) && text.includes('\n')))
  }, [text, isCompact])

  const ensureRouteReady = async (): Promise<string | null> => {
    const cur = useStore.getState()
    if (cur.selectedModelId) return cur.selectedModelId
    if (cur.modelsStatus === 'idle' || cur.modelsStatus === 'loading' || cur.modelsStatus === 'error') {
      setResolvingRoute(true)
      try {
        await loadModels()
      } finally {
        setResolvingRoute(false)
      }
      return useStore.getState().selectedModelId
    }
    return null
  }

  const handleSend = async () => {
    if (isStreaming || enhancing || resolvingRoute) return
    const trimmed = text.trim()
    if (!trimmed && attachments.length === 0) return
    const resolvedModelId = await ensureRouteReady()
    if (!resolvedModelId) {
      const latestStatus = useStore.getState().modelsStatus
      const msg =
        latestStatus === 'error'
          ? t('chat.routeLoadErrorToast', { defaultValue: 'Não foi possível carregar o catálogo de modelos. Tente novamente.' })
          : t('chat.noRouteAvailableToast', { defaultValue: 'Nenhuma rota de modelo disponível. Configure um provedor ou chave para enviar.' })
      showToast(msg, 'error')
      return
    }

    const ids = attachments.map((a) => a.id).filter((id): id is string => !!id)
    if (attachments.length > 0 && ids.length === 0) {
      showToast(t('artifacts.uploadError', { defaultValue: 'Anexo inválido. Remova e anexe novamente.' }), 'error')
      return
    }
    const sent = onSend(
      trimmed || (ids.length > 0 ? t('chat.attachedFileOnly', { defaultValue: '(arquivo anexado)' }) : ''),
      undefined,
      ids.length > 0 ? ids : undefined,
      attachments.length > 0 ? attachments : undefined
    )
    if (sent === false) return
    clearComposerDraft(user?.id, activeConversationId, activeProjectId)
    draftStateRef.current.text = ''
    draftStateRef.current.attachments = []
    setText('')
    setAttachments([])
  }

  const handleEnhance = async () => {
    const trimmed = text.trim()
    if (!trimmed || enhancing) return
    setEnhancing(true)
    setEnhanceError(null)
    try {
      const res = await api.enhancePrompt(trimmed)
      if (res.enhanced_prompt) {
        setText(res.enhanced_prompt)
        setEnhanceFlash(true)
        setTimeout(() => setEnhanceFlash(false), 500)
        textareaRef.current?.focus()
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('chat.enhanceError')
      setEnhanceError(msg)
      setTimeout(() => setEnhanceError(null), 4000)
    } finally {
      setEnhancing(false)
    }
  }

  const handleOpenFilePicker = async () => {
    if (!(await ensureRouteReady())) {
      showToast(t('artifacts.selectModelFirst', { defaultValue: 'Configure um provedor ou chave de API antes de anexar arquivos' }), 'info')
      return
    }
    fileInputRef.current?.click()
  }

  const handleOpenPhotoPicker = async () => {
    if (!(await ensureRouteReady())) {
      showToast(t('artifacts.selectModelFirst', { defaultValue: 'Configure um provedor ou chave de API antes de anexar fotos' }), 'info')
      return
    }
    photoInputRef.current?.click()
  }

  const handleOpenCameraPicker = async () => {
    if (!(await ensureRouteReady())) {
      showToast(t('artifacts.selectModelFirst', { defaultValue: 'Configure um provedor ou chave de API antes de usar a câmera' }), 'info')
      return
    }
    cameraInputRef.current?.click()
  }

  const handleOpenLibrary = () => {
    useStore.getState().setView('library')
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    const activeModelId = files && files.length > 0 ? await ensureRouteReady() : null
    if (!files || files.length === 0 || !activeModelId) return
    const MAX_SIZE = 20 * 1024 * 1024 // 20MB
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        if (file.size > MAX_SIZE) {
          throw new Error(t('artifacts.fileTooLarge', { name: file.name, defaultValue: `Arquivo ${file.name} excede o limite de 20MB.` }))
        }
        const res = await api.uploadAttachment(file, activeModelId)
        setAttachments((prev) => [...prev, res])
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : t('artifacts.uploadError')
      showToast(msg, 'error')
    } finally {
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    // Enter envia a mensagem; Shift+Enter insere quebra de linha normal.
    // Ignora composição IME (acentos, CJK em composição).
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleSend()
    }
  }

  const wrapperStyle =
    isMobile && keyboardOffset > 0
      ? { paddingBottom: `calc(8px + env(safe-area-inset-bottom, 0px) + ${keyboardOffset}px)` }
      : undefined

  // Máquina de estados da Fase 3 para o botão de ação à direita
  const renderRightActions = () => {
    // 1. Durante streaming: exibe botão Parar conectado a onStop
    if (isStreaming) {
      return (
        <button
          type="button"
          className="btn-send-enter btn-stop-stream touch-target custom-tooltip-trigger tooltip-up action-swap-fade"
          onClick={onStop}
          data-tooltip={t('chat.stop', { defaultValue: 'Parar geração' })}
          aria-label={t('chat.stop', { defaultValue: 'Parar geração' })}
        >
          <Square size={13} fill="currentColor" />
        </button>
      )
    }

    // 2. Durante escuta de voz ativa: mantém botões de voz mesmo com texto intermediário
    if (isListening) {
      return (
        <div className="action-transition-slot action-swap-fade">
          <button
            type="button"
            className={`composer-tool-btn touch-target ${talk.mode === 'once' ? 'listening' : ''}`}
            onClick={() => {
              stopSpeech()
              applyDecision(onMicTap(getTalk()))
            }}
            aria-label={t('chat.mic', { defaultValue: 'Falar' })}
            data-tooltip={t('chat.micStop', { defaultValue: 'Parar gravação' })}
          >
            <Mic size={16} />
          </button>
          <button
            type="button"
            className={`composer-tool-btn touch-target ${talk.mode === 'loop' ? 'listening' : ''}`}
            onClick={() => {
              stopSpeech()
              applyDecision(onTalkToggle(getTalk()))
            }}
            aria-pressed={talk.mode === 'loop'}
            aria-label={t('chat.talkLoop', { defaultValue: 'Conversar' })}
            data-tooltip={t('chat.talkLoop', { defaultValue: 'Conversar' })}
          >
            <AudioLines size={16} />
          </button>
        </div>
      )
    }

    // 3. Com conteúdo (texto ou anexos): exibe o botão Enter (↵ - Opção A)
    if (hasContent) {
      return (
        <button
          type="button"
          className="btn-send-enter touch-target custom-tooltip-trigger tooltip-up action-swap-fade"
          onClick={handleSend}
          disabled={!canSend}
          data-tooltip={t('chat.send', { defaultValue: 'Enviar (Enter)' })}
          aria-label={t('chat.send', { defaultValue: 'Enviar (Enter)' })}
        >
          <span className="enter-glyph" aria-hidden="true">↵</span>
        </button>
      )
    }

    // 4. Vazio em repouso: exibe controles de voz
    return (
      <div className="action-transition-slot action-swap-fade">
        <button
          type="button"
          className="composer-tool-btn touch-target"
          onClick={() => {
            stopSpeech()
            applyDecision(onMicTap(getTalk()))
          }}
          aria-label={t('chat.mic', { defaultValue: 'Falar' })}
          data-tooltip={t('chat.mic', { defaultValue: 'Falar' })}
        >
          <Mic size={16} />
        </button>
        <button
          type="button"
          className="composer-tool-btn touch-target"
          onClick={() => {
            stopSpeech()
            applyDecision(onTalkToggle(getTalk()))
          }}
          aria-pressed={false}
          aria-label={t('chat.talkLoop', { defaultValue: 'Conversar' })}
          data-tooltip={t('chat.talkLoop', { defaultValue: 'Conversar' })}
        >
          <AudioLines size={16} />
        </button>
      </div>
    )
  }

  return (
    <div className="input-wrapper" style={wrapperStyle}>
      {/* Inputs ocultos para upload de arquivos através do menu '+' */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        multiple
        accept=".pdf,.docx,.txt,.csv,.md,.json,.xml,.yaml,.yml,.png,.jpg,.jpeg,.webp"
      />
      <input
        type="file"
        ref={photoInputRef}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        multiple
        accept="image/*"
      />
      <input
        type="file"
        ref={cameraInputRef}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        accept="image/*"
        capture="environment"
      />

      <div className={`input-card ${isCompact ? 'compact-mode' : 'empty-mode'} ${enhanceFlash ? 'enhance-flash' : ''}`}>
        {noRouteState && (noRouteState !== 'loading' || hasContent || resolvingRoute) && (
          <div className={`route-status-banner route-status-${noRouteState}`} role="status" aria-live="polite">
            <div className="route-status-text">
              {noRouteState === 'loading' ? (
                <Loader2 size={14} className="spin" aria-hidden="true" />
              ) : (
                <AlertCircle size={14} aria-hidden="true" />
              )}
              <span>
                {noRouteState === 'loading'
                  ? t('chat.routeLoading', { defaultValue: 'Carregando rotas de IA…' })
                  : noRouteState === 'error'
                  ? t('chat.routeErrorInline', { defaultValue: 'Não foi possível carregar os modelos disponíveis.' })
                  : noRouteState === 'exhausted'
                  ? t('chat.routeExhaustedInline', { defaultValue: 'Todas as rotas configuradas atingiram a cota atual.' })
                  : user?.role === 'admin'
                  ? t('chat.routeEmptyAdmin', { defaultValue: 'Nenhuma rota de modelo disponível. Configure um provedor ou chave de API.' })
                  : t('chat.routeEmptyUser', { defaultValue: 'Nenhuma rota disponível no momento. Adicione sua chave pessoal ou aguarde.' })}
              </span>
            </div>
            {noRouteState !== 'loading' && (
              <div className="route-status-actions">
                <button
                  type="button"
                  className="route-status-btn"
                  onClick={() => openSettings('providers')}
                >
                  <Settings size={12} aria-hidden="true" />
                  <span>
                    {user?.role === 'admin'
                      ? t('chat.configureProvidersBtn', { defaultValue: 'Configurar provedores' })
                      : t('chat.configureKeysBtn', { defaultValue: 'Minhas chaves' })}
                  </span>
                </button>
                <button
                  type="button"
                  className="route-status-btn secondary"
                  onClick={() => void loadModels()}
                >
                  <RefreshCw size={12} aria-hidden="true" />
                  <span>{t('common.retry', { defaultValue: 'Recarregar' })}</span>
                </button>
              </div>
            )}
          </div>
        )}
        {/* Camada 1: Preview de Anexos no topo */}
        {attachments.length > 0 && (
          <>
            <div className="input-attachments-preview">
              {attachments.map((att) => (
                <AttachmentChip
                  key={att.id}
                  attachment={att}
                  onRemove={() => {
                    setAttachments((prev) => prev.filter((x) => x.id !== att.id))
                  }}
                />
              ))}
            </div>
            {attachments.some((a) => a.file_type === 'image') && selectedModelId && selectedModelId !== 'auto' && (() => {
              const selModel = models.find((m) => m.id === selectedModelId)
              if (!selModel) return null
              return (
                <div className="attachment-vision-hint">
                  <span>
                    {selModel.supports_vision
                      ? t('chat.visionNativeHint', { defaultValue: 'Leitura visual nativa neste modelo' })
                      : t('chat.visionRelayHint', { defaultValue: 'Sem visão nativa — usará Vision Relay se disponível' })}
                  </span>
                </div>
              )
            })()}
          </>
        )}

        {/* Camada 2: Linha / Área Unificada do Composer */}
        {isCompact ? (
          <div className="composer-single-line-row">
            <div className="composer-actions-left">
              <PlusActionMenu
                onOpenFilePicker={handleOpenFilePicker}
                onOpenPhotoPicker={handleOpenPhotoPicker}
                onOpenCameraPicker={handleOpenCameraPicker}
                onOpenLibrary={handleOpenLibrary}
                onEnhance={handleEnhance}
                enhancing={enhancing}
                hasText={!!text.trim()}
                enhancerReady={enhancerReady}
                disabled={isStreaming}
              />
            </div>

            <textarea
              id="composer-input"
              ref={textareaRef}
              className="composer-textarea composer-textarea-inline"
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                noteTyping()
              }}
              onKeyDown={handleKey}
              placeholder={
                talk.phase === 'listening'
                  ? t('chat.micListening', { defaultValue: 'Ouvindo…' })
                  : !selectedModelId
                  ? t('chat.selectModelPlaceholder')
                  : t('chat.writeMessage')
              }
              disabled={isStreaming || enhancing}
              rows={1}
              enterKeyHint="send"
            />

            <div className="composer-actions-right">
              {renderRightActions()}
            </div>
          </div>
        ) : (
          <div className="composer-multiline-container">
            <textarea
              id="composer-input"
              ref={textareaRef}
              className={`composer-textarea ${isMultiline ? 'is-multiline' : ''}`}
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                noteTyping()
              }}
              onKeyDown={handleKey}
              placeholder={
                talk.phase === 'listening'
                  ? t('chat.micListening', { defaultValue: 'Ouvindo…' })
                  : !selectedModelId
                  ? t('chat.selectModelPlaceholder')
                  : t('chat.writeMessage')
              }
              disabled={isStreaming || enhancing}
              rows={1}
              enterKeyHint="send"
            />

            <div className="composer-multiline-toolbar">
              <div className="composer-actions-left">
                <PlusActionMenu
                  onOpenFilePicker={handleOpenFilePicker}
                  onOpenPhotoPicker={handleOpenPhotoPicker}
                  onOpenCameraPicker={handleOpenCameraPicker}
                  onOpenLibrary={handleOpenLibrary}
                  onEnhance={handleEnhance}
                  enhancing={enhancing}
                  hasText={!!text.trim()}
                  enhancerReady={enhancerReady}
                  disabled={isStreaming}
                />
              </div>

              <div className="composer-actions-right">
                {isEmpty && (uiLevel === 'simple' ? <SimpleModeSelector /> : <ModelSelector />)}
                {renderRightActions()}
              </div>
            </div>
          </div>
        )}
      </div>

      {enhanceError && (
        <p className="enhance-error">
          <AlertCircle size={12} />
          {enhanceError}
        </p>
      )}

      {/* Camada 3: Rodapé Externo Unificado */}
      {!isEmpty && (
        <div className="input-footer-row">
          <span className="input-footer-disclaimer">
            {t('chat.inputHint', {
              defaultValue: 'O NexusLocal é uma IA e pode cometer erros. Por favor, verifique as fontes citadas.',
            })}
          </span>
          <div className="input-footer-model">
            {uiLevel === 'simple' ? <SimpleModeSelector compact /> : <ModelSelector compact />}
          </div>
        </div>
      )}
    </div>
  )
}
