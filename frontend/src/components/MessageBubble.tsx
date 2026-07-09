import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, Bot, Copy, Check, Zap, Sparkles, FileText, Globe, Image, FileCode, Download, Atom, ChevronRight, Brain, AlertCircle, RefreshCw } from 'lucide-react'
import React, { useState, useRef, useEffect, useDeferredValue } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '../i18n'
import type { Message } from '../types'
import { useStore } from '../store/useStore'
import { api } from '../api/client'
import { UserAvatar, AssistantAvatar, ErrorAvatar } from './Avatars'
import { AttachmentChip } from './AttachmentChip'
import { AIStatusIndicator } from './AIStatusIndicator'
import { CodeBlock } from './CodeBlock'
import { AdapterRegistry } from '../adapters/AdapterRegistry'
import { AIMetadataDisplay } from './AIMetadataDisplay'

// ─── ThinkingBlock — componente independente de modelo ─────────────────────────
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

function cleanContentForArtifacts(content: string, artifacts: { type: string; title?: string }[]): string {
  let cleaned = content

  artifacts.forEach(art => {
    if (art.type === 'html') {
      cleaned = cleaned.replace(/```html\s*[\s\S]*?```/gi, '')
      cleaned = cleaned.replace(/(<!DOCTYPE\s+html[\s\S]*?<\/html>|<html[\s\S]*?<\/html>)/gi, '')
    } else if (art.type === 'svg') {
      cleaned = cleaned.replace(/```svg\s*[\s\S]*?```/gi, '')
      cleaned = cleaned.replace(/(<svg[\s\S]*?<\/svg>)/gi, '')
    } else if (art.type === 'jsx') {
      cleaned = cleaned.replace(/```(?:jsx|tsx)\s*[\s\S]*?```/gi, '')
    } else if (art.type === 'code') {
      cleaned = cleaned.replace(/```(?:\w+)?\s*[\s\S]*?```/gi, '')
    } else if (art.type === 'markdown') {
      // Deixa o markdown ser renderizado inline no balão de chat, não o remova da resposta textual
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

function ModelBadge({ modelId, provider, displayName }: {
  modelId?: string
  provider?: string
  displayName?: string
}) {
  if (!displayName) return null
  return (
    <span
      className="model-badge custom-tooltip-trigger"
      data-tooltip={i18n.t('chat.providerModel', { provider: provider ?? i18n.t('chat.unknown'), model: modelId })}
    >
      {displayName}
    </span>
  )
}

const formatTime = (isoString?: string) => {
  if (!isoString) return ''
  try {
    const normalized = isoString.includes('T') ? isoString : isoString.replace(' ', 'T') + (isoString.endsWith('Z') ? '' : 'Z')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return ''
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

const formatDateFull = (isoString?: string) => {
  if (!isoString) return ''
  try {
    const normalized = isoString.includes('T') ? isoString : isoString.replace(' ', 'T') + (isoString.endsWith('Z') ? '' : 'Z')
    const d = new Date(normalized)
    if (isNaN(d.getTime())) return ''
    return d.toLocaleString([], { dateStyle: 'long', timeStyle: 'short' })
  } catch {
    return ''
  }
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
          transition: 'all 0.15s',
        }}
        title={t('chat.sourcesTitle')}
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

export function MessageBubble({ message }: Props) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)
  const lastCacheHit = useStore((s) => s.lastCacheHit)
  const { setActiveArtifact, setArtifactPanelOpen, loadArtifactHistory } = useStore()

  const copy = () => {
    navigator.clipboard.writeText(message.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (message.role === 'error') {
    return (
      <div className="message error">
        <ErrorAvatar />
        <div className="message-body error-body">
          <div className="error-title">{t('chat.generationError')}</div>
          <div className="error-content">{message.content}</div>
        </div>
      </div>
    )
  }

  // Mapeamento de múltiplos artefatos (com suporte a retrocompatibilidade)
  const artifacts = message.artifacts && message.artifacts.length > 0
    ? message.artifacts
    : message.artifact_id
      ? [{ id: message.artifact_id, type: message.artifact_type || 'code', title: message.artifact_title || t('chat.viewArtifact') }]
      : []

  // Parser universal de reasoning usando o adaptador correspondente (Fase 7.4)
  const adapter = AdapterRegistry.getAdapter(message.model_id || null, message.provider || null)
  const parsedResponse = adapter.parse(message.content)
  const { reasoning, answer, metadata } = parsedResponse
  
  // A flag de thinking agora é fornecida diretamente pelo adapter
  const isThinking = message.role === 'assistant' && (parsedResponse.isThinking ?? false)

  const cleanedContent = cleanContentForArtifacts(answer, artifacts)

  return (
    <div className={`message ${message.role}`}>
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

              {message.was_fallback && (
                <span className="failover-badge" style={{
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
                }}>
                  <RefreshCw size={11} /> {t('chat.failover')}
                </span>
              )}

              {message.relay_used && message.relay_model && (
                <div className="message-relay-notice">
                  <RefreshCw size={11} className="text-primary" />
                  <span>{t('chat.imageViaRelay', { model: message.relay_model })}</span>
                </div>
              )}

              {message.web_search_used && message.web_search_sources && message.web_search_sources.length > 0 && (
                <WebSearchSources sources={message.web_search_sources} query={message.web_search_query} />
              )}

              {/* ThinkingBlock — universal, fechado por padrão */}
              {(reasoning !== null || isThinking) && (
                <ThinkingBlock
                  content={reasoning || ''}
                  isThinking={isThinking}
                />
              )}

              {cleanedContent && (
                <div className="assistant-response">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                      pre({ children, ...props }) {
                        const firstChild = React.Children.toArray(children)[0]
                        if (React.isValidElement(firstChild) && firstChild.type === 'code') {
                          const codeProps = firstChild.props as any
                          const language = codeProps.className
                          const text = String(codeProps.children).replace(/\n$/, '')
                          return <CodeBlock language={language}>{text}</CodeBlock>
                        }
                        return <pre {...props}>{children}</pre>
                      },
                      code({ className, children, node, ...props }) {
                        return <code className="inline-code" {...props}>{children}</code>
                      },
                    }}
                  >
                    {cleanedContent}
                  </ReactMarkdown>
                </div>
              )}

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
          {message.created_at && (
            <span
              className="timestamp custom-tooltip-trigger"
              data-tooltip={formatDateFull(message.created_at)}
            >
              {formatTime(message.created_at)}
            </span>
          )}
          {message.model_display_name && (
            <>
              <span className="meta-sep">·</span>
              <ModelBadge
                modelId={message.model_id}
                provider={message.provider}
                displayName={message.model_display_name}
              />
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
        </div>
      </div>
    </div>
  )
}

// ─── StreamingBubble ───────────────────────────────────────────────────────────

export function StreamingBubble({ content }: { content: string }) {
  const { t } = useTranslation()
  const lastCacheHit = useStore((s) => s.lastCacheHit)
  const selectedModelId = useStore((s) => s.selectedModelId)
  const selectedProviderId = useStore((s) => s.selectedProviderId)

  // Obtém o adaptador e normaliza a resposta de stream em tempo real (Fase 7.4)
  const adapter = AdapterRegistry.getAdapter(selectedModelId, selectedProviderId)
  const parsedStream = adapter.parse(content)
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

  return (
    <div className="message assistant streaming">
      <AssistantAvatar />
      <div className="message-body">
        {lastCacheHit && (
          <div className={`cache-badge cache-badge--${lastCacheHit.type}`}>
            {lastCacheHit.type === 'exact'
              ? <><Zap size={11} /> {t('chat.cacheExactBadge')}</>
              : <><Sparkles size={11} /> {t('chat.cacheSemanticBadge', { pct: (lastCacheHit.similarity * 100).toFixed(1) })}</>
            }
          </div>
        )}

        {/* ThinkingBlock em streaming */}
        {(reasoning !== null || isThinking) && (
          <ThinkingBlock
            content={reasoning || ''}
            isThinking={isThinking}
          />
        )}

        {/* Resposta com renderização progressiva */}
        {deferredResponse && (
          <div
            className="assistant-response streaming-content"
            style={isStale ? { opacity: 0.92 } : undefined}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}
              components={{
                pre({ children, ...props }) {
                  const firstChild = React.Children.toArray(children)[0]
                  if (React.isValidElement(firstChild) && firstChild.type === 'code') {
                    const codeProps = firstChild.props as any
                    const language = codeProps.className
                    const text = String(codeProps.children).replace(/\n$/, '')
                    return <CodeBlock language={language}>{text}</CodeBlock>
                  }
                  return <pre {...props}>{children}</pre>
                },
                code({ className, children, node, ...props }) {
                  return <code className="inline-code" {...props}>{children}</code>
                },
              }}
            >
              {deferredResponse}
            </ReactMarkdown>
          </div>
        )}

        {/* Cursor ▍ piscando ao final do texto visível */}
        {showCursor && (
          <span className="streaming-cursor" aria-hidden="true">▍</span>
        )}
      </div>
    </div>
  )
}