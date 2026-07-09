import { useEffect } from 'react'
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
import { ChatProvider } from './context/ChatContext'
import { Login } from './components/Login'
import { applyDocumentLang } from './i18n'

function Toast() {
  const { t } = useTranslation()
  const { toast, hideToast } = useStore()

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

export default function App() {
  const { sidebarOpen, setSidebarOpen, view, theme, chatFont, artifactPanelOpen, activeArtifact, token, setAuth, locale } = useStore()
  const { setDeferredPrompt, setIsInstallable } = usePWAStore()

  useEffect(() => {
    applyDocumentLang(locale)
  }, [locale])

  // Capture PWA install prompt event
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
      <div className={layoutClass}>
        {sidebarOpen && (
          <div
            className="sidebar-overlay"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}
        {sidebarOpen && <Sidebar />}
        {view === 'chat' && <ChatWindow />}
        {view === 'conversations' && <ConversationsPanel />}
        {view === 'artifacts' && <ArtifactsPanel />}
        {hasArtifact && <ArtifactPanel />}
      </div>
      {view === 'admin' && <AdminPanel />}
      <Toast />
    </ChatProvider>
  )
}
