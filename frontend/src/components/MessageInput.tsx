import { useState, useRef, useEffect } from 'react'
import { Send, Square, Sparkles, Loader2, AlertCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from '../store/useStore'
import { ModelSelector } from './ModelSelector'
import { api } from '../api/client'
import { AttachmentButton } from './AttachmentButton'
import { AttachmentChip } from './AttachmentChip'
import { WebSearchToggle } from './WebSearchToggle'
import type { Attachment } from '../types'

interface Props {
  onSend: (text: string, displayText?: string, attachmentIds?: string[], attachments?: Attachment[]) => void
}

export function MessageInput({ onSend }: Props) {
  const { t } = useTranslation()
  const [text, setText] = useState('')
  const [enhancing, setEnhancing] = useState(false)
  const [enhancerEnabled, setEnhancerEnabled] = useState(true)
  const [enhancerConfigured, setEnhancerConfigured] = useState(false)
  const [enhanceFlash, setEnhanceFlash] = useState(false)
  const [enhanceError, setEnhanceError] = useState<string | null>(null)
  const [attachments, setAttachments] = useState<Attachment[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const { isStreaming, selectedModelId } = useStore()

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
    
    const ids = attachments.map((a) => a.id)
    onSend(trimmed, undefined, ids.length > 0 ? ids : undefined, attachments.length > 0 ? attachments : undefined)
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
    } catch (err: any) {
      const msg = err?.message || t('chat.enhanceError')
      setEnhanceError(msg)
      setTimeout(() => setEnhanceError(null), 4000)
    } finally {
      setEnhancing(false)
    }
  }

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const canSend = (!!text.trim() || attachments.length > 0) && !!selectedModelId && !isStreaming
  const enhancerReady = enhancerEnabled && enhancerConfigured

  return (
    <div className="input-wrapper">
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
                alert(err)
              }}
              disabled={isStreaming}
            />
            {enhancerEnabled && (
              <button
                className={`enhance-btn ${enhancing ? 'loading' : ''}`}
                onClick={handleEnhance}
                disabled={!text.trim() || enhancing || isStreaming}
                title={
                  !enhancerReady
                    ? t('chat.enhanceNotConfigured')
                    : t('chat.enhanceTitle')
                }
                style={{ marginRight: '4px' }}
              >
                {enhancing ? <Loader2 size={15} className="spin" /> : <Sparkles size={15} />}
              </button>
            )}
            <div style={{ display: 'inline-flex', alignSelf: 'center' }}>
              <WebSearchToggle />
            </div>
          </div>
          <div className="input-actions-right">
            <ModelSelector />
            <button
              className={`send-btn ${isStreaming ? 'stop' : ''}`}
              onClick={handleSend}
              disabled={!isStreaming && !canSend}
              title={isStreaming ? t('chat.stop') : t('chat.send')}
            >
              {isStreaming ? <Square size={15} fill="currentColor" /> : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>

      {enhanceError && (
        <p className="enhance-error">
          <AlertCircle size={12} />
          {enhanceError}
        </p>
      )}

      <p className="input-hint">
        {t('chat.inputHint')}
      </p>
    </div>
  )
}
