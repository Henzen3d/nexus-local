/**
 * NexusPetWidget.tsx — Widget Flutuante Mestre do Pet Virtual estilo "Clippy Moderno" (F9.3.3)
 */
import React, { useState, useEffect } from 'react'
import { Sparkles, Settings, EyeOff, RotateCcw } from 'lucide-react'
import { PetAvatar, type PetState } from './PetAvatar'
import { PetSpeechBalloon } from './PetSpeechBalloon'
import { PetSettingsModal } from './PetSettingsModal'
import { PetConfetti } from './PetConfetti'
import { getMascotProfile } from './mascotProfiles'
import type { MascotId } from '../../types'
import './petAnimations.css'

export interface ActiveBalloonData {
  id: string
  message: string
  title?: string
  primaryLabel?: string
  secondaryLabel?: string
  onPrimary?: () => void
  onSecondary?: () => void
}

interface NexusPetWidgetProps {
  currentPetId?: MascotId | string
  onPetChange?: (newPetId: MascotId) => void
  activeInsightBalloon?: ActiveBalloonData | null
  onOpenHub?: () => void
}

export const NexusPetWidget: React.FC<NexusPetWidgetProps> = ({
  currentPetId = 'lumi',
  onPetChange,
  activeInsightBalloon,
  onOpenHub,
}) => {
  const [selectedPet, setSelectedPet] = useState<MascotId>(
    (currentPetId as MascotId) || 'lumi'
  )
  const [petState, setPetState] = useState<PetState>('idle')
  const [isMinimized, setIsMinimized] = useState(false)
  const [isSettingsOpen, setIsSettingsOpen] = useState(false)
  const [showConfetti, setShowConfetti] = useState(false)
  const [activeBalloon, setActiveBalloon] = useState<ActiveBalloonData | null>(null)

  const profile = getMascotProfile(selectedPet)

  // Sincronizar com props externas
  useEffect(() => {
    if (currentPetId) {
      setSelectedPet(getMascotProfile(currentPetId).id)
    }
  }, [currentPetId])

  // Se um insight chegar via prop externa (ex: Roteiro de viagem pronto)
  useEffect(() => {
    if (activeInsightBalloon) {
      setActiveBalloon(activeInsightBalloon)
      setPetState('curious')
    }
  }, [activeInsightBalloon])

  const handlePetClick = () => {
    // Se o balão estiver aberto, fecha
    if (activeBalloon) {
      setActiveBalloon(null)
      setPetState('idle')
      return
    }

    // Se estiver fechado, abre saudação e opções amigáveis
    setPetState('happy')
    setActiveBalloon({
      id: 'greeting',
      message: `"${profile.greeting}"`,
      title: `${profile.name} · ${profile.role}`,
      primaryLabel: 'Explorar Descobertas',
      secondaryLabel: 'Mudar Mascote',
      onPrimary: () => {
        setActiveBalloon(null)
        setPetState('idle')
        onOpenHub?.()
      },
      onSecondary: () => {
        setActiveBalloon(null)
        setPetState('idle')
        setIsSettingsOpen(true)
      },
    })
  }

  const handleSelectPet = (newPet: MascotId) => {
    setSelectedPet(newPet)
    onPetChange?.(newPet)
    setPetState('celebrate')
    setShowConfetti(true)
    window.setTimeout(() => setPetState('idle'), 2000)
  }

  if (isMinimized) {
    return (
      <div
        className="nexus-pet-widget-container"
        style={{ pointerEvents: 'auto' }}
      >
        <button
          type="button"
          onClick={() => setIsMinimized(false)}
          className="nexus-pet-dock-btn"
          title={`Restaurar ${profile.name} (Pet Virtual)`}
          style={{
            width: 42,
            height: 42,
            backgroundColor: profile.color,
            color: '#fff',
            border: 'none',
          }}
        >
          <Sparkles size={18} />
        </button>
      </div>
    )
  }

  return (
    <>
      <div className="nexus-pet-widget-container">
        {/* Balão de Fala estilo Clippy */}
        {activeBalloon && (
          <PetSpeechBalloon
            mascotId={selectedPet}
            title={activeBalloon.title}
            message={activeBalloon.message}
            primaryLabel={activeBalloon.primaryLabel}
            secondaryLabel={activeBalloon.secondaryLabel}
            onPrimaryClick={activeBalloon.onPrimary}
            onSecondaryClick={activeBalloon.onSecondary}
            onClose={() => {
              setActiveBalloon(null)
              setPetState('idle')
            }}
          />
        )}

        {/* Linha do Pet e Ações de Apoio */}
        <div className="nexus-pet-anchor-row" style={{ position: 'relative' }}>
          {/* Efeito de Confetes */}
          <PetConfetti active={showConfetti} onComplete={() => setShowConfetti(false)} />

          {/* Botão de Configuração do Mascote */}
          <button
            type="button"
            className="nexus-pet-dock-btn"
            onClick={() => setIsSettingsOpen(true)}
            title="Escolher entre os 32 Mascotes"
          >
            <Settings size={15} />
          </button>

          {/* Botão de Minimizar */}
          <button
            type="button"
            className="nexus-pet-dock-btn"
            onClick={() => {
              setActiveBalloon(null)
              setIsMinimized(true)
            }}
            title="Minimizar Pet"
          >
            <EyeOff size={15} />
          </button>

          {/* Avatar Animado com Física de Molas */}
          <PetAvatar
            mascotId={selectedPet}
            state={petState}
            size={76}
            trackPointer={true}
            onClick={handlePetClick}
            title={`Clique para falar com ${profile.name}`}
          />
        </div>
      </div>

      {/* Modal de Escolha dos 32 Mascotes */}
      <PetSettingsModal
        isOpen={isSettingsOpen}
        currentPetId={selectedPet}
        onSelectPet={handleSelectPet}
        onClose={() => setIsSettingsOpen(false)}
      />
    </>
  )
}
