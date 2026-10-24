import { useEffect, useState } from 'react'
import { Brain, Check, ChevronRight, CircleAlert, Globe2, LoaderCircle, Search, Wrench } from 'lucide-react'
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

export function ExecutionSequence({ steps, isWorking, startedAt, durationMs, thinkingContent }: Props) {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(isWorking)
  const [elapsedMs, setElapsedMs] = useState(() => startedAt ? Date.now() - startedAt : 0)

  useEffect(() => {
    if (!isWorking) {
      setIsOpen(false)
      return
    }
    setIsOpen(true)
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

  const iconFor = (type: ProcessStep['type']) => {
    if (type === 'think') return thinkingContent ? <Brain size={14} aria-hidden="true" /> : <LoaderCircle className="execution-sequence-step-spinner" size={14} aria-hidden="true" />
    if (type === 'search') return <Search size={14} aria-hidden="true" />
    if (type === 'navigate') return <Globe2 size={14} aria-hidden="true" />
    return <Wrench size={14} aria-hidden="true" />
  }

  const getStepTitle = (step: ProcessStep) => {
    // 1. Passos com título customizado (triagem "⚡ Modo...", failover "Failover...", etc.) nunca são sobrescritos
    if (step.id.startsWith('triage-') || step.id.startsWith('failover-')) {
      return step.title
    }
    // 2. Se o passo tem título e não é o placeholder 'thinking', respeite o título
    if (step.title && step.id !== 'thinking') {
      return step.title
    }
    // 3. Passo de raciocínio
    if (step.type === 'think') {
      return thinkingContent
        ? t('chat.processThinking', { defaultValue: 'Raciocinando' })
        : (step.title || t('chat.generatingResponse', { defaultValue: 'Gerando resposta…' }))
    }
    return step.title
  }

  // Identifica o passo único designado para exibir o raciocínio (<think>).
  // Garante que o texto de raciocínio seja renderizado no MÁXIMO UMA VEZ em toda a timeline.
  const designatedThinkingStepId = visibleSteps.find(
    (s) => s.id === 'thinking' || (s.type === 'think' && !s.id.startsWith('triage-') && !s.id.startsWith('failover-'))
  )?.id

  return (
    <section className={`execution-sequence${isWorking ? ' is-working' : ''}`} aria-label={t('chat.processLabel')}>
      <button
        type="button"
        className="execution-sequence-toggle"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
      >
        {isWorking ? <LoaderCircle className="execution-sequence-live-icon" size={14} aria-hidden="true" /> : <span className="execution-sequence-summary-icon" aria-hidden="true">⚡</span>}
        <span>{isWorking ? t('chat.processWorking', { time: formatDuration(elapsedMs) }) : summary}</span>
        <ChevronRight className={`execution-sequence-chevron${isOpen ? ' is-open' : ''}`} size={14} aria-hidden="true" />
      </button>

      <div className={`execution-sequence-content${isOpen ? ' is-open' : ''}`}>
        <div className="execution-sequence-tree">
          {visibleSteps.map((step) => (
            <div className={`execution-sequence-step is-${step.status}`} key={step.id}>
              <span className="execution-sequence-step-icon">
                {step.status === 'running'
                  ? <LoaderCircle className="execution-sequence-step-spinner" size={14} aria-label={t('chat.processRunning')} />
                  : step.status === 'failed'
                    ? <CircleAlert size={14} aria-label={t('chat.processFailed')} />
                    : step.id.startsWith('triage-')
                      ? <Check size={13} aria-hidden="true" />
                      : step.type === 'think'
                        ? iconFor(step.type)
                        : <Check size={13} aria-hidden="true" />}
              </span>
              <div className="execution-sequence-step-copy">
                <div className="execution-sequence-step-title">{getStepTitle(step)}</div>
                {step.detail && (
                  <div className="execution-sequence-step-detail">
                    {step.type === 'navigate' && /^https?:\/\//i.test(step.detail)
                      ? <a href={step.detail} target="_blank" rel="noopener noreferrer">{step.detail}</a>
                      : step.detail}
                  </div>
                )}
                {step.subSteps && step.subSteps.length > 0 && (
                  <ul className="execution-sequence-substeps">
                    {step.subSteps.map((subStep, index) => <li key={`${step.id}-${index}`}>{subStep}</li>)}
                  </ul>
                )}
                {thinkingContent && step.id === designatedThinkingStepId && (
                  <div className="execution-sequence-reasoning">{thinkingContent}</div>
                )}
              </div>
            </div>
          ))}
          {thinkingContent && !designatedThinkingStepId && (
            <div className="execution-sequence-step is-completed">
              <span className="execution-sequence-step-icon">{iconFor('think')}</span>
              <div className="execution-sequence-step-copy">
                <div className="execution-sequence-step-title">{t('chat.processThinking', { defaultValue: 'Raciocinando' })}</div>
                <div className="execution-sequence-reasoning">{thinkingContent}</div>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
