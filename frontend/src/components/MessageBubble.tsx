import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, Bot, Copy, Check, Zap, Sparkles, FileText, Globe, Image, FileCode, Download, Atom, ChevronRight, Brain, AlertCircle, RefreshCw, Volume2, Square, Loader2, Play, Trash2 } from 'lucide-react'
import React, { useState, useRef, useEffect, useDeferredValue, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
import type { Message, UiEnvelope } from '../types'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { UserAvatar, AssistantAvatar, ErrorAvatar } from './Avatars'
import { AttachmentChip } from './AttachmentChip'
import { AIStatusIndicator } from './AIStatusIndicator'
import { markdownComponents } from './markdownComponents'
import { AdapterRegistry } from '../adapters/AdapterRegistry'
import { AIMetadataDisplay } from './AIMetadataDisplay'
import { playSpeech, useTtsPlay } from '../lib/ttsPlayer'
import { AutoRouteBadge } from './AutoRouteBadge'
import { CorrectionNotice } from '../ui/components/CorrectionNotice'
import { DynamicRenderer } from '../ui/DynamicRenderer'
import { mergeUiEnvelopes, parseUiEnvelope, stripUiFences } from '../lib/nexusUi'
import { scanPartialEnvelope } from '../lib/nexusUiStream'
import { useIntelligentUiEnabled } from '../ui/hooks/useIntelligentUi'
import { ExecutionSequence } from './ExecutionSequence'
import { mergeProcessTree } from '../lib/processTree'
import { SourceShelf } from './SourceShelf'
import { GeneratedImage } from './ImageLightbox'
import { stripDuplicateTrailingSources } from '../lib/sourceCards'
import { sanitizeErrorText, stripSensitiveSecrets } from '../lib/sanitization'
import { parseUtc } from '../lib/dates'

const REMARK_PLUGINS = [remarkGfm]
const STALE_STREAM_STYLE: React.CSSProperties = { opacity: 0.92 }
const NEXUS_FENCE_OPEN_RE = /^[ \t]{0,3}```(?:nexus-ui(?:\/1)?|nexus)[^\n]*\n/
const NEXUS_FENCE_CLOSE_RE = /\n[ \t]{0,3}```[ \t]*(?:\n|$)/

const MemoizedAssistantAvatar = React.memo(AssistantAvatar)
const MemoizedExecutionSequence = React.memo(ExecutionSequence)
const MemoizedDynamicRenderer = React.memo(DynamicRenderer)

const MemoizedMarkdownBody = React.memo(function MemoizedMarkdownBody({
  content,
}: {
  content: string
}) {
  if ((globalThis as { __NEXUS_RENDER_PROBE__?: boolean }).__NEXUS_RENDER_PROBE__ === true) {
    const probe = globalThis as { __NEXUS_MARKDOWN_RENDERS__?: number }
    probe.__NEXUS_MARKDOWN_RENDERS__ = (probe.__NEXUS_MARKDOWN_RENDERS__ ?? 0) + 1
  }
  return (
    <ReactMarkdown
      remarkPlugins={REMARK_PLUGINS}
      components={markdownComponents}
    >
      {content}
    </ReactMarkdown>
  )
})

function stripUiFencesFast(text: string): string {
  if (!text) return ''
  if (!text.includes('```nexus') && !text.includes('```chart') && !text.includes('```ui')) {
    return text.trim()
  }
  return stripUiFences(text)
}

function extractLastNexusFenceInput(text: string): string {
  const idx = text.lastIndexOf('```nexus')
  if (idx < 0) return ''
  const lineStart = text.lastIndexOf('\n', idx)
  const fromLine = lineStart >= 0 ? text.slice(lineStart + 1) : text
  if (!NEXUS_FENCE_OPEN_RE.test(fromLine)) {
    return text
  }
  const newlineAfterOpen = fromLine.indexOf('\n')
  if (newlineAfterOpen < 0) return ''
  const body = fromLine.slice(newlineAfterOpen + 1)
  const closeMatch = NEXUS_FENCE_CLOSE_RE.exec('\n' + body)
  if (!closeMatch) return fromLine
  const endOffset = newlineAfterOpen + 1 + closeMatch.index + closeMatch[0].length - 1
  return fromLine.slice(0, endOffset)
}

// ─── ThinkingBlock — componente independente de modelo ─────────────────────────
interface ThinkingBlockProps {
  content: string
  isThinking?: boolean
  durationLabel?: string
}

function ThinkingBlock({ content, isThinking, durationLabel }: ThinkingBlockProps) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const bodyRef = useRef<HTMLDivElement>(null)

  const statusLabel = isThinking ? t('chat.thinking') : durationLabel ?? t('chat.done')

  if (!content && !isThinking) return null

  return (
    <div className="thinking-block">
      <button
        type="button"
        className="thinking-header custom-tooltip-trigger"
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        data-tooltip={isOpen ? t('chat.collapseThinking') : t('chat.expandThinking')}
      >
        <span className="thinking-status">
          <AIStatusIndicator
            status={isThinking ? 'thinking' : 'completed'}
            label={isThinking ? t('chat.thinking') : (durationLabel ?? t('chat.done'))}
          />
        </span>
        <ChevronRight
          size={13}
          className={`thinking-chevron ${isOpen ? 'open' : ''}`}
        />
      </button>

      <div
        className={`thinking-body-wrapper ${isOpen ? 'open' : ''}`}
        ref={bodyRef}
      >
        <div className="thinking-body">
          <div className="thinking-text">{content}</div>
        </div>
      </div>
    </div>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────────────

function cleanContentForArtifacts(
  content: string,
  artifacts: { type: string; title?: string; content?: string }[]
): string {
  let cleaned = content

  // Mantém fences no chat (CodeBlock). Só remove dumps enormes de HTML/SVG bare
  // quando já existem como artefato — o card de Artefato continua disponível.
  artifacts.forEach((art) => {
    if (art.type === 'html') {
      // Não remove ```html — o CodeBlock exibe; remove bare HTML fora de fence se duplicar o artifact
      if (art.content && cleaned.includes(art.content) && !/```html/i.test(cleaned)) {
        cleaned = cleaned.split(art.content).join('')
      }
    } else if (art.type === 'svg') {
      if (art.content && cleaned.includes(art.content) && !/```svg/i.test(cleaned)) {
        cleaned = cleaned.split(art.content).join('')
      }
    } else if (art.type === 'jsx' || art.type === 'code' || art.type === 'markdown') {
      // Mantém o bloco no chat + card de artefato (se houver)
    }
  })

  cleaned = cleaned.replace(/^\s*(?:---|___|___|\*\*\*)\s*$/gm, '')
  cleaned = cleaned.replace(/^\s*(?:#{1,6}|[-*+])?\s*(?:📄|📁|📝|💻|🌐|🎨|⚙️|🛠️)?\s*(?:\*\*|`| )*[\w_.-]+\.[\w]{2,5}(?:\*\*|`| )*\s*$/gm, '')
  cleaned = cleaned.replace(/^\s*(?:\*\*|`| )*(?:[Ff]ile|[Aa]rquivo|arquivo):\s*(?:\*\*|`| )*[\w_.-]+\.[\w]{2,5}(?:\*\*|`| )*\s*$/gm, '')
  cleaned = cleaned.replace(/\n{3,}/g, '\n\n')

  const trimmed = cleaned.replace(/[\s\n\r]+/g, ' ').trim()
  if (trimmed.length < 5 && artifacts.some(a => a.type === 'markdown')) {
    const mdArt = artifacts.find(a => a.type === 'markdown')
    return i18n.t('chat.structuredDoc', { title: mdArt?.title || 'Markdown' })
  }

  return cleaned.trim()
}

const getFileExtension = (type: string) => {
  switch (type) {
    case 'html': return 'html'
    case 'markdown': return 'md'
    case 'svg': return 'svg'
    case 'jsx': return 'jsx'
    default: return 'txt'
  }
}

const getMimeType = (type: string) => {
  switch (type) {
    case 'html': return 'text/html'
    case 'markdown': return 'text/markdown'
    case 'svg': return 'image/svg+xml'
    default: return 'text/plain'
  }
}

const getFriendlyTypeName = (type: string) => {
  switch (type) {
    case 'html': return i18n.t('chat.typeHtml')
    case 'markdown': return i18n.t('chat.typeMd')
    case 'svg': return i18n.t('chat.typeSvg')
    case 'jsx': return i18n.t('chat.typeJsx')
    default: return i18n.t('chat.typeDefault')
  }
}

const renderCardIcon = (type: string) => {
  switch (type) {
    case 'html': return <Globe size={20} className="text-blue-500" />
    case 'svg': return <Image size={20} className="text-green-500" />
    case 'markdown': return <FileText size={20} className="text-orange-500" />
    case 'jsx': return <Atom size={20} className="text-cyan-500" />
    default: return <FileCode size={20} className="text-purple-500" />
  }
}

const KNOWN_PROVIDERS: Record<string, string> = {
  cloudflare: 'Cloudflare',
  groq: 'Groq',
  openrouter: 'OpenRouter',
  huggingface: 'HuggingFace',
  sambanova: 'SambaNova',
  cerebras: 'Cerebras',
  siliconflow: 'SiliconFlow',
  nvidia: 'NVIDIA',
  gemini: 'Google Gemini',
  ollama: 'Ollama',
  lmstudio: 'LM Studio',
  deepinfra: 'DeepInfra',
  together: 'Together AI',
  mistral: 'Mistral',
  cohere: 'Cohere',
  perplexity: 'Perplexity',
  bynara: 'Bynara',
  freetheai: 'FreeTheAI',
  llm7: 'LLM7',
  orcarouter: 'OrcaRouter',
}

function formatProviderName(provider?: string): string {
  if (!provider) return ''
  const trimmed = provider.trim()
  const lower = trimmed.toLowerCase()
  if (KNOWN_PROVIDERS[lower]) return KNOWN_PROVIDERS[lower]
  return trimmed.charAt(0).toUpperCase() + trimmed.slice(1)
}

function cleanModelName(displayName: string, provider?: string): { cleanName: string; detectedProvider?: string } {
  let cleanName = stripSensitiveSecrets(displayName.trim())
  let detectedProvider = provider

  if (cleanName.includes('/')) {
    const parts = cleanName.split('/')
    if (!detectedProvider && parts.length > 1) {
      detectedProvider = parts[0]
      cleanName = parts.slice(1).join('/')
    }
  }

  const parenMatch = cleanName.match(/^(.+?)\s*\(([^)]+)\)$/)
  if (parenMatch) {
    const inside = parenMatch[2].trim()
    const insideLower = inside.toLowerCase()
    if (
      KNOWN_PROVIDERS[insideLower] ||
      (provider && insideLower === provider.toLowerCase().trim()) ||
      insideLower.includes('cloudflare') ||
      insideLower.includes('groq') ||
      insideLower.includes('openrouter') ||
      insideLower.includes('huggingface')
    ) {
      cleanName = parenMatch[1].trim()
      if (!detectedProvider) {
        detectedProvider = inside
      }
    }
  }

  if (detectedProvider) {
    const escaped = detectedProvider.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    cleanName = cleanName.replace(new RegExp(`\\s*\\(${escaped}\\)$`, 'i'), '').trim()
  }

  return { cleanName, detectedProvider }
}

function ModelBadge({
  modelId,
  provider,
  displayName,
  requestedModel,
  wasFallback,
  uiLevel,
}: {
  modelId?: string
  provider?: string
  displayName?: string
  requestedModel?: string | null
  wasFallback?: boolean
  uiLevel?: string
}) {
  const { t } = useTranslation()
  if (!displayName) return null

  const { cleanName, detectedProvider } = cleanModelName(displayName, provider)
  const formattedProvider = formatProviderName(detectedProvider)

  let tooltipText = formattedProvider
    ? t('chat.providerModel', {
        provider: formattedProvider,
        defaultValue: `${t('chat.providerLabel', { defaultValue: 'Provedor' })}: ${formattedProvider}`,
      })
    : cleanName

  if (uiLevel === 'advanced' && wasFallback) {
    const fallbackDesc = requestedModel
      ? t('chat.failoverTooltipDetailed', {
          requested: requestedModel,
          served: cleanName,
          defaultValue: `Failover ativo: solicitado ${requestedModel}, atendido por ${cleanName}`,
        })
      : t('chat.failoverTooltip', {
          defaultValue: 'Atendido via modelo reserva (failover)',
        })
    tooltipText = `${tooltipText} · ${fallbackDesc}`
  }

  return (
    <span
      className="model-badge custom-tooltip-trigger"
      data-tooltip={tooltipText}
    >
      {cleanName}
    </span>
  )
}

function MemoryUsedAccordion({
  messageId,
  items,
}: {
  messageId: string
  items: NonNullable<Message['memory_used']>
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [localItems, setLocalItems] = useState(items)
  const [busyId, setBusyId] = useState<string | null>(null)
  const loadConversation = useStore((s) => s.loadConversation)
  const openSettings = useStore((s) => s.openSettings)
  const showToast = useStore((s) => s.showToast)

  useEffect(() => {
    setLocalItems(items)
  }, [items])

  if (!localItems.length) return null

  const handlePromote = async (factId: string) => {
    setBusyId(factId)
    try {
      await api.updateMemoryFactScope(factId, { scope: 'global' })
      setLocalItems((prev) =>
        prev.map((f) => (f.id === factId ? { ...f, scope: 'global', project_id: null, version: (f.version || 1) + 1 } : f))
      )
      showToast(t('memory.promotedSuccess', { defaultValue: 'Memória promovida para global.' }), 'success')
    } catch {
      showToast(t('memory.promoteToGlobalError', { defaultValue: 'Não foi possível promover a memória.' }), 'error')
    } finally {
      setBusyId(null)
    }
  }

  const handleDelete = async (factId: string) => {
    setBusyId(factId)
    try {
      await api.deleteMemoryFact(factId)
      setLocalItems((prev) => prev.filter((f) => f.id !== factId))
      showToast(t('memory.factDeletedToast', { defaultValue: 'Memória removida.' }), 'info')
    } catch {
      showToast(t('memory.deleteFactError', { defaultValue: 'Não foi possível remover a memória.' }), 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="memory-used-block" data-message-id={messageId}>
      <button
        type="button"
        className="memory-used-toggle"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
      >
        <Brain size={12} aria-hidden="true" />
        <span>
          {t('memory.usedSummary', {
            count: localItems.length,
            defaultValue: `Memória usada (${localItems.length})`,
          })}
        </span>
        <ChevronRight size={12} className={`execution-chevron-mini${open ? ' is-open' : ''}`} aria-hidden="true" />
      </button>

      {open && (
        <div className="memory-used-panel">
          <ul className="memory-used-list">
            {localItems.map((item) => {
              const scopeLabel =
                item.scope === 'project'
                  ? t('memory.scopeProjectShort', { defaultValue: 'Projeto' })
                  : item.scope === 'unknown'
                  ? t('memory.scopeUnknown', { defaultValue: 'Origem incerta' })
                  : t('memory.scopeGlobal', { defaultValue: 'Global' })
              return (
                <li key={item.id || item.fact} className="memory-used-item">
                  <div className="memory-used-item-text">{item.fact}</div>
                  <div className="memory-used-item-meta">
                    <span className={`memory-scope-pill scope-${item.scope || 'global'}`}>{scopeLabel}</span>
                    {item.version != null && (
                      <span className="memory-version-pill">v{item.version}</span>
                    )}
                    {item.source_conv_id && (
                      <button
                        type="button"
                        className="memory-used-link"
                        onClick={() => void loadConversation(item.source_conv_id!)}
                      >
                        {t('memory.viewOriginConv', { defaultValue: 'Ver origem' })}
                      </button>
                    )}
                    {item.id && item.scope !== 'global' && (
                      <button
                        type="button"
                        className="memory-used-link"
                        disabled={busyId === item.id}
                        onClick={() => void handlePromote(item.id)}
                      >
                        <Globe size={11} aria-hidden="true" />
                        <span>{t('memory.promoteToGlobal', { defaultValue: 'Promover para global' })}</span>
                      </button>
                    )}
                    {item.id && (
                      <button
                        type="button"
                        className="memory-used-link danger"
                        disabled={busyId === item.id}
                        onClick={() => void handleDelete(item.id)}
                        aria-label={t('common.delete', { defaultValue: 'Remover' })}
                      >
                        <Trash2 size={11} aria-hidden="true" />
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
          <div className="memory-used-footer">
            <button
              type="button"
              className="memory-used-manage-btn"
              onClick={() => openSettings('memory')}
            >
              {t('memory.manageAll', { defaultValue: 'Gerenciar todas as memórias' })}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function WebSearchSources({ sources, query }: { sources: { title: string; url: string }[]; query?: string }) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div style={{ marginBottom: '10px' }}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          fontSize: '11.5px',
          fontWeight: 500,
          color: 'var(--cyan)',
          background: 'rgba(93, 184, 166, 0.08)',
          border: '1px solid rgba(93, 184, 166, 0.2)',
          padding: '4px 8px',
          borderRadius: 'var(--radius-pill)',
          cursor: 'pointer',
          transition: 'background 120ms cubic-bezier(0.25, 1, 0.5, 1), border-color 120ms cubic-bezier(0.25, 1, 0.5, 1)',
        }}
        className="custom-tooltip-trigger"
        data-tooltip={t('chat.sourcesTitle')}
      >
        <Globe size={12} />
        <span>🌐 {t(sources.length === 1 ? 'chat.sourcesCount_one' : 'chat.sourcesCount_other', { count: sources.length })}</span>
        <ChevronRight size={12} style={{ transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>

      {isOpen && (
        <div
          style={{
            marginTop: '8px',
            padding: '10px 12px',
            background: 'var(--surface-soft)',
            border: '1px solid var(--hairline)',
            borderRadius: 'var(--radius-md)',
            fontSize: '12.5px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            maxWidth: '100%',
          }}
        >
          {query && (
            <div style={{ color: 'var(--muted)', fontSize: '11px', borderBottom: '1px solid var(--hairline)', paddingBottom: '4px', marginBottom: '4px' }}>
              {t('chat.queryMade')} <strong>"{query}"</strong>
            </div>
          )}
          {sources.map((src, i) => (
            <a
              key={i}
              href={src.url}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                color: 'var(--ink)',
                textDecoration: 'none',
                transition: 'color 0.15s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--primary)')}
              onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--ink)')}
            >
              <Globe size={11} style={{ flexShrink: 0, color: 'var(--muted)' }} />
              <span style={{ textDecoration: 'underline', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {src.title || src.url}
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── MessageBubble ─────────────────────────────────────────────────────────────

interface Props {
  message: Message
}

export const MessageBubble = React.memo(function MessageBubble({ message }: Props) {
  if ((globalThis as { __NEXUS_RENDER_PROBE__?: boolean }).__NEXUS_RENDER_PROBE__ === true) {
    const probe = globalThis as { __NEXUS_BUBBLE_RENDERS__?: number }
    probe.__NEXUS_BUBBLE_RENDERS__ = (probe.__NEXUS_BUBBLE_RENDERS__ ?? 0) + 1
  }
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const ttsPlay = useTtsPlay()
  const lastCacheHit = useStore((s) => s.lastCacheHit)
  const uiLevel = useStore((s) => s.uiLevel)
  const isSearchTarget = useStore((s) => s.highlightMessageId === message.id)
  const setActiveArtifact = useStore((s) => s.setActiveArtifact)
  const setArtifactPanelOpen = useStore((s) => s.setArtifactPanelOpen)
  const loadArtifactHistory = useStore((s) => s.loadArtifactHistory)

  const copy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (message.role === 'error') {
    return (
      <div id={`msg-${message.id}`} className={`message error${isSearchTarget ? ' is-search-target' : ''}`}>
        <ErrorAvatar />
        <div className="message-body error-body">
          <div className="error-title">{t('chat.generationError', { defaultValue: 'Erro na geração da resposta' })}</div>
          <div className="error-content">{sanitizeErrorText(message.content)}</div>
        </div>
      </div>
    )
  }

  // Mapeamento de múltiplos artefatos (com suporte a retrocompatibilidade)
  const artifacts = useMemo(
    () =>
      message.artifacts && message.artifacts.length > 0
        ? message.artifacts
        : message.artifact_id
          ? [{ id: message.artifact_id, type: message.artifact_type || 'code', title: message.artifact_title || t('chat.viewArtifact') }]
          : [],
    [message.artifacts, message.artifact_id, message.artifact_type, message.artifact_title, t],
  )

  // Parser universal de reasoning usando o adaptador correspondente (Fase 7.4)
  const adapter = useMemo(
    () => AdapterRegistry.getAdapter(message.model_id || null, message.provider || null),
    [message.model_id, message.provider],
  )
  const parsedResponse = useMemo(
    () => adapter.parse(message.content),
    [adapter, message.content],
  )
  const { reasoning, answer, metadata } = parsedResponse

  const [runtimeUiError, setRuntimeUiError] = useState<{ title: string; message: string } | null>(null)
  const handleRuntimeUiError = React.useCallback((title: string, error: string) => {
    setRuntimeUiError((previous) => previous ?? { title, message: error })
  }, [])

  // Intelligent UI: o envelope vem SEMPRE do servidor (stream_end / GET da conversa),
  // já validado e gravado em message_ui_blocks. Sem reparse do markdown no cliente.
  // Com a flag desligada o texto fica intacto: um fence eventual aparece como
  // bloco de código, exatamente como antes do recurso existir.
  const intelligentUiEnabled = useIntelligentUiEnabled()
  const { effectiveUiEnvelope, textWithoutUi } = useMemo(() => {
    if (!intelligentUiEnabled) {
      return { effectiveUiEnvelope: null, textWithoutUi: answer }
    }
    return {
      effectiveUiEnvelope: message.ui_blocks ?? null,
      textWithoutUi: stripUiFencesFast(answer),
    }
  }, [intelligentUiEnabled, message.ui_blocks, answer])

  const cleanedContent = useMemo(
    () => cleanContentForArtifacts(textWithoutUi, artifacts),
    [textWithoutUi, artifacts],
  )

  const displayedContent = useMemo(() => {
    if (!cleanedContent) return ''
    if (message.web_search_sources && message.web_search_sources.length > 0) {
      return stripDuplicateTrailingSources(cleanedContent, message.web_search_sources)
    }
    return cleanedContent
  }, [cleanedContent, message.web_search_sources])

  const hasExecutionSequence =
    message.role === 'assistant' && Boolean(reasoning || message.process_steps?.length || message.web_search_used)
  const mergedProcessSteps = useMemo(() => {
    if (!hasExecutionSequence) return null
    return mergeProcessTree(
      message.process_steps,
      {
        used: message.web_search_used,
        query: message.web_search_query,
        sources: message.web_search_sources,
      },
      { searching: t('chat.processSearching'), reading: t('chat.processReading', { defaultValue: 'Lendo página' }) },
    )
  }, [hasExecutionSequence, message.process_steps, message.web_search_used, message.web_search_query, message.web_search_sources, t])
  const createdAt = parseUtc(message.created_at)
  const messageDate = createdAt === null ? null : new Date(createdAt)

  return (
    <div id={`msg-${message.id}`} className={`message ${message.role}${isSearchTarget ? ' is-search-target' : ''}`}>
      {message.role === 'user' ? <UserAvatar /> : <AssistantAvatar />}
      <div className="message-body-wrapper">
        <div className="message-body">
          {message.role === 'assistant' ? (
            <>
              {lastCacheHit && (
                <div className={`cache-badge cache-badge--${lastCacheHit.type}`}>
                  {lastCacheHit.type === 'exact'
                    ? <><Zap size={11} /> {t('chat.cacheExactBadge')}</>
                    : <><Sparkles size={11} /> {t('chat.cacheSemanticBadge', { pct: (lastCacheHit.similarity * 100).toFixed(1) })}</>
                  }
                </div>
              )}

              {uiLevel !== 'simple' && message.was_fallback && (
                <span
                  className="failover-badge custom-tooltip-trigger"
                  data-tooltip={
                    message.requested_model
                      ? t('chat.failoverTooltipDetailed', {
                          requested: message.requested_model,
                          served: message.model_display_name || message.served_by || message.model_id || '',
                          defaultValue: `Solicitado: ${message.requested_model} · Atendido por ${message.model_display_name || message.served_by || message.model_id}`,
                        })
                      : t('chat.failoverTooltip', { defaultValue: 'Atendido via modelo reserva (failover)' })
                  }
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '2px 6px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: 600,
                    color: 'var(--primary)',
                    backgroundColor: 'rgba(204, 120, 92, 0.12)',
                    border: '1px solid rgba(204, 120, 92, 0.3)',
                    marginLeft: '6px',
                  }}
                >
                  <RefreshCw size={11} />{' '}
                  {message.model_display_name
                    ? t('chat.failoverServedBy', {
                        served: message.model_display_name,
                        defaultValue: `Failover · ${message.model_display_name}`,
                      })
                    : t('chat.failover', 'Failover')}
                </span>
              )}

              {message.relay_status === 'placeholder_only' ? (
                <div className="message-relay-notice is-degraded">
                  <AlertCircle size={12} aria-hidden="true" />
                  <span>
                    {t('chat.imageNotAnalyzedNotice', {
                      defaultValue: 'Imagem anexada não pôde ser lida visualmente (visão nativa e Vision Relay indisponíveis).',
                    })}
                  </span>
                </div>
              ) : (message.relay_used && message.relay_model) ? (
                <div className="message-relay-notice">
                  <RefreshCw size={11} className="text-primary" />
                  <span>{t('chat.imageViaRelay', { model: message.relay_model })}</span>
                </div>
              ) : null}

              {mergedProcessSteps ? (
                <MemoizedExecutionSequence
                  steps={mergedProcessSteps}
                  isWorking={false}
                  durationMs={message.process_duration_ms}
                  thinkingContent={reasoning || undefined}
                />
              ) : null}

              {displayedContent ? (
                <div className="assistant-response">
                  <MemoizedMarkdownBody content={displayedContent} />
                </div>
              ) : reasoning ? (
                <div className="reasoning-exhausted-card">
                  <div className="reasoning-exhausted-header">
                    <AlertCircle size={15} className="text-warning flex-shrink-0" />
                    <span>
                      {t('chat.reasoningExhausted', {
                        defaultValue: 'O raciocínio foi concluído, mas o modelo não gerou a resposta final devido ao limite de tokens.',
                      })}
                    </span>
                  </div>
                  <div className="reasoning-exhausted-actions">
                    <button
                      type="button"
                      className="reasoning-exhausted-retry-btn"
                      onClick={() => {
                        const requestId = useStore.getState().lastUserMessage?.request_id
                        if (requestId) {
                          window.dispatchEvent(
                            new CustomEvent('nexus:retry-message', {
                              detail: { requestId, effort: 'low' },
                            })
                          )
                        }
                      }}
                    >
                      <RefreshCw size={12} />
                      {t('chat.retryLowerEffort', {
                        defaultValue: 'Tentar novamente (menos raciocínio)',
                      })}
                    </button>
                  </div>
                </div>
              ) : null}

              {message.role === 'assistant' && message.web_search_sources && message.web_search_sources.length > 0 && (
                <SourceShelf sources={message.web_search_sources} />
              )}

              {message.role === 'assistant' && message.memory_used && message.memory_used.length > 0 && (
                <MemoryUsedAccordion messageId={message.id} items={message.memory_used} />
              )}

              {/* Intelligent UI: renderizador de blocos visuais e micro-ferramentas */}
              {effectiveUiEnvelope && <MemoizedDynamicRenderer envelope={effectiveUiEnvelope} messageId={message.id} onRuntimeError={handleRuntimeUiError} />}
              <CorrectionNotice messageId={message.id} errors={message.ui_errors} dropped={message.ui_dropped} runtime={runtimeUiError} />

              {artifacts.length > 0 && (
                <div className="artifact-chat-card-list">
                  {artifacts.map((art) => {
                    const handleCardClick = async () => {
                      try {
                        const artifact = await api.getArtifact(art.id)
                        setActiveArtifact(artifact)
                        setArtifactPanelOpen(true)
                        if (artifact.artifact_group_id) {
                          await loadArtifactHistory(artifact.artifact_group_id)
                        }
                      } catch (e) {
                        console.error('Falha ao abrir artifact pelo card:', e)
                      }
                    }

                    const handleDownloadClick = async (e: React.MouseEvent) => {
                      e.stopPropagation()
                      try {
                        const artifact = await api.getArtifact(art.id)
                        const mime = getMimeType(artifact.type)
                        const blob = new Blob([artifact.content], { type: mime })
                        const url = URL.createObjectURL(blob)
                        const a = document.createElement('a')
                        a.href = url
                        const safeTitle = artifact.title.replace(/[^a-z0-9\s-_.]/gi, '')
                        const ext = getFileExtension(artifact.type)
                        a.download = safeTitle.toLowerCase().endsWith(`.${ext}`) ? safeTitle : `${safeTitle}.${ext}`
                        document.body.appendChild(a)
                        a.click()
                        document.body.removeChild(a)
                        URL.revokeObjectURL(url)
                      } catch (err) {
                        console.error('Falha ao baixar artifact:', err)
                      }
                    }

                    return (
                      <div
                        key={art.id}
                        className="artifact-chat-card"
                        onClick={handleCardClick}
                      >
                        <div className="artifact-chat-card-content">
                          <div className="artifact-chat-card-preview" aria-hidden="true">
                            <div className="artifact-chat-card-sheet">
                              {renderCardIcon(art.type)}
                            </div>
                          </div>
                          <div className="artifact-chat-card-info">
                            <div className="artifact-chat-card-title">{art.title}</div>
                            <div className="artifact-chat-card-subtitle">{getFriendlyTypeName(art.type)}</div>
                          </div>
                          <div className="artifact-chat-card-actions">
                            <button
                              type="button"
                              className="artifact-chat-card-download-btn"
                              onClick={handleDownloadClick}
                            >
                              {t('chat.download')}
                            </button>
                          </div>
                        </div>
                      </div>
                    )
                  })}

                  {artifacts.length > 1 && (
                    <div className="flex justify-start mt-1">
                      <button
                        type="button"
                        className="artifact-download-all-btn"
                        onClick={async () => {
                          for (const art of artifacts) {
                            try {
                              const artifact = await api.getArtifact(art.id)
                              const mime = getMimeType(artifact.type)
                              const blob = new Blob([artifact.content], { type: mime })
                              const url = URL.createObjectURL(blob)
                              const a = document.createElement('a')
                              a.href = url
                              const safeTitle = artifact.title.replace(/[^a-z0-9\s-_.]/gi, '')
                              const ext = getFileExtension(artifact.type)
                              a.download = safeTitle.toLowerCase().endsWith(`.${ext}`) ? safeTitle : `${safeTitle}.${ext}`
                              document.body.appendChild(a)
                              a.click()
                              document.body.removeChild(a)
                              URL.revokeObjectURL(url)
                            } catch (err) {
                              console.error('Erro ao baixar tudo:', err)
                            }
                          }
                        }}
                      >
                        <Download size={14} />
                        {t('chat.downloadAll')}
                      </button>
                    </div>
                  )}
                </div>
              )}

              {message.attachments && message.attachments.length > 0 && (
                <div className="message-assistant-attachments" style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {message.attachments.filter(a => a.file_type === 'image').map(att => {
                    const backendUrl = import.meta.env.VITE_API_URL || ''
                    const cleanBackendUrl = backendUrl.endsWith('/api') ? backendUrl.slice(0, -4) : backendUrl
                    const fileUrl = att.file_url ? (att.file_url.startsWith('http') ? att.file_url : cleanBackendUrl + att.file_url) : ''
                    return (
                      <GeneratedImage key={att.id} fileUrl={fileUrl} filename={att.filename} />
                    )
                  })}
                  {message.attachments.filter(a => a.file_type !== 'image').length > 0 && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {message.attachments.filter(a => a.file_type !== 'image').map(att => (
                        <AttachmentChip key={att.id} attachment={att} readonly />
                      ))}
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
            <>
              <p>{message.content}</p>
              {message.attachments && message.attachments.length > 0 && (
                <div
                  className="message-attachments"
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: '8px',
                    marginTop: '8px'
                  }}
                >
                  {message.attachments.map((att) => (
                    <AttachmentChip key={att.id} attachment={att} readonly />
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Metadados: horário · modelo · ações — discretos e agrupados */}
        <div className="message-meta">
          {messageDate && (
            <span
              className="timestamp custom-tooltip-trigger"
              data-tooltip={messageDate.toLocaleString([], { dateStyle: 'long', timeStyle: 'short' })}
            >
              {messageDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          {uiLevel !== 'simple' && message.model_display_name && (
            <>
              <span className="meta-sep">·</span>
              <ModelBadge
                modelId={message.model_id}
                provider={message.provider}
                displayName={message.model_display_name}
                requestedModel={message.requested_model}
                wasFallback={message.was_fallback}
                uiLevel={uiLevel}
              />
            </>
          )}

          {uiLevel !== 'simple' && message.memory_none_relevant && (!message.memory_used || message.memory_used.length === 0) && (
            <>
              <span className="meta-sep">·</span>
              <span
                className="memory-none-pill custom-tooltip-trigger"
                data-tooltip={t('memory.noneRelevantHint', { defaultValue: 'Nenhuma memória guardada era pertinente para este turno.' })}
              >
                {t('memory.noneRelevantShort', { defaultValue: 'Sem memória relevante' })}
              </span>
            </>
          )}

          {uiLevel !== 'simple' && message.auto_route && (
            <>
              <span className="meta-sep">·</span>
              <AutoRouteBadge decision={message.auto_route} />
            </>
          )}

          
          {/* Exibição opcional de metadados de performance da IA (Fase 8.3) */}
          <AIMetadataDisplay metadata={metadata} visible={false} />

          <button
            className="meta-copy-btn custom-tooltip-trigger"
            onClick={copy}
            data-tooltip={copied ? t('common.copied') : t('common.copy')}
          >
            {copied ? <Check size={12} className="text-success" /> : <Copy size={12} />}
          </button>
          {message.role === 'assistant' && message.content && (
            <button
              className={`meta-copy-btn custom-tooltip-trigger ${
                ttsPlay.id === message.id && ttsPlay.status === 'playing' ? 'tts-active' : ''
              } ${ttsPlay.id === message.id && ttsPlay.status === 'loading' ? 'tts-loading' : ''}`}
              onClick={() => {
                const textToSpeak = (cleanedContent || answer || message.content).trim()
                playSpeech(message.id, textToSpeak).catch(() => {})
              }}
              data-tooltip={
                ttsPlay.id === message.id && ttsPlay.status === 'loading'
                  ? `${t('settings.voiceGenerating', { defaultValue: 'Gerando áudio...' })} (${ttsPlay.progress}%)`
                  : ttsPlay.id === message.id && ttsPlay.status === 'playing'
                  ? t('settings.voiceStop', { defaultValue: 'Parar leitura' })
                  : ttsPlay.cachedIds?.has(message.id)
                  ? t('settings.voicePlay', { defaultValue: 'Tocar áudio' })
                  : t('settings.voiceListen', { defaultValue: 'Ouvir resposta' })
              }
              aria-label={
                ttsPlay.id === message.id && ttsPlay.status === 'loading'
                  ? `${t('settings.voiceGenerating', { defaultValue: 'Gerando áudio...' })} ${ttsPlay.progress}%`
                  : ttsPlay.id === message.id && ttsPlay.status === 'playing'
                  ? t('settings.voiceStop', { defaultValue: 'Parar leitura' })
                  : ttsPlay.cachedIds?.has(message.id)
                  ? t('settings.voicePlay', { defaultValue: 'Tocar áudio' })
                  : t('settings.voiceListen', { defaultValue: 'Ouvir resposta' })
              }
            >
              {ttsPlay.id === message.id && ttsPlay.status === 'loading' ? (
                <>
                  <Loader2 size={12} className="animate-spin text-primary" />
                  <span className="tts-progress-percent">{ttsPlay.progress}%</span>
                </>
              ) : ttsPlay.id === message.id && ttsPlay.status === 'playing' ? (
                <Square size={12} className="text-primary" />
              ) : ttsPlay.cachedIds?.has(message.id) ? (
                <Play size={12} className="text-primary" fill="currentColor" />
              ) : (
                <Volume2 size={12} />
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
})

// ─── StreamingBubble ───────────────────────────────────────────────────────────

export const StreamingBubble = React.memo(function StreamingBubble({ content }: { content: string }) {
  if ((globalThis as { __NEXUS_RENDER_PROBE__?: boolean }).__NEXUS_RENDER_PROBE__ === true) {
    const probe = globalThis as { __NEXUS_STREAMING_BUBBLE_RENDERS__?: number }
    probe.__NEXUS_STREAMING_BUBBLE_RENDERS__ = (probe.__NEXUS_STREAMING_BUBBLE_RENDERS__ ?? 0) + 1
  }
  const { t } = useTranslation()
  const lastCacheHit = useStore((s) => s.lastCacheHit)
  const selectedModelId = useStore((s) => s.selectedModelId)
  const selectedProviderId = useStore((s) => s.selectedProviderId)
  const processSteps = useStore((s) => s.processSteps)
  const processStartedAt = useStore((s) => s.processStartedAt)
  // Blocos do host (ui_progress) chegados durante o stream — spec §3/§5
  const streamingUiBlocks = useStore((s) => s.streamingUiBlocks)

  // Obtém o adaptador e normaliza a resposta de stream em tempo real (Fase 7.4)
  const adapter = useMemo(
    () => AdapterRegistry.getAdapter(selectedModelId, selectedProviderId),
    [selectedModelId, selectedProviderId],
  )
  const parsedStream = useMemo(
    () => adapter.parse(content),
    [adapter, content],
  )
  const { reasoning, answer } = parsedStream

  // A flag de thinking agora é fornecida diretamente pelo adapter
  const isThinking = parsedStream.isThinking ?? false

  // Renderização progressiva: useDeferredValue adia updates pesados do Markdown
  // enquanto o estado urgente (cursor, ThinkingBlock) atualiza imediatamente.
  const deferredResponse = useDeferredValue(answer)

  // Detecta se o conteúdo deferido está desatualizado (ainda processando)
  const isStale = deferredResponse !== answer

  // Componente de cursor piscando — só exibe fora do ThinkingBlock
  const showCursor = !isThinking

  // Durante o stream, esconde o fence parcial só com a flag ligada (ver MessageBubble acima)
  const streamUiEnabled = useIntelligentUiEnabled()
  const streamText = useMemo(
    () => (streamUiEnabled ? stripUiFencesFast(deferredResponse) : deferredResponse),
    [streamUiEnabled, deferredResponse],
  )

  const nexusFenceInput = useMemo(
    () => (streamUiEnabled ? extractLastNexusFenceInput(deferredResponse) : ''),
    [streamUiEnabled, deferredResponse],
  )

  const modelEnvelopeCacheRef = useRef<{ key: string; envelope: UiEnvelope | null }>({
    key: '',
    envelope: null,
  })

  // Extrai blocos fechados e bloco pendente do fence em streaming sem depender de streamingUiBlocks
  const { modelEnvelope, pendingBlockType } = useMemo(() => {
    if (!streamUiEnabled || !nexusFenceInput) {
      return { modelEnvelope: null as UiEnvelope | null, pendingBlockType: null as string | null }
    }
    const scanned = scanPartialEnvelope(nexusFenceInput)
    if (scanned.blocks.length === 0) {
      return { modelEnvelope: null as UiEnvelope | null, pendingBlockType: scanned.pendingType }
    }
    const blocksKey = JSON.stringify(scanned.blocks)
    let parsed = modelEnvelopeCacheRef.current.envelope
    if (modelEnvelopeCacheRef.current.key !== blocksKey) {
      parsed = parseUiEnvelope({ v: 1, blocks: scanned.blocks })
      modelEnvelopeCacheRef.current = { key: blocksKey, envelope: parsed }
    }
    return {
      modelEnvelope: parsed,
      pendingBlockType: scanned.pendingType,
    }
  }, [streamUiEnabled, nexusFenceInput])

  const streamEnvelope = useMemo(() => {
    if (!streamUiEnabled) return streamingUiBlocks || null
    return mergeUiEnvelopes(streamingUiBlocks, modelEnvelope)
  }, [streamUiEnabled, streamingUiBlocks, modelEnvelope])

  // A fase de preparação ativa (busca web / thinking) termina assim que os primeiros tokens
  // da resposta final começam a ser gerados.
  const isStillWorking = isThinking || !streamText.trim()
  const prepDurationRef = useRef<number | null>(null)
  if (!isStillWorking && prepDurationRef.current === null && processStartedAt) {
    prepDurationRef.current = Math.max(500, Date.now() - processStartedAt)
  }

  return (
    <div className="message assistant streaming">
      <MemoizedAssistantAvatar />
      <div className="message-body">
        {lastCacheHit && (
          <div className={`cache-badge cache-badge--${lastCacheHit.type}`}>
            {lastCacheHit.type === 'exact'
              ? <><Zap size={11} /> {t('chat.cacheExactBadge')}</>
              : <><Sparkles size={11} /> {t('chat.cacheSemanticBadge', { pct: (lastCacheHit.similarity * 100).toFixed(1) })}</>
            }
          </div>
        )}

        <MemoizedExecutionSequence
          steps={processSteps}
          isWorking={isStillWorking}
          startedAt={processStartedAt}
          durationMs={prepDurationRef.current ?? undefined}
          thinkingContent={reasoning || undefined}
        />

        {/* Resposta com renderização progressiva */}
        {streamText && (
          <div
            className="assistant-response streaming-content"
            style={isStale ? STALE_STREAM_STYLE : undefined}
          >
            <MemoizedMarkdownBody content={streamText} />
          </div>
        )}

        {/* Cursor ▍ piscando ao final do texto visível */}
        {showCursor && (
          <span className="streaming-cursor" aria-hidden="true">▍</span>
        )}

        {/* Componentes UI do host ou modelo durante o stream */}
        {(streamEnvelope || pendingBlockType) && (
          <MemoizedDynamicRenderer
            envelope={streamEnvelope}
            streaming={true}
            pendingType={pendingBlockType}
            messageId="__streaming__"
          />
        )}
      </div>
    </div>
  )
})
