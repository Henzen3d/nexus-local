import { useState, useCallback, useMemo } from 'react'
import { Copy, Check } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'

interface CodeBlockProps {
  language?: string
  children: string
}

import { highlightCode } from '../lib/codeHighlight'
export { highlightCode } from '../lib/codeHighlight'

export function CodeBlock({ language, children }: CodeBlockProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'code' | 'preview'>('code')
  const [hovered, setHovered] = useState(false)

  const handleCopy = useCallback(() => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(children)
        .then(() => {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        })
        .catch((err) => {
          console.warn('[Clipboard] writeText failed:', err)
          setCopied(false)
        })
    } else {
      try {
        const textarea = document.createElement('textarea')
        textarea.value = children
        textarea.style.position = 'fixed'
        textarea.style.opacity = '0'
        document.body.appendChild(textarea)
        textarea.select()
        const success = document.execCommand('copy')
        document.body.removeChild(textarea)
        if (success) {
          setCopied(true)
          setTimeout(() => setCopied(false), 2000)
        }
      } catch (err) {
        console.warn('[Clipboard] execCommand failed:', err)
        setCopied(false)
      }
    }
  }, [children])

  const cleanLang = (language?.replace(/^language-/, '') || '').trim().toLowerCase()
  const langLabel = cleanLang || t('chat.code', { defaultValue: 'code' })
  const isMarkdown = cleanLang === 'markdown' || cleanLang === 'md'
  const highlighted = useMemo(
    () => highlightCode(children, cleanLang),
    [children, cleanLang]
  )

  return (
    <div
      className="code-block"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div className="code-block-header">
        <div className="code-block-tabs">
          <span className="code-lang">{langLabel}</span>
          {isMarkdown && (
            <div className="code-tab-group">
              <button
                type="button"
                className={`code-tab-btn ${activeTab === 'preview' ? 'active' : ''}`}
                onClick={() => setActiveTab('preview')}
              >
                {t('chat.preview', { defaultValue: 'Prévia' })}
              </button>
              <button
                type="button"
                className={`code-tab-btn ${activeTab === 'code' ? 'active' : ''}`}
                onClick={() => setActiveTab('code')}
              >
                {t('chat.code', { defaultValue: 'Código' })}
              </button>
            </div>
          )}
        </div>
        <button
          type="button"
          className={`code-copy-btn custom-tooltip-trigger ${hovered || copied ? 'is-visible' : ''}`}
          onClick={handleCopy}
          aria-label={copied ? t('common.copied', { defaultValue: 'Copiado' }) : t('chat.copyCode', { defaultValue: 'Copiar código' })}
          data-tooltip={copied ? t('common.copied', { defaultValue: 'Copiado' }) : t('chat.copyCode', { defaultValue: 'Copiar código' })}
        >
          {copied ? <Check size={14} strokeWidth={2} /> : <Copy size={14} strokeWidth={1.75} />}
        </button>
      </div>

      {isMarkdown && activeTab === 'preview' ? (
        <div className="markdown-preview-container">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{children}</ReactMarkdown>
        </div>
      ) : (
        <pre className="code-block-pre">
          <code
            className={language ?? `language-${cleanLang}`}
            dangerouslySetInnerHTML={{ __html: highlighted }}
          />
        </pre>
      )}
    </div>
  )
}
