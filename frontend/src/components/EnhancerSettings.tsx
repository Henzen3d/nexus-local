import { useEffect, useState } from 'react'
import { Save, Sparkles, ToggleLeft, ToggleRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { EnhancerConfig, Provider } from '../types'

export function EnhancerSettings() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<EnhancerConfig | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [cfg, provs] = await Promise.all([
        api.getEnhancerConfig(),
        api.getProviders(),
      ])
      setConfig(cfg)
      setProviders(provs.filter((p) => p.has_key && p.enabled))
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    if (!config) return
    await api.saveEnhancerConfig(config)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  if (loading || !config) return null

  const selectedProvider = providers.find((p) => p.id === config.enhancer_provider_id)
  const availableModels = selectedProvider?.models.filter((m) => m.enabled) ?? []

  return (
    <div className="enhancer-settings">
      <div className="enhancer-header">
        <Sparkles size={20} />
        <div>
          <h3>{t('toolsSettings.enhancerTitle')}</h3>
          <p>{t('toolsSettings.enhancerDesc')}</p>
        </div>
      </div>

      <div className="enhancer-field">
        <label>{t('toolsSettings.providerLabel')}</label>
        <select
          value={config.enhancer_provider_id ?? ''}
          onChange={(e) =>
            setConfig({
              ...config,
              enhancer_provider_id: e.target.value || null,
              enhancer_model_id: null,
            })
          }
        >
          <option value="">{t('toolsSettings.selectProvider')}</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </select>
      </div>

      <div className="enhancer-field">
        <label>{t('toolsSettings.modelLabel')}</label>
        <select
          value={config.enhancer_model_id ?? ''}
          onChange={(e) =>
            setConfig({ ...config, enhancer_model_id: e.target.value || null })
          }
          disabled={!config.enhancer_provider_id}
        >
          <option value="">
            {!config.enhancer_provider_id
              ? t('toolsSettings.selectProviderFirst')
              : t('toolsSettings.selectModel')}
          </option>
          {availableModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.display_name}
            </option>
          ))}
        </select>
      </div>

      <div className="enhancer-field">
        <label>{t('toolsSettings.agentPromptLabel')}</label>
        <textarea
          value={config.enhancer_system_prompt}
          onChange={(e) =>
            setConfig({ ...config, enhancer_system_prompt: e.target.value })
          }
          rows={6}
          placeholder={t('tools.enhancerPlaceholder')}
        />
      </div>

      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.enableChatButton')}</span>
          <small>{t('toolsSettings.enableChatButtonDesc')}</small>
        </div>
        <button
          className={`toggle-btn ${config.enhancer_enabled ? 'on' : 'off'}`}
          onClick={() =>
            setConfig({ ...config, enhancer_enabled: !config.enhancer_enabled })
          }
        >
          {config.enhancer_enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.enhancer_enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      <div className="enhancer-actions">
        <button
          className={`save-btn ${saved ? 'saved' : ''}`}
          onClick={save}
          disabled={!config.enhancer_provider_id || !config.enhancer_model_id}
        >
          <Save size={14} />
          {saved ? t('common.saved') : t('tools.saveConfig')}
        </button>
      </div>
    </div>
  )
}
