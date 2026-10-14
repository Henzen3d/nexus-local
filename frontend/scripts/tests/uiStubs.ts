import { useSyncExternalStore } from 'react'
export const controls = { enabled: true, sendSuccess: true, sent: [] as unknown[][], offers: [] as string[] }
let state: any = { isStreaming: false, uiCorrectionRequested: {}, showToast: () => {} }
const listeners = new Set<() => void>()
export const useStore = Object.assign((selector: (s: any) => unknown) => useSyncExternalStore(
  (cb) => { listeners.add(cb); return () => listeners.delete(cb) },
  () => selector(state), () => selector(state),
), {
  getState: () => state,
  setState: (update: any) => { state = { ...state, ...(typeof update === 'function' ? update(state) : update) }; listeners.forEach((cb) => cb()) },
})
export function reset() {
  controls.enabled = true; controls.sendSuccess = true; controls.sent = []; controls.offers = []
  useStore.setState({ isStreaming: false, uiCorrectionRequested: {} })
}
export function useIntelligentUiEnabled() { return controls.enabled }
export function useIntelligentUiConfig() { return { image_hosts: [] } }
export function useChatContext() { return { sendMessage: (...args: unknown[]) => { controls.sent.push(args); return controls.sendSuccess } } }
export const api = { offerUiCorrection: async (id: string) => { controls.offers.push(id); return { ok: true } } }
export function useTranslation() { return { t: (key: string, values?: object) => key + JSON.stringify(values ?? {}), i18n: { language: 'pt-BR' } } }
export function useNearScreen() { return true }
export function useReducedMotion() { return false }
export function useResolvedTheme() { return 'dark' }
export function readLiveThemeTokens() { return {} }
export function buildSandboxCsp() { return "default-src 'none'" }
export function injectThemeTokens(doc: string) { return doc }
export const SANDBOX_IMPORTMAP = {}
export const THEME_MESSAGE_TYPE = '__nexus_theme'
