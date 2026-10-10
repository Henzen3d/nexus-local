export type DreamLogInput = {
  status: string
  facts_before: number
  facts_after: number
  error_message?: string | null
  can_rollback?: boolean
  snapshot_id?: string | null
}

export type DreamLogView = {
  showNoise: boolean
  noisePct: number
  headline: string
  pill: 'rollback' | 'blocked' | 'expired' | 'failed' | 'running' | 'none'
}

export function describeDreamLog(log: DreamLogInput): DreamLogView {
  const noisePct =
    log.facts_before > 0
      ? Math.max(0, Math.round(((log.facts_before - log.facts_after) / log.facts_before) * 100))
      : 0

  if (log.status === 'running') {
    return {
      showNoise: false,
      noisePct: 0,
      headline: 'Em andamento. Nada gravado ainda.',
      pill: 'running',
    }
  }

  if (log.status === 'failed' || log.status === 'aborted_safety') {
    const why = (log.error_message || '').trim() || 'Nada foi gravado.'
    return {
      showNoise: false,
      noisePct: 0,
      headline: `Falhou. ${why}`,
      pill: 'failed',
    }
  }

  if (log.status === 'rolled_back') {
    return { showNoise: false, noisePct: 0, headline: 'Revertido.', pill: 'none' }
  }

  if (log.status !== 'success') {
    return { showNoise: false, noisePct: 0, headline: log.status, pill: 'none' }
  }

  let pill: DreamLogView['pill'] = 'blocked'
  if (log.can_rollback) pill = 'rollback'
  else if (!log.snapshot_id) pill = 'expired'

  return {
    showNoise: true,
    noisePct,
    headline: `${log.facts_before} fatos → ${log.facts_after} consolidados (-${noisePct}% de ruído)`,
    pill,
  }
}

const UI_STEPS = ['snapshot', 'connecting', 'reasoning', 'persisting', 'done']

export function dreamStepState(
  stepIndex: number,
  currentStep: string,
): 'done' | 'active' | 'pending' {
  const normalized = currentStep === 'validating' ? 'reasoning' : currentStep
  const current = UI_STEPS.indexOf(normalized)
  if (current < 0) return 'pending'
  if (stepIndex < current) return 'done'
  if (stepIndex === current) return 'active'
  return 'pending'
}
