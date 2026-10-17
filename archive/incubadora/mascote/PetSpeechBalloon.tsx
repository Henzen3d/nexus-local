/**
 * PetSpeechBalloon.tsx — Balão de Fala Proativo com Ações Rápidas (F9.3.1)
 * Apresenta a mensagem do Pet estilo Clippy Moderno sem interromper o usuário.
 */
import React from 'react'
import { Sparkles, X, Compass, Bookmark, Clock } from 'lucide-react'
import { getMascotProfile } from './mascotProfiles'
import type { MascotId } from '../../types'

export interface PetSpeechBalloonProps {
  mascotId?: MascotId | string
  message: string
  title?: string
  primaryLabel?: string
  secondaryLabel?: string
  onPrimaryClick?: () => void
  onSecondaryClick?: () => void
  onClose?: () => void
}

export const PetSpeechBalloon: React.FC<PetSpeechBalloonProps> = ({
  mascotId = 'lumi',
  message,
  title,
  primaryLabel = 'Ver Roteiro / Detalhes',
  secondaryLabel = 'Guardar para depois',
  onPrimaryClick,
  onSecondaryClick,
  onClose,
}) => {
  const profile = getMascotProfile(mascotId)

  return (
    <div className="nexus-pet-balloon" role="dialog" aria-label={`Mensagem de ${profile.name}`}>
      {/* Cabeçalho com ícone e botão fechar */}
      <div className="nexus-pet-balloon-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Sparkles size={16} color={profile.color} />
          <span style={{ color: profile.color }}>
            {title || `${profile.name} · ${profile.role}`}
          </span>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar balão"
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink, #64748B)',
              padding: 2,
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={15} />
          </button>
        )}
      </div>

      {/* Corpo da mensagem */}
      <div className="nexus-pet-balloon-body">{message}</div>

      {/* Ações interativas */}
      <div className="nexus-pet-balloon-actions">
        {onPrimaryClick && (
          <button
            type="button"
            className="nexus-pet-balloon-btn-primary"
            onClick={onPrimaryClick}
            style={{ backgroundColor: profile.color }}
          >
            <Compass size={14} />
            <span>{primaryLabel}</span>
          </button>
        )}

        {onSecondaryClick && (
          <button
            type="button"
            className="nexus-pet-balloon-btn-secondary"
            onClick={onSecondaryClick}
          >
            <Bookmark size={13} style={{ marginRight: 4, display: 'inline' }} />
            <span>{secondaryLabel}</span>
          </button>
        )}
      </div>
    </div>
  )
}
