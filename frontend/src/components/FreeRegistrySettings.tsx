import { useEffect, useState } from 'react'
import { Save, RefreshCw, ToggleLeft, ToggleRight, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { FreeRegistryConfig } from '../types'

export function FreeRegistrySettings() {
  const { t, i18n } = useTranslation()
  const [config, setConfig] = useState<FreeRegistryConfig | null>(null)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<string | null>(null)

  const load = async () => {
    try {
      const cfg = await api.getFreeRegistryConfig()
      setConfig(cfg)
    } catch (err) {
      console.error('[FreeRegistrySettings load error]', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    if (!config) return
    try {
      await api.updateFreeRegistryConfig({
        threshold: config.threshold,
        hide_unconfirmed: config.hide_unconfirmed
      })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      console.error('[FreeRegistrySettings save error]', err)
    }
  }

  const forceSync = async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await api.syncFreeRegistry()
      if (res.status === 'up_to_date') {
        setSyncResult(t('tools.registryUpToDate'))
      } else {
        setSyncResult(t('tools.syncSuccessMsg', { count: res.match_report?.matched || 0, defaultValue: `Atualizado com sucesso. Modelos novos mapeados: ${res.match_report?.matched || 0}` }))
      }
      await load() // refresh config
    } catch (err) {
      console.error('[FreeRegistrySettings sync error]', err)
      setSyncResult(t('tools.syncError'))
    } finally {
      setSyncing(false)
    }
  }

  if (loading || !config) return null

  return (
    <div className="enhancer-settings" style={{ borderTop: 'none', paddingTop: 0 }}>
      <div className="enhancer-header">
        <RefreshCw size={20} />
        <div>
          <h3>{t('toolsSettings.freeRegistryTitle')}</h3>
          <p>{t('toolsSettings.freeRegistryDesc')}</p>
        </div>
      </div>

      <div className="enhancer-field">
        <label>{t('toolsSettings.manualSync')}</label>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <button 
            className="sync-btn" 
            onClick={forceSync} 
            disabled={syncing}
            style={{ width: 'auto' }}
          >
            {syncing ? <RefreshCw size={16} className="spin" /> : <RefreshCw size={16} />}
            {syncing ? t('common.syncing') : t('tools.forceSync')}
          </button>
          <span style={{ fontSize: '13px', color: 'var(--ink-light)' }}>
            {t('toolsSettings.lastUpdate')}: {config.last_updated ? new Date(config.last_updated).toLocaleString(i18n.language) : t('common.never')}
          </span>
        </div>
        {syncResult && (
          <div style={{ marginTop: '8px', fontSize: '13px', color: 'var(--ink)' }}>
            {syncResult}
          </div>
        )}
      </div>

      <div className="enhancer-field">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>
            <label style={{ margin: 0 }}>{t('toolsSettings.hideUnconfirmed')}</label>
            <div style={{ fontSize: '12.5px', color: 'var(--ink-light)', marginTop: '2px' }}>
              {t('toolsSettings.hideUnconfirmedDesc')}
            </div>
          </div>
          <button
            type="button"
            className="toggle-btn"
            onClick={() => setConfig({ ...config, hide_unconfirmed: !config.hide_unconfirmed })}
            style={{ padding: 0, background: 'none', border: 'none', color: config.hide_unconfirmed ? 'var(--primary)' : 'var(--ink-light)', cursor: 'pointer' }}
          >
            {config.hide_unconfirmed ? <ToggleRight size={32} /> : <ToggleLeft size={32} />}
          </button>
        </div>
      </div>

      <div className="enhancer-field">
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <label>{t('toolsSettings.preemptiveThreshold')}</label>
          <span style={{ fontWeight: 600 }}>{config.threshold}%</span>
        </div>
        <p style={{ fontSize: '12.5px', color: 'var(--ink-light)', marginTop: '-4px', marginBottom: '8px' }}>
          {t('toolsSettings.preemptiveThresholdDesc')}
        </p>
        <input
          type="range"
          min="50"
          max="100"
          value={config.threshold}
          onChange={(e) => setConfig({ ...config, threshold: parseInt(e.target.value) })}
          style={{ width: '100%', accentColor: 'var(--primary)' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--ink-light)' }}>
          <span>50%</span>
          <span>75%</span>
          <span>100%</span>
        </div>
      </div>

      <div className="enhancer-actions" style={{ marginTop: '24px' }}>
        <button className="save-btn" onClick={save}>
          <Save size={16} />
          {saved ? t('common.saved') : t('tools.saveSettings')}
        </button>
      </div>
    </div>
  )
}
