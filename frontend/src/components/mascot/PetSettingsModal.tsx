/**
 * PetSettingsModal.tsx — Galeria e Seletor dos 32 Mascotes do NexusLocal (F9.3.4)
 */
import React, { useState } from 'react'
import { X, Check, Sparkles, Search } from 'lucide-react'
import { MASCOT_LIST, getMascotProfile } from './mascotProfiles'
import { PetAvatar } from './PetAvatar'
import type { MascotId } from '../../types'

interface PetSettingsModalProps {
  isOpen: boolean
  currentPetId: MascotId | string
  onSelectPet: (petId: MascotId) => void
  onClose: () => void
}

export const PetSettingsModal: React.FC<PetSettingsModalProps> = ({
  isOpen,
  currentPetId,
  onSelectPet,
  onClose,
}) => {
  const [search, setSearch] = useState('')
  const [previewPetId, setPreviewPetId] = useState<MascotId>(
    (currentPetId as MascotId) || 'lumi'
  )

  if (!isOpen) return null

  const filtered = MASCOT_LIST.filter(
    (m) =>
      m.name.toLowerCase().includes(search.toLowerCase()) ||
      m.role.toLowerCase().includes(search.toLowerCase()) ||
      m.personality.toLowerCase().includes(search.toLowerCase())
  )

  const previewProfile = getMascotProfile(previewPetId)

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(8px)',
        zIndex: 1200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 840,
          maxWidth: '100%',
          maxHeight: '88vh',
          backgroundColor: 'var(--surface, #ffffff)',
          border: '1px solid var(--hairline, rgba(255, 255, 255, 0.2))',
          borderRadius: 24,
          boxShadow: '0 24px 48px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          color: 'var(--ink, #0f172a)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Header */}
        <div
          style={{
            padding: '20px 24px',
            borderBottom: '1px solid var(--hairline, rgba(0,0,0,0.08))',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 10,
                backgroundColor: 'var(--primary-soft, rgba(59,130,246,0.12))',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--primary, #3b82f6)',
              }}
            >
              <Sparkles size={20} />
            </div>
            <div>
              <h2 style={{ fontSize: 18, fontWeight: 700, margin: 0 }}>
                Escolha seu Companheiro Virtual (Pet)
              </h2>
              <p style={{ fontSize: 13, color: 'var(--ink-muted, #64748b)', margin: 0 }}>
                32 amigos para acompanhar seu trabalho, estudos e pesquisas
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: 'var(--ink-muted, #64748b)',
              padding: 4,
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Content Body: Split view (Preview on left, Gallery on right) */}
        <div
          style={{
            display: 'flex',
            flex: 1,
            overflow: 'hidden',
          }}
        >
          {/* Coluna da esquerda: Destaque do Pet selecionado */}
          <div
            style={{
              width: 280,
              backgroundColor: 'var(--surface-soft, rgba(0,0,0,0.02))',
              borderRight: '1px solid var(--hairline, rgba(0,0,0,0.08))',
              padding: 24,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              textAlign: 'center',
            }}
          >
            <div style={{ marginBottom: 16 }}>
              <PetAvatar
                mascotId={previewPetId}
                state="happy"
                size={110}
                trackPointer={true}
              />
            </div>
            <h3 style={{ fontSize: 20, fontWeight: 700, margin: '0 0 4px 0' }}>
              {previewProfile.name}
            </h3>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 20,
                backgroundColor: 'var(--surface-hover, rgba(0,0,0,0.06))',
                color: previewProfile.color,
                marginBottom: 12,
              }}
            >
              {previewProfile.role}
            </span>
            <p
              style={{
                fontSize: 13,
                lineHeight: 1.5,
                color: 'var(--ink-muted, #475569)',
                marginBottom: 16,
              }}
            >
              {previewProfile.personality}
            </p>
            <div
              style={{
                backgroundColor: 'var(--surface, #ffffff)',
                border: '1px solid var(--hairline, rgba(0,0,0,0.1))',
                borderRadius: 14,
                padding: 12,
                fontSize: 12,
                fontStyle: 'italic',
                color: 'var(--ink, #334155)',
                marginBottom: 20,
              }}
            >
              "{previewProfile.greeting}"
            </div>

            <button
              type="button"
              onClick={() => {
                onSelectPet(previewPetId)
                onClose()
              }}
              style={{
                width: '100%',
                padding: '10px 16px',
                borderRadius: 14,
                border: 'none',
                backgroundColor: previewProfile.color,
                color: '#ffffff',
                fontWeight: 600,
                fontSize: 14,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
                marginTop: 'auto',
                boxShadow: '0 4px 14px rgba(0,0,0,0.15)',
              }}
            >
              <Check size={16} />
              <span>Escolher {previewProfile.name}</span>
            </button>
          </div>

          {/* Coluna da direita: Grid com os 32 mascotes */}
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              padding: 20,
              overflow: 'hidden',
            }}
          >
            {/* Search Input */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 14px',
                backgroundColor: 'var(--surface-soft, rgba(0,0,0,0.03))',
                borderRadius: 12,
                border: '1px solid var(--hairline, rgba(0,0,0,0.08))',
                marginBottom: 16,
              }}
            >
              <Search size={16} color="var(--ink-muted, #94a3b8)" />
              <input
                type="text"
                placeholder="Buscar mascote pelo nome, função ou perfil..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                style={{
                  border: 'none',
                  background: 'transparent',
                  outline: 'none',
                  width: '100%',
                  fontSize: 13,
                  color: 'inherit',
                }}
              />
            </div>

            {/* Grid Scrollable */}
            <div
              style={{
                flex: 1,
                overflowY: 'auto',
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(115px, 1fr))',
                gap: 12,
                paddingRight: 6,
              }}
            >
              {filtered.map((m) => {
                const isSelected = previewPetId === m.id
                const isCurrent = currentPetId === m.id

                return (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => setPreviewPetId(m.id)}
                    style={{
                      background: isSelected
                        ? 'var(--surface-hover, rgba(59,130,246,0.08))'
                        : 'var(--surface, #ffffff)',
                      border: isSelected
                        ? `2px solid ${m.color}`
                        : '1px solid var(--hairline, rgba(0,0,0,0.08))',
                      borderRadius: 16,
                      padding: 10,
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      cursor: 'pointer',
                      transition: 'all 0.16s ease',
                      position: 'relative',
                    }}
                  >
                    {isCurrent && (
                      <span
                        style={{
                          position: 'absolute',
                          top: 6,
                          right: 6,
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          backgroundColor: '#10B981',
                        }}
                        title="Mascote ativo no momento"
                      />
                    )}
                    <PetAvatar mascotId={m.id} state="idle" size={46} trackPointer={false} />
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        marginTop: 6,
                        color: 'var(--ink, #1e293b)',
                      }}
                    >
                      {m.name}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        color: 'var(--ink-muted, #64748b)',
                        textAlign: 'center',
                        lineHeight: 1.2,
                        marginTop: 2,
                      }}
                    >
                      {m.role}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
