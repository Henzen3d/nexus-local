import { useEffect, useRef } from 'react'
import { X, AlertCircle, CheckCircle, Info } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useStore } from './store/useStore'
import { usePWAStore } from './store/pwaStore'
import { Sidebar } from './components/Sidebar'
import { ChatWindow } from './components/ChatWindow'
import { AdminPanel } from './components/AdminPanel'
import { ArtifactPanel } from './components/ArtifactPanel'
import { ConversationsPanel } from './components/ConversationsPanel'
import { ArtifactsPanel } from './components/ArtifactsPanel'
import { ProjectsPanel } from './components/ProjectsPanel'
import { ChatProvider } from './context/ChatContext'
import { Login } from './components/Login'
import { MemoryOnboarding } from './components/MemoryOnboarding'
import { PwaInstallBanner } from './components/PwaInstallBanner'
import { applyDocumentLang } from './i18n'
import { MOBILE_BREAKPOINT } from './hooks/useIsMobile'

function Toast() {
  const { t } = useTranslation()
  const toast = useStore((s) => s.toast)
  const hideToast = useStore((s) => s.hideToast)

  useEffect(() => {
    if (!toast) return
    const timer = setTimeout(() => {
      hideToast()
    }, 5000)
    return () => clearTimeout(timer)
  }, [toast, hideToast])

  if (!toast) return null

  const getIcon = () => {
    switch (toast.type) {
      case 'success':
        return <CheckCircle size={16} />
      case 'error':
        return <AlertCircle size={16} />
      default:
        return <Info size={16} />
    }
  }

  return (
    <div className={`toast-container toast-${toast.type}`}>
      <div className="toast-icon-wrapper">{getIcon()}</div>
      <div className="toast-message">{toast.message}</div>
      <button className="toast-close" onClick={hideToast} aria-label={t('toast.closeAlert')}>
        <X size={14} />
      </button>
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

  useEffect(() => {
    applyDocumentLang(locale)
  }, [locale])

  useEffect(() => {
    if (token) {
      hydrateProfileFromServer()
    }
  }, [token, hydrateProfileFromServer])

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
        {hasArtifact && <ArtifactPanel />}
      </div>
      {view === 'admin' && <AdminPanel />}
      <PwaInstallBanner />
      <Toast />
      <MemoryOnboarding />
    </ChatProvider>
  )
}
