const fs = require('fs')
const p = 'J:/Arquivos Osmar/Multi+/frontend/src/components/MessageBubble.tsx'
let s = fs.readFileSync(p, 'utf8')

if (!s.includes('react-i18next')) {
  s = s.replace(
    "import ReactMarkdown from 'react-markdown'\n",
    "import ReactMarkdown from 'react-markdown'\nimport { useTranslation } from 'react-i18next'\nimport i18n from '../i18n'\n"
  )
}

s = s.replace(
  `function ThinkingBlock({ content, isThinking, durationLabel }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(false) // Fechado por padrão
  const bodyRef = useRef<HTMLDivElement>(null)

  // Anima a expansão suavemente usando grid-template-rows
  const statusLabel = isThinking ? 'Pensando...' : durationLabel ?? 'Concluído'

  if (!content && !isThinking) return null

  return (
    <div className="thinking-block">
      <button
        type="button"
        className="thinking-header"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        title={isOpen ? 'Recolher raciocínio' : 'Expandir raciocínio'}
      >
        <span className="thinking-status">
          <AIStatusIndicator
            status={isThinking ? 'thinking' : 'completed'}
            label={isThinking ? 'Pensando...' : (durationLabel ?? 'Concluído')}
          />
        </span>`,
  `function ThinkingBlock({ content, isThinking, durationLabel }: ThinkingBlockProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false) // Fechado por padrão
  const bodyRef = useRef<HTMLDivElement>(null)

  // Anima a expansão suavemente usando grid-template-rows
  const statusLabel = isThinking ? t('chat.thinking') : durationLabel ?? t('chat.done')

  if (!content && !isThinking) return null

  return (
    <div className="thinking-block">
      <button
        type="button"
        className="thinking-header"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        title={isOpen ? t('chat.collapseThinking') : t('chat.expandThinking')}
      >
        <span className="thinking-status">
          <AIStatusIndicator
            status={isThinking ? 'thinking' : 'completed'}
            label={isThinking ? t('chat.thinking') : (durationLabel ?? t('chat.done'))}
          />
        </span>`
)

s = s.replace(
  "return `Documento estruturado **${mdArt?.title || 'Markdown'}** gerado com sucesso.`",
  "return i18n.t('chat.structuredDoc', { title: mdArt?.title || i18n.t('chat.markdownDefault') })"
)

s = s.replace(
  `const getFriendlyTypeName = (type: string) => {
  switch (type) {
    case 'html': return 'Código · HTML'
    case 'markdown': return 'Documento · MD'
    case 'svg': return 'Imagem · SVG'
    case 'jsx': return 'Componente · React'
    default: return 'Código · Fonte'
  }
}`,
  `const getFriendlyTypeName = (type: string) => {
  switch (type) {
    case 'html': return i18n.t('chat.typeHtml')
    case 'markdown': return i18n.t('chat.typeMd')
    case 'svg': return i18n.t('chat.typeSvg')
    case 'jsx': return i18n.t('chat.typeJsx')
    default: return i18n.t('chat.typeDefault')
  }
}`
)

s = s.replace(
  "data-tooltip={`Provedor: ${provider ?? 'Desconhecido'} · Modelo: ${modelId}`}",
  "data-tooltip={i18n.t('chat.providerModel', { provider: provider ?? i18n.t('chat.unknown'), model: modelId })}"
)

s = s.replace(
  `function WebSearchSources({ sources, query }: { sources: { title: string; url: string }[]; query?: string }) {
  const [isOpen, setIsOpen] = useState(false)`,
  `function WebSearchSources({ sources, query }: { sources: { title: string; url: string }[]; query?: string }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)`
)

s = s.replace(
  'title="Ver fontes consultadas na busca web"',
  "title={t('chat.sourcesTitle')}"
)

s = s.replace(
  "<span>🌐 {sources.length} {sources.length === 1 ? 'fonte consultada' : 'fontes consultadas'}</span>",
  "<span>🌐 {t('chat.sourcesCount', { count: sources.length })}</span>"
)

s = s.replace(
  `              Consulta efetuada: <strong>"{query}"</strong>`,
  `              {t('chat.queryMade')} <strong>"{query}"</strong>`
)

s = s.replace(
  'export function MessageBubble({ message }: Props) {\n  const [copied, setCopied] = useState(false)',
  "export function MessageBubble({ message }: Props) {\n  const { t } = useTranslation()\n  const [copied, setCopied] = useState(false)"
)

s = s.replace(
  '<div className="error-title">Erro na geração da resposta</div>',
  "<div className=\"error-title\">{t('chat.generationError')}</div>"
)

s = s.replace(
  "title: message.artifact_title || 'Visualizar Artifact'",
  "title: message.artifact_title || t('chat.viewArtifact')"
)

s = s.replace(
  `                  {lastCacheHit.type === 'exact'
                    ? <><Zap size={11} /> Cache exato</>
                    : <><Sparkles size={11} /> Cache semântico·{(lastCacheHit.similarity * 100).toFixed(1)}%</>
                  }`,
  `                  {lastCacheHit.type === 'exact'
                    ? <><Zap size={11} /> {t('chat.cacheExactBadge')}</>
                    : <><Sparkles size={11} /> {t('chat.cacheSemanticBadge', { pct: (lastCacheHit.similarity * 100).toFixed(1) })}</>
                  }`
)

s = s.replace(
  '<RefreshCw size={11} /> Failover',
  "<RefreshCw size={11} /> {t('chat.failover')}"
)

s = s.replace(
  '<span>Imagem interpretada via {message.relay_model}</span>',
  "<span>{t('chat.imageViaRelay', { model: message.relay_model })}</span>"
)

s = s.replace(
  `                            >
                              Baixar
                            </button>`,
  `                            >
                              {t('chat.download')}
                            </button>`
)

s = s.replace(
  `                        <Download size={14} />
                        Baixar tudo
                      </button>`,
  `                        <Download size={14} />
                        {t('chat.downloadAll')}
                      </button>`
)

s = s.replace(
  "data-tooltip={copied ? 'Copiado!' : 'Copiar'}",
  "data-tooltip={copied ? t('common.copied') : t('common.copy')}"
)

s = s.replace(
  'export function StreamingBubble({ content }: { content: string }) {\n  const lastCacheHit = useStore((s) => s.lastCacheHit)',
  "export function StreamingBubble({ content }: { content: string }) {\n  const { t } = useTranslation()\n  const lastCacheHit = useStore((s) => s.lastCacheHit)"
)

s = s.replace(
  `            {lastCacheHit.type === 'exact'
              ? <><Zap size={11} /> Cache exato</>
              : <><Sparkles size={11} /> Cache semântico·{(lastCacheHit.similarity * 100).toFixed(1)}%</>
            }`,
  `            {lastCacheHit.type === 'exact'
              ? <><Zap size={11} /> {t('chat.cacheExactBadge')}</>
              : <><Sparkles size={11} /> {t('chat.cacheSemanticBadge', { pct: (lastCacheHit.similarity * 100).toFixed(1) })}</>
            }`
)

fs.writeFileSync(p, s)
console.log('MessageBubble patched OK')

// leftover Portuguese UI strings check
const leftovers = []
const patterns = [
  'Pensando', 'Concluído', 'Baixar', 'Cache exato', 'fonte consultada',
  'Erro na geração', 'Copiado!', 'Recolher', 'Expandir', 'Imagem interpretada',
  'Ver fontes', 'Consulta efetuada', 'Visualizar Artifact', 'Código · HTML',
]
for (const ptn of patterns) {
  if (s.includes(ptn)) leftovers.push(ptn)
}
console.log('leftovers:', leftovers)
