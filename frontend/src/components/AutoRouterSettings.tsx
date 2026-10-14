import React, { useEffect, useState } from 'react'
import { Target, Zap, ShieldCheck, Sparkles, Check, Save, Loader2, ArrowRight, FlaskConical, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useStore } from '../store/useStore'
import type { AutoRouterPreviewResult } from '../types'

const INTENT_LABEL_KEYS: Record<string, string> = {
  code_engineering: 'autoRouter.codeEngineering',
  deep_reasoning: 'autoRouter.deepReasoning',
  trivial_quick: 'autoRouter.trivialQuick',
  creative_longform: 'autoRouter.creativeLongform',
  multimodal_vision: 'autoRouter.multimodalVision',
  web_research: 'autoRouter.webResearch',
  general_chat: 'autoRouter.generalChat',
}

export function AutoRouterSettings() {
  const { t } = useTranslation()
  const { showToast } = useStore()
  const [policy, setPolicy] = useState('balanced_smart')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedSuccess, setSavedSuccess] = useState(false)

  // ── Testar o roteador (dry-run) ────────────────────────────────────────────
  const [previewPrompt, setPreviewPrompt] = useState('')
  const [previewContinue, setPreviewContinue] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [preview, setPreview] = useState<AutoRouterPreviewResult | null>(null)
  const [lastChosenModelId, setLastChosenModelId] = useState<string | null>(null)
  const [lastIntent, setLastIntent] = useState<string | null>(null)

  const complexityLabel = (c?: number) => {
    if (c === 1) return t('autoRouter.complexityLight', { defaultValue: 'Leve' })
    if (c === 3) return t('autoRouter.complexityHeavy', { defaultValue: 'Pesada' })
    return t('autoRouter.complexityMedium', { defaultValue: 'Média' })
  }

  const intentLabel = (intent: string, fallback?: string) => {
    const key = INTENT_LABEL_KEYS[intent]
    return key ? t(key, { defaultValue: fallback || intent }) : (fallback || intent)
  }

  const runPreview = async () => {
    const prompt = previewPrompt.trim()
    if (!prompt || previewLoading) return
    try {
      setPreviewLoading(true)
      const res = await api.previewAutoRouter({
        prompt,
        previous_model_id: previewContinue ? lastChosenModelId : null,
        previous_intent: previewContinue ? lastIntent : null,
        limit: 8,
      })
      setPreview(res)
      setLastChosenModelId(res.decision.chosen_model_id)
      setLastIntent(res.decision.intent)
    } catch (err) {
      console.error('Erro ao simular rota:', err)
      showToast(t('autoRouter.previewError', { defaultValue: 'Não foi possível simular a rota.' }), 'error')
    } finally {
      setPreviewLoading(false)
    }
  }

  useEffect(() => {
    let mounted = true
    api.getAutoRouterPolicy()
      .then((res) => {
        if (mounted && res?.policy) {
          setPolicy(res.policy)
        }
      })
      .catch((err) => console.error('Erro ao buscar política do roteador:', err))
      .finally(() => {
        if (mounted) setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [])

  const handleSave = async (selectedPolicy: string) => {
    try {
      setSaving(true)
      setSavedSuccess(false)
      await api.setAutoRouterPolicy(selectedPolicy)
      setPolicy(selectedPolicy)
      setSavedSuccess(true)
      showToast(t('autoRouter.policyUpdatedSuccess', { defaultValue: 'Política de roteamento atualizada com sucesso.' }), 'success')
      setTimeout(() => setSavedSuccess(false), 3000)
    } catch (err) {
      console.error('Erro ao salvar política do roteador:', err)
      showToast('Erro ao salvar política do roteador.', 'error')
    } finally {
      setSaving(false)
    }
  }

  const policies = [
    {
      id: 'economical_free',
      icon: <Zap size={18} style={{ color: 'var(--success, #10b981)' }} />,
      badge: '🟢 ' + t('autoRouter.policyEconomical', { defaultValue: 'Econômica (Free-First)' }),
      title: t('autoRouter.policyEconomical', { defaultValue: 'Econômica (Free-First)' }),
      desc: t('autoRouter.policyEconomicalDesc', {
        defaultValue: 'Prioridade absoluta para modelos 100% gratuitos (Groq, Cerebras, Cloudflare). Modelos com custo só são acionados se não houver alternativa gratuita ativa.',
      }),
      tag: 'Economia Máxima',
    },
    {
      id: 'balanced_smart',
      icon: <Target size={18} style={{ color: 'var(--accent, #6366f1)' }} />,
      badge: '🔵 ' + t('autoRouter.policyBalanced', { defaultValue: 'Equilibrada (Smart)' }),
      title: t('autoRouter.policyBalanced', { defaultValue: 'Equilibrada (Smart)' }),
      desc: t('autoRouter.policyBalancedDesc', {
        defaultValue: 'O melhor dos dois mundos: velocidade extrema em saudações e resumos (Groq 8B/Cerebras), profundidade e precisão em código e raciocínio (70B ou DeepSeek-R1).',
      }),
      tag: 'PADRÃO RECOMENDADO',
      isDefault: true,
    },
    {
      id: 'max_performance',
      icon: <Sparkles size={18} style={{ color: 'var(--purple, #a855f7)' }} />,
      badge: '🟣 ' + t('autoRouter.policyPerformance', { defaultValue: 'Máxima Performance' }),
      title: t('autoRouter.policyPerformance', { defaultValue: 'Máxima Performance' }),
      desc: t('autoRouter.policyPerformanceDesc', {
        defaultValue: 'Busca sempre o maior score de qualidade do ranking para a tarefa detectada (ex: Claude 3.5 Sonnet, DeepSeek-R1, Qwen 2.5 Coder 32B), independente de custo.',
      }),
      tag: 'Qualidade Extrema',
    },
  ]

  if (loading) {
    return (
      <div style={{ padding: '24px', display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--muted)' }}>
        <Loader2 size={16} className="animate-spin" />
        <span>Carregando configurações do roteador...</span>
      </div>
    )
  }

  return (
    <div className="auto-router-settings" style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '14px' }}>
        <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Target size={18} className="text-primary" />
          {t('autoRouter.title', { defaultValue: 'Auto-Roteador Inteligente' })}
        </h3>
        <p style={{ margin: '6px 0 0', fontSize: '13px', color: 'var(--muted)' }}>
          {t('autoRouter.subtitle', { defaultValue: 'Distribuição preditiva e cirúrgica de tarefas por contexto, cotas e especialidade.' })}
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <label style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
          {t('autoRouter.policy', { defaultValue: 'Modo de Roteamento Padrão' })}:
        </label>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
          {policies.map((p) => {
            const isSelected = policy === p.id
            return (
              <div
                key={p.id}
                onClick={() => handleSave(p.id)}
                style={{
                  background: isSelected ? 'var(--surface-card, #1e1e24)' : 'var(--surface-soft, #16161a)',
                  border: isSelected
                    ? '2px solid var(--accent, #6366f1)'
                    : '1px solid var(--hairline, rgba(255,255,255,0.08))',
                  borderRadius: '10px',
                  padding: '16px',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  gap: '12px',
                  position: 'relative',
                  transition: 'all 0.18s ease',
                  boxShadow: isSelected ? '0 4px 14px rgba(99, 102, 241, 0.18)' : 'none',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      {p.icon}
                      <span style={{ fontSize: '14px', fontWeight: 700, color: 'var(--ink)' }}>
                        {p.title}
                      </span>
                    </div>
                    {isSelected && (
                      <span style={{ color: 'var(--accent, #6366f1)', display: 'flex', alignItems: 'center' }}>
                        <Check size={16} strokeWidth={3} />
                      </span>
                    )}
                  </div>

                  <p style={{ margin: 0, fontSize: '12px', lineHeight: 1.5, color: 'var(--muted)' }}>
                    {p.desc}
                  </p>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '4px' }}>
                  <span
                    style={{
                      fontSize: '10px',
                      fontWeight: 700,
                      letterSpacing: '0.04em',
                      padding: '2px 7px',
                      borderRadius: '10px',
                      background: p.isDefault
                        ? 'var(--accent-subtle, rgba(99, 102, 241, 0.15))'
                        : 'var(--surface-badge, rgba(255, 255, 255, 0.06))',
                      color: p.isDefault ? 'var(--accent, #6366f1)' : 'var(--muted)',
                    }}
                  >
                    {p.tag}
                  </span>

                  {saving && isSelected && (
                    <Loader2 size={13} className="animate-spin text-primary" />
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Testar o roteador (simulação sem gastar tokens) */}
      <div
        style={{
          background: 'var(--surface-soft)',
          border: '1px solid var(--hairline)',
          borderRadius: '10px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
          marginTop: '6px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
          <FlaskConical size={16} className="text-primary" />
          <span>{t('autoRouter.previewTitle', { defaultValue: 'Testar o roteador' })}</span>
        </div>
        <p style={{ margin: 0, fontSize: '12px', color: 'var(--muted)', lineHeight: 1.5 }}>
          {t('autoRouter.previewSubtitle', {
            defaultValue:
              'Simule a decisão para uma mensagem sem gastar tokens: veja a intenção detectada, o modelo escolhido e o ranking de adequação do seu catálogo.',
          })}
        </p>

        <textarea
          value={previewPrompt}
          onChange={(e) => setPreviewPrompt(e.target.value)}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault()
              void runPreview()
            }
          }}
          rows={3}
          placeholder={t('autoRouter.previewPlaceholder', {
            defaultValue: "Digite uma mensagem de teste… ex.: 'Oi' ou 'Analise a viabilidade de abrir uma franquia…'",
          })}
          style={{
            width: '100%',
            boxSizing: 'border-box',
            resize: 'vertical',
            fontSize: '13px',
            padding: '10px 12px',
            borderRadius: '8px',
            border: '1px solid var(--hairline)',
            background: 'var(--surface-card, #1e1e24)',
            color: 'var(--ink)',
            fontFamily: 'inherit',
          }}
        />

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '12px', color: 'var(--muted)', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={previewContinue}
              onChange={(e) => setPreviewContinue(e.target.checked)}
              disabled={!lastChosenModelId}
            />
            <span>
              {t('autoRouter.previewContinueConversation', {
                defaultValue: 'Simular como continuação (usa o modelo escolhido na simulação anterior)',
              })}
            </span>
          </label>

          <button
            type="button"
            onClick={() => void runPreview()}
            disabled={previewLoading || !previewPrompt.trim()}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '8px 14px',
              borderRadius: '8px',
              border: 'none',
              background: 'var(--accent, #6366f1)',
              color: '#fff',
              fontSize: '13px',
              fontWeight: 600,
              cursor: previewLoading || !previewPrompt.trim() ? 'not-allowed' : 'pointer',
              opacity: previewLoading || !previewPrompt.trim() ? 0.6 : 1,
            }}
          >
            {previewLoading ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
            {previewLoading
              ? t('autoRouter.previewRunning', { defaultValue: 'Simulando…' })
              : t('autoRouter.previewRun', { defaultValue: 'Simular rota' })}
          </button>
        </div>

        {preview && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: '8px',
                fontSize: '12px',
              }}
            >
              <div style={{ background: 'var(--surface-card, #1e1e24)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ color: 'var(--muted)', marginBottom: '2px' }}>{t('autoRouter.intent', { defaultValue: 'Intenção' })}</div>
                <div style={{ color: 'var(--ink)', fontWeight: 600 }}>
                  {intentLabel(preview.intent.intent, preview.intent.reason_label_pt)}
                  <span style={{ color: 'var(--muted)', fontWeight: 400 }}> · {Math.round((preview.intent.confidence ?? 0) * 100)}%</span>
                </div>
              </div>
              <div style={{ background: 'var(--surface-card, #1e1e24)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ color: 'var(--muted)', marginBottom: '2px' }}>{t('autoRouter.previewComplexity', { defaultValue: 'Complexidade' })}</div>
                <div style={{ color: 'var(--ink)', fontWeight: 600 }}>
                  {complexityLabel(preview.intent.complexity)}
                  <span style={{ color: 'var(--muted)', fontWeight: 400 }}> · {preview.intent.complexity_score.toFixed(2)}</span>
                </div>
              </div>
              <div style={{ background: 'var(--surface-card, #1e1e24)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ color: 'var(--muted)', marginBottom: '2px' }}>{t('autoRouter.modelChosen', { defaultValue: 'Modelo Escolhido' })}</div>
                <div style={{ color: 'var(--accent, #6366f1)', fontWeight: 700, wordBreak: 'break-word' }}>
                  {preview.decision.chosen_model_name}
                </div>
                <div style={{ color: 'var(--muted)' }}>{preview.decision.provider_id} · {preview.decision.reason_pt}</div>
              </div>
              <div style={{ background: 'var(--surface-card, #1e1e24)', borderRadius: '8px', padding: '10px 12px' }}>
                <div style={{ color: 'var(--muted)', marginBottom: '2px' }}>{t('autoRouter.previewEffort', { defaultValue: 'Esforço de raciocínio' })}</div>
                <div style={{ color: 'var(--ink)', fontWeight: 600 }}>
                  {preview.decision.reasoning_effort || t('autoRouter.previewEffortNone', { defaultValue: 'sem dial' })}
                  <span style={{ color: 'var(--muted)', fontWeight: 400 }}> · T {preview.decision.temperature} · {preview.decision.decision_latency_ms}ms</span>
                </div>
              </div>
            </div>

            <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ink)', marginTop: '4px' }}>
              {t('autoRouter.previewRanking', { defaultValue: 'Ranking de adequação' })}
              <span style={{ color: 'var(--muted)', fontWeight: 400 }}>
                {' '}· {t('autoRouter.previewCandidates', {
                  defaultValue: '{{count}} candidatos avaliados de {{total}} modelos habilitados',
                  count: preview.candidates_considered,
                  total: preview.catalog_size,
                })}
              </span>
            </div>

            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ color: 'var(--muted)', textAlign: 'left' }}>
                    <th style={{ padding: '6px 8px', fontWeight: 600 }}>#</th>
                    <th style={{ padding: '6px 8px', fontWeight: 600 }}>{t('autoRouter.modelChosen', { defaultValue: 'Modelo' })}</th>
                    <th style={{ padding: '6px 8px', fontWeight: 600 }}>{t('autoRouter.previewFit', { defaultValue: 'Fit' })}</th>
                    <th style={{ padding: '6px 8px', fontWeight: 600 }}>{t('autoRouter.previewQuality', { defaultValue: 'Qualidade' })}</th>
                    <th style={{ padding: '6px 8px', fontWeight: 600 }}>{t('autoRouter.previewTags', { defaultValue: 'Perfil' })}</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.ranking.map((c, idx) => {
                    const chosen = c.model_id === preview.decision.chosen_model_id
                    return (
                      <tr
                        key={c.model_id}
                        style={{
                          borderTop: '1px solid var(--hairline)',
                          background: chosen ? 'var(--accent-subtle, rgba(99, 102, 241, 0.12))' : 'transparent',
                        }}
                      >
                        <td style={{ padding: '6px 8px', color: 'var(--muted)' }}>{idx + 1}</td>
                        <td style={{ padding: '6px 8px', color: 'var(--ink)' }}>
                          <div style={{ fontWeight: chosen ? 700 : 500 }}>
                            {c.model_name}
                            {chosen && (
                              <span style={{ marginLeft: '6px', color: 'var(--accent, #6366f1)', fontSize: '10px', fontWeight: 700 }}>
                                ✓ {t('autoRouter.previewChosen', { defaultValue: 'escolhido' })}
                              </span>
                            )}
                          </div>
                          <div style={{ color: 'var(--muted)', fontSize: '11px' }}>
                            {c.provider_id}
                            {c.is_free ? ` · ${t('autoRouter.previewFree', { defaultValue: 'grátis' })}` : ''}
                            {c.quota_status && c.quota_status !== 'available' ? ` · ${c.quota_status}` : ''}
                          </div>
                        </td>
                        <td style={{ padding: '6px 8px', color: 'var(--ink)', fontVariantNumeric: 'tabular-nums', fontWeight: 600 }}>
                          {c.fit_score.toFixed(1)}
                        </td>
                        <td style={{ padding: '6px 8px', color: 'var(--muted)', fontVariantNumeric: 'tabular-nums' }}>
                          {c.quality_score.toFixed(0)}{c.has_ranking ? '' : '*'}
                        </td>
                        <td style={{ padding: '6px 8px' }}>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                            {c.tags.map((tag) => (
                              <span
                                key={tag}
                                style={{
                                  fontSize: '10px',
                                  padding: '1px 6px',
                                  borderRadius: '8px',
                                  background: 'var(--surface-badge, rgba(255, 255, 255, 0.06))',
                                  color: 'var(--muted)',
                                  whiteSpace: 'nowrap',
                                }}
                              >
                                {tag}
                              </span>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ fontSize: '11px', color: 'var(--muted)' }}>
              {t('autoRouter.previewQualityNote', {
                defaultValue: '* qualidade estimada pelo perfil heurístico (modelo ainda sem ranking real).',
              })}
            </div>
          </div>
        )}
      </div>

      {/* Blindagens de Segunda Escala Ativas */}
      <div
        style={{
          background: 'var(--surface-soft)',
          border: '1px solid var(--hairline)',
          borderRadius: '10px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
          marginTop: '6px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
          <ShieldCheck size={16} className="text-primary" />
          <span>Blindagens Ativas de 2ª Escala</span>
        </div>

        <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '12px', color: 'var(--muted)', lineHeight: 1.6 }}>
          <li>
            <strong>Context Window Guard:</strong> Descarta modelos automaticamente se o histórico estimado + nova pergunta ultrapassar o tamanho de contexto (impede erro HTTP 400).
          </li>
          <li>
            <strong>Sticky Routing (KV Cache Protector):</strong> Mantém o modelo do turno anterior apenas enquanto ele continua adequado à nova mensagem (follow-ups do mesmo tema); mudanças de intenção ou de complexidade trocam de modelo.
          </li>
          <li>
            <strong>Perfil de Capacidades + Esforço Adaptativo:</strong> Cada modelo é classificado por porte, raciocínio (thinking), especialidade e velocidade; saudações vão para modelos pequenos/rápidos com esforço baixo, análises pesadas para modelos pensantes com esforço alto.
          </li>
          <li>
            <strong>Weighted Slot Rotation:</strong> Aplica rotação circular entre provedores gratuitos rápidos (Groq, Cerebras, Cloudflare) para mitigar efeito Thundering Herd e rate limit 429.
          </li>
          <li>
            <strong>Ghost Switch (Failover Silencioso):</strong> Transborda de modelo instantaneamente em caso de erro 402 ou 429 sem interromper o WebSocket.
          </li>
        </ul>
      </div>
    </div>
  )
}
