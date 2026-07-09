import { useEffect, useState } from 'react'
import {
  Eye, EyeOff, Save, ToggleLeft, ToggleRight, Database, Sparkles, Users, Trash2, X, Monitor, Sun, Moon, Search, ChevronDown, ChevronRight,
  ChevronLeft, Info, Settings, CreditCard, Shield, Sliders, Volume2, Lock, Link2, LogOut, Check, User, Palette, Type, Smartphone, Trash, Activity,
  Award, Languages
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { api } from '../api/client'
import { SUPPORTED_LOCALES } from '../i18n'
import { useStore } from '../store/useStore'
import type { Provider } from '../types'
import { CachePanel } from './CachePanel'
import { EnhancerSettings } from './EnhancerSettings'
import { FusionSettings } from './FusionSettings'
import { VisionRelaySettings } from './VisionRelaySettings'
import { WebSearchSettings } from './WebSearchSettings'
import { FreeRegistrySettings } from './FreeRegistrySettings'
import { FamilySettings } from './FamilySettings'
import { UsageDashboard } from './UsageDashboard'
import { RankingWeightsSettings } from './RankingWeightsSettings'
import { RankingsView } from './RankingsView'
type Tab = 'general' | 'providers' | 'rankings' | 'cache' | 'tools' | 'users' | 'dashboard'

// Responsive hook to detect mobile screens (< 768px)
function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' ? window.matchMedia('(max-width: 768px)').matches : false)
  
  useEffect(() => {
    if (typeof window === 'undefined') return
    const media = window.matchMedia('(max-width: 768px)')
    const listener = (e: MediaQueryListEvent) => setIsMobile(e.matches)
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }, [])
  
  return isMobile
}

export function AdminPanel() {
  const isMobile = useIsMobile()
  
  if (isMobile) {
    return <AdminPanelMobile />
  }
  return <AdminPanelDesktop />
}

// ─────────────────────────────────────────────────────────────────────────────
// 📱 MOBILE SETTINGS VIEW
// ─────────────────────────────────────────────────────────────────────────────

function AdminPanelMobile() {
  const { t, i18n } = useTranslation()
  const {
    setView, loadModels, user, theme, setTheme, chatFont, setChatFont,
    hapticFeedback, setHapticFeedback, displayName, fullName, occupation,
    customInstructions, setProfile, logout, locale, setLocale
  } = useStore()

  // Stack navigation state
  const [screenStack, setScreenStack] = useState<string[]>(['list'])
  const [activeBottomSheet, setActiveBottomSheet] = useState<'theme' | 'font' | 'language' | null>(null)
  const handleLocaleChange = (code: string) => {
    setLocale(code)
    i18n.changeLanguage(code)
  }

  // Profile temporary edit state
  const [tempFullName, setTempFullName] = useState(fullName)
  const [tempDisplayName, setTempDisplayName] = useState(displayName)
  const [tempOccupation, setTempOccupation] = useState(occupation)
  const [tempInstructions, setTempInstructions] = useState(customInstructions)
  const [profileSaved, setProfileSaved] = useState(false)

  // System states load
  const [providers, setProviders] = useState<Provider[]>([])
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [showKey, setShowKey] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [cfAccountId, setCfAccountId] = useState('')
  const [syncingAll, setSyncingAll] = useState(false)
  const [syncing, setSyncing] = useState<Record<string, boolean>>({})
  const [searchQueries, setSearchQueries] = useState<Record<string, string>>({})
  const [freeFilters, setFreeFilters] = useState<Record<string, boolean>>({})
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({})
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [tempCtx, setTempCtx] = useState('')
  const [showAllModels, setShowAllModels] = useState<Record<string, boolean>>({})

  // Users management state
  const [usersList, setUsersList] = useState<any[]>([])
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [userError, setUserError] = useState('')

  // Tool counters (dynamic check)
  const [toolsCount, setToolsCount] = useState(0)

  const activeModelsCount = providers.flatMap(p => p.models).filter(m => m.enabled).length

  const load = async () => {
    try {
      const data = await api.getProviders()
      setProviders(data)
      const cf = data.find((p) => p.id === 'cloudflare')
      if (cf) {
        const match = cf.base_url.match(/\/accounts\/([^/]+)\/ai/)
        if (match && match[1] !== '{account_id}') {
          setCfAccountId(match[1])
        }
      }
    } catch (e) {
      console.error(e)
    }
  }

  const loadTools = async () => {
    try {
      const [cfgEnh, cfgFus, cfgVis, cfgWeb] = await Promise.all([
        api.getEnhancerConfig().then(c => c.enhancer_enabled ? 1 : 0).catch(() => 0),
        api.getFusionConfig().then(c => c.enabled ? 1 : 0).catch(() => 0),
        api.getVisionRelayConfig().then(c => c.enabled ? 1 : 0).catch(() => 0),
        api.getWebSearchConfig().then(c => c.heuristic_enabled || c.api_key ? 1 : 0).catch(() => 0),
      ])
      setToolsCount(cfgEnh + cfgFus + cfgVis + cfgWeb)
    } catch {}
  }

  const fetchUsers = async () => {
    if (user?.role !== 'admin') return
    setLoadingUsers(true)
    setUserError('')
    try {
      const data = await api.getUsers()
      setUsersList(data)
    } catch (err: any) {
      console.error(err)
      setUserError(t('settings.loadUsersError'))
    } finally {
      setLoadingUsers(false)
    }
  }

  const saveKey = async (id: string) => {
    const payload: { api_key?: string; base_url?: string } = {}
    if (keys[id]?.trim()) {
      payload.api_key = keys[id].trim()
    }
    if (id === 'cloudflare') {
      payload.base_url = `https://api.cloudflare.com/client/v4/accounts/${cfAccountId.trim()}/ai/v1`
    }
    await api.updateProvider(id, payload)
    setSaved((s) => ({ ...s, [id]: true }))
    setTimeout(() => setSaved((s) => ({ ...s, [id]: false })), 2000)
    await load()
    await loadModels()
  }

  const toggleProvider = async (id: string, enabled: boolean) => {
    await api.updateProvider(id, { enabled })
    await load()
    await loadModels()
  }

  const toggleModel = async (modelId: string, enabled: boolean) => {
    await api.toggleModel(modelId, enabled)
    await load()
    await loadModels()
  }

  const handleConfirmFree = async (modelId: string) => {
    if (!window.confirm(t('settings.confirmFreePrompt'))) return
    try {
      await api.confirmModelFree(modelId)
      await load()
      await loadModels()
    } catch (err) {
      console.error(err)
      alert(t('settings.confirmModelError'))
    }
  }

  const handleSync = async (id: string) => {
    setSyncing((s) => ({ ...s, [id]: true }))
    try {
      await api.syncProviderModels(id)
      await load()
    } catch (err) {
      console.error(err)
    } finally {
      setSyncing((s) => ({ ...s, [id]: false }))
    }
  }

  const handleSyncAll = async () => {
    setSyncingAll(true)
    try {
      await api.syncAllProvidersModels()
      await load()
    } catch (err) {
      console.error(err)
    } finally {
      setSyncingAll(false)
    }
  }

  const handleToggleAll = async (providerId: string, enabled: boolean) => {
    await api.toggleAllModels(providerId, enabled)
    await load()
    await loadModels()
  }

  const handleDeleteUser = async (id: string, username: string) => {
    if (!window.confirm(t('settings.deleteUserConfirm', { username }))) {
      return
    }
    try {
      await api.deleteUser(id)
      setUsersList((prev) => prev.filter((u) => u.id !== id))
    } catch (err: any) {
      console.error(err)
      alert(t('settings.deleteUserFail'))
    }
  }

  const startEditing = (modelId: string, currentVal: number) => {
    setEditingModelId(modelId)
    setTempCtx(currentVal.toString())
  }

  const saveCtx = async (modelId: string) => {
    const val = parseInt(tempCtx)
    if (!isNaN(val) && val > 0) {
      await api.updateModel(modelId, { context_length: val })
      await load()
      await loadModels()
    }
    setEditingModelId(null)
  }

  useEffect(() => {
    load()
    loadTools()
  }, [])

  // Stack navigation with Browser history synchronization
  useEffect(() => {
    const initialStack = ['list']
    setScreenStack(initialStack)
    window.history.pushState({ inSettings: true, screenStack: initialStack }, '')

    const handlePopState = (e: PopStateEvent) => {
      if (e.state && e.state.inSettings && e.state.screenStack) {
        if (hapticFeedback && typeof navigator !== 'undefined' && navigator.vibrate) {
          navigator.vibrate(8)
        }
        setScreenStack(e.state.screenStack)
      } else {
        setView('chat')
      }
    }

    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [setView])

  const pushScreen = (screenName: string) => {
    if (hapticFeedback && typeof navigator !== 'undefined' && navigator.vibrate) {
      navigator.vibrate(10)
    }
    const nextStack = [...screenStack, screenName]
    setScreenStack(nextStack)
    window.history.pushState({ inSettings: true, screenStack: nextStack }, '')
  }

  const popScreen = () => {
    window.history.back()
  }

  const currentScreen = screenStack[screenStack.length - 1]

  useEffect(() => {
    if (currentScreen === 'usuarios') {
      fetchUsers()
    }
  }, [currentScreen])

  // Custom vibrate helper
  const triggerHaptic = (ms = 12) => {
    if (hapticFeedback && typeof navigator !== 'undefined' && navigator.vibrate) {
      try { navigator.vibrate(ms) } catch {}
    }
  }

  // Reusable header component for sub-screens
  function Header({ title }: { title: string }) {
    return (
      <header className="settings-mobile-header">
        <button className="settings-mobile-header-btn" onClick={popScreen} title={t("common.back")} aria-label={t("settings.backToPrevious")}>
          <ChevronLeft size={20} />
        </button>
        <span className="settings-mobile-header-title">{title}</span>
        <button className="settings-mobile-header-btn" onClick={() => alert('NexusLocal v1.0.0 (Local-First AI Server)')} title={t("common.info")}>
          <Info size={18} />
        </button>
      </header>
    )
  }

  const handleUpdateProfile = () => {
    setProfile({
      fullName: tempFullName,
      displayName: tempDisplayName,
      occupation: tempOccupation,
      customInstructions: tempInstructions
    })
    setProfileSaved(true)
    triggerHaptic(20)
    setTimeout(() => setProfileSaved(false), 2000)
  }

  const handleToggleHaptic = (val: boolean) => {
    setHapticFeedback(val)
    if (val && typeof navigator !== 'undefined' && navigator.vibrate) {
      try { navigator.vibrate(20) } catch {}
    }
  }

  // Permissões Mock State
  const [micPerm, setMicPerm] = useState(true)
  const [camPerm, setCamPerm] = useState(false)
  const [notifPerm, setNotifPerm] = useState(true)
  const [locPerm, setLocPerm] = useState(false)

  // Privacidade Mock State
  const [telemetry, setTelemetry] = useState(false)
  const [localHistory, setLocalHistory] = useState(true)

  // Voz Mock State
  const [selectedVoice, setSelectedVoice] = useState('auto')

  return (
    <>
      {/* SCREEN 1: Main Settings List */}
      {currentScreen === 'list' && (
        <div className="settings-mobile-container-view">
          <header className="settings-mobile-header">
            <button className="settings-mobile-header-btn" onClick={() => setView('chat')} title={t("settings.closeSettings")} aria-label={t("settings.closeModal")}>
              <ChevronLeft size={20} />
            </button>
            <span className="settings-mobile-header-title">{t("settings.title")}</span>
            <button className="settings-mobile-header-btn" onClick={() => alert('NexusLocal v1.0.0 (Local-First AI Server)')} title={t("settings.information")}>
              <Info size={18} />
            </button>
          </header>

          <div className="settings-mobile-content">
            {/* User Profile Summary Card */}
            <div 
              className="settings-card-section" 
              style={{ padding: '16px', display: 'flex', flexDirection: 'row', alignItems: 'center', gap: '14px', cursor: 'pointer' }}
              onClick={() => pushScreen('perfil')}
            >
              <div style={{
                width: '46px',
                height: '46px',
                borderRadius: '50%',
                background: 'var(--primary)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '18px',
                fontWeight: 'bold',
                flexShrink: 0
              }}>
                {displayName.charAt(0).toUpperCase()}
              </div>
              <div style={{ flex: 1 }}>
                <h4 style={{ fontWeight: 600, fontSize: '15px', color: 'var(--ink)' }}>{displayName}</h4>
                <p style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>{t("settings.viewUpdateProfile")}</p>
              </div>
              <ChevronRight size={16} style={{ color: 'var(--muted)' }} />
            </div>

            {/* General Preferences Section */}
            <div className="settings-card-section">
              <div className="settings-card-section-title">{t("settings.appearancePrefs")}</div>
              
              <div className="settings-list-item" onClick={() => { setActiveBottomSheet('theme'); triggerHaptic() }}>
                <div className="settings-list-item-left">
                  <Palette size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t("settings.colorMode")}</span>
                    <span className="settings-list-item-subtitle">
                      {theme === 'system' ? t('settings.themeSystem') : theme === 'light' ? t('settings.themeLight') : t('settings.themeDark')}
                    </span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => { setActiveBottomSheet('font'); triggerHaptic() }}>
                <div className="settings-list-item-left">
                  <Type size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t("settings.fontStyle")}</span>
                    <span className="settings-list-item-subtitle">
                      {chatFont === 'sans' ? 'Claude Sans (Inter)' : chatFont === 'serif' ? 'Claude Serif (Garamond)' : 'JetBrains Mono'}
                    </span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => { setActiveBottomSheet('language'); triggerHaptic() }}>
                <div className="settings-list-item-left">
                  <Languages size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t('settings.language')}</span>
                    <span className="settings-list-item-subtitle">
                      {SUPPORTED_LOCALES.find(l => l.code === locale)?.nativeName || locale}
                    </span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">{t("settings.haptic")}</span>
                  <span className="toggle-row-desc">{t("settings.hapticDesc")}</span>
                </div>
                <button className={`toggle-btn ${hapticFeedback ? 'on' : 'off'}`} onClick={() => handleToggleHaptic(!hapticFeedback)}>
                  {hapticFeedback ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
            </div>

            {/* Model capabilities & Tools */}
            <div className="settings-card-section">
              <div className="settings-card-section-title">{t("settings.modelsAgents")}</div>

              <div className="settings-list-item" onClick={() => pushScreen('capacidades')}>
                <div className="settings-list-item-left">
                  <Sliders size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t("settings.capabilities")}</span>
                    <span className="settings-list-item-subtitle">{t("settings.capabilitiesSub")}</span>
                  </div>
                </div>
                <div className="settings-list-item-right">
                  {activeModelsCount > 0 && <span className="settings-list-item-counter">{t('settings.activatedCount', { count: activeModelsCount })}</span>}
                  <ChevronRight size={16} />
                </div>
              </div>

              <div className="settings-list-item" onClick={() => { pushScreen('rankings'); triggerHaptic() }}>
                <div className="settings-list-item-left">
                  <Award size={16} style={{ color: 'var(--primary)' }} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t("settings.modelRankings")}</span>
                    <span className="settings-list-item-subtitle">{t("settings.rankingsSub")}</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('conectores')}>
                <div className="settings-list-item-left">
                  <Sparkles size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t("settings.connectors")}</span>
                    <span className="settings-list-item-subtitle">{t("settings.connectorsSub")}</span>
                  </div>
                </div>
                <div className="settings-list-item-right">
                  {toolsCount > 0 && <span className="settings-list-item-counter">{t('settings.activeToolsCount', { count: toolsCount })}</span>}
                  <ChevronRight size={16} />
                </div>
              </div>

              {user?.role === 'admin' && (
                <div className="settings-list-item" onClick={() => pushScreen('usuarios')}>
                  <div className="settings-list-item-left">
                    <Users size={16} className="settings-list-item-icon" />
                    <div>
                      <span className="settings-list-item-label">{t("settings.manageUsers")}</span>
                      <span className="settings-list-item-subtitle">{t("settings.manageUsersSub")}</span>
                    </div>
                  </div>
                  <ChevronRight size={16} />
                </div>
              )}
            </div>

            {/* System Info & Permissions */}
            <div className="settings-card-section">
              <div className="settings-card-section-title">{t("settings.systemSecurity")}</div>

              <div className="settings-list-item" onClick={() => pushScreen('permissoes')}>
                <div className="settings-list-item-left">
                  <Smartphone size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Permissões</span>
                    <span className="settings-list-item-subtitle">Microfone, câmera e notificações</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('privacy')}>
                <div className="settings-list-item-left">
                  <Shield size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Privacidade & Dados</span>
                    <span className="settings-list-item-subtitle">Persistência SQLite e telemetria</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('shared_links')}>
                <div className="settings-list-item-left">
                  <Link2 size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Links Compartilhados</span>
                    <span className="settings-list-item-subtitle">Lista de conversas partilhadas publicamente</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('cobranca')}>
                <div className="settings-list-item-left">
                  <CreditCard size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Cobrança</span>
                    <span className="settings-list-item-subtitle">Community Edition e faturamento</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('voice')}>
                <div className="settings-list-item-left">
                  <Volume2 size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Leitura de Voz</span>
                    <span className="settings-list-item-subtitle">Seletor de vozes TTS do chat</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>
            </div>

            {/* Logout Card */}
            <div className="settings-card-section">
              <div 
                className="settings-list-item settings-list-item-danger" 
                onClick={() => { triggerHaptic(25); logout() }}
              >
                <div className="settings-list-item-left">
                  <LogOut size={16} className="settings-list-item-icon" />
                  <span className="settings-list-item-label">Sair da Conta</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 2: Perfil Edit Screen */}
      {currentScreen === 'perfil' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.editProfile")} />
          <div className="settings-mobile-content">
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', margin: '16px 0', gap: '8px' }}>
              <div style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                background: 'var(--primary)',
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: '24px',
                fontWeight: 'bold',
                border: '2px solid var(--hairline)'
              }}>
                {displayName.charAt(0).toUpperCase()}
              </div>
              <span style={{ fontSize: '13px', color: 'var(--muted)' }}>{t("settings.initialsHint")}</span>
            </div>

            <div className="settings-card-section" style={{ padding: '16px', gap: '14px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', marginBottom: '6px' }}>{t("settings.fullName")}</label>
                <input 
                  type="text" 
                  value={tempFullName} 
                  onChange={(e) => setTempFullName(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-md)', color: 'var(--ink)', fontSize: '14px', outline: 'none' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', marginBottom: '6px' }}>{t("settings.howToCall")}</label>
                <input 
                  type="text" 
                  value={tempDisplayName} 
                  onChange={(e) => setTempDisplayName(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-md)', color: 'var(--ink)', fontSize: '14px', outline: 'none' }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', marginBottom: '6px' }}>{t("settings.occupation")}</label>
                <select 
                  value={tempOccupation} 
                  onChange={(e) => setTempOccupation(e.target.value)}
                  style={{ width: '100%', padding: '10px 12px', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-md)', color: 'var(--ink)', fontSize: '14px', outline: 'none' }}
                >
                  <option value="">{t("common.select")}</option>
                  <option value="Desenvolvedor">{t("settings.occupationDev")}</option>
                  <option value="Designer">{t("settings.occupationDesigner")}</option>
                  <option value="Gerente">{t("settings.occupationManager")}</option>
                  <option value="Estudante">{t("settings.occupationStudent")}</option>
                  <option value="Outro">{t("settings.occupationOther")}</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: 'var(--muted)', textTransform: 'uppercase', marginBottom: '6px' }}>{t("settings.customInstructions")}</label>
                <textarea 
                  value={tempInstructions} 
                  onChange={(e) => setTempInstructions(e.target.value)}
                  placeholder={t("settings.instructionsPlaceholder")}
                  style={{ width: '100%', height: '100px', padding: '10px 12px', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-md)', color: 'var(--ink)', fontSize: '14px', outline: 'none', resize: 'none' }}
                />
              </div>
            </div>

            <div className="settings-card-section" style={{ padding: '16px' }}>
              <h4 style={{ fontWeight: 600, fontSize: '14px', color: 'var(--ink)', marginBottom: '4px' }}>{t("settings.accountActions")}</h4>
              <p style={{ fontSize: '11px', color: 'var(--muted)', marginBottom: '12px' }}>{t("settings.accountActionsDesc")}</p>
              <button 
                style={{ width: '100%', padding: '10px', background: 'rgba(198,69,69,0.08)', border: '1px solid var(--error)', borderRadius: 'var(--radius-md)', color: 'var(--error)', fontSize: '13px', fontWeight: 500 }}
                onClick={() => {
                  if (window.confirm(t('settings.deleteAccountConfirm'))) {
                    logout()
                  }
                }}
              >
                Excluir Conta
              </button>
            </div>
          </div>

          <div className="settings-mobile-sticky-footer">
            <button 
              className="settings-mobile-primary-btn" 
              onClick={handleUpdateProfile}
              disabled={profileSaved}
            >
              {profileSaved ? t('settings.profileUpdated') : t('settings.savePreferences')}
            </button>
          </div>
        </div>
      )}

      {/* SCREEN 3: Capacidades Screen */}
      {currentScreen === 'capacidades' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.capabilities")} />
          <div className="settings-mobile-content">
            <p style={{ fontSize: '13px', color: 'var(--muted)', padding: '0 4px', marginBottom: '8px' }}>
              {t('settings.capabilitiesDesc')}
            </p>

            <div className="settings-card-section">
              <div className="settings-list-item" onClick={() => pushScreen('cache_settings')}>
                <div className="settings-list-item-left">
                  <Database size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">{t("settings.smartCache")}</span>
                    <span className="settings-list-item-subtitle">{t("settings.cacheSettingsSub")}</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>
            </div>

            <div className="settings-card-section-title" style={{ marginTop: '12px' }}>🎁 Provedores Gratuitos/Testes</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {providers.filter(p => p.is_free).map(prov => (
                <div key={prov.id} className="settings-card-section">
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 16px', background: 'var(--surface-soft)', borderBottom: '1px solid var(--hairline)' }}>
                    <div>
                      <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--ink)' }}>{prov.name}</h4>
                      <span className="tier-badge free" style={{ marginTop: '4px', display: 'inline-block' }}>{t("settings.offersFree")}</span>
                    </div>
                    <button 
                      className={`toggle-btn ${prov.enabled ? 'on' : 'off'}`}
                      onClick={() => toggleProvider(prov.id, !prov.enabled)}
                    >
                      {prov.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                    </button>
                  </div>

                  {prov.enabled && (
                    <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {prov.has_key && (
                        <button 
                          className="sync-btn" 
                          style={{ width: '100%', justifyContent: 'center' }} 
                          disabled={syncing[prov.id]}
                          onClick={() => handleSync(prov.id)}
                        >
                          {syncing[prov.id] ? t('common.syncing') : t('settings.syncModels')}
                        </button>
                      )}
                      
                      <div className="key-field" style={{ padding: 0, border: 'none' }}>
                        <label style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>{t("settings.apiKey")}</label>
                        <div className="key-input-row" style={{ marginTop: '6px' }}>
                          <input 
                            type={showKey[prov.id] ? 'text' : 'password'}
                            placeholder={prov.has_key ? '••••••••••••••••' : 'Cole sua chave aqui'}
                            value={keys[prov.id] ?? ''}
                            onChange={(e) => setKeys({ ...keys, [prov.id]: e.target.value })}
                            style={{ flex: 1, padding: '8px 12px', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-sm)', color: 'var(--ink)', fontSize: '13px' }}
                          />
                          <button 
                            className={`save-btn ${saved[prov.id] ? 'saved' : ''}`}
                            onClick={() => saveKey(prov.id)}
                            disabled={!keys[prov.id]?.trim()}
                          >
                            {saved[prov.id] ? t('common.saved') : t('common.save')}
                          </button>
                        </div>
                      </div>

                      {/* Models List */}
                      <div style={{ marginTop: '6px' }}>
                        <label style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600, display: 'block', marginBottom: '8px' }}>{t("settings.enabledModels")}</label>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                          {(showAllModels[prov.id] ? prov.models : prov.models.slice(0, 6)).map(model => (
                            <div 
                              key={model.id} 
                              style={{ 
                                display: 'flex', 
                                alignItems: 'center', 
                                gap: '6px', 
                                padding: '4px 8px', 
                                background: model.enabled ? 'rgba(204,120,92,0.08)' : 'var(--surface-soft)', 
                                border: '1px solid',
                                borderColor: model.enabled ? 'rgba(204,120,92,0.2)' : 'var(--hairline)',
                                borderRadius: 'var(--radius-pill)',
                                fontSize: '12px'
                              }}
                            >
                              <span style={{ color: model.enabled ? 'var(--ink)' : 'var(--muted)', display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                                {model.display_name}
                                {model.confirmed_free && (
                                  <span style={{ color: 'var(--cyan)', fontSize: '10px' }} title="Confirmado Free">✓</span>
                                )}
                              </span>
                              <button 
                                onClick={() => toggleModel(model.id, !model.enabled)} 
                                style={{ display: 'flex', alignItems: 'center', color: model.enabled ? 'var(--primary)' : 'var(--muted)' }}
                              >
                                {model.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                              </button>
                            </div>
                          ))}
                        </div>
                        {prov.models.length > 6 && (
                          <button
                            onClick={() => setShowAllModels(prev => ({ ...prev, [prov.id]: !prev[prov.id] }))}
                            style={{
                              width: '100%',
                              padding: '6px 12px',
                              marginTop: '8px',
                              borderRadius: 'var(--radius-sm)',
                              border: '1px solid var(--hairline)',
                              background: 'var(--surface-soft)',
                              color: 'var(--primary)',
                              fontSize: '12px',
                              fontWeight: 500,
                              cursor: 'pointer',
                              textAlign: 'center'
                            }}
                          >
                            {showAllModels[prov.id] ? 'Mostrar menos' : `Mostrar todos (${prov.models.length})`}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div className="settings-card-section-title" style={{ marginTop: '12px' }}>💎 Provedores Pagos</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {providers.filter(p => !p.is_free).map(prov => (
                <div key={prov.id} className="settings-card-section">
                  <div style={{ display: 'flex', justifyContent: 'space-between', padding: '14px 16px', background: 'var(--surface-soft)', borderBottom: '1px solid var(--hairline)' }}>
                    <div>
                      <h4 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--ink)' }}>{prov.name}</h4>
                      <span className="tier-badge paid" style={{ marginTop: '4px', display: 'inline-block' }}>{t("settings.paidOnly")}</span>
                    </div>
                    <button 
                      className={`toggle-btn ${prov.enabled ? 'on' : 'off'}`}
                      onClick={() => toggleProvider(prov.id, !prov.enabled)}
                    >
                      {prov.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                    </button>
                  </div>

                  {prov.enabled && (
                    <div style={{ padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      {prov.has_key && (
                        <button 
                          className="sync-btn" 
                          style={{ width: '100%', justifyContent: 'center' }} 
                          disabled={syncing[prov.id]}
                          onClick={() => handleSync(prov.id)}
                        >
                          {syncing[prov.id] ? t('common.syncing') : t('settings.syncModels')}
                        </button>
                      )}
                      
                      <div className="key-field" style={{ padding: 0, border: 'none' }}>
                        <label style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600 }}>{t("settings.apiKey")}</label>
                        <div className="key-input-row" style={{ marginTop: '6px' }}>
                          <input 
                            type={showKey[prov.id] ? 'text' : 'password'}
                            placeholder={prov.has_key ? '••••••••••••••••' : 'Cole sua chave aqui'}
                            value={keys[prov.id] ?? ''}
                            onChange={(e) => setKeys({ ...keys, [prov.id]: e.target.value })}
                            style={{ flex: 1, padding: '8px 12px', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-sm)', color: 'var(--ink)', fontSize: '13px' }}
                          />
                          <button 
                            className={`save-btn ${saved[prov.id] ? 'saved' : ''}`}
                            onClick={() => saveKey(prov.id)}
                            disabled={!keys[prov.id]?.trim()}
                          >
                            {saved[prov.id] ? t('common.saved') : t('common.save')}
                          </button>
                        </div>
                      </div>

                      {/* Models List */}
                      <div style={{ marginTop: '6px' }}>
                        <label style={{ fontSize: '11px', color: 'var(--muted)', fontWeight: 600, display: 'block', marginBottom: '8px' }}>{t("settings.enabledModels")}</label>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                          {(showAllModels[prov.id] ? prov.models : prov.models.slice(0, 6)).map(model => (
                            <div 
                              key={model.id} 
                              style={{ 
                                display: 'flex', 
                                alignItems: 'center', 
                                gap: '6px', 
                                padding: '4px 8px', 
                                background: model.enabled ? 'rgba(204,120,92,0.08)' : 'var(--surface-soft)', 
                                border: '1px solid',
                                borderColor: model.enabled ? 'rgba(204,120,92,0.2)' : 'var(--hairline)',
                                borderRadius: 'var(--radius-pill)',
                                fontSize: '12px'
                              }}
                            >
                              <span style={{ color: model.enabled ? 'var(--ink)' : 'var(--muted)' }}>{model.display_name}</span>
                              <button 
                                onClick={() => toggleModel(model.id, !model.enabled)} 
                                style={{ display: 'flex', alignItems: 'center', color: model.enabled ? 'var(--primary)' : 'var(--muted)' }}
                              >
                                {model.enabled ? <ToggleRight size={18} /> : <ToggleLeft size={18} />}
                              </button>
                            </div>
                          ))}
                        </div>
                        {prov.models.length > 6 && (
                          <button
                            onClick={() => setShowAllModels(prev => ({ ...prev, [prov.id]: !prev[prov.id] }))}
                            style={{
                              width: '100%',
                              padding: '6px 12px',
                              marginTop: '8px',
                              borderRadius: 'var(--radius-sm)',
                              border: '1px solid var(--hairline)',
                              background: 'var(--surface-soft)',
                              color: 'var(--primary)',
                              fontSize: '12px',
                              fontWeight: 500,
                              cursor: 'pointer',
                              textAlign: 'center'
                            }}
                          >
                            {showAllModels[prov.id] ? 'Mostrar menos' : `Mostrar todos (${prov.models.length})`}
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 4: Cache Settings Screen */}
      {currentScreen === 'cache_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.smartCache")} />
          <div className="settings-mobile-content">
            <CachePanel />
          </div>
        </div>
      )}

      {/* SCREEN 5: Conectores (Ferramentas) Screen */}
      {currentScreen === 'conectores' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.connectorsShort")} />
          <div className="settings-mobile-content">
            <p style={{ fontSize: '13px', color: 'var(--muted)', padding: '0 4px', marginBottom: '8px' }}>
              Gerencie conectores e agentes especiais de prompt, roteamento inteligente e busca externa.
            </p>

            <div className="settings-card-section">
              <div className="settings-list-item" onClick={() => pushScreen('enhancer_settings')}>
                <div className="settings-list-item-left">
                  <Sparkles size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Melhorador de Prompt</span>
                    <span className="settings-list-item-subtitle">Otimização automática de prompts do usuário</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('fusion_settings')}>
                <div className="settings-list-item-left">
                  <Sliders size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Modo Fusion</span>
                    <span className="settings-list-item-subtitle">Execução paralela com modelo consolidador Juiz</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('vision_relay_settings')}>
                <div className="settings-list-item-left">
                  <Monitor size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Vision Relay</span>
                    <span className="settings-list-item-subtitle">Roteador para leitura de imagens sem visão nativa</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('web_search_settings')}>
                <div className="settings-list-item-left">
                  <Info size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Busca Web</span>
                    <span className="settings-list-item-subtitle">Conexão à internet via DuckDuckGo ou Brave Search</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('free_registry_settings')}>
                <div className="settings-list-item-left">
                  <Database size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Free Registry</span>
                    <span className="settings-list-item-subtitle">Sincronização da base e thresholds de failover</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>

              <div className="settings-list-item" onClick={() => pushScreen('ranking_weights_settings')}>
                <div className="settings-list-item-left">
                  <Sliders size={16} className="settings-list-item-icon" />
                  <div>
                    <span className="settings-list-item-label">Calibração de Score</span>
                    <span className="settings-list-item-subtitle">Ajustar pesos de qualidade, popularidade e uso</span>
                  </div>
                </div>
                <ChevronRight size={16} />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 6-9: Specific Tools Sub-screens */}
      {currentScreen === 'enhancer_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.enhancer")} />
          <div className="settings-mobile-content">
            <EnhancerSettings />
          </div>
        </div>
      )}

      {currentScreen === 'fusion_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.fusionMode")} />
          <div className="settings-mobile-content">
            <FusionSettings />
          </div>
        </div>
      )}

      {currentScreen === 'vision_relay_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.visionRelay")} />
          <div className="settings-mobile-content">
            <VisionRelaySettings />
          </div>
        </div>
      )}

      {currentScreen === 'web_search_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.webSearch")} />
          <div className="settings-mobile-content">
            <WebSearchSettings />
          </div>
        </div>
      )}

      {currentScreen === 'free_registry_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.freeRegistry")} />
          <div className="settings-mobile-content">
            <FreeRegistrySettings />
          </div>
        </div>
      )}

      {currentScreen === 'ranking_weights_settings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.scoreCalibration")} />
          <div className="settings-mobile-content">
            <RankingWeightsSettings />
          </div>
        </div>
      )}

      {currentScreen === 'rankings' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.modelRankings")} />
          <div className="settings-mobile-content" style={{ padding: '16px 8px calc(80px + env(safe-area-inset-bottom)) 8px' }}>
            <RankingsView />
          </div>
        </div>
      )}

      {/* SCREEN 10: Users Manager Screen */}
      {currentScreen === 'usuarios' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.users")} />
          <div className="settings-mobile-content">
            <h4 style={{ fontWeight: 600, fontSize: '15px', color: 'var(--ink)' }}>{t("settings.registeredUsers")}</h4>
            <p style={{ fontSize: '12px', color: 'var(--muted)' }}>Controle de acessos do servidor</p>

            {loadingUsers ? (
              <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '30px' }}>{t("settings.loadingUsers")}</div>
            ) : userError ? (
              <div className="login-error">{userError}</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
                {usersList.map((u) => (
                  <div 
                    key={u.id} 
                    className="settings-card-section" 
                    style={{ 
                      padding: '14px', 
                      gap: '8px', 
                      background: u.id === user?.id ? 'rgba(204,120,92,0.03)' : undefined,
                      borderColor: u.id === user?.id ? 'rgba(204,120,92,0.15)' : undefined
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span className="user-td-avatar" style={{ width: '32px', height: '32px', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface-soft)', border: '1px solid var(--hairline)', borderRadius: '50%', color: 'var(--primary)', fontWeight: 'bold' }}>
                          {u.username.charAt(0).toUpperCase()}
                        </span>
                        <div>
                          <strong style={{ fontSize: '14px', color: 'var(--ink)' }}>
                            {u.username}
                          </strong>
                          {u.id === user?.id && <span className="badge-you" style={{ marginLeft: '6px' }}>Você</span>}
                        </div>
                      </div>
                      <span className={`role-tag role-${u.role}`} style={{ fontSize: '10.5px' }}>
                        {u.role === 'admin' ? t('common.admin') : t('common.user')}
                      </span>
                    </div>

                    <div style={{ fontSize: '12.5px', color: 'var(--body)', marginTop: '4px', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                      <div>Email: {u.email || '-'}</div>
                      <div>Telefone: {u.phone || '-'}</div>
                      <div style={{ fontSize: '11px', color: 'var(--muted)', marginTop: '4px' }}>
                        Cadastrado em: {u.created_at ? new Date(u.created_at).toLocaleDateString('pt-BR') : '-'}
                      </div>
                    </div>

                    {u.id !== user?.id && (
                      <button 
                        className="user-delete-btn" 
                        style={{ alignSelf: 'flex-end', border: '1px solid var(--hairline)', padding: '6px 12px', background: 'rgba(198,69,69,0.05)', fontSize: '12px', width: 'auto', display: 'inline-flex', gap: '6px', marginTop: '6px' }}
                        onClick={() => handleDeleteUser(u.id, u.username)}
                      >
                        <Trash2 size={13} />
                        Excluir Usuário
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* SCREEN 11: Cobrança Screen */}
      {currentScreen === 'cobranca' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.billing")} />
          <div className="settings-mobile-content">
            <div className="settings-card-section" style={{ padding: '20px', gap: '16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h4 style={{ fontWeight: 600, color: 'var(--ink)' }}>Plano Atual</h4>
                  <p style={{ fontSize: '12px', color: 'var(--muted)', marginTop: '2px' }}>NexusLocal Community Edition</p>
                </div>
                <span className="tier-badge free">Gratuito</span>
              </div>
              <div style={{ borderTop: '1px solid var(--hairline)', paddingTop: '16px' }}>
                <h4 style={{ fontWeight: 500, fontSize: '13px', color: 'var(--muted)', marginBottom: '8px' }}>Métricas de Uso Local</h4>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span>Tokens Processados</span>
                    <strong style={{ color: 'var(--ink)' }}>2.4M</strong>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                    <span>Economia Estimada (Semantic Cache)</span>
                    <strong style={{ color: 'var(--primary)' }}>$ 38.40</strong>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="settings-card-section" style={{ padding: '20px', background: 'linear-gradient(135deg, rgba(204,120,92,0.12), rgba(204,120,92,0.03))', border: '1px solid rgba(204,120,92,0.2)', gap: '12px' }}>
              <h4 style={{ color: 'var(--primary)', fontWeight: 600 }}>Fazer upgrade para NexusLocal Pro</h4>
              <p style={{ fontSize: '12.5px', color: 'var(--body)', lineHeight: '1.5' }}>
                Obtenha suporte a multiplas instâncias, sincronização em nuvem segura, logs avançados e maior performance de cache distribuído.
              </p>
              <button className="settings-mobile-primary-btn" onClick={() => alert(t('settings.proInterest'))}>
                Upgrade para Pro
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 12: Permissões Screen */}
      {currentScreen === 'permissoes' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.permissions")} />
          <div className="settings-mobile-content">
            <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '12px', padding: '0 4px' }}>
              {t('settings.permissionsDesc')}
            </p>
            <div className="settings-card-section">
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Microfone</span>
                  <span className="toggle-row-desc">Permitir entrada de voz para transcrição de mensagens e prompts falados.</span>
                </div>
                <button className={`toggle-btn ${micPerm ? 'on' : 'off'}`} onClick={() => setMicPerm(!micPerm)}>
                  {micPerm ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Câmera</span>
                  <span className="toggle-row-desc">Permitir tirar fotos diretamente do chat para análise com modelos visuais.</span>
                </div>
                <button className={`toggle-btn ${camPerm ? 'on' : 'off'}`} onClick={() => setCamPerm(!camPerm)}>
                  {camPerm ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Notificações Push</span>
                  <span className="toggle-row-desc">Avisar quando execuções de agentes em segundo plano ou consolidações forem concluídas.</span>
                </div>
                <button className={`toggle-btn ${notifPerm ? 'on' : 'off'}`} onClick={() => setNotifPerm(!notifPerm)}>
                  {notifPerm ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Serviços de Localização</span>
                  <span className="toggle-row-desc">Usar geolocalização sutil para refinar buscas web com contexto de relevância regional.</span>
                </div>
                <button className={`toggle-btn ${locPerm ? 'on' : 'off'}`} onClick={() => setLocPerm(!locPerm)}>
                  {locPerm ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 13: Privacidade Screen */}
      {currentScreen === 'privacy' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.privacy")} />
          <div className="settings-mobile-content">
            <div className="settings-card-section">
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Telemetria Anônima</span>
                  <span className="toggle-row-desc">Compartilhar relatórios de erros totalmente limpos de dados sensíveis para ajudar a melhorar o app.</span>
                </div>
                <button className={`toggle-btn ${telemetry ? 'on' : 'off'}`} onClick={() => setTelemetry(!telemetry)}>
                  {telemetry ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
              <div className="toggle-row">
                <div className="toggle-row-info">
                  <span className="toggle-row-title">Persistir Histórico Local</span>
                  <span className="toggle-row-desc">Guardar conversas e artefatos apenas na base de dados SQLite local deste servidor.</span>
                </div>
                <button className={`toggle-btn ${localHistory ? 'on' : 'off'}`} onClick={() => setLocalHistory(!localHistory)}>
                  {localHistory ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
                </button>
              </div>
            </div>
            
            <div className="settings-card-section" style={{ padding: '16px', gap: '12px' }}>
              <h4 style={{ fontWeight: 600, fontSize: '14px', color: 'var(--ink)' }}>Segurança dos Dados</h4>
              <p style={{ fontSize: '12px', color: 'var(--muted)', lineHeight: '1.5' }}>
                Suas chaves de API de provedores de IA são encriptadas antes de serem salvas no banco de dados e nunca são compartilhadas com terceiros.
              </p>
              <button 
                style={{ padding: '10px 14px', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-md)', fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px', cursor: 'pointer', color: 'var(--error)', background: 'rgba(198,69,69,0.05)', marginTop: '8px' }}
                onClick={() => {
                  if (window.confirm(t('settings.clearCacheConfirm'))) {
                    localStorage.clear()
                    window.location.reload()
                  }
                }}
              >
                <Trash size={14} />
                Limpar todos os dados locais (localStorage)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 14: Shared Links Screen */}
      {currentScreen === 'shared_links' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.sharedLinks")} />
          <div className="settings-mobile-content" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minHeight: '60vh', gap: '16px' }}>
            <Link2 size={36} style={{ color: 'var(--muted)', opacity: 0.5 }} />
            <div style={{ textAlign: 'center' }}>
              <h4 style={{ fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>Nenhum link público</h4>
              <p style={{ fontSize: '12.5px', color: 'var(--muted)', maxWidth: '250px', lineHeight: '1.5' }}>
                Qualquer chat ou artefato que você compartilhar gerará um link público que aparecerá listado aqui.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SCREEN 15: Voz Screen */}
      {currentScreen === 'voice' && (
        <div className="settings-mobile-container-view">
          <Header title={t("settings.voiceSettings")} />
          <div className="settings-mobile-content">
            <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '12px', padding: '0 4px' }}>
              Selecione a voz sintetizada para leitura de mensagens e respostas de áudio do chat.
            </p>
            <div className="settings-card-section">
              {[
                { id: 'auto', name: 'Automático (Voz Padrão do Sistema)' },
                { id: 'google-pt', name: 'Google Português (Brasil)' },
                { id: 'maria', name: 'Microsoft Maria - Portuguese (Brazil)' },
                { id: 'daniel', name: 'Microsoft Daniel - Portuguese (Brazil)' },
                { id: 'luciana', name: 'Speech Synthesis Pt-BR (Premium)' },
              ].map((v) => (
                <div 
                  key={v.id} 
                  className="settings-list-item"
                  onClick={() => { setSelectedVoice(v.id); triggerHaptic(10) }}
                  style={{ background: selectedVoice === v.id ? 'rgba(204,120,92,0.05)' : undefined }}
                >
                  <span style={{ fontSize: '13.5px', color: selectedVoice === v.id ? 'var(--primary)' : 'var(--ink)', fontWeight: selectedVoice === v.id ? 600 : 500 }}>
                    {v.name}
                  </span>
                  {selectedVoice === v.id && <Check size={16} style={{ color: 'var(--primary)' }} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
         BOTTOM SHEETS FOR QUICK SELECT preference rows
         ───────────────────────────────────────────────────────────────────────────── */}

      {/* Theme Bottom Sheet */}
      {activeBottomSheet === 'theme' && (
        <div className="bottom-sheet-overlay" onClick={() => setActiveBottomSheet(null)}>
          <div className="bottom-sheet-container" onClick={(e) => e.stopPropagation()}>
            <div className="bottom-sheet-header">
              <span className="bottom-sheet-title">{t("settings.colorMode")}</span>
              <button 
                style={{ padding: '6px', borderRadius: '50%', background: 'var(--surface-soft)' }} 
                onClick={() => setActiveBottomSheet(null)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="bottom-sheet-options">
              {[
                { id: 'system' as const, label: t('settings.themeDevice'), icon: <Monitor size={16} /> },
                { id: 'light' as const, label: t('settings.themeLight'), icon: <Sun size={16} /> },
                { id: 'dark' as const, label: t('settings.themeDark'), icon: <Moon size={16} /> }
              ].map((opt) => (
                <div 
                  key={opt.id}
                  className={`bottom-sheet-option ${theme === opt.id ? 'active' : ''}`}
                  onClick={() => {
                    setTheme(opt.id)
                    triggerHaptic(15)
                    setActiveBottomSheet(null)
                  }}
                >
                  <div className="bottom-sheet-option-left">
                    {opt.icon}
                    <span>{opt.label}</span>
                  </div>
                  {theme === opt.id && <Check size={16} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}


      {activeBottomSheet === 'language' && (
        <div className="bottom-sheet-overlay" onClick={() => setActiveBottomSheet(null)}>
          <div className="bottom-sheet-container" onClick={(e) => e.stopPropagation()}>
            <div className="bottom-sheet-header">
              <span className="bottom-sheet-title">{t('settings.languageTitle')}</span>
              <button
                style={{ padding: '6px', borderRadius: '50%', background: 'var(--surface-soft)' }}
                onClick={() => setActiveBottomSheet(null)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="bottom-sheet-options">
              {SUPPORTED_LOCALES.map((opt) => (
                <div
                  key={opt.code}
                  className={`bottom-sheet-option ${locale === opt.code ? 'active' : ''}`}
                  onClick={() => {
                    handleLocaleChange(opt.code)
                    triggerHaptic(15)
                    setActiveBottomSheet(null)
                  }}
                >
                  <div className="bottom-sheet-option-left">
                    <Languages size={16} />
                    <span>{opt.nativeName}</span>
                  </div>
                  {locale === opt.code && <Check size={16} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Font Bottom Sheet */}
      {activeBottomSheet === 'font' && (
        <div className="bottom-sheet-overlay" onClick={() => setActiveBottomSheet(null)}>
          <div className="bottom-sheet-container" onClick={(e) => e.stopPropagation()}>
            <div className="bottom-sheet-header">
              <span className="bottom-sheet-title">{t("settings.fontStyleChat")}</span>
              <button 
                style={{ padding: '6px', borderRadius: '50%', background: 'var(--surface-soft)' }} 
                onClick={() => setActiveBottomSheet(null)}
              >
                <X size={16} />
              </button>
            </div>
            <div className="bottom-sheet-options">
              {[
                { id: 'sans' as const, label: 'Claude Sans (Inter)' },
                { id: 'serif' as const, label: 'Claude Serif (Cormorant Garamond)' },
                { id: 'mono' as const, label: 'JetBrains Mono' }
              ].map((opt) => (
                <div 
                  key={opt.id}
                  className={`bottom-sheet-option ${chatFont === opt.id ? 'active' : ''}`}
                  onClick={() => {
                    setChatFont(opt.id)
                    triggerHaptic(15)
                    setActiveBottomSheet(null)
                  }}
                >
                  <div className="bottom-sheet-option-left">
                    <Type size={16} />
                    <span style={{ fontFamily: opt.id === 'sans' ? 'var(--font-body)' : opt.id === 'serif' ? 'var(--font-serif)' : 'var(--font-mono)' }}>
                      {opt.label}
                    </span>
                  </div>
                  {chatFont === opt.id && <Check size={16} />}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// 💻 DESKTOP SETTINGS VIEW
// ─────────────────────────────────────────────────────────────────────────────

function AdminPanelDesktop() {
  const { t, i18n } = useTranslation()
  const { setView, loadModels, user, theme, setTheme, chatFont, setChatFont, modelSortMode, setModelSortMode, displayName, fullName, occupation, customInstructions, setProfile, locale, setLocale } = useStore()
  const handleLocaleChange = (code: string) => {
    setLocale(code)
    i18n.changeLanguage(code)
  }
  const [providers, setProviders] = useState<Provider[]>([])
  const [keys, setKeys] = useState<Record<string, string>>({})
  const [showKey, setShowKey] = useState<Record<string, boolean>>({})
  const [saved, setSaved] = useState<Record<string, boolean>>({})
  const [cfAccountId, setCfAccountId] = useState('')
  const [syncingAll, setSyncingAll] = useState(false)
  const [searchQueries, setSearchQueries] = useState<Record<string, string>>({})
  const [freeFilters, setFreeFilters] = useState<Record<string, boolean>>({})
  const [expandedProviders, setExpandedProviders] = useState<Record<string, boolean>>({})
  const [tab, setTab] = useState<Tab>('general')
  const [editingModelId, setEditingModelId] = useState<string | null>(null)
  const [tempCtx, setTempCtx] = useState('')
  const [usersList, setUsersList] = useState<any[]>([])
  const [loadingUsers, setLoadingUsers] = useState(false)
  const [userError, setUserError] = useState('')
  const [sidebarSearch, setSidebarSearch] = useState('')

  const startEditing = (modelId: string, currentVal: number) => {
    setEditingModelId(modelId)
    setTempCtx(currentVal.toString())
  }

  const saveCtx = async (modelId: string) => {
    const val = parseInt(tempCtx)
    if (!isNaN(val) && val > 0) {
      await api.updateModel(modelId, { context_length: val })
      await load()
      await loadModels()
    }
    setEditingModelId(null)
  }

  const load = async () => {
    const data = await api.getProviders()
    setProviders(data)
    const cf = data.find((p) => p.id === 'cloudflare')
    if (cf) {
      const match = cf.base_url.match(/\/accounts\/([^/]+)\/ai/)
      if (match && match[1] !== '{account_id}') {
        setCfAccountId(match[1])
      }
    }
  }

  const fetchUsers = async () => {
    if (user?.role !== 'admin') return
    setLoadingUsers(true)
    setUserError('')
    try {
      const data = await api.getUsers()
      setUsersList(data)
    } catch (err: any) {
      console.error(err)
      setUserError(t('settings.loadUsersError'))
    } finally {
      setLoadingUsers(false)
    }
  }

  const handleDeleteUser = async (id: string, username: string) => {
    if (!window.confirm(t('settings.deleteUserConfirm', { username }))) {
      return
    }
    try {
      await api.deleteUser(id)
      setUsersList((prev) => prev.filter((u) => u.id !== id))
    } catch (err: any) {
      console.error(err)
      alert(t('settings.deleteUserFail'))
    }
  }

  useEffect(() => {
    load()
  }, [])

  useEffect(() => {
    if (tab === 'users') {
      fetchUsers()
    }
  }, [tab])

  const saveKey = async (id: string) => {
    const payload: { api_key?: string; base_url?: string } = {}
    if (keys[id]?.trim()) {
      payload.api_key = keys[id].trim()
    }
    if (id === 'cloudflare') {
      payload.base_url = `https://api.cloudflare.com/client/v4/accounts/${cfAccountId.trim()}/ai/v1`
    }
    await api.updateProvider(id, payload)
    setSaved((s) => ({ ...s, [id]: true }))
    setTimeout(() => setSaved((s) => ({ ...s, [id]: false })), 2000)
    await load()
    await loadModels()
  }

  const toggleProvider = async (id: string, enabled: boolean) => {
    await api.updateProvider(id, { enabled })
    await load()
    await loadModels()
  }

  const [syncing, setSyncing] = useState<Record<string, boolean>>({})

  const toggleModel = async (modelId: string, enabled: boolean) => {
    await api.toggleModel(modelId, enabled)
    await load()
    await loadModels()
  }

  const handleConfirmFree = async (modelId: string) => {
    if (!window.confirm(t('settings.confirmFreePrompt'))) return
    try {
      await api.confirmModelFree(modelId)
      await load()
      await loadModels()
    } catch (err) {
      console.error(err)
      alert(t('settings.confirmModelError'))
    }
  }

  const handleSync = async (id: string) => {
    setSyncing((s) => ({ ...s, [id]: true }))
    try {
      await api.syncProviderModels(id)
      await load()
    } catch (err) {
      console.error(err)
    } finally {
      setSyncing((s) => ({ ...s, [id]: false }))
    }
  }

  const handleSyncAll = async () => {
    setSyncingAll(true)
    try {
      await api.syncAllProvidersModels()
      await load()
    } catch (err) {
      console.error(err)
    } finally {
      setSyncingAll(false)
    }
  }

  const handleToggleAll = async (providerId: string, enabled: boolean) => {
    await api.toggleAllModels(providerId, enabled)
    await load()
    await loadModels()
  }

  const freeProviders = providers.filter((p) => p.is_free)
  const paidProviders = providers.filter((p) => !p.is_free)

  const renderProvider = (prov: Provider) => {
    const q = (searchQueries[prov.id] || '').toLowerCase().trim()
    const freeOnly = freeFilters[prov.id] || false
    const isExpanded = expandedProviders[prov.id] || false

    const filteredModels = prov.models.filter((m) => {
      const matchesSearch = m.display_name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q)
      const isModelFree = prov.is_free || m.id.includes(':free') || m.id.includes('/free') || m.display_name.toLowerCase().includes('free')
      const matchesFree = !freeOnly || isModelFree
      return matchesSearch && matchesFree
    })

    return (
      <div key={prov.id} className="provider-card">
        <div 
          className="provider-header"
          onClick={() => setExpandedProviders((prev) => ({ ...prev, [prov.id]: !isExpanded }))}
          style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
        >
          <div className="provider-meta">
            <div className="provider-title-row" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              {isExpanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
              <h2>{prov.name}</h2>
              <span className={`tier-badge ${prov.is_free ? 'free' : 'paid'}`}>
                {prov.is_free ? t('settings.offersFree') : t('settings.paidOnly')}
              </span>
            </div>
            <span className="provider-url">{prov.base_url}</span>
          </div>
          <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
            {prov.has_key && (
              <button
                className="sync-btn"
                onClick={(e) => {
                  e.stopPropagation()
                  handleSync(prov.id)
                }}
                disabled={syncing[prov.id]}
              >
                {syncing[prov.id] ? t('common.syncing') : t('settings.syncModels')}
              </button>
            )}
            <button
              className={`toggle-btn ${prov.enabled ? 'on' : 'off'}`}
              onClick={(e) => {
                e.stopPropagation()
                toggleProvider(prov.id, !prov.enabled)
              }}
            >
              {prov.enabled ? <ToggleRight size={24} /> : <ToggleLeft size={24} />}
              {prov.enabled ? t('common.active') : t('common.inactive')}
            </button>
          </div>
        </div>

        {isExpanded && (
          <div className="provider-body" style={{ padding: '20px', borderTop: '1px solid var(--hairline)' }}>
            <div className="key-field">
              {prov.id === 'cloudflare' && (
                <div style={{ marginBottom: '12px' }}>
                  <label style={{ display: 'block', fontSize: '11.5px', fontWeight: 600, color: 'var(--muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                    Cloudflare Account ID
                  </label>
                  <input
                    type="text"
                    placeholder={t("settings.cloudflareId")}
                    value={cfAccountId}
                    onChange={(e) => setCfAccountId(e.target.value)}
                    style={{
                      width: '100%',
                      background: 'var(--surface-cream-strong)',
                      border: '1px solid var(--hairline)',
                      borderRadius: 'var(--radius-sm)',
                      padding: '8px 12px',
                      fontSize: '13.5px',
                      fontFamily: 'var(--font-mono)',
                      outline: 'none',
                      color: 'var(--ink)'
                    }}
                  />
                </div>
              )}
              <label>{t("settings.apiKey")}</label>
              <div className="key-input-row">
                <input
                  type={showKey[prov.id] ? 'text' : 'password'}
                  placeholder={prov.has_key ? (showKey[prov.id] ? (prov.masked_key || '••••••••••••••••') : '••••••••••••••••') : 'Cole sua chave aqui'}
                  value={keys[prov.id] ?? ''}
                  onChange={(e) => setKeys((k) => ({ ...k, [prov.id]: e.target.value }))}
                  autoComplete="new-password"
                  name={`api-key-${prov.id}`}
                />
                <button
                  className="icon-btn"
                  onClick={() => setShowKey((s) => ({ ...s, [prov.id]: !s[prov.id] }))}
                >
                  {showKey[prov.id] ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
                <button
                  className={`save-btn ${saved[prov.id] ? 'saved' : ''}`}
                  onClick={() => saveKey(prov.id)}
                  disabled={prov.id === 'cloudflare' ? (!cfAccountId.trim() && !keys[prov.id]?.trim()) : !keys[prov.id]?.trim()}
                >
                  <Save size={14} />
                  {saved[prov.id] ? t('common.saved') : t('common.save')}
                </button>
              </div>
              {!prov.has_key && (
                <p className="key-hint">
                  🔑 Sem chave configurada — os modelos deste provider não aparecerão no seletor.
                </p>
              )}
              {prov.id === 'freetheai' && (
                <div style={{ marginTop: '12px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                  <a 
                    href="https://discord.gg/secrets" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="sync-btn"
                    style={{ 
                      textDecoration: 'none', 
                      display: 'inline-flex', 
                      alignItems: 'center', 
                      gap: '6px',
                      background: '#5865F2',
                      borderColor: '#5865F2',
                      color: 'white',
                      padding: '6px 12px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12.5px',
                      fontWeight: 500
                    }}
                  >
                    <span>💬 Realizar Check-in (/checkin)</span>
                  </a>
                  <span style={{ fontSize: '11.5px', color: 'var(--muted)' }}>
                    Execute o comando <code>/checkin</code> no Discord do FreeTheAI diariamente para manter a chave ativa.
                  </span>
                </div>
              )}
            </div>

            {prov.models.length > 5 && (
              <div style={{ display: 'flex', gap: '10px', padding: '10px 0', borderBottom: '1px solid var(--hairline)', alignItems: 'center' }}>
                <input
                  type="text"
                  placeholder={t("settings.searchModel")}
                  value={searchQueries[prov.id] || ''}
                  onChange={(e) => setSearchQueries((prev) => ({ ...prev, [prov.id]: e.target.value }))}
                  style={{
                    flex: 1,
                    background: 'var(--surface-cream-strong)',
                    border: '1px solid var(--hairline)',
                    borderRadius: 'var(--radius-sm)',
                    padding: '6px 12px',
                    fontSize: '13px',
                    outline: 'none',
                    color: 'var(--ink)'
                  }}
                />
                {!prov.is_free && prov.models.some((m) => m.id.includes(':free') || m.id.includes('/free')) && (
                  <button
                    onClick={() => setFreeFilters((prev) => ({ ...prev, [prov.id]: !freeOnly }))}
                    style={{
                      padding: '6px 12px',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '12px',
                      fontWeight: 500,
                      border: '1px solid',
                      background: freeOnly ? 'rgba(93,184,166,0.10)' : 'var(--surface-cream-strong)',
                      color: freeOnly ? 'var(--cyan)' : 'var(--muted)',
                      borderColor: freeOnly ? 'rgba(93,184,166,0.25)' : 'var(--hairline)',
                      cursor: 'pointer'
                    }}
                  >
                    Apenas Gratuitos
                  </button>
                )}
              </div>
            )}

            {prov.models.length > 0 && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', padding: '8px 0', borderBottom: '1px solid var(--hairline)' }}>
                <button
                  onClick={() => handleToggleAll(prov.id, true)}
                  style={{
                    fontSize: '11px',
                    fontWeight: 500,
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid rgba(93,184,166,0.25)',
                    background: 'rgba(93,184,166,0.08)',
                    color: 'var(--cyan)',
                    cursor: 'pointer'
                  }}
                >
                  Ativar Todos
                </button>
                <button
                  onClick={() => handleToggleAll(prov.id, false)}
                  style={{
                    fontSize: '11px',
                    fontWeight: 500,
                    padding: '4px 10px',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--hairline)',
                    background: 'var(--surface-cream-strong)',
                    color: 'var(--muted-soft)',
                    cursor: 'pointer'
                  }}
                >
                  Desativar Todos
                </button>
              </div>
            )}

            <div className="models-grid" style={{ padding: '12px 0 0' }}>
              {filteredModels.length === 0 ? (
                <span style={{ fontSize: '13px', color: 'var(--muted-soft)', padding: '6px 0' }}>
                  Nenhum modelo encontrado com os filtros atuais.
                </span>
              ) : (
                filteredModels.map((m) => {
                  const isModelFree = prov.is_free || m.id.includes(':free') || m.id.includes('/free') || m.display_name.toLowerCase().includes('free')
                  return (
                    <div key={m.id} className={`model-chip ${m.enabled ? 'enabled' : 'disabled'} ${isModelFree ? 'free-model' : ''}`}>
                      <span className="model-chip-name">{m.display_name}</span>
                      {m.confirmed_free ? (
                        <span className="model-chip-free-badge confirmed" title="Modelo confirmado como gratuito pela comunidade">
                          <Check size={10} /> Free confirmado
                        </span>
                      ) : (
                        <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                          <span className="model-chip-free-badge not-confirmed" title="Não verificado como gratuito. Pode ser um modelo pago.">
                            Não verificado
                          </span>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleConfirmFree(m.id); }}
                            style={{
                              fontSize: '9px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              background: 'var(--surface-card)',
                              border: '1px solid var(--hairline)',
                              color: 'var(--muted)',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '2px'
                            }}
                            title="Confirmar manualmente como gratuito"
                          >
                            <Check size={10} /> Confirmar
                          </button>
                        </div>
                      )}
                      {editingModelId === m.id ? (
                        <input
                          type="number"
                          className="model-chip-ctx-input"
                          value={tempCtx}
                          onChange={(e) => setTempCtx(e.target.value)}
                          onBlur={() => saveCtx(m.id)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') saveCtx(m.id)
                            if (e.key === 'Escape') setEditingModelId(null)
                          }}
                          autoFocus
                        />
                      ) : (
                        <span
                          className={`model-chip-ctx source-${m.context_source || 'default'}`}
                          onClick={() => startEditing(m.id, m.context_length)}
                          style={{ cursor: 'pointer' }}
                          title="Clique para editar o limite de contexto"
                        >
                          {m.context_length >= 1000000
                            ? `${(m.context_length / 1000000).toFixed(0)}M`
                            : `${(m.context_length / 1000).toFixed(0)}K`}
                        </span>
                      )}
                      <button
                        className="chip-toggle"
                        onClick={() => toggleModel(m.id, !m.enabled)}
                        title={m.enabled ? 'Desativar' : 'Ativar'}
                      >
                        {m.enabled ? <ToggleRight size={16} /> : <ToggleLeft size={16} />}
                      </button>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        )}
      </div>
    )
  }

  const menuItems = [
    { id: 'general' as Tab, label: t('settings.general'), icon: <Monitor size={14} /> },
    { id: 'providers' as Tab, label: t('settings.providersModels'), icon: <Sparkles size={14} /> },
    { id: 'rankings' as Tab, label: t('settings.modelRankings'), icon: <Award size={14} /> },
    { id: 'dashboard' as Tab, label: t('settings.usage'), icon: <Activity size={14} /> },
    { id: 'cache' as Tab, label: t('settings.smartCache'), icon: <Database size={14} /> },
    { id: 'tools' as Tab, label: t('settings.tools'), icon: <Sparkles size={14} /> },
    ...(user?.role === 'admin' ? [{ id: 'users' as Tab, label: t('settings.users'), icon: <Users size={14} /> }] : [])
  ]

  const filteredMenuItems = menuItems.filter((item) =>
    item.label.toLowerCase().includes(sidebarSearch.toLowerCase())
  )

  return (
    <div className="settings-modal-overlay" onClick={() => setView('chat')}>
      <div className="settings-modal-container" onClick={(e) => e.stopPropagation()}>
        
        <aside className="settings-sidebar">
          <div className="settings-search-container">
            <Search size={14} className="search-icon" />
            <input
              type="text"
              placeholder={t("settings.searchPlaceholder")}
              value={sidebarSearch}
              onChange={(e) => setSidebarSearch(e.target.value)}
              className="settings-search-input"
            />
          </div>

          <div className="settings-menu-group">
            <div className="settings-group-title">{t("settings.title")}</div>
            {filteredMenuItems.map((item) => (
              <button
                key={item.id}
                className={`settings-menu-item ${tab === item.id ? 'active' : ''}`}
                onClick={() => setTab(item.id)}
              >
                {item.icon}
                <span>{item.label}</span>
              </button>
            ))}
          </div>
        </aside>

        <main className="settings-content-pane">
          <button className="settings-close-btn" onClick={() => setView('chat')} title={t("common.close")}>
            <X size={18} />
          </button>

          <div className="settings-content-scroll">
            
            {/* 1. General Tab */}
            {tab === 'general' && (
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>{t("settings.general")}</h2>
                <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '24px' }}>
                  {t('settings.generalDesc')}
                </p>

                <h3 style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '8px', marginBottom: '16px' }}>{t("settings.profile")}</h3>
                
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px' }}>
                  <div style={{
                    width: '48px',
                    height: '48px',
                    borderRadius: '50%',
                    background: 'var(--primary)',
                    color: '#fff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: '20px',
                    fontWeight: 'bold'
                  }}>
                    {displayName.charAt(0).toUpperCase()}
                  </div>
                  <div>
                    <h4 style={{ fontWeight: 600, color: 'var(--ink)', fontSize: '14px' }}>{t("settings.avatar")}</h4>
                    <p style={{ fontSize: '12px', color: 'var(--muted)' }}>{t("settings.initialsHint")}</p>
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--ink)' }}>
                    {t('settings.fullNameAlt')}
                  </label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setProfile({ fullName: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      fontSize: '14px',
                      outline: 'none'
                    }}
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--ink)' }}>
                    {t('settings.howClaudeCall')}
                  </label>
                  <input
                    type="text"
                    value={displayName}
                    onChange={(e) => setProfile({ displayName: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      fontSize: '14px',
                      outline: 'none'
                    }}
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '6px', color: 'var(--ink)' }}>
                    {t('settings.occupationDesc')}
                  </label>
                  <select
                    value={occupation}
                    onChange={(e) => setProfile({ occupation: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      fontSize: '14px',
                      outline: 'none'
                    }}
                  >
                    <option value="">{t("common.select")}</option>
                    <option value="Desenvolvedor">{t("settings.occupationDev")}</option>
                    <option value="Designer">{t("settings.occupationDesigner")}</option>
                    <option value="Gerente">{t("settings.occupationManager")}</option>
                    <option value="Estudante">{t("settings.occupationStudent")}</option>
                    <option value="Outro">{t("settings.occupationOther")}</option>
                  </select>
                </div>

                <div style={{ marginBottom: '24px' }}>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: 500, marginBottom: '4px', color: 'var(--ink)' }}>
                    {t('settings.instructionsForClaude')}
                  </label>
                  <p style={{ fontSize: '12px', color: 'var(--muted)', marginBottom: '8px', lineHeight: '1.4' }}>
                    {t('settings.instructionsHint')}
                  </p>
                  <textarea
                    value={customInstructions}
                    onChange={(e) => setProfile({ customInstructions: e.target.value })}
                    placeholder={t("settings.instructionsPlaceholder")}
                    style={{
                      width: '100%',
                      height: '90px',
                      padding: '8px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      fontSize: '14px',
                      outline: 'none',
                      resize: 'none'
                    }}
                  />
                </div>

                <h3 style={{ borderBottom: '1px solid var(--hairline)', paddingBottom: '8px', marginBottom: '16px' }}>{t("settings.preferences")}</h3>
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>{t("settings.appearance")}</h4>
                    <p style={{ fontSize: '12px', color: 'var(--muted)' }}>{t("settings.appearanceDesc")}</p>
                  </div>
                  <div style={{
                    display: 'flex',
                    gap: '4px',
                    background: 'var(--surface-card)',
                    border: '1px solid var(--hairline)',
                    padding: '4px',
                    borderRadius: 'var(--radius-md)'
                  }}>
                    <button
                      onClick={() => setTheme('system')}
                      style={{
                        padding: '6px 12px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '12px',
                        fontWeight: theme === 'system' ? 600 : 500,
                        background: theme === 'system' ? 'var(--canvas)' : 'transparent',
                        color: theme === 'system' ? 'var(--primary)' : 'var(--muted)',
                        cursor: 'pointer'
                      }}
                    >
                      <Monitor size={14} />
                      Dispositivo
                    </button>
                    <button
                      onClick={() => setTheme('light')}
                      style={{
                        padding: '6px 12px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '12px',
                        fontWeight: theme === 'light' ? 600 : 500,
                        background: theme === 'light' ? 'var(--canvas)' : 'transparent',
                        color: theme === 'light' ? 'var(--primary)' : 'var(--muted)',
                        cursor: 'pointer'
                      }}
                    >
                      <Sun size={14} />
                      Claro
                    </button>
                    <button
                      onClick={() => setTheme('dark')}
                      style={{
                        padding: '6px 12px',
                        borderRadius: 'var(--radius-sm)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        fontSize: '12px',
                        fontWeight: theme === 'dark' ? 600 : 500,
                        background: theme === 'dark' ? 'var(--canvas)' : 'transparent',
                        color: theme === 'dark' ? 'var(--primary)' : 'var(--muted)',
                        cursor: 'pointer'
                      }}
                    >
                      <Moon size={14} />
                      Escuro
                    </button>
                  </div>
                </div>

                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>{t('settings.language')}</h4>
                    <p style={{ fontSize: '12px', color: 'var(--muted)' }}>{t('settings.languageDesc')}</p>
                  </div>
                  <select
                    style={{
                      padding: '6px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      outline: 'none',
                      fontSize: '13px',
                      maxWidth: '220px'
                    }}
                    value={locale}
                    onChange={(e) => handleLocaleChange(e.target.value)}
                  >
                    {SUPPORTED_LOCALES.map((l) => (
                      <option key={l.code} value={l.code}>{l.nativeName}</option>
                    ))}
                  </select>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>{t('settings.fontStyleChatTitle')}</h4>
                    <p style={{ fontSize: '12px', color: 'var(--muted)' }}>{t('settings.fontStyleChatDesc')}</p>
                  </div>
                  <select
                    style={{
                      padding: '6px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      outline: 'none',
                      fontSize: '13px'
                    }}
                    value={chatFont}
                    onChange={(e) => setChatFont(e.target.value as 'sans' | 'serif' | 'mono')}
                  >
                    <option value="sans">{t('settings.fontSans')}</option>
                    <option value="serif">{t('settings.fontSerif')}</option>
                    <option value="mono">{t('settings.fontMono')}</option>
                  </select>
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h4 style={{ fontSize: '14px', fontWeight: 500, color: 'var(--ink)' }}>{t('settings.modelSortModeTitle')}</h4>
                    <p style={{ fontSize: '12px', color: 'var(--muted)' }}>{t('settings.modelSortModeDesc')}</p>
                  </div>
                  <select
                    style={{
                      padding: '6px 12px',
                      borderRadius: 'var(--radius-md)',
                      border: '1px solid var(--hairline)',
                      background: 'var(--surface-card)',
                      color: 'var(--ink)',
                      outline: 'none',
                      fontSize: '13px'
                    }}
                    value={modelSortMode}
                    onChange={(e) => setModelSortMode(e.target.value as 'ranking' | 'alphabetical')}
                  >
                    <option value="ranking">{t('settings.modelSortModeScore')}</option>
                    <option value="alphabetical">{t('settings.modelSortModeAlpha')}</option>
                  </select>
                </div>
              </div>
            )}

            {/* 2. Providers Tab */}
            {tab === 'providers' && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                  <div>
                    <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', margin: 0 }}>{t('settings.providersTitle')}</h2>
                    <p style={{ fontSize: '13px', color: 'var(--muted)', marginTop: '2px' }}>{t('settings.providersDesc')}</p>
                  </div>
                  <button
                    className="sync-btn"
                    onClick={handleSyncAll}
                    disabled={syncingAll || providers.every((p) => !p.has_key)}
                    style={{ padding: '8px 16px', borderRadius: 'var(--radius-md)', fontSize: '13px' }}
                  >
                    {syncingAll ? t('common.syncing') : t('settings.syncAll')}
                  </button>
                </div>

                <div className="providers-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '24px', marginTop: '16px' }}>
                  <div className="admin-section">
                    <h3 className="section-title">🎁 {t('settings.providersFreeSection')}</h3>
                    <p className="section-desc">{t('settings.providersFreeSectionDesc')}</p>
                    <div className="providers-list">
                      {freeProviders.map(renderProvider)}
                    </div>
                  </div>

                  <div className="admin-divider" />

                  <div className="admin-section">
                    <h3 className="section-title">💎 {t('settings.providersPaidSection')}</h3>
                    <p className="section-desc">{t('settings.providersPaidSectionDesc')}</p>
                    <div className="providers-list">
                      {paidProviders.map(renderProvider)}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* 3. Cache Tab */}
            {tab === 'cache' && (
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>{t('settings.cacheTitle')}</h2>
                <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '24px' }}>
                  {t('settings.cacheDesc')}
                </p>
                <CachePanel />
              </div>
            )}

            {/* 4. Tools Tab */}
            {tab === 'tools' && (
              <div>
                <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>{t('settings.toolsTitle')}</h2>
                <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '24px' }}>
                  {t('settings.toolsDesc')}
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                  <EnhancerSettings />
                  <div className="admin-divider" style={{ margin: 0 }} />
                  <FusionSettings />
                  <div className="admin-divider" style={{ margin: 0 }} />
                  <VisionRelaySettings />
                  <div className="admin-divider" style={{ margin: 0 }} />
                  <WebSearchSettings />
                  <div className="admin-divider" style={{ margin: 0 }} />
                  <FreeRegistrySettings />
                  <div className="admin-divider" style={{ margin: 0 }} />
                  <FamilySettings />
                  <div className="admin-divider" style={{ margin: 0 }} />
                  <RankingWeightsSettings />
                </div>
              </div>
            )}

            {/* 5. Users Tab */}
            {tab === 'users' && (
              <div className="users-manager-section">
                <h2 style={{ fontSize: '18px', fontWeight: 600, color: 'var(--ink)', marginBottom: '4px' }}>{t('settings.usersTitle')}</h2>
                <p style={{ fontSize: '13px', color: 'var(--muted)', marginBottom: '24px' }}>
                  {t('settings.usersDesc')}
                </p>
                {loadingUsers ? (
                  <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '20px' }}>{t("settings.loadingUsers")}</div>
                ) : userError ? (
                  <div className="login-error" style={{ margin: '20px 0' }}>{userError}</div>
                ) : (
                  <div className="users-table-wrapper">
                    <table className="users-table">
                      <thead>
                        <tr>
                          <th>{t('settings.userTableUser')}</th>
                          <th>{t('settings.userTableEmail')}</th>
                          <th>{t('settings.userTablePhone')}</th>
                          <th>{t('settings.userTableRole')}</th>
                          <th>{t('settings.userTableRegistered')}</th>
                          <th>{t('settings.userTableActions')}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {usersList.map((u) => (
                          <tr key={u.id} className={u.id === user?.id ? 'current-user-row' : ''}>
                            <td className="user-td-username">
                              <span className="user-td-avatar">{u.username.charAt(0).toUpperCase()}</span>
                              <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                {u.username}
                                {u.id === user?.id && <span className="badge-you">{t('settings.userTableYou')}</span>}
                              </span>
                            </td>
                            <td>{u.email || <span className="text-muted-soft">-</span>}</td>
                            <td>{u.phone || <span className="text-muted-soft">-</span>}</td>
                            <td>
                              <span className={`role-tag role-${u.role}`}>
                                {u.role === 'admin' ? t('common.admin') : t('common.user')}
                              </span>
                            </td>
                            <td>{u.created_at ? new Date(u.created_at).toLocaleDateString(locale) : '-'}</td>
                            <td>
                              {u.id !== user?.id && (
                                <button
                                  className="user-delete-btn"
                                  onClick={() => handleDeleteUser(u.id, u.username)}
                                  title={t("settings.deleteUserTitle")}
                                >
                                  <Trash2 size={14} />
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* 6. Dashboard Tab */}
            {tab === 'dashboard' && (
              <UsageDashboard />
            )}

            {/* 7. Rankings Tab */}
            {tab === 'rankings' && (
              <RankingsView />
            )}

          </div>
        </main>
      </div>
    </div>
  )
}