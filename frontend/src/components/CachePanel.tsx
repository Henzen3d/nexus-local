import { useEffect, useState, useCallback } from 'react'
import {
  Zap, Sparkles, Trash2, RefreshCw, ToggleLeft, ToggleRight,
  Database, TrendingUp, Clock, AlertCircle, CheckCircle2
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import type { CacheStats, CacheSettings, CacheEntry } from '../types'

export function CachePanel() {
  const { t, i18n } = useTranslation()
  const [stats, setStats] = useState<CacheStats | null>(null)
  const [settings, setSettings] = useState<CacheSettings | null>(null)
  const [entries, setEntries] = useState<CacheEntry[]>([])
  const [entryType, setEntryType] = useState<'exact' | 'semantic'>('exact')
  const [loading, setLoading] = useState(true)
  const [clearing, setClearing] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, cfg, e] = await Promise.all([
        api.getCacheStats(),
        api.getCacheSettings(),
        api.getCacheEntries(entryType),
      ])
      setStats(s)
      setSettings(cfg)
      setEntries(e)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [entryType])

  useEffect(() => { load() }, [load])

  const saveSetting = async (key: keyof CacheSettings, value: boolean | number) => {
    if (!settings) return
    const updated = { ...settings, [key]: value }
    setSettings(updated)
    await api.updateCacheSettings({ [key]: value })
    const s = await api.getCacheStats()
    setStats(s)
  }

  const handleClear = async (expiredOnly: boolean) => {
    setClearing(true)
    await api.clearCache(expiredOnly)
    await load()
    setClearing(false)
  }

  const handleDeleteEntry = async (id: string) => {
    await api.deleteCacheEntry(entryType, id)
    setEntries(e => e.filter(x => x.id !== id))
    const s = await api.getCacheStats()
    setStats(s)
  }

  const fmtTokens = (n: number) =>
    n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n)

  if (loading || !settings || !stats) {
    return (
      <div className="cache-loading">
        <RefreshCw size={20} className="spin" />
        {t('settings.cacheLoadingStats')}
      </div>
    )
  }

  return (
    <div className="cache-panel">

      {/* ── Stats grid ─────────────────────────────────────────────────── */}
      <div className="cache-stats-grid">
        <div className="stat-card stat-card--total">
          <TrendingUp size={18} />
          <div>
            <span className="stat-value">{stats.total_hits}</span>
            <span className="stat-label">{t('settings.cacheTotalHits')}</span>
          </div>
        </div>
        <div className="stat-card stat-card--tokens">
          <Database size={18} />
          <div>
            <span className="stat-value">{fmtTokens(stats.total_tokens_saved)}</span>
            <span className="stat-label">{t('settings.cacheTokensSaved')}</span>
          </div>
        </div>
        <div className="stat-card stat-card--exact">
          <Zap size={18} />
          <div>
            <span className="stat-value">{stats.exact.hits}</span>
            <span className="stat-label">{t('settings.cacheExactHits', { count: stats.exact.entries })}</span>
          </div>
        </div>
        <div className="stat-card stat-card--semantic">
          <Sparkles size={18} />
          <div>
            <span className="stat-value">{stats.semantic.hits}</span>
            <span className="stat-label">{t('settings.cacheSemanticHits', { count: stats.semantic.entries })}</span>
          </div>
        </div>
      </div>

      {/* ── Embedder status ─────────────────────────────────────────────── */}
      {settings.semantic_enabled && (
        <div className={`embedder-status ${stats.semantic.embedder_ready ? 'ready' : 'warn'}`}>
          {stats.semantic.embedder_ready
            ? <><CheckCircle2 size={14} /> {t('settings.cacheSemanticActive')}</>
            : <><AlertCircle size={14} /> {stats.semantic.embedder_error || t('tools.embedderMissing')}
                <code>pip install fastembed</code>
              </>
          }
        </div>
      )}

      {/* ── Settings ────────────────────────────────────────────────────── */}
      <section className="cache-section">
        <h3>{t('settings.cacheConfigTitle')}</h3>

        <div className="cache-toggles">
          <ToggleRow
            label={t('tools.cacheGlobal')}
            desc={t('tools.cacheGlobalDesc')}
            value={settings.enabled}
            onChange={v => saveSetting('enabled', v)}
            accent
          />
          <ToggleRow
            label={t('tools.cacheExact')}
            desc={t('tools.cacheExactDesc')}
            value={settings.exact_enabled}
            onChange={v => saveSetting('exact_enabled', v)}
            disabled={!settings.enabled}
            icon={<Zap size={14} />}
          />
          <ToggleRow
            label={t('tools.cacheSemantic')}
            desc={t('tools.cacheSemanticDesc')}
            value={settings.semantic_enabled}
            onChange={v => saveSetting('semantic_enabled', v)}
            disabled={!settings.enabled}
            icon={<Sparkles size={14} />}
          />
        </div>

        <div className="cache-sliders">
          <SliderRow
            label={t('tools.similarityThreshold')}
            desc={t('tools.similarityDesc')}
            value={settings.similarity_threshold}
            min={0.80}
            max={0.99}
            step={0.01}
            fmt={v => `${(v * 100).toFixed(0)}%`}
            onChange={v => saveSetting('similarity_threshold', v)}
            disabled={!settings.enabled || !settings.semantic_enabled}
          />
          <SliderRow
            label={t('tools.ttlExact')}
            desc={t('tools.ttlExactDesc')}
            value={settings.exact_ttl_hours}
            min={1}
            max={720}
            step={1}
            fmt={v => v >= 24 ? `${(v / 24).toFixed(0)}d` : `${v}h`}
            onChange={v => saveSetting('exact_ttl_hours', v)}
            disabled={!settings.enabled || !settings.exact_enabled}
          />
          <SliderRow
            label={t('tools.ttlSemantic')}
            desc={t('tools.ttlSemanticDesc')}
            value={settings.semantic_ttl_hours}
            min={1}
            max={168}
            step={1}
            fmt={v => v >= 24 ? `${(v / 24).toFixed(0)}d` : `${v}h`}
            onChange={v => saveSetting('semantic_ttl_hours', v)}
            disabled={!settings.enabled || !settings.semantic_enabled}
          />
        </div>
      </section>

      {/* ── Actions ─────────────────────────────────────────────────────── */}
      <section className="cache-section">
        <h3>{t('settings.cacheManageTitle')}</h3>
        <div className="cache-actions">
          <button
            className="cache-action-btn secondary"
            onClick={() => handleClear(true)}
            disabled={clearing}
          >
            <Clock size={14} />
            {t('settings.cacheClearExpired')}
          </button>
          <button
            className="cache-action-btn danger"
            onClick={() => { if (confirm(t('tools.clearAllCache'))) handleClear(false) }}
            disabled={clearing}
          >
            <Trash2 size={14} />
            {t('settings.cacheClearAll')}
          </button>
          <button className="cache-action-btn" onClick={load} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            {t('settings.cacheRefresh')}
          </button>
        </div>
      </section>

      {/* ── Entries ─────────────────────────────────────────────────────── */}
      <section className="cache-section">
        <div className="entries-header">
          <h3>{t('settings.cacheEntriesTitle')}</h3>
          <div className="entry-tabs">
            <button
              className={entryType === 'exact' ? 'active' : ''}
              onClick={() => setEntryType('exact')}
            >
              <Zap size={12} /> {t('settings.cacheExactTab')} ({stats.exact.entries})
            </button>
            <button
              className={entryType === 'semantic' ? 'active' : ''}
              onClick={() => setEntryType('semantic')}
            >
              <Sparkles size={12} /> {t('settings.cacheSemanticTab')} ({stats.semantic.entries})
            </button>
          </div>
        </div>

        <div className="entries-list">
          {entries.length === 0 ? (
            <div className="entries-empty">
              <Database size={24} />
              <p>{t('settings.cacheNoEntries')}</p>
            </div>
          ) : (
            entries.map(e => (
              <div key={e.id} className="entry-row">
                <div className="entry-content">
                  <span className="entry-key">{e.key}</span>
                  <div className="entry-meta">
                    <span>{e.model_id}</span>
                    <span>·</span>
                    <span>{t('settings.cacheHitsSuffix', { count: e.hits })}</span>
                    <span>·</span>
                    <span>{t('settings.cacheTokensSuffix', { count: fmtTokens(e.token_est) })}</span>
                    <span>·</span>
                    <span>{formatDate(e.created_at, i18n.language)}</span>
                  </div>
                </div>
                <button
                  className="entry-delete"
                  onClick={() => handleDeleteEntry(e.id)}
                  title={t('tools.removeEntry')}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}

// ── Sub-components ────────────────────────────────────────────────────────

function ToggleRow({
  label, desc, value, onChange, disabled, icon, accent
}: {
  label: string; desc: string; value: boolean
  onChange: (v: boolean) => void; disabled?: boolean; icon?: React.ReactNode; accent?: boolean
}) {
  return (
    <div className={`toggle-row ${disabled ? 'disabled' : ''}`}>
      <div className="toggle-info">
        {icon && <span className="toggle-icon">{icon}</span>}
        <div>
          <span className="toggle-label">{label}</span>
          <span className="toggle-desc">{desc}</span>
        </div>
      </div>
      <button
        className={`toggle-switch ${value ? 'on' : 'off'} ${accent ? 'accent' : ''}`}
        onClick={() => !disabled && onChange(!value)}
        disabled={disabled}
      >
        {value ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
      </button>
    </div>
  )
}

function SliderRow({
  label, desc, value, min, max, step, fmt, onChange, disabled
}: {
  label: string; desc: string; value: number; min: number; max: number
  step: number; fmt: (v: number) => string; onChange: (v: number) => void; disabled?: boolean
}) {
  return (
    <div className={`slider-row ${disabled ? 'disabled' : ''}`}>
      <div className="slider-header">
        <span className="slider-label">{label}</span>
        <span className="slider-value">{fmt(value)}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={e => onChange(parseFloat(e.target.value))}
        onMouseUp={e => onChange(parseFloat((e.target as HTMLInputElement).value))}
      />
      <span className="slider-desc">{desc}</span>
    </div>
  )
}

function formatDate(iso: string, lang: string) {
  const d = new Date(iso)
  return d.toLocaleDateString(lang || 'pt-BR', { day: '2-digit', month: '2-digit' })
}