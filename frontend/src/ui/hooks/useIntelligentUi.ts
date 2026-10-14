import { useStore } from '../../store/useStore'
import type { IntelligentUiConfig } from '../../types'

const OFF: IntelligentUiConfig = { enabled: false, image_hosts: [], allow_private_http: false, source: 'default' }

/**
 * Configuração efetiva do Intelligent UI vinda do servidor.
 * Enquanto não carregou (null), devolve desligado: "ausente significa falso".
 */
export function useIntelligentUiConfig(): IntelligentUiConfig {
  return useStore((s) => s.intelligentUiConfig) ?? OFF
}

export function useIntelligentUiEnabled(): boolean {
  return useStore((s) => !!s.intelligentUiConfig?.enabled)
}

/** Leitura imperativa (fora de componentes React, ex.: markdownComponents). */
export function isIntelligentUiEnabled(): boolean {
  return !!useStore.getState().intelligentUiConfig?.enabled
}
