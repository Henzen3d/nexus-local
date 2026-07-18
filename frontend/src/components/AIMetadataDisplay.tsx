import React from 'react'
import { useTranslation } from 'react-i18next'
import type { NormalizedMetadata } from '../types'

interface AIMetadataDisplayProps {
  metadata?: NormalizedMetadata
  visible?: boolean
}

/**
 * AIMetadataDisplay
 * 
 * Componente simples e isolado por flag para exibir as métricas de performance
 * de IA decodificadas pelos adaptadores de modelo.
 */
export function AIMetadataDisplay({ metadata, visible = false }: AIMetadataDisplayProps) {
  const { t } = useTranslation()

  if (!visible || !metadata) return null

  const {
    tokens_generated,
    input_tokens,
    tokens_per_second,
    total_time_ms,
    reasoning_time_ms,
  } = metadata

  // Se não houver dados, não renderiza nada
  if (
    tokens_generated === undefined &&
    input_tokens === undefined &&
    tokens_per_second === undefined &&
    total_time_ms === undefined &&
    reasoning_time_ms === undefined
  ) {
    return null
  }

  return (
    <span 
      className="ai-performance-metadata" 
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: '6px',
        fontSize: 'var(--font-meta, 11px)',
        color: 'var(--text-meta)',
        opacity: 'var(--opacity-meta, 0.55)',
        backgroundColor: 'var(--surface-hover, rgba(0, 0, 0, 0.02))',
        padding: '1px 6px',
        borderRadius: 'var(--radius-chat, 4px)',
        border: '1px solid var(--hairline, rgba(0, 0, 0, 0.05))',
        marginLeft: '4px',
        marginRight: '4px',
        verticalAlign: 'middle',
      }}
    >
      {input_tokens !== undefined && (
        <span className="custom-tooltip-trigger" data-tooltip={t('chat.tokensIn')}>In: {input_tokens}</span>
      )}
      {tokens_generated !== undefined && (
        <span className="custom-tooltip-trigger" data-tooltip={t('chat.tokensOut')}>Out: {tokens_generated}</span>
      )}
      {total_time_ms !== undefined && (
        <span className="custom-tooltip-trigger" data-tooltip={t('chat.totalTime')}>Total: {(total_time_ms / 1000).toFixed(2)}s</span>
      )}
      {tokens_per_second !== undefined && (
        <span className="custom-tooltip-trigger" style={{ fontWeight: 500 }} data-tooltip={t('chat.avgSpeed')}>{tokens_per_second} t/s</span>
      )}
      {reasoning_time_ms !== undefined && (
        <span className="custom-tooltip-trigger" data-tooltip={t('chat.reasoningTime')}>🧠 {(reasoning_time_ms / 1000).toFixed(2)}s</span>
      )}
    </span>
  )
}
