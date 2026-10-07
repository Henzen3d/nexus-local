import React from 'react'
import ReactDOM from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './i18n'
import App from './App'
import './index.css'

// Register PWA service worker with auto-update.
// A shell already controlled by an old worker reloads once when the new one takes over.
registerSW({
  immediate: true,
  onRegisteredSW(_url, registration) {
    void registration?.update()
  },
})

if ('serviceWorker' in navigator) {
  const hadController = !!navigator.serviceWorker.controller
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController) window.location.reload()
  })
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
