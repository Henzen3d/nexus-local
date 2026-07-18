import { useState, useRef, useEffect } from 'react'
import { ArrowUp, Square, Sparkles, Loader2, AlertCircle, Wrench, Globe } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { ModelSelector } from './ModelSelector'
import { api } from '../api/client'
import { AttachmentButton } from './AttachmentButton'
import { AttachmentChip } from './AttachmentChip'
import { WebSearchToggle } from './WebSearchToggle'
import { Button } from './ui/Button'
import { BottomSheet } from './ui/BottomSheet'
import { useIsMobile } from '../hooks/useIsMobile'
import { useVisualViewportOffset } from '../hooks/useVisualViewportOffset'
import type { Attachment } from '../types'

interface Props {
  onSend: (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[]) => void
  isEmpty?: boolean
}

export function MessageInput({ onSend, isEmpty = false }: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [enhancing, setEnhancing] = useState(false)
  const [enhancerEnabled, setEnhancerEnabled] = useState(true)
  const [enhancerConfigured, setEnhancerConfigured] = useState(false)
  const [enhanceFlash, setEnhanceFlash] = useState(false)
  const [enhanceError, setEnhanceError] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const [toolsOpen, setToolsOpen] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const {
    isStreaming,
    selectedModelId,
    webSearchActive,
    setWebSearchActive,
    showToast,
    activeConversationId,
  } = useStore()
  const isMobile = useIsMobile()
  const keyboardOffset = useVisualViewportOffset()

  // Focus the input on mount or when conversation changes on desktop
  useEffect(() => {
    if (!isMobile) {
      textareaRef.current?.focus()
    }
  }, [activeConversationId, isMobile])

  // Focus the input when streaming or enhancing ends on desktop
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

  useEffect(() => {
    const ta = textareaRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 200) + 'px'
  }, [text])

  const handleSend = () => {
    if (isStreaming || enhancing) return
    const trimmed = text.trim()
    if (!trimmed && attachments.length === 0) return
    if (!selectedModelId) return

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

  const handleKey = (e: React.KeyboardEvent) => {
    // Mobile: Enter inserts newline; send only via button
    if (isMobile) return
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const canSend = (!!text.trim() || attachments.length > 0) && !!selectedModelId && !isStreaming
  const enhancerReady = enhancerEnabled && enhancerConfigured
  const toolsActiveCount = webSearchActive ? 1 : 0

  const wrapperStyle =
    isMobile && keyboardOffset > 0
      ? { paddingBottom: `calc(8px + env(safe-area-inset-bottom, 0px) + ${keyboardOffset}px)` }
      : undefined

  return (
    <div className="input-wrapper" style={wrapperStyle}>
      <div className={`input-card ${enhanceFlash ? 'enhance-flash' : ''}`}>
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
        <div className="input-textarea-row">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKey}
            placeholder={
              !selectedModelId
                ? t('chat.selectModelPlaceholder')
                : t('chat.writeMessage')
            }
            disabled={isStreaming || enhancing}
            rows={1}
            enterKeyHint={isMobile ? 'enter' : 'send'}
          />
        </div>

        <div className="input-actions-row">
          <div className="input-actions-left">
            <AttachmentButton
              currentModelId={selectedModelId}
              onUploadStart={() => {}}
              onUploadSuccess={(att) => {
                setAttachments((prev) => [...prev, att])
              }}
              onUploadError={(err) => {
                showToast(err, 'error')
              }}
              disabled={isStreaming}
            />

            {/* Desktop: all tools inline */}
            {!isMobile && (
              <>
                {enhancerEnabled && (
                  <Button
                    variant="ghost"
                    size="icon"
                    className={`composer-tool-btn custom-tooltip-trigger tooltip-up ${enhancing ? 'loading' : ''}`}
                    onClick={handleEnhance}
                    disabled={!text.trim() || enhancing || isStreaming}
                    data-tooltip={
                      !enhancerReady
                        ? t('chat.enhanceNotConfigured')
                        : t('chat.enhanceTitle')
                    }
                    aria-label={t('chat.enhanceTitle')}
                  >
                    {enhancing ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
                  </Button>
                )}
                <WebSearchToggle />
              </>
            )}

            {/* Mobile: overflow into tools sheet */}
            {isMobile && (
              <button
                type="button"
                className={`composer-tools-btn touch-target ${toolsActiveCount > 0 ? 'has-active' : ''}`}
                onClick={() => setToolsOpen(true)}
                disabled={isStreaming}
                aria-label={t('chat.toolsTitle', { defaultValue: 'Ferramentas' })}
              >
                <Wrench size={16} />
                {toolsActiveCount > 0 && (
                  <span className="composer-tools-badge">{toolsActiveCount}</span>
                )}
              </button>
            )}
          </div>
          <div className="input-actions-right">
            <ModelSelector />
            <Button
              variant={isStreaming ? 'secondary' : 'primary'}
              size="icon"
              className="custom-tooltip-trigger tooltip-up send-btn-target"
              onClick={handleSend}
              disabled={!isStreaming && !canSend}
              data-tooltip={isStreaming ? t('chat.stop') : t('chat.send')}
              aria-label={isStreaming ? t('chat.stop') : t('chat.send')}
            >
              {isStreaming ? (
                <Square size={12} fill="currentColor" />
              ) : (
                <ArrowUp size={16} strokeWidth={2.5} />
              )}
            </Button>
          </div>
        </div>
      </div>

      {enhanceError && (
        <p className="enhance-error">
          <AlertCircle size={12} />
          {enhanceError}
        </p>
      )}

      {!isEmpty && (
        <p className="input-hint">
          {t('chat.inputHint')}
        </p>
      )}

      <BottomSheet
        open={toolsOpen && isMobile}
        onClose={() => setToolsOpen(false)}
        title={t('chat.toolsTitle', { defaultValue: 'Ferramentas' })}
      >
        <div className="composer-tools-sheet">
          {enhancerEnabled && (
            <button
              type="button"
              className="composer-tool-row"
              disabled={!text.trim() || enhancing || isStreaming || !enhancerReady}
              onClick={async () => {
                await handleEnhance()
                setToolsOpen(false)
              }}
            >
              <span className="composer-tool-icon">
                {enhancing ? <Loader2 size={18} className="spin" /> : <Sparkles size={18} />}
              </span>
              <span className="composer-tool-text">
                <span className="composer-tool-label">{t('chat.enhanceTitle')}</span>
                <span className="composer-tool-desc">
                  {!enhancerReady
                    ? t('chat.enhanceNotConfigured')
                    : t('chat.enhanceDesc', { defaultValue: 'Reescreve e melhora seu prompt' })}
                </span>
              </span>
            </button>
          )}

          <button
            type="button"
            className={`composer-tool-row ${webSearchActive ? 'active' : ''}`}
            onClick={() => setWebSearchActive(!webSearchActive)}
          >
            <span className="composer-tool-icon">
              <Globe size={18} />
            </span>
            <span className="composer-tool-text">
              <span className="composer-tool-label">
                {webSearchActive ? t('chat.webSearchOn') : t('chat.webSearchOff')}
              </span>
              <span className="composer-tool-desc">
                {t('chat.webSearchDesc', { defaultValue: 'Consulta a web durante a resposta' })}
              </span>
            </span>
            <span className={`composer-tool-switch ${webSearchActive ? 'on' : ''}`} aria-hidden />
          </button>
        </div>
      </BottomSheet>
    </div>
  )
}
