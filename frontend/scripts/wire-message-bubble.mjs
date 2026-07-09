import fs from 'fs'

const path = 'src/components/MessageBubble.tsx'
let s = fs.readFileSync(path, 'utf8')

if (!s.includes('useTranslation')) {
  s = s.replace(
    "import type { Message } from '../types'",
    "import { useTranslation } from 'react-i18next'\nimport i18n from '../i18n'\nimport type { Message } from '../types'"
  )
}

// ThinkingBlock
s = s.replace(
  'function ThinkingBlock({ content, isThinking, durationLabel }: ThinkingBlockProps) {\n  const [isOpen, setIsOpen] = useState(false) // Fechado por padrão\n  const bodyRef = useRef<HTMLDivElement>(null)\n\n  // Anima a expansão suavemente usando grid-template-rows\n  const statusLabel = isThinking ? \'Pensando...\' : durationLabel ?? \'Concluído\'',
  `function ThinkingBlock({ content, isThinking, durationLabel }: ThinkingBlockProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  const statusLabel = isThinking ? t('chat.thinking') : durationLabel ?? t('chat.done')`
)

s = s.replace(
  "title={isOpen ? 'Recolher raciocínio' : 'Expandir raciocínio'}",
  "title={isOpen ? t('chat.collapseThinking') : t('chat.expandThinking')}"
)
s = s.replace(
  "label={isThinking ? 'Pensando...' : (durationLabel ?? 'Concluído')}",
  "label={isThinking ? t('chat.thinking') : (durationLabel ?? t('chat.done'))}"
)

// getFriendlyTypeName - use i18n outside component
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
  'function WebSearchSources({ sources, query }: { sources: { title: string; url: string }[]; query?: string }) {\n  const [isOpen, setIsOpen] = useState(false)',
  `function WebSearchSources({ sources, query }: { sources: { title: string; url: string }[]; query?: string }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)`
)

s = s.replace(
  'title="Ver fontes consultadas na busca web"',
  "title={t('chat.sourcesTitle')}"
)

s = s.replace(
  `<span>🌐 {sources.length} {sources.length === 1 ? 'fonte consultada' : 'fontes consultadas'}</span>`,
  `<span>🌐 {t(sources.length === 1 ? 'chat.sourcesCount_one' : 'chat.sourcesCount_other', { count: sources.length })}</span>`
)

s = s.replace(
  'Consulta efetuada: <strong>"{query}"</strong>',
  `{t('chat.queryMade')} <strong>"{query}"</strong>`
)

// cleanContent structured doc message
s = s.replace(
  'return `Documento estruturado **${mdArt?.title || \'Markdown\'}** gerado com sucesso.`',
  "return i18n.t('chat.structuredDoc', { title: mdArt?.title || 'Markdown' })"
)

// MessageBubble main - add useTranslation if export function MessageBubble
if (s.includes('export function MessageBubble') && !s.includes("export function MessageBubble") === false) {
  // check if MessageBubble already has t
}

// Common remaining PT strings in file
const pairs = [
  ["title=\"Copiar\"", "title={t('common.copy')}"],
  ["title=\"Baixar\"", "title={t('chat.download')}"],
  ["'Erro na geração da resposta'", "t('chat.generationError')"],
  ["'Visualizar Artifact'", "t('chat.viewArtifact')"],
  ["'Cache exato'", "t('chat.cacheExactBadge')"],
  ["'Imagem interpretada via'", "/* image via */"],
]

// StreamingBubble labels
s = s.replace(/Pensando\.\.\./g, (match, offset) => {
  // only replace string literals still hardcoded
  return match
})

// More careful remaining
s = s.replace(
  /\{copied \? 'Copiado!' : 'Copiar'\}/g,
  "{copied ? t('common.copied') : t('common.copy')}"
)

// Add useTranslation to MessageBubble export function
s = s.replace(
  /export function MessageBubble\(\{ message \}: \{ message: Message \}\) \{\n/,
  `export function MessageBubble({ message }: { message: Message }) {
  const { t } = useTranslation()
`
)
// Avoid double if already there
if ((s.match(/export function MessageBubble[\s\S]*?const \{ t \} = useTranslation\(\)/g) || []).length > 1) {
  // remove second occurrence carefully - skip for now
}

// StreamingBubble
s = s.replace(
  /export function StreamingBubble\([^)]*\) \{\n/,
  (m) => m + "  const { t } = useTranslation()\n"
)

// Failover / cache badges - common patterns
s = s.replace(/>Cache exato</g, ">{t('chat.cacheExactBadge')}<")
s = s.replace(/>Failover</g, ">{t('chat.failover')}<")

fs.writeFileSync(path, s)
console.log('MessageBubble wired')
