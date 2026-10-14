import { lazy, Suspense, useEffect, useRef } from 'react'
import { X, AlertCircle, CheckCircle, Info, Sparkles } from 'lucide-react'
import type { ToastItem } from './types'
import { useTranslation } from 'react-i18next'
import { useStore } from './store/useStore'
import { usePWAStore } from './store/pwaStore'
import { Sidebar } from './components/Sidebar'
import { ChatWindow } from './components/ChatWindow'
// AdminPanel puxa recharts (UsageDashboard/RankingsView). Lazy para a lib sair do
// chunk do chat — assim só ChartCard (também lazy) e o admin pagam por ela.
const AdminPanel = lazy(() => import('./components/AdminPanel').then((m) => ({ default: m.AdminPanel })))
import { ArtifactPanel } from './components/ArtifactPanel'
import { ConversationsPanel } from './components/ConversationsPanel'
import { ArtifactsPanel } from './components/ArtifactsPanel'
import { ProjectsPanel } from './components/ProjectsPanel'
import { LibraryPanel } from './components/LibraryPanel'
import { ProactiveHubPanel } from './components/ProactiveHubPanel'
import { ChatProvider } from './context/ChatContext'
import { Login } from './components/Login'
import { MemoryOnboarding } from './components/MemoryOnboarding'
import { ProactiveOnboarding } from './components/ProactiveOnboarding'
import { loadTtsPrefs } from './lib/ttsPlayer'
import { PwaInstallBanner } from './components/PwaInstallBanner'
import { applyDocumentLang } from './i18n'
import { useProactive } from './hooks/useProactive'
import { UNAUTHORIZED_EVENT } from './api/client'
import { MOBILE_BREAKPOINT } from './hooks/useIsMobile'

function Toast() {
  const { t } = useTranslation()
  const toasts = useStore((s) => s.toasts)
  const hideToast = useStore((s) => s.hideToast)

  if (toasts.length === 0) return null

  const getIcon = (type: ToastItem['type']) => {
    switch (type) {
      case 'success':
        return <CheckCircle size={16} />
      case 'error':
        return <AlertCircle size={16} />
      case 'proactive':
        return <Sparkles size={16} />
      default:
        return <Info size={16} />
    }
  }

  // Pilha de até 3 toasts (o store descarta os mais antigos); o auto-hide é do store.
  return (
    <div className="toast-stack" role="region" aria-live="polite" aria-label={t('toast.regionLabel', { defaultValue: 'Notificações' })}>
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-container toast-${toast.type}`}>
          <div className="toast-icon-wrapper">{getIcon(toast.type)}</div>
          <div className="toast-body">
            {toast.title && <div className="toast-title">{toast.title}</div>}
            <div className="toast-message">{toast.message}</div>
            {toast.action && (
              <button
                type="button"
                className="toast-action"
                onClick={() => {
                  toast.action?.onClick()
                  hideToast(toast.id)
                }}
              >
                {toast.action.label}
              </button>
            )}
          </div>
          <button className="toast-close" onClick={() => hideToast(toast.id)} aria-label={t('toast.closeAlert')}>
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

/** Edge swipe from left to open sidebar on mobile */
function useEdgeSwipeOpenSidebar() {
  const sidebarOpen = useStore((s) => s.sidebarOpen)
  const setSidebarOpen = useStore((s) => s.setSidebarOpen)
  const touchRef = useRef({ startX: 0, startY: 0, tracking: false })

  useEffect(() => {
    const isMobile = () => window.innerWidth <= MOBILE_BREAKPOINT

    const onStart = (e: TouchEvent) => {
      if (!isMobile() || sidebarOpen) return
      const t = e.touches[0]
      if (t.clientX > 28) return
      touchRef.current = { startX: t.clientX, startY: t.clientY, tracking: true }
    }

    const onMove = (e: TouchEvent) => {
      if (!touchRef.current.tracking) return
      const t = e.touches[0]
      const dx = t.clientX - touchRef.current.startX
      const dy = t.clientY - touchRef.current.startY
      if (Math.abs(dy) > Math.abs(dx) * 1.2) {
        touchRef.current.tracking = false
        return
      }
      if (dx > 56 && Math.abs(dx) > Math.abs(dy) * 1.4) {
        touchRef.current.tracking = false
        setSidebarOpen(true)
      }
    }

    const onEnd = () => {
      touchRef.current.tracking = false
    }

    document.addEventListener('touchstart', onStart, { passive: true })
    document.addEventListener('touchmove', onMove, { passive: true })
    document.addEventListener('touchend', onEnd)
    document.addEventListener('touchcancel', onEnd)
    return () => {
      document.removeEventListener('touchstart', onStart)
      document.removeEventListener('touchmove', onMove)
      document.removeEventListener('touchend', onEnd)
      document.removeEventListener('touchcancel', onEnd)
    }
  }, [sidebarOpen, setSidebarOpen])
}

export default function App() {
  const sidebarOpen = useStore((s) => s.sidebarOpen)
  const setSidebarOpen = useStore((s) => s.setSidebarOpen)
  const view = useStore((s) => s.view)
  const theme = useStore((s) => s.theme)
  const chatFont = useStore((s) => s.chatFont)
  const artifactPanelOpen = useStore((s) => s.artifactPanelOpen)
  const activeArtifact = useStore((s) => s.activeArtifact)
  const token = useStore((s) => s.token)
  const setAuth = useStore((s) => s.setAuth)
  const locale = useStore((s) => s.locale)
  const hydrateProfileFromServer = useStore((s) => s.hydrateProfileFromServer)
  const { setDeferredPrompt, setIsInstallable } = usePWAStore()

  useEdgeSwipeOpenSidebar()
  // Assistente proativo (F3): fila de pendentes no boot + poda local de vencidos
  useProactive()

  useEffect(() => {
    applyDocumentLang(locale)
  }, [locale])

  useEffect(() => {
    if (token) {
      hydrateProfileFromServer()
      loadTtsPrefs().catch(() => {})
      // Intelligent UI: flag e hosts de imagem vêm do servidor (painel > .env)
      useStore.getState().loadIntelligentUiConfig()
    }
  }, [token, hydrateProfileFromServer])

  // Sessão expirada/revogada (401 em qualquer chamada autenticada) → limpa e volta ao login
  useEffect(() => {
    const onUnauthorized = () => {
      if (useStore.getState().token) useStore.getState().logout()
    }
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [])

  useEffect(() => {
    const handler = (e: Event) => {
      e.preventDefault()
      setDeferredPrompt(e)
      setIsInstallable(true)
    }

    window.addEventListener('beforeinstallprompt', handler)
    return () => window.removeEventListener('beforeinstallprompt', handler)
  }, [setDeferredPrompt, setIsInstallable])

  useEffect(() => {
    const applyTheme = () => {
      const root = document.documentElement
      let resolvedTheme = theme
      if (theme === 'system') {
        resolvedTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
      }
      root.setAttribute('data-theme', resolvedTheme)
    }

    applyTheme()

    if (theme === 'system') {
      const media = window.matchMedia('(prefers-color-scheme: dark)')
      const listener = () => applyTheme()
      media.addEventListener('change', listener)
      return () => media.removeEventListener('change', listener)
    }
  }, [theme])

  useEffect(() => {
    document.documentElement.setAttribute('data-chat-font', chatFont)
  }, [chatFont])

  if (!token) {
    return <Login onLoginSuccess={setAuth} />
  }

  const hasArtifact = !!activeArtifact

  const layoutClass = [
    'app-layout',
    sidebarOpen ? 'sidebar-open' : 'sidebar-closed',
    hasArtifact && artifactPanelOpen ? 'with-artifact-open' : 'with-artifact-closed'
  ].join(' ')

  return (
    <ChatProvider>
      {/* Overlay outside grid so it never steals a column */}
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'is-visible' : ''}`}
        onClick={() => setSidebarOpen(false)}
        aria-hidden={!sidebarOpen}
      />
      <div className={layoutClass}>
        <Sidebar />
        {view === 'chat' && <ChatWindow />}
        {view === 'conversations' && <ConversationsPanel />}
        {view === 'artifacts' && <ArtifactsPanel />}
        {view === 'projects' && <ProjectsPanel />}
        {view === 'library' && <LibraryPanel />}
        {view === 'proactive' && <ProactiveHubPanel />}
        {hasArtifact && <ArtifactPanel />}
      </div>
      {view === 'admin' && (
        <Suspense fallback={null}>
          <AdminPanel />
        </Suspense>
      )}
      <PwaInstallBanner />
      <Toast />
      <MemoryOnboarding />
      <ProactiveOnboarding />
    </ChatProvider>
  )
}
