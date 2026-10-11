import React, { useEffect, useState } from 'react'
import { Target, Zap, ShieldCheck, Sparkles, Check, Save, Loader2, ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { useStore } from '../store/useStore'

export function AutoRouterSettings() {
  const { t } = useTranslation()
  const { showToast } = useStore()
  const [policy, setPolicy] = useState('balanced_smart')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedSuccess, setSavedSuccess] = useState(false)

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
            <strong>Sticky Routing (KV Cache Protector):</strong> Mantém o modelo do turno anterior se ele atender à intenção atual, evitando quebra desnecessária de cache de servidor e latência inicial.
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
