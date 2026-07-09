import { useEffect, useState } from 'react'
import { Save, RefreshCw, ToggleLeft, ToggleRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { VisionRelayConfig, Provider } from '../types'

export function VisionRelaySettings() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<VisionRelayConfig | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [cfg, provs] = await Promise.all([
        api.getVisionRelayConfig(),
        api.getProviders(),
      ])
      setConfig(cfg)
      // Only show providers that are enabled and have an API key configured
      setProviders(provs.filter((p) => p.has_key && p.enabled))
    } catch (err) {
      console.error('[VisionRelaySettings load error]', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    if (!config) return
    try {
      await api.saveVisionRelayConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error('[VisionRelaySettings save error]', err)
    }
  }

  if (loading || !config) return null

  const selectedProvider = providers.find((p) => p.id === config.relay_provider_id)
  const availableModels = selectedProvider?.models.filter((m) => m.enabled) ?? []

  return (
    <div className="enhancer-settings">
      <div className="enhancer-header">
        <RefreshCw size={20} />
        <div>
          <h3>{t('toolsSettings.visionTitle')}</h3>
          <p>{t('toolsSettings.visionDesc')}</p>
        </div>
      </div>

      <div className="enhancer-field">
        <label>{t('toolsSettings.interpreterProvider')}</label>
        <select
          value={config.relay_provider_id ?? ''}
          onChange={(e) =>
            setConfig({
              ...config,
              relay_provider_id: e.target.value || null,
              relay_model_id: null,
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
        <label>{t('toolsSettings.interpreterModel')}</label>
        <select
          value={config.relay_model_id ?? ''}
          onChange={(e) =>
            setConfig({ ...config, relay_model_id: e.target.value || null })
          }
          disabled={!config.relay_provider_id}
        >
          <option value="">
            {!config.relay_provider_id
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
        <label>{t('toolsSettings.descriptionSystemPrompt')}</label>
        <textarea
          value={config.relay_system_prompt}
          onChange={(e) =>
            setConfig({ ...config, relay_system_prompt: e.target.value })
          }
          rows={5}
          placeholder={t('tools.visionPlaceholder')}
        />
      </div>

      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.enableAutoRouting')}</span>
          <small>{t('toolsSettings.enableAutoRoutingDesc')}</small>
        </div>
        <button
          className={`toggle-btn ${config.enabled ? 'on' : 'off'}`}
          onClick={() =>
            setConfig({ ...config, enabled: !config.enabled })
          }
        >
          {config.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.cacheDescriptions')}</span>
          <small>{t('toolsSettings.cacheDescriptionsDesc')}</small>
        </div>
        <button
          className={`toggle-btn ${config.cache_descriptions ? 'on' : 'off'}`}
          onClick={() =>
            setConfig({ ...config, cache_descriptions: !config.cache_descriptions })
          }
        >
          {config.cache_descriptions ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.cache_descriptions ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      <div className="enhancer-actions">
        <button
          className={`save-btn ${saved ? 'saved' : ''}`}
          onClick={save}
          disabled={!config.relay_provider_id || !config.relay_model_id}
        >
          <Save size={14} />
          {saved ? t('common.saved') : t('tools.saveConfig')}
        </button>
      </div>
    </div>
  )
}
