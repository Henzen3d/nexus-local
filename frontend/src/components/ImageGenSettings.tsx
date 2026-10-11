import { useEffect, useState } from 'react'
import { Save, Image as ImageIcon, ToggleLeft, ToggleRight, AlertCircle, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { ImageGenConfig, ImageModel, Provider } from '../types'

export function ImageGenSettings() {
  const { t } = useTranslation()
  const [config, setConfig] = useState<ImageGenConfig | null>(null)
  const [models, setModels] = useState<ImageModel[]>([])
  const [providers, setProviders] = useState<Provider[]>([])
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [cfg, mdlList, provList] = await Promise.all([
        api.getImageGenConfig(),
        api.getImageModels(),
        api.getProviders(),
      ])
      setConfig(cfg)
      setModels(mdlList)
      setProviders(provList)
    } catch (err) {
      console.error('[ImageGenSettings load error]', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const save = async () => {
    if (!config) return
    try {
      await api.saveImageGenConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error('[ImageGenSettings save error]', err)
    }
  }

  if (loading || !config) return null

  const cfProvider = providers.find((p) => p.id === 'cloudflare')
  const cfConfigured = !!(cfProvider && cfProvider.has_key)

  return (
    <div className="enhancer-settings">
      <div className="enhancer-header">
        <ImageIcon size={20} />
        <div>
          <h3>{t('toolsSettings.imageGenTitle', { defaultValue: 'Geração de Imagens' })}</h3>
          <p>
            {t('toolsSettings.imageGenDesc', {
              defaultValue: 'Geração nativa de imagens com Flux via Cloudflare Workers AI e detecção inteligente de intenção.',
            })}
          </p>
        </div>
      </div>

      {!cfConfigured && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: '10px',
            padding: '12px 14px',
            background: 'rgba(239, 68, 68, 0.08)',
            border: '1px solid rgba(239, 68, 68, 0.25)',
            borderRadius: 'var(--radius-md)',
            marginBottom: '16px',
            fontSize: '13px',
            color: 'var(--ink)',
          }}
        >
          <AlertCircle size={18} style={{ color: 'var(--danger, #ef4444)', flexShrink: 0, marginTop: '2px' }} />
          <div>
            <strong>{t('toolsSettings.imageGenNoKeyTitle', { defaultValue: 'Cloudflare não configurada' })}</strong>
            <p style={{ margin: '4px 0 0', color: 'var(--muted)', fontSize: '12px' }}>
              {t('toolsSettings.imageGenNoKeyDesc', {
                defaultValue:
                  'Para gerar imagens, configure seu API Token e Account ID da Cloudflare na aba Provedores.',
              })}
            </p>
          </div>
        </div>
      )}

      {/* Toggle Principal */}
      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.imageGenEnable', { defaultValue: 'Ativar Geração de Imagens' })}</span>
          <small>
            {t('toolsSettings.imageGenEnableDesc', {
              defaultValue: 'Permite criar imagens com /imagem ou quando solicitadas no chat.',
            })}
          </small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${config.enabled ? 'on' : 'off'}`}
          onClick={() => setConfig({ ...config, enabled: !config.enabled })}
        >
          {config.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {/* Toggle Detecção Automática */}
      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.imageGenAutoDetect', { defaultValue: 'Detecção Automática de Intenção' })}</span>
          <small>
            {t('toolsSettings.imageGenAutoDetectDesc', {
              defaultValue: 'Dispara a geração de imagem automaticamente ao identificar pedidos de desenho ou foto (sem precisar de /imagem).',
            })}
          </small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${config.auto_detect ? 'on' : 'off'}`}
          onClick={() => setConfig({ ...config, auto_detect: !config.auto_detect })}
        >
          {config.auto_detect ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.auto_detect ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {/* Seleção de Modelo */}
      <div className="enhancer-field">
        <label>{t('toolsSettings.imageGenModel', { defaultValue: 'Modelo de Imagem' })}</label>
        <select
          value={config.model_id}
          onChange={(e) => {
            const selected = models.find((m) => m.model_id === e.target.value)
            setConfig({
              ...config,
              model_id: e.target.value,
              provider_id: selected?.provider_id || config.provider_id,
              steps: selected ? selected.default_steps : config.steps,
            })
          }}
        >
          {models.map((m) => (
            <option key={m.id} value={m.model_id}>
              {m.display_name} ({m.provider_id})
            </option>
          ))}
        </select>
      </div>

      {/* Steps (Passos de Inferência) */}
      <div className="enhancer-field">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
          <label style={{ margin: 0 }}>{t('toolsSettings.imageGenSteps', { defaultValue: 'Passos de Inferência (Steps)' })}</label>
          <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--primary)' }}>{config.steps}</span>
        </div>
        <input
          type="range"
          min={1}
          max={8}
          step={1}
          value={config.steps}
          onChange={(e) => setConfig({ ...config, steps: parseInt(e.target.value, 10) || 4 })}
          style={{ width: '100%' }}
        />
        <small style={{ color: 'var(--muted)', fontSize: '11.5px', marginTop: '4px', display: 'block' }}>
          {t('toolsSettings.imageGenStepsHint', {
            defaultValue: 'Para Flux-1-Schnell, 4 passos é o equilíbrio ideal entre qualidade e velocidade (~1-3s). Máximo 8.',
          })}
        </small>
      </div>

      {/* Limite Diário por Usuário */}
      <div className="enhancer-field">
        <label>{t('toolsSettings.imageGenDailyCap', { defaultValue: 'Limite Diário por Usuário' })}</label>
        <input
          type="number"
          min={1}
          max={500}
          value={config.daily_cap_per_user}
          onChange={(e) => setConfig({ ...config, daily_cap_per_user: parseInt(e.target.value, 10) || 20 })}
        />
        <small style={{ color: 'var(--muted)', fontSize: '11.5px', marginTop: '4px', display: 'block' }}>
          {t('toolsSettings.imageGenDailyCapHint', {
            defaultValue: 'Protege contra estouro de quota em contas compartilhadas.',
          })}
        </small>
      </div>

      {/* Informações sobre Dimensões e Formato */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          padding: '10px 12px',
          background: 'var(--surface-soft)',
          border: '1px solid var(--hairline)',
          borderRadius: 'var(--radius-md)',
          fontSize: '12px',
          color: 'var(--ink-muted)',
          marginBottom: '16px',
        }}
      >
        <Info size={15} style={{ color: 'var(--cyan)', flexShrink: 0 }} />
        <span>
          {t('toolsSettings.imageGenDimensionsInfo', {
            defaultValue: 'Resolução padrão: 1024x1024px · Formato de saída: PNG · Armazenamento local no Nexus.',
          })}
        </span>
      </div>

      <div className="enhancer-actions">
        <button
          type="button"
          className={`save-btn ${saved ? 'saved' : ''}`}
          onClick={save}
        >
          <Save size={14} />
          {saved ? t('common.saved') : t('tools.saveConfig')}
        </button>
      </div>
    </div>
  )
}
