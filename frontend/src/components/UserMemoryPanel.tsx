import { useEffect, useState, useRef } from 'react'
import { Briefcase, User, FolderGit2, Sliders, Trash2, Brain, Search, Info, Code, Eye, X, Save, ToggleLeft, ToggleRight, AlertTriangle, Download, Upload, BarChart3, Pin, PinOff, Copy, Check, Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api, type MemoryExtractorConfig, type MemoryStatsApi } from '../api/client'
import type { MemorySummary, Provider } from '../types'

interface MemoryFact {
  id: string
  category: 'professional' | 'personal' | 'project' | 'preference' | 'identity' | 'tech'
  fact: string
  fact_key?: string | null
  source_conv_id?: string
  confidence: number
  is_pinned?: number
  is_active?: number
  updated_at: string
}

interface MemoryPreview {
  fact_count: number
  block: string
  block_chars: number
}

export function UserMemoryPanel() {
  const { t } = useTranslation()
  const [memories, setMemories] = useState<MemoryFact[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [preview, setPreview] = useState<MemoryPreview | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [clearConfirm, setClearConfirm] = useState(false)

  // Global memory + extractor (B2)
  const [memoryEnabled, setMemoryEnabled] = useState(true)
  const [extractor, setExtractor] = useState<MemoryExtractorConfig | null>(null)
  const [providers, setProviders] = useState<Provider[]>([])
  const [extractorSaved, setExtractorSaved] = useState(false)
  const [summaries, setSummaries] = useState<MemorySummary[]>([])
  const [refreshingSummaries, setRefreshingSummaries] = useState(false)
  const [stats, setStats] = useState<MemoryStatsApi | null>(null)
  const [importing, setImporting] = useState(false)
  const importInputRef = useRef<HTMLInputElement>(null)

  // Import from other AI providers (Claude-style)
  const [showImportAi, setShowImportAi] = useState(false)
  const [importPrompt, setImportPrompt] = useState('')
  const [importPaste, setImportPaste] = useState('')
  const [importPromptCopied, setImportPromptCopied] = useState(false)
  const [importingText, setImportingText] = useState(false)
  const [importPromptLoading, setImportPromptLoading] = useState(false)

  const loadMemory = async () => {
    setLoading(true)
    setError('')
    try {
      const [data, profile, ext, provs, sums, st] = await Promise.all([
        api.getUserMemory(),
        api.getUserProfile().catch(() => null),
        api.getMemoryExtractorConfig().catch(() => null),
        api.getProviders().catch(() => [] as Provider[]),
        api.getMemorySummaries().catch(() => [] as MemorySummary[]),
        api.getMemoryStats().catch(() => null),
      ])
      setMemories(data)
      if (profile) {
        setMemoryEnabled(profile.memory_enabled === undefined ? true : !!profile.memory_enabled)
      }
      if (ext) setExtractor(ext)
      setProviders((provs || []).filter((p: Provider) => p.has_key && p.enabled))
      setSummaries(sums || [])
      setStats(st)
    } catch (err: any) {
      console.error(err)
      setError(t('memory.loadError'))
    } finally {
      setLoading(false)
    }
  }

  const handleExport = async () => {
    try {
      const bundle = await api.exportMemory()
      const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `nexuslocal-memory-${new Date().toISOString().slice(0, 10)}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error(err)
      alert(t('memory.exportError'))
    }
  }

  const handleImportFile = async (file: File) => {
    setImporting(true)
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      if (!data || (!Array.isArray(data.facts) && !data.profile && !Array.isArray(data.summaries))) {
        throw new Error('invalid')
      }
      const mode = window.confirm(t('memory.importReplaceConfirm')) ? 'replace' : 'merge'
      const res = await api.importMemory({ ...data, mode })
      await loadMemory()
      alert(t('memory.importSuccess', { facts: res.imported_facts, summaries: res.imported_summaries }))
    } catch (err) {
      console.error(err)
      alert(t('memory.importError'))
    } finally {
      setImporting(false)
      if (importInputRef.current) importInputRef.current.value = ''
    }
  }

  const openImportFromAi = async () => {
    setShowImportAi(true)
    setImportPaste('')
    setImportPromptCopied(false)
    if (importPrompt) return
    setImportPromptLoading(true)
    try {
      const data = await api.getMemoryImportPrompt()
      setImportPrompt(data.prompt || '')
    } catch (err) {
      console.error(err)
      // Fallback local prompt if API fails
      setImportPrompt(
        'Export all of my stored memories and any context you\'ve learned about me from past conversations. ' +
        'Preserve my words verbatim where possible, especially for instructions and preferences.\n\n' +
        '## Categories (output in this order):\n\n' +
        '1. **Instructions**\n2. **Identity**\n3. **Career**\n4. **Projects**\n5. **Preferences**\n\n' +
        'Format each line as: [YYYY-MM-DD] - Entry content here.\n' +
        'If no date is known, use [unknown]. Wrap the entire export in a single code block.'
      )
    } finally {
      setImportPromptLoading(false)
    }
  }

  const handleCopyImportPrompt = async () => {
    if (!importPrompt) return
    try {
      await navigator.clipboard.writeText(importPrompt)
      setImportPromptCopied(true)
      setTimeout(() => setImportPromptCopied(false), 2000)
    } catch {
      // Fallback for older browsers
      const ta = document.createElement('textarea')
      ta.value = importPrompt
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      setImportPromptCopied(true)
      setTimeout(() => setImportPromptCopied(false), 2000)
    }
  }

  const handleImportFromAi = async () => {
    const text = importPaste.trim()
    if (!text) {
      alert(t('memory.importTextEmpty'))
      return
    }
    setImportingText(true)
    try {
      const res = await api.importMemoryText({ text, mode: 'merge', merge_instructions_into_profile: true })
      await loadMemory()
      const sections =
        res.sections_found?.length
          ? ` (${res.sections_found.join(', ')})`
          : ''
      alert(t('memory.importTextSuccess', { facts: res.imported_facts, sections }))
      setShowImportAi(false)
      setImportPaste('')
    } catch (err) {
      console.error(err)
      alert(t('memory.importTextError'))
    } finally {
      setImportingText(false)
    }
  }

  const handleRefreshSummaries = async () => {
    setRefreshingSummaries(true)
    try {
      const sums = await api.refreshMemorySummaries()
      setSummaries(sums)
    } catch (err) {
      console.error(err)
      alert(t('memory.summaryRefreshError'))
    } finally {
      setRefreshingSummaries(false)
    }
  }

  const toggleMemoryEnabled = async () => {
    const next = !memoryEnabled
    setMemoryEnabled(next)
    try {
      await api.saveUserProfile({ memory_enabled: next })
    } catch (err) {
      console.error(err)
      setMemoryEnabled(!next)
      alert(t('memory.savePrefError'))
    }
  }

  const saveExtractor = async () => {
    if (!extractor) return
    try {
      const saved = await api.saveMemoryExtractorConfig({
        memory_extractor_provider_id: extractor.memory_extractor_provider_id || '',
        memory_extractor_model_id: extractor.memory_extractor_model_id || '',
        memory_extractor_enabled: extractor.memory_extractor_enabled,
        memory_llm_summaries_enabled: extractor.memory_llm_summaries_enabled,
      })
      setExtractor(saved)
      setExtractorSaved(true)
      setTimeout(() => setExtractorSaved(false), 2000)
    } catch (err) {
      console.error(err)
      alert(t('memory.extractorSaveError'))
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await api.deleteMemoryFact(id)
      setMemories((prev) => prev.filter((m) => m.id !== id))
      const st = await api.getMemoryStats().catch(() => null)
      if (st) setStats(st)
    } catch (err) {
      console.error(err)
      alert(t('memory.deleteError'))
    }
  }

  const handleTogglePin = async (m: MemoryFact) => {
    const next = !m.is_pinned
    try {
      await api.pinMemoryFact(m.id, !!next)
      setMemories((prev) =>
        prev.map((x) => (x.id === m.id ? { ...x, is_pinned: next ? 1 : 0 } : x))
      )
    } catch (err) {
      console.error(err)
      alert(t('memory.pinError'))
    }
  }

  const handleClearAll = async () => {
    try {
      await api.clearAllMemory()
      setMemories([])
      setSummaries([])
      setPreview(null)
      setClearConfirm(false)
      const st = await api.getMemoryStats().catch(() => null)
      if (st) setStats(st)
    } catch (err) {
      console.error(err)
      alert(t('memory.clearError'))
    }
  }

  const handlePreview = async () => {
    setPreviewLoading(true)
    setShowPreview(true)
    try {
      const data = await api.getUserMemoryPreview()
      setPreview(data)
    } catch (err) {
      console.error(err)
      alert(t('memory.previewError'))
    } finally {
      setPreviewLoading(false)
    }
  }

  useEffect(() => {
    loadMemory()
  }, [])

  const getCategoryIcon = (category: string) => {
    switch (category) {
      case 'professional': return <Briefcase size={13} />
      case 'personal': return <User size={13} />
      case 'project': return <FolderGit2 size={13} />
      case 'identity': return <User size={13} />
      case 'tech': return <Code size={13} />
      default: return <Sliders size={13} />
    }
  }

  const getCategoryLabel = (category: string) => {
    const map: Record<string, string> = {
      professional: t('memory.catProfessional'),
      personal: t('memory.catPersonal'),
      project: t('memory.catProject'),
      preference: t('memory.catPreference'),
      identity: t('memory.catIdentity'),
      tech: t('memory.catTech'),
    }
    return map[category] ?? category
  }

  const getCategoryColor = (category: string) => {
    const map: Record<string, string> = {
      professional: 'var(--primary)',
      personal: 'var(--success, #22c55e)',
      project: 'var(--cyan, #06b6d4)',
      identity: 'var(--violet, #8b5cf6)',
      tech: 'var(--warning, #f59e0b)',
      preference: 'var(--muted)',
    }
    return map[category] ?? 'var(--muted)'
  }

  /** M5: domain = first segment of fact_key (work.company → work), else category */
  const getFactDomain = (m: MemoryFact): string => {
    const key = (m.fact_key || '').trim().toLowerCase()
    if (key.includes('.')) return key.split('.')[0] || 'other'
    if (key) return key
    return m.category || 'other'
  }

  const getDomainLabel = (domain: string) => {
    const map: Record<string, string> = {
      work: t('memory.domainWork'),
      family: t('memory.domainFamily'),
      project: t('memory.domainProject'),
      prefs: t('memory.domainPrefs'),
      preference: t('memory.domainPrefs'),
      identity: t('memory.domainIdentity'),
      tech: t('memory.domainTech'),
      professional: t('memory.catProfessional'),
      personal: t('memory.catPersonal'),
      other: t('memory.domainOther'),
    }
    return map[domain] ?? domain.charAt(0).toUpperCase() + domain.slice(1)
  }

  const DOMAIN_ORDER = [
    'identity', 'work', 'professional', 'personal', 'family',
    'project', 'tech', 'prefs', 'preference', 'other',
  ]

  // Show only active facts (is_active not 0) in the UI
  const activeFacts = memories.filter(m => (m as any).is_active !== 0)
  const q = searchQuery.toLowerCase().trim()
  const filteredMemories = activeFacts.filter((m) => {
    if (!q) return true
    return (
      m.fact.toLowerCase().includes(q) ||
      getCategoryLabel(m.category).toLowerCase().includes(q) ||
      (m.fact_key || '').toLowerCase().includes(q) ||
      getDomainLabel(getFactDomain(m)).toLowerCase().includes(q)
    )
  })

  // M5: group by fact_key domain for easier browsing/editing
  const groupedByDomain = (() => {
    const groups = new Map<string, MemoryFact[]>()
    for (const m of filteredMemories) {
      const d = getFactDomain(m)
      if (!groups.has(d)) groups.set(d, [])
      groups.get(d)!.push(m)
    }
    // Sort facts inside each group: pinned first, then by fact_key, then text
    for (const list of groups.values()) {
      list.sort((a, b) => {
        const pin = (b.is_pinned ? 1 : 0) - (a.is_pinned ? 1 : 0)
        if (pin !== 0) return pin
        const ka = (a.fact_key || '').localeCompare(b.fact_key || '')
        if (ka !== 0) return ka
        return a.fact.localeCompare(b.fact)
      })
    }
    const keys = Array.from(groups.keys()).sort((a, b) => {
      const ia = DOMAIN_ORDER.indexOf(a)
      const ib = DOMAIN_ORDER.indexOf(b)
      const ra = ia === -1 ? 999 : ia
      const rb = ib === -1 ? 999 : ib
      if (ra !== rb) return ra - rb
      return a.localeCompare(b)
    })
    return keys.map((domain) => ({ domain, facts: groups.get(domain)! }))
  })()

  return (
    <div style={{ padding: '4px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', flexWrap: 'wrap', gap: '8px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Brain size={22} style={{ color: 'var(--primary)' }} />
          <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', margin: 0 }}>
            {t('settings.memory')}
            {activeFacts.length > 0 && (
              <span style={{
                marginLeft: '10px', fontSize: '12px', fontWeight: 600,
                background: 'var(--primary)', color: '#fff',
                borderRadius: '20px', padding: '1px 8px', verticalAlign: 'middle'
              }}>
                {t('memory.factsCount', { count: activeFacts.length })}
              </span>
            )}
          </h2>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button
            type="button"
            onClick={handleExport}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              border: '1px solid var(--hairline)',
              background: 'var(--surface-card)', color: 'var(--ink)',
              fontSize: '12.5px', fontWeight: 500, cursor: 'pointer',
            }}
          >
            <Download size={14} />
            {t('memory.export')}
          </button>
          <button
            type="button"
            onClick={openImportFromAi}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              border: '1px solid var(--primary)',
              background: 'color-mix(in srgb, var(--primary) 12%, transparent)',
              color: 'var(--primary)',
              fontSize: '12.5px', fontWeight: 600, cursor: 'pointer',
            }}
          >
            <Sparkles size={14} />
            {t('memory.importFromAi')}
          </button>
          <button
            type="button"
            onClick={() => importInputRef.current?.click()}
            disabled={importing}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              border: '1px solid var(--hairline)',
              background: 'var(--surface-card)', color: 'var(--ink)',
              fontSize: '12.5px', fontWeight: 500, cursor: 'pointer',
            }}
          >
            <Upload size={14} />
            {importing ? t('common.loading') : t('memory.import')}
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept="application/json,.json"
            style={{ display: 'none' }}
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) handleImportFile(f)
            }}
          />
          <button
            onClick={handlePreview}
            style={{
              display: 'flex', alignItems: 'center', gap: '6px',
              padding: '7px 14px', borderRadius: '8px',
              border: '1px solid var(--hairline)',
              background: 'var(--surface-card)', color: 'var(--ink)',
              fontSize: '12.5px', fontWeight: 500, cursor: 'pointer',
            }}
          >
            <Eye size={14} />
            {t('memory.previewBtn')}
          </button>
          {activeFacts.length > 0 && !clearConfirm && (
            <button
              onClick={() => setClearConfirm(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: '6px',
                padding: '7px 14px', borderRadius: '8px',
                border: '1px solid var(--error, #ef4444)',
                background: 'transparent', color: 'var(--error, #ef4444)',
                fontSize: '12.5px', fontWeight: 500, cursor: 'pointer',
              }}
            >
              <Trash2 size={14} />
              {t('memory.forgetAll')}
            </button>
          )}
          {clearConfirm && (
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', color: 'var(--muted)' }}>{t('memory.confirmClear')}</span>
              <button
                onClick={handleClearAll}
                style={{
                  padding: '6px 12px', borderRadius: '8px', border: 'none',
                  background: 'var(--error, #ef4444)', color: '#fff',
                  fontSize: '12px', fontWeight: 600, cursor: 'pointer',
                }}
              >
                {t('memory.confirmYes')}
              </button>
              <button
                onClick={() => setClearConfirm(false)}
                style={{
                  padding: '6px 12px', borderRadius: '8px',
                  border: '1px solid var(--hairline)', background: 'transparent',
                  color: 'var(--muted)', fontSize: '12px', cursor: 'pointer',
                }}
              >
                {t('common.cancel')}
              </button>
            </div>
          )}
        </div>
      </div>

      <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '16px' }}>
        {t('memory.panelDesc')}
      </p>

      {/* Phase D: metrics */}
      {stats && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
          gap: '10px', marginBottom: '16px',
        }}>
          {[
            { label: t('memory.statActive'), value: stats.active_facts },
            { label: t('memory.statInactive'), value: stats.inactive_facts },
            { label: t('memory.statSummaries'), value: stats.summaries_count },
            { label: t('memory.statExtractToday'), value: stats.extractions_today },
            { label: t('memory.statExtractTotal'), value: stats.extractions_total },
          ].map((item) => (
            <div
              key={item.label}
              style={{
                background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                borderRadius: '10px', padding: '10px 12px',
              }}
            >
              <div style={{ fontSize: '11px', color: 'var(--muted)', display: 'flex', alignItems: 'center', gap: 4 }}>
                <BarChart3 size={12} />
                {item.label}
              </div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--ink)', marginTop: 4 }}>{item.value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Global memory toggle — default ON; this is the main kill-switch */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        gap: '12px',
        background: memoryEnabled
          ? 'rgba(62, 207, 142, 0.06)'
          : 'var(--surface-card)',
        border: '1px solid',
        borderColor: memoryEnabled
          ? 'rgba(62, 207, 142, 0.28)'
          : 'var(--hairline)',
        borderRadius: '12px', padding: '12px 16px', marginBottom: '12px',
      }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--ink)' }}>
              {t('memory.useMemoryGlobal')}
            </span>
            <span
              style={{
                fontSize: '10.5px',
                fontWeight: 600,
                letterSpacing: '0.02em',
                padding: '2px 7px',
                borderRadius: '999px',
                background: memoryEnabled
                  ? 'rgba(62, 207, 142, 0.16)'
                  : 'rgba(239, 68, 68, 0.1)',
                color: memoryEnabled ? '#2db87a' : 'var(--error, #ef4444)',
                border: '1px solid',
                borderColor: memoryEnabled
                  ? 'rgba(62, 207, 142, 0.3)'
                  : 'rgba(239, 68, 68, 0.25)',
              }}
            >
              {memoryEnabled
                ? t('chat.memoryActiveShort', { defaultValue: 'Memória ativa' })
                : t('chat.memoryPausedShort', { defaultValue: 'Memória pausada' })}
            </span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '4px', lineHeight: 1.4 }}>
            {t('memory.useMemoryGlobalDesc')}
          </div>
        </div>
        <button
          className={`toggle-btn ${memoryEnabled ? 'on' : 'off'}`}
          onClick={toggleMemoryEnabled}
          type="button"
          aria-pressed={memoryEnabled}
          aria-label={t('memory.useMemoryGlobal')}
        >
          {memoryEnabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
        </button>
      </div>

      {/* Info Card */}
      <div style={{
        background: 'var(--surface-soft)', border: '1px solid var(--hairline)',
        borderRadius: '12px', padding: '12px 16px', display: 'flex',
        gap: '12px', marginBottom: '20px',
      }}>
        <Info size={18} style={{ color: 'var(--primary)', flexShrink: 0, marginTop: '2px' }} />
        <div>
          <h4 style={{ fontSize: '13.5px', fontWeight: 600, color: 'var(--ink)', margin: '0 0 4px 0' }}>{t('memory.howTitle')}</h4>
          <p style={{ fontSize: '12.5px', color: 'var(--body)', margin: 0, lineHeight: '1.5' }}>
            {t('memory.howBody')}
          </p>
        </div>
      </div>

      {/* Phase C2: Summaries */}
      <div style={{
        marginBottom: '20px', background: 'var(--surface-card)',
        border: '1px solid var(--hairline)', borderRadius: '12px', padding: '14px 16px',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px', gap: '8px', flexWrap: 'wrap' }}>
          <h3 style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: 'var(--ink)' }}>
            {t('memory.summariesTitle')}
          </h3>
          <button
            type="button"
            onClick={handleRefreshSummaries}
            disabled={refreshingSummaries}
            style={{
              fontSize: '12px', padding: '6px 12px', borderRadius: '8px',
              border: '1px solid var(--hairline)', background: 'var(--surface-soft)',
              color: 'var(--ink)', cursor: 'pointer',
            }}
          >
            {refreshingSummaries ? t('common.loading') : t('memory.refreshSummaries')}
          </button>
        </div>
        <p style={{ fontSize: '12px', color: 'var(--muted)', margin: '0 0 12px 0' }}>
          {t('memory.summariesDesc')}
        </p>
        {summaries.length === 0 ? (
          <p style={{ fontSize: '12.5px', color: 'var(--muted)', margin: 0 }}>
            {t('memory.summariesEmpty')}
          </p>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {summaries.map((s) => (
              <div
                key={s.id}
                style={{
                  border: '1px solid var(--hairline)', borderRadius: '8px',
                  padding: '10px 12px', background: 'var(--surface-soft)',
                }}
              >
                <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--primary)', marginBottom: '6px', textTransform: 'uppercase' }}>
                  {s.scope === 'global'
                    ? t('memory.summaryGlobal')
                    : s.scope === 'project'
                      ? `${t('memory.summaryProject')}: ${s.scope_ref || '-'}`
                      : s.scope}
                </div>
                <pre style={{
                  margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  fontFamily: 'inherit', fontSize: '12.5px', color: 'var(--body)',
                  lineHeight: 1.45,
                }}>
                  {s.summary_md}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Search Bar */}
      <div style={{ position: 'relative', marginBottom: '16px', maxWidth: '360px' }}>
        <Search size={14} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)' }} />
        <input
          type="text"
          placeholder={t('memory.searchPlaceholder')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%', padding: '8px 12px 8px 34px',
            borderRadius: '8px', border: '1px solid var(--hairline)',
            background: 'var(--surface-card)', color: 'var(--ink)',
            fontSize: '13px', outline: 'none', boxSizing: 'border-box',
          }}
        />
      </div>

      {/* Content */}
      {loading ? (
        <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '32px' }}>{t('memory.loading')}</div>
      ) : error ? (
        <div style={{ color: 'var(--error, #ef4444)', padding: '16px 0', fontSize: '13px' }}>{error}</div>
      ) : filteredMemories.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '48px 16px', border: '1px dashed var(--hairline)', borderRadius: '12px', color: 'var(--muted)' }}>
          <Brain size={32} style={{ opacity: 0.3, marginBottom: '8px' }} />
          <p style={{ margin: 0, fontSize: '13.5px' }}>
            {searchQuery
              ? t('memory.emptySearch')
              : t('memory.emptyFacts')}
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {groupedByDomain.map(({ domain, facts }) => (
            <section key={domain}>
              <div style={{
                display: 'flex', alignItems: 'center', gap: '8px',
                marginBottom: '10px', paddingBottom: '6px',
                borderBottom: '1px solid var(--hairline)',
              }}>
                <h3 style={{
                  margin: 0, fontSize: '13px', fontWeight: 700,
                  color: 'var(--ink)', letterSpacing: '0.02em',
                }}>
                  {getDomainLabel(domain)}
                </h3>
                <span style={{
                  fontSize: '11px', fontWeight: 600, color: 'var(--muted)',
                  background: 'var(--surface-soft)', borderRadius: '10px',
                  padding: '1px 8px',
                }}>
                  {facts.length}
                </span>
                <span style={{
                  fontSize: '10px', color: 'var(--muted-soft)', fontFamily: 'ui-monospace, monospace',
                }}>
                  {domain}
                </span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '10px' }}>
                {facts.map((m) => (
                  <div
                    key={m.id}
                    style={{
                      background: 'var(--surface-card)', border: '1px solid var(--hairline)',
                      borderRadius: '10px', padding: '12px 14px',
                      display: 'flex', justifyContent: 'space-between', gap: '10px',
                      transition: 'box-shadow 0.15s',
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1, minWidth: 0 }}>
                      {/* Category + fact_key badges */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'wrap' }}>
                        <span style={{ color: getCategoryColor(m.category) }}>{getCategoryIcon(m.category)}</span>
                        <span style={{ fontSize: '10px', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', color: getCategoryColor(m.category) }}>
                          {getCategoryLabel(m.category)}
                        </span>
                        {m.fact_key ? (
                          <span
                            title={t('memory.factKey')}
                            style={{
                              fontSize: '10px', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                              color: 'var(--muted)', background: 'var(--surface-soft)',
                              borderRadius: '4px', padding: '1px 6px',
                              maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}
                          >
                            {m.fact_key}
                          </span>
                        ) : null}
                        {m.is_pinned ? (
                          <span style={{ fontSize: '9px', fontWeight: 700, color: 'var(--primary)', border: '1px solid var(--primary)', borderRadius: '4px', padding: '0 4px' }}>
                            {t('memory.pin')}
                          </span>
                        ) : null}
                      </div>
                      {/* Fact text */}
                      <p style={{ fontSize: '13.5px', color: 'var(--body-strong)', margin: 0, lineHeight: '1.4', wordBreak: 'break-word' }}>
                        {m.fact}
                      </p>
                      {/* Confidence + date */}
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                        <span style={{
                          fontSize: '10px', color: 'var(--muted-soft)',
                          background: 'var(--surface-soft)', borderRadius: '4px', padding: '1px 5px'
                        }}>
                          {t('memory.confidence', { pct: Math.round(m.confidence * 100) })}
                        </span>
                        <span style={{ fontSize: '10px', color: 'var(--muted-soft)' }}>
                          {new Date(m.updated_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', flexShrink: 0 }}>
                      <button
                        type="button"
                        onClick={() => handleTogglePin(m)}
                        title={m.is_pinned ? t('memory.unpin') : t('memory.pinAction')}
                        style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          padding: '6px', borderRadius: '6px',
                          border: 'none',
                          background: m.is_pinned ? 'rgba(204,120,92,0.12)' : 'transparent',
                          color: m.is_pinned ? 'var(--primary)' : 'var(--muted)',
                          cursor: 'pointer',
                        }}
                      >
                        {m.is_pinned ? <Pin size={14} /> : <PinOff size={14} />}
                      </button>
                      <button
                        onClick={() => handleDelete(m.id)}
                        title={t('memory.deleteFact')}
                        style={{
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          padding: '6px', borderRadius: '6px',
                          border: 'none', background: 'transparent', color: 'var(--muted)',
                          cursor: 'pointer',
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* B2: Extractor model settings */}
      {extractor && (
        <div style={{
          marginTop: '28px', borderTop: '1px solid var(--hairline)', paddingTop: '20px',
        }}>
          <h3 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--ink)', margin: '0 0 6px 0' }}>
            {t('memory.extractorTitle')}
          </h3>
          <p style={{ fontSize: '12.5px', color: 'var(--muted)', marginBottom: '14px', lineHeight: 1.45 }}>
            {t('memory.extractorDesc')}
          </p>

          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: '12px', gap: '12px',
          }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>{t('memory.extractorEnabled')}</div>
              <div style={{ fontSize: '11.5px', color: 'var(--muted)' }}>{t('memory.extractorEnabledDesc')}</div>
            </div>
            <button
              type="button"
              className={`toggle-btn ${extractor.memory_extractor_enabled !== false ? 'on' : 'off'}`}
              onClick={() =>
                setExtractor({
                  ...extractor,
                  memory_extractor_enabled: extractor.memory_extractor_enabled === false,
                })
              }
            >
              {extractor.memory_extractor_enabled !== false ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
            </button>
          </div>

          <div style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            marginBottom: '12px', gap: '12px',
          }}>
            <div>
              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--ink)' }}>{t('memory.llmSummaries')}</div>
              <div style={{ fontSize: '11.5px', color: 'var(--muted)' }}>{t('memory.llmSummariesDesc')}</div>
            </div>
            <button
              type="button"
              className={`toggle-btn ${extractor.memory_llm_summaries_enabled !== false ? 'on' : 'off'}`}
              onClick={() =>
                setExtractor({
                  ...extractor,
                  memory_llm_summaries_enabled: extractor.memory_llm_summaries_enabled === false,
                })
              }
            >
              {extractor.memory_llm_summaries_enabled !== false ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
            </button>
          </div>

          <div style={{ display: 'grid', gap: '10px', maxWidth: '420px' }}>
            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>
                {t('toolsSettings.providerLabel')}
              </label>
              <select
                value={extractor.memory_extractor_provider_id || ''}
                onChange={(e) =>
                  setExtractor({
                    ...extractor,
                    memory_extractor_provider_id: e.target.value || null,
                    memory_extractor_model_id: null,
                  })
                }
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: '8px',
                  border: '1px solid var(--hairline)', background: 'var(--surface-card)',
                  color: 'var(--ink)', fontSize: '13px',
                }}
              >
                <option value="">{t('memory.extractorUseFallback')}</option>
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ fontSize: '12px', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px' }}>
                {t('toolsSettings.modelLabel')}
              </label>
              <select
                value={extractor.memory_extractor_model_id || ''}
                disabled={!extractor.memory_extractor_provider_id}
                onChange={(e) =>
                  setExtractor({
                    ...extractor,
                    memory_extractor_model_id: e.target.value || null,
                  })
                }
                style={{
                  width: '100%', padding: '8px 10px', borderRadius: '8px',
                  border: '1px solid var(--hairline)', background: 'var(--surface-card)',
                  color: 'var(--ink)', fontSize: '13px',
                }}
              >
                <option value="">{t('toolsSettings.selectModel')}</option>
                {(
                  providers.find((p) => p.id === extractor.memory_extractor_provider_id)?.models.filter((m) => m.enabled) || []
                ).map((m) => (
                  <option key={m.id} value={m.id}>{m.display_name}</option>
                ))}
              </select>
            </div>
            <p style={{ fontSize: '11.5px', color: 'var(--muted)', margin: 0 }}>
              {t('memory.extractorSource')}:{' '}
              <strong>
                {extractor.resolved_source === 'memory_extractor'
                  ? t('memory.sourceDedicated')
                  : extractor.resolved_source === 'enhancer'
                    ? t('memory.sourceEnhancer')
                    : t('memory.sourceChat')}
              </strong>
            </p>
            <button
              type="button"
              className={`save-btn ${extractorSaved ? 'saved' : ''}`}
              onClick={saveExtractor}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                padding: '8px 14px', borderRadius: '8px', border: 'none',
                background: 'var(--primary)', color: '#fff', fontSize: '13px',
                fontWeight: 600, cursor: 'pointer', width: 'fit-content',
              }}
            >
              <Save size={14} />
              {extractorSaved ? t('common.saved') : t('tools.saveConfig')}
            </button>
          </div>
        </div>
      )}

      {/* Preview Modal */}
      {showPreview && (
        <div
          onClick={() => setShowPreview(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 9999, padding: '20px',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              background: 'var(--canvas)', borderRadius: '16px', padding: '24px',
              width: '100%', maxWidth: '620px', maxHeight: '80vh',
              overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--ink)', display: 'flex', gap: '8px', alignItems: 'center' }}>
                <Eye size={18} style={{ color: 'var(--primary)' }} />
                {t('memory.previewTitle')}
              </h3>
              <button onClick={() => setShowPreview(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)' }}>
                <X size={20} />
              </button>
            </div>

            {previewLoading ? (
              <p style={{ color: 'var(--muted)', textAlign: 'center', padding: '24px' }}>{t('memory.previewLoading')}</p>
            ) : preview ? (
              <>
                <div style={{ display: 'flex', gap: '12px', marginBottom: '14px' }}>
                  <span style={{ fontSize: '12px', background: 'var(--surface-soft)', borderRadius: '6px', padding: '4px 10px', color: 'var(--muted)' }}>
                    {t('memory.previewActiveFacts', { count: preview.fact_count })}
                  </span>
                  <span style={{ fontSize: '12px', background: 'var(--surface-soft)', borderRadius: '6px', padding: '4px 10px', color: 'var(--muted)' }}>
                    {t('memory.previewChars', { chars: preview.block_chars, tokens: Math.round(preview.block_chars / 4) })}
                  </span>
                </div>
                <pre style={{
                  whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                  fontSize: '12.5px', color: 'var(--body)', lineHeight: '1.6',
                  background: 'var(--surface-card)', borderRadius: '10px',
                  padding: '16px', border: '1px solid var(--hairline)', margin: 0,
                }}>
                  {preview.block || t('memory.previewEmpty')}
                </pre>
                <p style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '12px', marginBottom: 0 }}>
                  {t('memory.previewHint')}
                </p>
              </>
            ) : (
              <div style={{ display: 'flex', gap: '8px', color: 'var(--warning, #f59e0b)', alignItems: 'center' }}>
                <AlertTriangle size={16} />
                <span style={{ fontSize: '13px' }}>{t('memory.previewFail')}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Import memory from other AI providers (Claude-style) */}
      {showImportAi && (
        <div
          onClick={() => !importingText && setShowImportAi(false)}
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 9999, padding: '16px',
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="import-ai-title"
            style={{
              background: 'var(--canvas)', borderRadius: '16px', padding: '22px 24px',
              width: '100%', maxWidth: '560px', maxHeight: '90vh',
              overflow: 'auto', boxShadow: '0 20px 60px rgba(0,0,0,0.35)',
              border: '1px solid var(--hairline)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
              <div>
                <h3
                  id="import-ai-title"
                  style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--ink)', display: 'flex', gap: '8px', alignItems: 'center' }}
                >
                  <Sparkles size={18} style={{ color: 'var(--primary)' }} />
                  {t('memory.importFromAiTitle')}
                </h3>
                <p style={{ margin: '6px 0 0', fontSize: '12.5px', color: 'var(--muted)', lineHeight: 1.45 }}>
                  {t('memory.importFromAiDesc')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => !importingText && setShowImportAi(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--muted)', padding: 4 }}
                aria-label={t('memory.importCancel')}
              >
                <X size={20} />
              </button>
            </div>

            {/* Step 1 — copy prompt */}
            <div style={{ marginTop: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{
                  width: 22, height: 22, borderRadius: '50%',
                  background: 'var(--primary)', color: '#fff',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700, flexShrink: 0,
                }}>1</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
                  {t('memory.importStep1')}
                </span>
              </div>
              <div style={{
                position: 'relative',
                background: 'var(--surface-card)',
                border: '1px solid var(--hairline)',
                borderRadius: '10px',
                padding: '12px 12px 36px',
              }}>
                {importPromptLoading ? (
                  <p style={{ margin: 0, fontSize: '12.5px', color: 'var(--muted)' }}>{t('common.loading')}</p>
                ) : (
                  <pre style={{
                    margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                    fontSize: '11.5px', lineHeight: 1.5, color: 'var(--body)',
                    maxHeight: 160, overflow: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
                  }}>
                    {importPrompt}
                  </pre>
                )}
                <button
                  type="button"
                  onClick={handleCopyImportPrompt}
                  disabled={!importPrompt || importPromptLoading}
                  style={{
                    position: 'absolute', right: 10, bottom: 8,
                    display: 'inline-flex', alignItems: 'center', gap: 5,
                    padding: '5px 10px', borderRadius: 8,
                    border: '1px solid var(--hairline)',
                    background: 'var(--canvas)', color: 'var(--ink)',
                    fontSize: 12, fontWeight: 500, cursor: 'pointer',
                  }}
                >
                  {importPromptCopied ? <Check size={13} /> : <Copy size={13} />}
                  {importPromptCopied ? t('memory.importCopied') : t('memory.importCopyPrompt')}
                </button>
              </div>
            </div>

            {/* Step 2 — paste export */}
            <div style={{ marginTop: '18px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{
                  width: 22, height: 22, borderRadius: '50%',
                  background: 'var(--primary)', color: '#fff',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700, flexShrink: 0,
                }}>2</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--ink)' }}>
                  {t('memory.importStep2')}
                </span>
              </div>
              <textarea
                value={importPaste}
                onChange={(e) => setImportPaste(e.target.value)}
                placeholder={t('memory.importPastePlaceholder')}
                rows={8}
                disabled={importingText}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  resize: 'vertical', minHeight: 120,
                  borderRadius: 10, border: '1px solid var(--hairline)',
                  background: 'var(--surface-card)', color: 'var(--ink)',
                  padding: '12px 14px', fontSize: 13, lineHeight: 1.5,
                  fontFamily: 'inherit', outline: 'none',
                }}
              />
              <p style={{ margin: '8px 0 0', fontSize: 11.5, color: 'var(--muted)' }}>
                {t('memory.importMergeNote')}
              </p>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
              <button
                type="button"
                onClick={() => !importingText && setShowImportAi(false)}
                disabled={importingText}
                style={{
                  padding: '8px 14px', borderRadius: 8,
                  border: '1px solid var(--hairline)',
                  background: 'transparent', color: 'var(--ink)',
                  fontSize: 13, fontWeight: 500, cursor: 'pointer',
                }}
              >
                {t('memory.importCancel')}
              </button>
              <button
                type="button"
                onClick={handleImportFromAi}
                disabled={importingText || !importPaste.trim()}
                style={{
                  padding: '8px 16px', borderRadius: 8,
                  border: 'none',
                  background: !importPaste.trim() || importingText ? 'var(--muted)' : 'var(--primary)',
                  color: '#fff',
                  fontSize: 13, fontWeight: 600,
                  cursor: !importPaste.trim() || importingText ? 'not-allowed' : 'pointer',
                  opacity: !importPaste.trim() || importingText ? 0.7 : 1,
                }}
              >
                {importingText ? t('memory.importAdding') : t('memory.importAdd')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
