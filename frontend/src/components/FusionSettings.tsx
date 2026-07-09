import { useEffect, useState } from 'react'
import { Save, Dna, Plus, Trash2, ToggleLeft, ToggleRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { FusionConfig, Provider } from '../types'

const DEFAULT_JUDGE_PROMPT =
  "Você é o Agente Juiz e Consolidador do NexusLocal.\n\n" +
  "Abaixo estão as respostas de diferentes modelos LLM para a pergunta do usuário. " +
  "Analise cada resposta, extraia os pontos fortes de cada uma, neutralize erros " +
  "factuais ou alucinações e monte a resposta ideal: unificada, clara e abrangente.\n\n" +
  "Responda diretamente ao usuário, sem mencionar que está consolidando respostas. " +
  "Retorne apenas a resposta final em Markdown."

interface ParallelLine {
  key: string
  provider_id: string
  model_id: string
}

export function FusionSettings() {
  const { t } = useTranslation()
  const [providers, setProviders] = useState<Provider[]>([])
  const [lines, setLines] = useState<ParallelLine[]>([])
  const [judgeProviderId, setJudgeProviderId] = useState('')
  const [judgeModelId, setJudgeModelId] = useState('')
  const [judgePrompt, setJudgePrompt] = useState(DEFAULT_JUDGE_PROMPT)
  const [enabled, setEnabled] = useState(true)
  const [groundingEnabled, setGroundingEnabled] = useState(true)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [cfg, provs] = await Promise.all([
        api.getFusionConfig(),
        api.getProviders(),
      ])
      setProviders(provs.filter((p) => p.has_key && p.enabled))
      setJudgeProviderId(cfg.judge_provider_id || '')
      setJudgeModelId(cfg.judge_model_id || '')
      setJudgePrompt(cfg.judge_system_prompt || DEFAULT_JUDGE_PROMPT)
      setEnabled(cfg.enabled)
      setGroundingEnabled(cfg.grounding_enabled ?? true)
      setLines(
        cfg.models.map((m, i) => ({
          key: `existing-${m.id}`,
          provider_id: m.provider_id,
          model_id: m.model_id,
        }))
      )
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const activeProviders = providers.filter((p) => p.enabled)
  const usedProviderIds = lines.map((l) => l.provider_id).filter(Boolean)

  const addLine = () => {
    const available = activeProviders.filter((p) => !usedProviderIds.includes(p.id))
    if (available.length === 0) return
    setLines([...lines, { key: `new-${Date.now()}`, provider_id: '', model_id: '' }])
  }

  const removeLine = (key: string) => {
    setLines(lines.filter((l) => l.key !== key))
  }

  const updateLine = (key: string, field: 'provider_id' | 'model_id', value: string) => {
    setLines(
      lines.map((l) => {
        if (l.key !== key) return l
        if (field === 'provider_id') return { ...l, provider_id: value, model_id: '' }
        return { ...l, model_id: value }
      })
    )
  }

  const getLineProviderModels = (providerId: string) => {
    const p = providers.find((p) => p.id === providerId)
    return p?.models.filter((m) => m.enabled) ?? []
  }

  const save = async () => {
    const validLines = lines.filter((l) => l.provider_id && l.model_id)
    await api.saveFusionConfig({
      judge_provider_id: judgeProviderId,
      judge_model_id: judgeModelId,
      judge_system_prompt: judgePrompt,
      enabled,
      grounding_enabled: groundingEnabled,
      models: validLines.map((l, i) => ({
        id: 0,
        provider_id: l.provider_id,
        model_id: l.model_id,
        position: i,
      })),
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  if (loading) return null

  const canAddLine = activeProviders.filter((p) => !usedProviderIds.includes(p.id)).length > 0

  return (
    <div className="fusion-settings">
      <div className="fusion-header">
        <Dna size={20} />
        <div>
          <h3>{t('toolsSettings.fusionTitle')}</h3>
          <p>{t('toolsSettings.fusionDesc')}</p>
        </div>
      </div>

      {/* Parallel Models Section */}
      <div className="fusion-section">
        <h4 className="fusion-section-title">{t('toolsSettings.parallelModels')}</h4>
        <p className="fusion-section-desc">
          {t('toolsSettings.parallelModelsDesc')}
        </p>

        {lines.map((line, idx) => {
          const blockedIds = lines.filter((l) => l.key !== line.key && l.provider_id).map((l) => l.provider_id)
          return (
            <div key={line.key} className="fusion-line">
              <div className="fusion-line-header">
                <span className="fusion-line-num">#{idx + 1}</span>
                <button className="fusion-line-remove" onClick={() => removeLine(line.key)} title={t('common.remove')}>
                  <Trash2 size={14} />
                </button>
              </div>
              <div className="fusion-line-fields">
                <select
                  value={line.provider_id}
                  onChange={(e) => updateLine(line.key, 'provider_id', e.target.value)}
                >
                  <option value="">{t('toolsSettings.selectProvider')}</option>
                  {activeProviders.map((p) => (
                    <option
                      key={p.id}
                      value={p.id}
                      disabled={blockedIds.includes(p.id)}
                    >
                      {blockedIds.includes(p.id) ? `${p.name} (${t('toolsSettings.inUse')})` : p.name}
                    </option>
                  ))}
                </select>
                <select
                  value={line.model_id}
                  onChange={(e) => updateLine(line.key, 'model_id', e.target.value)}
                  disabled={!line.provider_id}
                >
                  <option value="">
                    {!line.provider_id ? t('toolsSettings.selectProviderFirst') : t('toolsSettings.selectModel')}
                  </option>
                  {getLineProviderModels(line.provider_id).map((m) => (
                    <option key={m.id} value={m.id}>{m.display_name}</option>
                  ))}
                </select>
              </div>
            </div>
          )
        })}

        <button
          className="fusion-add-btn"
          onClick={addLine}
          disabled={!canAddLine}
        >
          <Plus size={14} />
          {t('toolsSettings.addModel')}
        </button>
      </div>

      {/* Judge Section */}
      <div className="fusion-section">
        <h4 className="fusion-section-title">{t('toolsSettings.judgeModel')}</h4>
        <p className="fusion-section-desc">
          {t('toolsSettings.judgeModelDesc')}
        </p>

        <div className="fusion-field">
          <label>{t('toolsSettings.providerLabel')}</label>
          <select
            value={judgeProviderId}
            onChange={(e) => { setJudgeProviderId(e.target.value); setJudgeModelId('') }}
          >
            <option value="">{t('toolsSettings.selectProvider')}</option>
            {activeProviders.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>

        <div className="fusion-field">
          <label>{t('toolsSettings.modelLabel')}</label>
          <select
            value={judgeModelId}
            onChange={(e) => setJudgeModelId(e.target.value)}
            disabled={!judgeProviderId}
          >
            <option value="">
              {!judgeProviderId ? t('toolsSettings.selectProviderFirst') : t('toolsSettings.selectModel')}
            </option>
            {getLineProviderModels(judgeProviderId).map((m) => (
              <option key={m.id} value={m.id}>{m.display_name}</option>
            ))}
          </select>
        </div>

        <div className="fusion-field">
          <label>{t('toolsSettings.judgeSystemPrompt')}</label>
          <textarea
            value={judgePrompt}
            onChange={(e) => setJudgePrompt(e.target.value)}
            rows={6}
            placeholder={t('tools.fusionJudgePlaceholder')}
          />
        </div>
      </div>

      {/* Grounding toggle */}
      <div className="fusion-toggle-row">
        <div className="fusion-toggle-info">
          <span>{t('toolsSettings.factualCheck')}</span>
          <small>{t('toolsSettings.factualCheckDesc')}</small>
        </div>
        <button
          className={`toggle-btn ${groundingEnabled ? 'on' : 'off'}`}
          onClick={() => setGroundingEnabled(!groundingEnabled)}
        >
          {groundingEnabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {groundingEnabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {/* Enable toggle */}
      <div className="fusion-toggle-row">
        <div className="fusion-toggle-info">
          <span>{t('toolsSettings.enableFusion')}</span>
          <small>{t('toolsSettings.enableFusionDesc')}</small>
        </div>
        <button
          className={`toggle-btn ${enabled ? 'on' : 'off'}`}
          onClick={() => setEnabled(!enabled)}
        >
          {enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      <div className="fusion-actions">
        <button
          className={`save-btn ${saved ? 'saved' : ''}`}
          onClick={save}
          disabled={!judgeProviderId || !judgeModelId}
        >
          <Save size={14} />
          {saved ? t('common.saved') : t('tools.saveConfig')}
        </button>
      </div>
    </div>
  )
}
