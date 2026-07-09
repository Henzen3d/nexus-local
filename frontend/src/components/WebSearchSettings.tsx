import { useEffect, useState } from 'react'
import { Save, Globe, Eye, EyeOff, FileText, ToggleLeft, ToggleRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { WebSearchConfig, WebSearchLog } from '../types'

export function WebSearchSettings() {
  const { t, i18n } = useTranslation()
  const [config, setConfig] = useState<WebSearchConfig | null>(null)
  const [logs, setLogs] = useState<WebSearchLog[]>([])
  const [showKey, setShowKey] = useState(false)
  const [saved, setSaved] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    try {
      const [cfg, logData] = await Promise.all([
        api.getWebSearchConfig(),
        api.getWebSearchLogs(20),
      ])
      setConfig(cfg)
      setLogs(logData)
    } catch (err) {
      console.error('[WebSearchSettings load error]', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  const save = async () => {
    if (!config) return
    try {
      await api.saveWebSearchConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      
      // Reload logs after saving just to refresh
      const logData = await api.getWebSearchLogs(20)
      setLogs(logData)
    } catch (err) {
      console.error('[WebSearchSettings save error]', err)
    }
  }

  if (loading || !config) return null

  return (
    <div className="enhancer-settings" style={{ borderTop: 'none', paddingTop: 0 }}>
      <div className="enhancer-header">
        <Globe size={20} />
        <div>
          <h3>{t('toolsSettings.webSearchTitle')}</h3>
          <p>{t('toolsSettings.webSearchDesc')}</p>
        </div>
      </div>

      <div className="enhancer-field">
        <label>{t('toolsSettings.searchProvider')}</label>
        <select
          value={config.search_provider}
          onChange={(e) =>
            setConfig({
              ...config,
              search_provider: e.target.value as 'duckduckgo' | 'brave',
            })
          }
        >
          <option value="duckduckgo">{t('toolsSettings.ddgFree')}</option>
          <option value="brave">{t('toolsSettings.braveSearchLimit')}</option>
        </select>
      </div>

      {config.search_provider === 'brave' && (
        <div className="enhancer-field">
          <label>{t('toolsSettings.braveApiKey')}</label>
          <div style={{ display: 'flex', gap: '8px' }}>
            <input
              type={showKey ? 'text' : 'password'}
              value={config.api_key}
              onChange={(e) => setConfig({ ...config, api_key: e.target.value })}
              placeholder="BSp..."
              style={{
                flex: 1,
                padding: '8px 12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--hairline)',
                background: 'var(--surface-card)',
                color: 'var(--ink)',
                fontSize: '13.5px',
                outline: 'none',
              }}
            />
            <button
              type="button"
              onClick={() => setShowKey(!showKey)}
              style={{
                padding: '8px 12px',
                borderRadius: 'var(--radius-md)',
                border: '1px solid var(--hairline)',
                background: 'var(--surface-cream-strong)',
                color: 'var(--muted)',
                cursor: 'pointer',
              }}
            >
              {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>
        </div>
      )}

      <div className="enhancer-field">
        <label>{t('toolsSettings.maxResults')}</label>
        <select
          value={config.max_results}
          onChange={(e) =>
            setConfig({
              ...config,
              max_results: parseInt(e.target.value) || 5,
            })
          }
        >
          <option value={3}>{t('toolsSettings.resultsCount', { count: 3 })}</option>
          <option value={5}>{t('toolsSettings.resultsCountRecommended', { count: 5 })}</option>
          <option value={8}>{t('toolsSettings.resultsCount', { count: 8 })}</option>
          <option value={10}>{t('toolsSettings.resultsCount', { count: 10 })}</option>
        </select>
      </div>

      <div className="enhancer-toggle-row">
        <div className="enhancer-toggle-info">
          <span>{t('toolsSettings.enableHeuristic')}</span>
          <small>{t('toolsSettings.enableHeuristicDesc')}</small>
        </div>
        <button
          type="button"
          className={`toggle-btn ${config.heuristic_enabled ? 'on' : 'off'}`}
          onClick={() =>
            setConfig({ ...config, heuristic_enabled: !config.heuristic_enabled })
          }
        >
          {config.heuristic_enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
          {config.heuristic_enabled ? t('common.active') : t('common.inactive')}
        </button>
      </div>

      {config.heuristic_enabled && (
        <div className="enhancer-field" style={{ marginTop: '10px' }}>
          <label>{t('toolsSettings.heuristicSensitivity')}</label>
          <div style={{ display: 'flex', gap: '16px', marginTop: '6px' }}>
            {(['low', 'medium', 'high'] as const).map((level) => (
              <label key={level} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', color: 'var(--body)', cursor: 'pointer' }}>
                <input
                  type="radio"
                  name="heuristic_sensitivity"
                  value={level}
                  checked={config.heuristic_sensitivity === level}
                  onChange={() => setConfig({ ...config, heuristic_sensitivity: level })}
                  style={{ cursor: 'pointer' }}
                />
                 {level === 'low' && t('tools.sensitivityLow')}
                 {level === 'medium' && t('tools.sensitivityMed')}
                 {level === 'high' && t('tools.sensitivityHigh')}
              </label>
            ))}
          </div>
        </div>
      )}

      <div className="enhancer-field" style={{ marginTop: '10px' }}>
        <label>{t('toolsSettings.injectionTemplate')}</label>
        <textarea
          value={config.injection_template}
          onChange={(e) => setConfig({ ...config, injection_template: e.target.value })}
          rows={4}
          placeholder='Resultados de busca para "{query}":\n\n{results}\n\n---...'
          style={{
            width: '100%',
            padding: '8px 12px',
            borderRadius: 'var(--radius-md)',
            border: '1px solid var(--hairline)',
            background: 'var(--surface-card)',
            color: 'var(--ink)',
            fontSize: '13px',
            fontFamily: 'var(--font-mono)',
            outline: 'none',
          }}
        />
        <small style={{ color: 'var(--muted)', fontSize: '11px', marginTop: '4px', display: 'block' }}>
          {t('toolsSettings.injectionTemplateDesc')}
        </small>
      </div>

      <div className="enhancer-actions" style={{ marginBottom: '24px' }}>
        <button
          type="button"
          className={`save-btn ${saved ? 'saved' : ''}`}
          onClick={save}
          style={{ width: '100%' }}
        >
          <Save size={14} />
          {saved ? t('common.saved') : t('tools.saveConfig')}
        </button>
      </div>

      <div className="admin-divider" style={{ margin: '16px 0 28px' }} />

      {/* Logs Section */}
      <div className="enhancer-header" style={{ marginBottom: '12px' }}>
        <FileText size={18} />
        <div>
          <h3 style={{ fontSize: '14.5px' }}>{t('toolsSettings.queryLogs')}</h3>
          <p>{t('toolsSettings.queryLogsDesc')}</p>
        </div>
      </div>

      <div className="users-table-wrapper" style={{ maxHeight: '250px', overflowY: 'auto' }}>
        {logs.length === 0 ? (
          <p style={{ fontSize: '13px', color: 'var(--muted-soft)', textAlign: 'center', padding: '16px 0' }}>
            {t('toolsSettings.noLogs')}
          </p>
        ) : (
          <table className="users-table" style={{ fontSize: '12.5px' }}>
            <thead>
              <tr>
                <th style={{ padding: '8px 12px' }}>{t('toolsSettings.logQuery')}</th>
                <th style={{ padding: '8px 12px' }}>{t('toolsSettings.logTrigger')}</th>
                <th style={{ padding: '8px 12px' }}>{t('toolsSettings.logResults')}</th>
                <th style={{ padding: '8px 12px' }}>{t('toolsSettings.logDate')}</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td style={{ padding: '8px 12px', fontWeight: 500, color: 'var(--ink)' }}>
                    {log.query}
                  </td>
                  <td style={{ padding: '8px 12px' }}>
                    <span className={`role-tag role-${log.trigger_type === 'manual' ? 'user' : 'admin'}`} style={{ fontSize: '10.5px', padding: '2px 6px' }}>
                      {log.trigger_type === 'manual' ? t('toolsSettings.triggerManual') : t('toolsSettings.triggerAuto')}
                    </span>
                  </td>
                  <td style={{ padding: '8px 12px', fontFamily: 'var(--font-mono)' }}>
                    {log.results_count}
                  </td>
                  <td style={{ padding: '8px 12px', color: 'var(--muted-soft)' }}>
                    {new Date(log.created_at).toLocaleTimeString(i18n.language, { hour: '2-digit', minute: '2-digit' })} - {new Date(log.created_at).toLocaleDateString(i18n.language)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
