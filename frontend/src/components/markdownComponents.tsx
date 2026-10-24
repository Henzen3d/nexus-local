import React from 'react'
import type { Components } from 'react-markdown'
import { CodeBlock } from './CodeBlock'
import { isIntelligentUiEnabled } from '../ui/hooks/useIntelligentUi'

/**
 * Componentes react-markdown compartilhados.
 * Blocos fenced (```lang) → CodeBlock (balão com header + copiar).
 * Código inline → .inline-code ou .markdown-badge-chip para tags [Item].
 *
 * Importante: não testar firstChild.type === 'code' no pre —
 * em react-markdown v9 o type é a função customizada, não a string 'code'.
 */
export const markdownComponents: Components = {
  pre({ children }) {
    // O <code> fenced já vira CodeBlock; evita <pre> aninhado.
    return <>{children}</>
  },
  code({ className, children, ...props }) {
    const raw = String(children).replace(/\n$/, '')
    // Fenced block: className language-xxx (ou só language- se lang vazio)
    const isFenced =
      Boolean(className && /language-/.test(className)) ||
      (raw.includes('\n') && raw.length > 40)

    // Com o Intelligent UI ligado, o fence nexus-ui não é código para o usuário:
    // o DynamicRenderer desenha o bloco. Desligado, mostra como código (comportamento antigo).
    if (className && /language-nexus(-ui)?(\/1)?\b/i.test(className) && isIntelligentUiEnabled()) {
      return null
    }

    if (isFenced) {
      return <CodeBlock language={className}>{raw}</CodeBlock>
    }

    // Padrão visual ChatGPT: Badges/chips como `[92 °C]` ou `[Opção 1]`
    const isBadge =
      typeof raw === 'string' &&
      raw.startsWith('[') &&
      raw.endsWith(']') &&
      raw.length >= 3 &&
      raw.length <= 40 &&
      !raw.includes('\n')

    if (isBadge) {
      return (
        <span className="markdown-badge-chip">
          {raw.slice(1, -1)}
        </span>
      )
    }

    return (
      <code className="inline-code" {...props}>
        {children}
      </code>
    )
  },
  li({ children, ...props }) {
    if (React.Children.count(children) > 0) {
      const childArray = React.Children.toArray(children)
      const first = childArray[0]
      if (typeof first === 'string') {
        const match = first.match(/^\[([^\]\n]{2,40})\]\s*(.*)$/s)
        if (match && !/^\s*x?\s*$/i.test(match[1])) {
          return (
            <li {...props}>
              <span className="markdown-badge-chip">{match[1]}</span>
              {match[2]}
              {childArray.slice(1)}
            </li>
          )
        }
      }
    }
    return <li {...props}>{children}</li>
  },
  table({ children, ...props }) {
    return (
      <div className="markdown-table-wrapper">
        <table className="markdown-table" {...props}>
          {children}
        </table>
      </div>
    )
  },
  img({ src, alt, ...props }) {
    if (!src) return null
    return (
      <span className="markdown-image-card">
        <img
          src={src}
          alt={alt || ''}
          loading="lazy"
          className="markdown-image"
          {...props}
          onError={(e) => {
            const target = e.currentTarget
            const parent = target.parentElement
            if (parent && parent.classList.contains('markdown-image-card')) {
              parent.style.display = 'none'
            } else {
              target.style.display = 'none'
            }
          }}
        />
        {alt && <span className="markdown-image-caption">{alt}</span>}
      </span>
    )
  },
  a({ href, children, ...props }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="markdown-link"
        {...props}
      >
        {children}
      </a>
    )
  },
}
