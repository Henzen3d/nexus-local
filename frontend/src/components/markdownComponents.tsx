import type { Components } from 'react-markdown'
import { CodeBlock } from './CodeBlock'

/**
 * Componentes react-markdown compartilhados.
 * Blocos fenced (```lang) → CodeBlock (balão com header + copiar).
 * Código inline → .inline-code.
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

    if (isFenced) {
      return <CodeBlock language={className}>{raw}</CodeBlock>
    }

    return (
      <code className="inline-code" {...props}>
        {children}
      </code>
    )
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
}
