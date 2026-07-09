import React, { useState } from 'react'
import { Dna, ChevronDown, ChevronUp, Loader2, CheckCircle2, XCircle, Brain, ChevronRight, Globe, Sparkles } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useTranslation } from 'react-i18next'
import type { FusionStatusEntry } from '../types'

interface Props {
  fusionStatuses: FusionStatusEntry[]
  fusionJudgeModelId: string | null
  fusionGrounding?: { status: 'checking' | 'searching' | 'done'; queries?: string[]; found?: boolean } | null
  fusionRefinedPrompt?: string | null
}

export function FusionStatusCard({ fusionStatuses, fusionJudgeModelId, fusionGrounding, fusionRefinedPrompt }: Props) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState(true)
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({})

  const toggleModel = (modelId: string) => {
    setExpandedModels((prev) => ({
      ...prev,
      [modelId]: !prev[modelId],
    }))
  }

  if (fusionStatuses.length === 0) return null

  const allDone = fusionStatuses.every((s) => s.status === 'done' || s.status === 'error')
  const collapsed = !expanded && allDone

  const statusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <Loader2 size={14} className="fusion-icon-spin" />
      case 'done':
        return <CheckCircle2 size={14} className="fusion-icon-done" />
      case 'error':
        return <XCircle size={14} className="fusion-icon-error" />
      default:
        return <span className="fusion-icon-pending">⏳</span>
    }
  }

  const confidenceBadge = (s: FusionStatusEntry) => {
    if (!s.confidence) return null
    const labels: Record<string, string> = {
      alta: t('fusion.confidenceHigh'),
      media: t('fusion.confidenceMed'),
      baixa: t('fusion.confidenceLow'),
    }
    const levelLabel = labels[s.confidence]
    return (
      <span
        className={`fusion-confidence-badge ${s.confidence}`}
        title={s.confidence_reason
          ? t('fusion.confidenceTitleReason', { level: levelLabel, reason: s.confidence_reason })
          : t('fusion.confidenceTitle', { level: levelLabel })}
      >
        {levelLabel}
      </span>
    )
  }

  return (
    <div className={`fusion-status-card ${collapsed ? 'collapsed' : ''} ${allDone && fusionJudgeModelId ? 'judge-active' : ''}`}>
      <button className="fusion-status-header" onClick={() => setExpanded(!expanded)}>
        <div className="fusion-status-title">
          <Dna size={16} />
          <span>{t('fusion.parallelModels', { count: fusionStatuses.length })}</span>
        </div>
        {collapsed ? <ChevronDown size={14} /> : <ChevronUp size={14} />}
      </button>

      {!collapsed && (
        <div className="fusion-status-body">
          {fusionStatuses.map((s) => {
            const hasResponse = s.status === 'done' && !!s.response
            const isExpanded = !!expandedModels[s.model_id]

            return (
              <div key={s.model_id} className="fusion-status-item">
                <div
                  className={`fusion-status-row ${s.status} ${hasResponse ? 'clickable' : ''}`}
                  onClick={() => hasResponse && toggleModel(s.model_id)}
                >
                  {statusIcon(s.status)}
                  <span className="fusion-status-model">{s.model_id}</span>
                  {s.provider_id && (
                    <span className="fusion-status-provider">[{s.provider_id}]</span>
                  )}
                  {confidenceBadge(s)}
                  <span className="fusion-status-label">
                    {s.status === 'running' && t('fusion.generating')}
                    {s.status === 'done' && (
                      <span className="fusion-status-done-wrapper">
                        {t('chat.done')}
                        {hasResponse && (
                          isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
                        )}
                      </span>
                    )}
                    {s.status === 'error' && t('common.error')}
                    {s.status === 'pending' && t('fusion.waiting')}
                  </span>
                </div>

                {isExpanded && s.response && (
                  <div className="fusion-model-response">
                    <ReactMarkdown
                      remarkPlugins={[remarkGfm]}
                      components={{
                        pre({ children, ...props }) {
                          const firstChild = React.Children.toArray(children)[0]
                          if (React.isValidElement(firstChild) && firstChild.type === 'code') {
                            const codeProps = firstChild.props as any
                            const language = codeProps.className
                            const text = String(codeProps.children).replace(/\n$/, '')
                            return (
                              <div className="code-block">
                                <span className="code-lang">{language?.replace('language-', '') || 'code'}</span>
                                <pre><code className={language} {...props}>{text}</code></pre>
                              </div>
                            )
                          }
                          return <pre {...props}>{children}</pre>
                        },
                        code({ className, children, node, ...props }) {
                          return <code className="inline-code" {...props}>{children}</code>
                        },
                      }}
                    >
                      {s.response}
                    </ReactMarkdown>
                  </div>
                )}
              </div>
            )
          })}

          {fusionGrounding && (
            <div className="fusion-status-row">
              {fusionGrounding.status === 'checking' || fusionGrounding.status === 'searching' ? (
                <Loader2 size={14} className="fusion-icon-spin" />
              ) : (
                <Globe size={14} className="fusion-icon-grounding" />
              )}
              <span className="fusion-status-model">{t('fusion.factualGrounding')}</span>
              <span className="fusion-status-provider">{t('fusion.webSearchTag')}</span>
              <span className="fusion-status-label">
                {fusionGrounding.status === 'checking' && t('fusion.analyzingClaims')}
                {fusionGrounding.status === 'searching' && t('fusion.searchingSources')}
                {fusionGrounding.status === 'done' && (
                  fusionGrounding.found ? t('fusion.searchDone') : t('fusion.noCriticalClaims')
                )}
              </span>
            </div>
          )}

          {fusionJudgeModelId && (
            <div className="fusion-status-row judge">
              <Brain size={14} className="fusion-icon-judge" />
              <span className="fusion-status-model">{fusionJudgeModelId}</span>
              <span className="fusion-status-provider">{t('fusion.judgeTag')}</span>
              <span className="fusion-status-label">
                {allDone ? t('fusion.consolidating') : t('fusion.waiting')}
              </span>
            </div>
          )}

          {fusionRefinedPrompt && (
            <div className="fusion-status-row fusion-refined-prompt-row">
              <Sparkles size={14} className="fusion-icon-refined" />
              <span className="fusion-status-label" style={{ fontStyle: 'italic', color: 'var(--text-secondary)' }}>
                {t('fusion.refinedAs', { prompt: fusionRefinedPrompt })}
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
