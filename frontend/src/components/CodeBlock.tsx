import { useState, useCallback } from 'react'
import { Copy, Check } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'

interface CodeBlockProps {
  language?: string
  children: string
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'code' | 'preview'>('preview')

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [children])

  const cleanLang = language?.replace(/^language-/, '') || ''
  const langLabel = cleanLang || 'code'
  const isMarkdown = cleanLang === 'markdown' || cleanLang === 'md'

  return (
    <div className="code-block">
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
                {t('chat.preview')}
              </button>
              <button
                type="button"
                className={`code-tab-btn ${activeTab === 'code' ? 'active' : ''}`}
                onClick={() => setActiveTab('code')}
              >
                {t('chat.code')}
              </button>
            </div>
          )}
        </div>
        <button
          type="button"
          className="code-copy-btn"
          onClick={handleCopy}
          aria-label={copied ? t('common.copied') : t('chat.copyCode')}
          title={copied ? t('common.copied') : t('chat.copyCode')}
        >
          {copied
            ? <><Check size={13} /><span>{t('common.copied').replace('!', '')}</span></>
            : <><Copy size={13} /><span>{t('common.copy')}</span></>
          }
        </button>
      </div>

      {isMarkdown && activeTab === 'preview' ? (
        <div className="markdown-preview-container">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>
            {children}
          </ReactMarkdown>
        </div>
      ) : (
        <pre className="code-block-pre">
          <code className={language ?? ''}>{children}</code>
        </pre>
      )}
    </div>
  )
}
