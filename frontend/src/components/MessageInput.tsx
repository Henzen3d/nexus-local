import { useState, useRef, useEffect, useSyncExternalStore } from 'react'
import { Square, Mic, AudioLines, AlertCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { ModelSelector } from './ModelSelector'
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
  onSend: (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[], voiceMode?: boolean) => void
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

  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const {
    isStreaming,
    selectedModelId,
    showToast,
    activeConversationId,
    composerPrefill,
    setComposerPrefill,
    noteTyping,
  } = useStore()

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
  const canSend = hasContent && !!selectedModelId && !isStreaming

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

  // Foco no input ao montar ou trocar de conversa no desktop
  useEffect(() => {
    if (!isMobile) {
      textareaRef.current?.focus()
    }
  }, [activeConversationId, isMobile])

  // Retorna foco quando o streaming termina no desktop
  const prevIsStreaming = useRef(isStreaming)
  const prevEnhancing = useRef(enhancing)

  useEffect(() => {
    const wasBusy = prevIsStreaming.current || prevEnhancing.current
    const isBusy = isStreaming || enhancing

    if (wasBusy && !isBusy && !isMobile) {
      const timer = setTimeout(() => {
        textareaRef.current?.focus()
      }, 50)
      return () => clearTimeout(timer)
    }

    prevIsStreaming.current = isStreaming
    prevEnhancing.current = enhancing
  }, [isStreaming, enhancing, isMobile])

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

  const handleSend = () => {
    if (isStreaming || enhancing) return
    const trimmed = text.trim()
    if (!trimmed && attachments.length === 0) return
    if (!selectedModelId) {
      showToast(t('chat.selectModelPlaceholder'), 'error')
      return
    }

    const ids = attachments.map((a) => a.id).filter((id): id is string => !!id)
    if (attachments.length > 0 && ids.length === 0) {
      showToast(t('artifacts.uploadError', { defaultValue: 'Anexo inválido. Remova e anexe novamente.' }), 'error')
      return
    }
    onSend(
      trimmed || (ids.length > 0 ? t('chat.attachedFileOnly', { defaultValue: '(arquivo anexado)' }) : ''),
      undefined,
      ids.length > 0 ? ids : undefined,
      attachments.length > 0 ? attachments : undefined
    )
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

  const handleOpenFilePicker = () => {
    if (!selectedModelId) {
      showToast(t('artifacts.selectModelFirst', { defaultValue: 'Selecione um modelo antes de anexar arquivos' }), 'info')
      return
    }
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (!files || files.length === 0 || !selectedModelId) return
    const MAX_SIZE = 20 * 1024 * 1024 // 20MB
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i]
        if (file.size > MAX_SIZE) {
          throw new Error(t('artifacts.fileTooLarge', { name: file.name, defaultValue: `Arquivo ${file.name} excede o limite de 20MB.` }))
        }
        const res = await api.uploadAttachment(file, selectedModelId)
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
      {/* Input oculto para upload de arquivos através do menu '+' */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        style={{ display: 'none' }}
        multiple
        accept=".pdf,.docx,.txt,.csv,.md,.png,.jpg,.jpeg,.webp"
      />

      <div className={`input-card ${isCompact ? 'compact-mode' : 'empty-mode'} ${enhanceFlash ? 'enhance-flash' : ''}`}>
        {/* Camada 1: Preview de Anexos no topo */}
        {attachments.length > 0 && (
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
        )}

        {/* Camada 2: Linha / Área Unificada do Composer */}
        {isCompact ? (
          <div className="composer-single-line-row">
            <div className="composer-actions-left">
              <PlusActionMenu
                onOpenFilePicker={handleOpenFilePicker}
                onEnhance={handleEnhance}
                enhancing={enhancing}
                hasText={!!text.trim()}
                enhancerReady={enhancerReady}
                disabled={isStreaming}
              />
            </div>

            <textarea
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
                  onEnhance={handleEnhance}
                  enhancing={enhancing}
                  hasText={!!text.trim()}
                  enhancerReady={enhancerReady}
                  disabled={isStreaming}
                />
              </div>

              <div className="composer-actions-right">
                {isEmpty && <ModelSelector />}
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
            <ModelSelector compact />
          </div>
        </div>
      )}
    </div>
  )
}
