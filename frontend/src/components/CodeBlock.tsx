import { useState, useCallback, useMemo } from 'react'
import { Copy, Check } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'

interface CodeBlockProps {
  language?: string
  children: string
}

const KW: Record<string, string[]> = {
  ts: [
    'import', 'from', 'export', 'default', 'const', 'let', 'var', 'function',
    'return', 'if', 'else', 'for', 'while', 'class', 'interface', 'type',
    'extends', 'implements', 'async', 'await', 'new', 'this', 'true', 'false',
    'null', 'undefined', 'as', 'of', 'in', 'void', 'typeof', 'keyof',
  ],
  js: [],
  py: [
    'def', 'class', 'import', 'from', 'return', 'if', 'elif', 'else', 'for',
    'while', 'with', 'as', 'try', 'except', 'finally', 'True', 'False', 'None',
    'async', 'await', 'yield', 'lambda', 'pass', 'raise', 'and', 'or', 'not',
    'in', 'is', 'break', 'continue', 'global', 'nonlocal', 'assert', 'del',
  ],
}
KW.typescript = KW.ts
KW.javascript = KW.ts
KW.tsx = KW.ts
KW.jsx = KW.ts
KW.python = KW.py

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/** Highlight leve (sem deps) — strings, comentários, keywords, tags. */
export function highlightCode(code: string, lang: string): string {
  const L = lang.toLowerCase()
  // Tokenize roughly: comments / strings first via placeholder map
  const parts: { type: string; text: string }[] = []
  let i = 0
  const push = (type: string, text: string) => {
    if (text) parts.push({ type, text })
  }

  while (i < code.length) {
    // line comment //
    if (
      (code[i] === '/' && code[i + 1] === '/') &&
      !['py', 'python', 'bash', 'sh', 'yaml', 'yml'].includes(L)
    ) {
      const end = code.indexOf('\n', i)
      const endIdx = end === -1 ? code.length : end
      push('comment', code.slice(i, endIdx))
      i = endIdx
      continue
    }
    // block comment /* */
    if (code[i] === '/' && code[i + 1] === '*') {
      const end = code.indexOf('*/', i + 2)
      const endIdx = end === -1 ? code.length : end + 2
      push('comment', code.slice(i, endIdx))
      i = endIdx
      continue
    }
    // hash comment
    if (
      code[i] === '#' &&
      (i === 0 || code[i - 1] === '\n' || /\s/.test(code[i - 1])) &&
      ['py', 'python', 'bash', 'sh', 'shell', 'yaml', 'yml'].includes(L)
    ) {
      const end = code.indexOf('\n', i)
      const endIdx = end === -1 ? code.length : end
      push('comment', code.slice(i, endIdx))
      i = endIdx
      continue
    }
    // strings
    if (code[i] === '"' || code[i] === "'" || code[i] === '`') {
      const q = code[i]
      let j = i + 1
      while (j < code.length) {
        if (code[j] === '\\') {
          j += 2
          continue
        }
        if (code[j] === q) {
          j++
          break
        }
        if (q !== '`' && code[j] === '\n') break
        j++
      }
      push('string', code.slice(i, j))
      i = j
      continue
    }
    // plain chunk until special
    let j = i + 1
    while (
      j < code.length &&
      code[j] !== '"' &&
      code[j] !== "'" &&
      code[j] !== '`' &&
      !(code[j] === '/' && (code[j + 1] === '/' || code[j + 1] === '*')) &&
      !(code[j] === '#' && ['py', 'python', 'bash', 'sh', 'shell', 'yaml', 'yml'].includes(L))
    ) {
      j++
    }
    push('plain', code.slice(i, j))
    i = j
  }

  const kwList = KW[L] || []
  const kwRe = kwList.length ? new RegExp(`\\b(${kwList.join('|')})\\b`, 'g') : null

  return parts
    .map(({ type, text }) => {
      const e = escapeHtml(text)
      if (type === 'comment') return `<span class="tok-comment">${e}</span>`
      if (type === 'string') return `<span class="tok-string">${e}</span>`
      let out = e
      if (kwRe) {
        out = out.replace(kwRe, '<span class="tok-kw">$1</span>')
      }
      if (['html', 'xml', 'svg', 'jsx', 'tsx'].includes(L)) {
        out = out.replace(
          /(&lt;\/?)([A-Za-z][\w.-]*)/g,
          '$1<span class="tok-tag">$2</span>'
        )
      }
      return out
    })
    .join('')
}

export function CodeBlock({ language, children }: CodeBlockProps) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'code' | 'preview'>('code')
  const [hovered, setHovered] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(children).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }, [children])

  const cleanLang = (language?.replace(/^language-/, '') || '').trim().toLowerCase()
  const langLabel = cleanLang || 'code'
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
