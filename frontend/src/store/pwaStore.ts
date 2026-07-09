import { create } from 'zustand'

interface PWAState {
  deferredPrompt: any
  isInstallable: boolean
  setDeferredPrompt: (prompt: any) => void
  setIsInstallable: (status: boolean) => void
}

export const usePWAStore = create<PWAState>((set) => ({
  deferredPrompt: null,
  isInstallable: false,
  setDeferredPrompt: (prompt) => set({ deferredPrompt: prompt }),
  setIsInstallable: (status) => set({ isInstallable: status }),
}))
