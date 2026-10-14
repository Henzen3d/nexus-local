import type { Components } from 'react-markdown'
import { CodeBlock } from './CodeBlock'
import { isIntelligentUiEnabled } from '../ui/hooks/useIntelligentUi'

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

    // Com o Intelligent UI ligado, o fence nexus-ui não é código para o usuário:
    // o DynamicRenderer desenha o bloco. Desligado, mostra como código (comportamento antigo).
    if (className && /language-nexus(-ui)?(\/1)?\b/i.test(className) && isIntelligentUiEnabled()) {
      return null
    }

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
