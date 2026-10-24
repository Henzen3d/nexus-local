import { useEffect, useState } from 'react'
import {
  Brain,
  Check,
  ChevronRight,
  CircleAlert,
  ExternalLink,
  Globe2,
  LoaderCircle,
  RefreshCw,
  Search,
  Wrench,
  Zap,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ProcessStep } from '../types'

interface Props {
  steps: ProcessStep[]
  isWorking: boolean
  startedAt?: number | null
  durationMs?: number
  thinkingContent?: string
}

function formatDuration(ms: number): string {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return minutes > 0 ? `${minutes}m ${remainder}s` : `${seconds}s`
}

function extractDomain(url: string): string {
  try {
    const parsed = new URL(url)
    return parsed.hostname.replace(/^www\./i, '')
  } catch {
    const clean = url.replace(/^https?:\/\//i, '').replace(/^www\./i, '').split('/')[0]
    return clean || url
  }
}

type StepKind = 'triage' | 'search' | 'navigate' | 'think' | 'failover' | 'tool'

function getStepKind(step: ProcessStep): StepKind {
  if (step.id.startsWith('triage-')) return 'triage'
  if (step.id.startsWith('failover-')) return 'failover'
  if (step.type === 'search') return 'search'
  if (step.type === 'navigate') return 'navigate'
  if (step.type === 'think') return 'think'
  return 'tool'
}

function getNavigateInfo(step: ProcessStep) {
  const rawUrl = (step.detail && /^https?:\/\//i.test(step.detail))
    ? step.detail
    : (step.title && /^https?:\/\//i.test(step.title.replace(/^Lendo conteúdo de\s*/i, ''))
        ? step.title.replace(/^Lendo conteúdo de\s*/i, '')
        : '')
  const domain = rawUrl ? extractDomain(rawUrl) : ''

  let displayTitle = step.title || ''
  if (/^Lendo conteúdo de\s*https?:\/\//i.test(displayTitle) || displayTitle === rawUrl) {
    try {
      const parsed = new URL(rawUrl)
      const pathPart = decodeURIComponent(parsed.pathname).replace(/^\/|\/$/g, '')
      displayTitle = pathPart ? `${domain}/${pathPart}` : domain
    } catch {
      displayTitle = domain || rawUrl
    }
  }

  return { title: displayTitle, domain, url: rawUrl }
}

function getSearchInfo(step: ProcessStep, fallbackAction: string) {
  let query = (step.detail || '').trim()
  let action = step.title || fallbackAction

  const match = action.match(/^Pesquisado(?:\s+na\s+web)?\s+por:\s*(.+)$/i)
  if (match) {
    if (!query) query = match[1].trim()
    action = 'Pesquisado na web'
  } else if (/^Pesquisando(?:\s+na\s+web)?/i.test(action)) {
    action = fallbackAction
  }

  return { action, query }
}

function formatTriageTitle(title: string): string {
  return title.replace(/^[⚡\s]+/, '').trim()
}

export function ExecutionSequence({ steps, isWorking, startedAt, durationMs, thinkingContent }: Props) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(isWorking)
  const [isReasoningOpen, setIsReasoningOpen] = useState(() => Boolean(isWorking && thinkingContent))
  const [elapsedMs, setElapsedMs] = useState(() => (startedAt ? Date.now() - startedAt : 0))

  useEffect(() => {
    if (!isWorking) {
      setIsOpen(false)
      return
    }
    setIsOpen(true)
    setIsReasoningOpen(true)
    const update = () => setElapsedMs(startedAt ? Date.now() - startedAt : 0)
    update()
    const timer = window.setInterval(update, 1000)
    return () => window.clearInterval(timer)
  }, [isWorking, startedAt])

  const visibleSteps = steps.filter((step) => {
    if (isWorking) return true
    // Oculta apenas o placeholder genérico inicial 'thinking' quando não houve raciocínio real
    if (step.id === 'thinking' && !thinkingContent) return false
    // Passos de triagem e failover devem sempre permanecer visíveis após a conclusão
    if (step.id.startsWith('triage-') || step.id.startsWith('failover-')) return true
    if (step.type === 'think' && !thinkingContent && !step.title) return false
    return true
  })

  if (!visibleSteps.length && !thinkingContent) return null

  const totalTime = durationMs && durationMs > 0
    ? formatDuration(durationMs)
    : (isWorking ? formatDuration(elapsedMs) : null)
  const hasResearch = visibleSteps.some((step) => step.type === 'search' || step.type === 'navigate')
  const summary = totalTime
    ? (hasResearch
        ? t('chat.processDoneResearch', { time: totalTime })
        : t('chat.processDone', { time: totalTime }))
    : (hasResearch
        ? t('chat.researchComplete')
        : t('chat.processComplete'))

  // Identifica o passo único designado para exibir o raciocínio (<think>).
  const designatedThinkingStepId = visibleSteps.find(
    (s) => s.id === 'thinking' || (s.type === 'think' && !s.id.startsWith('triage-') && !s.id.startsWith('failover-'))
  )?.id

  const renderStepBadge = (kind: StepKind, status: ProcessStep['status']) => {
    if (status === 'running') {
      return (
        <span className="execution-step-badge is-running" aria-label={t('chat.processRunning')}>
          <LoaderCircle size={13} className="execution-sequence-step-spinner" />
        </span>
      )
    }
    if (status === 'failed') {
      return (
        <span className="execution-step-badge is-failed" aria-label={t('chat.processFailed')}>
          <CircleAlert size={13} />
        </span>
      )
    }
    switch (kind) {
      case 'triage':
        return (
          <span className="execution-step-badge is-triage" aria-label="Modo">
            <Zap size={13} />
          </span>
        )
      case 'search':
        return (
          <span className="execution-step-badge is-search" aria-label={t('chat.processSearching')}>
            <Search size={13} />
          </span>
        )
      case 'navigate':
        return (
          <span className="execution-step-badge is-navigate" aria-label={t('chat.processReading', { defaultValue: 'Navegação' })}>
            <Globe2 size={13} />
          </span>
        )
      case 'think':
        return (
          <span className="execution-step-badge is-think" aria-label={t('chat.processThinking', { defaultValue: 'Raciocínio' })}>
            <Brain size={13} />
          </span>
        )
      case 'failover':
        return (
          <span className="execution-step-badge is-failover" aria-label="Failover">
            <RefreshCw size={13} />
          </span>
        )
      case 'tool':
      default:
        return (
          <span className="execution-step-badge is-tool" aria-label="Ferramenta">
            <Wrench size={13} />
          </span>
        )
    }
  }

  return (
    <section className={`execution-sequence${isWorking ? ' is-working' : ''}`} aria-label={t('chat.processLabel')}>
      <button
        type="button"
        className="execution-sequence-toggle"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        {isWorking ? (
          <LoaderCircle className="execution-sequence-live-icon" size={13} aria-hidden="true" />
        ) : (
          <Zap className="execution-sequence-summary-icon" size={13} aria-hidden="true" />
        )}
        <span>{isWorking ? t('chat.processWorking', { time: formatDuration(elapsedMs) }) : summary}</span>
        <ChevronRight className={`execution-sequence-chevron${isOpen ? ' is-open' : ''}`} size={13} aria-hidden="true" />
      </button>

      <div className={`execution-sequence-content${isOpen ? ' is-open' : ''}`}>
        <div className="execution-sequence-card">
          <div className="execution-sequence-tree">
            {visibleSteps.map((step, idx) => {
              const kind = getStepKind(step)
              const isDesignatedThinking = Boolean(thinkingContent && step.id === designatedThinkingStepId)

              return (
                <div
                  className={`execution-step-row is-${kind} is-${step.status}`}
                  key={step.id || `step-${idx}`}
                >
                  {renderStepBadge(kind, step.status)}

                  <div className="execution-step-body">
                    {kind === 'navigate' ? (
                      (() => {
                        const nav = getNavigateInfo(step)
                        const content = (
                          <>
                            <span className="execution-source-title" title={nav.title || nav.url}>
                              {nav.title || nav.domain || nav.url}
                            </span>
                            {nav.domain && (
                              <span className="execution-source-badge">
                                <span>{nav.domain}</span>
                                <ExternalLink size={10} aria-hidden="true" />
                              </span>
                            )}
                          </>
                        )
                        return nav.url ? (
                          <a
                            href={nav.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="execution-source-link"
                            title={nav.url}
                          >
                            {content}
                          </a>
                        ) : (
                          <div className="execution-step-main">{content}</div>
                        )
                      })()
                    ) : kind === 'search' ? (
                      (() => {
                        const search = getSearchInfo(step, t('chat.processSearching'))
                        return (
                          <div className="execution-step-main">
                            <div className="execution-step-text">
                              <span className="execution-step-label">{search.action}</span>
                              {search.query && (
                                <>
                                  {': '}
                                  <span className="execution-step-query">"{search.query}"</span>
                                </>
                              )}
                            </div>
                            {step.status === 'completed' && (
                              <Check size={12} className="execution-step-check" aria-hidden="true" />
                            )}
                          </div>
                        )
                      })()
                    ) : kind === 'triage' ? (
                      <div className="execution-step-main">
                        <span className="execution-step-text execution-step-query">
                          {formatTriageTitle(step.title)}
                        </span>
                        {step.status === 'completed' && (
                          <Check size={12} className="execution-step-check" aria-hidden="true" />
                        )}
                      </div>
                    ) : kind === 'think' ? (
                      <div className="execution-step-think-block">
                        <div className="execution-step-main">
                          <span className="execution-step-text font-medium">
                            {step.status === 'completed'
                              ? t('chat.reasoningDone', { defaultValue: 'Raciocínio concluído' })
                              : (step.title || t('chat.processThinking', { defaultValue: 'Raciocinando…' }))}
                          </span>
                          {isDesignatedThinking && (
                            <button
                              type="button"
                              className="execution-reasoning-toggle-btn"
                              onClick={() => setIsReasoningOpen((prev) => !prev)}
                              aria-expanded={isReasoningOpen}
                            >
                              <span>
                                {isReasoningOpen ? t('chat.collapseThinking') : t('chat.expandThinking')}
                              </span>
                              {thinkingContent && (
                                <span className="execution-reasoning-count">
                                  {thinkingContent.length > 1000
                                    ? `${(thinkingContent.length / 1000).toFixed(1)}k chars`
                                    : `${thinkingContent.length} chars`}
                                </span>
                              )}
                              <ChevronRight
                                size={12}
                                className={`execution-chevron-mini${isReasoningOpen ? ' is-open' : ''}`}
                                aria-hidden="true"
                              />
                            </button>
                          )}
                        </div>
                        {isDesignatedThinking && isReasoningOpen && (
                          <div className="execution-sequence-reasoning">{thinkingContent}</div>
                        )}
                      </div>
                    ) : (
                      <div className="execution-step-main">
                        <div className="execution-step-text">{step.title}</div>
                        {step.detail && <div className="execution-step-detail">{step.detail}</div>}
                        {step.status === 'completed' && (
                          <Check size={12} className="execution-step-check" aria-hidden="true" />
                        )}
                      </div>
                    )}

                    {step.subSteps && step.subSteps.length > 0 && (
                      <ul className="execution-sequence-substeps">
                        {step.subSteps.map((sub, sIdx) => (
                          <li key={`${step.id}-${sIdx}`}>{sub}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              )
            })}

            {thinkingContent && !designatedThinkingStepId && (
              <div className="execution-step-row is-think is-completed">
                {renderStepBadge('think', 'completed')}
                <div className="execution-step-body">
                  <div className="execution-step-think-block">
                    <div className="execution-step-main">
                      <span className="execution-step-text font-medium">
                        {t('chat.reasoningDone', { defaultValue: 'Raciocínio concluído' })}
                      </span>
                      <button
                        type="button"
                        className="execution-reasoning-toggle-btn"
                        onClick={() => setIsReasoningOpen((prev) => !prev)}
                        aria-expanded={isReasoningOpen}
                      >
                        <span>
                          {isReasoningOpen ? t('chat.collapseThinking') : t('chat.expandThinking')}
                        </span>
                        <span className="execution-reasoning-count">
                          {thinkingContent.length > 1000
                            ? `${(thinkingContent.length / 1000).toFixed(1)}k chars`
                            : `${thinkingContent.length} chars`}
                        </span>
                        <ChevronRight
                          size={12}
                          className={`execution-chevron-mini${isReasoningOpen ? ' is-open' : ''}`}
                          aria-hidden="true"
                        />
                      </button>
                    </div>
                    {isReasoningOpen && (
                      <div className="execution-sequence-reasoning">{thinkingContent}</div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
