/**
 * NexusPetWidget.tsx — Widget Flutuante Mestre do Pet Virtual estilo "Clippy Moderno" (F9.3.3)
 */
import React, { useState, useEffect, useRef } from 'react'
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

  // Suporte a Arrasto (Drag & Drop) com persistência em localStorage
  const [position, setPosition] = useState<{ x: number; y: number } | null>(() => {
    try {
      const saved = localStorage.getItem('nexus_pet_widget_pos')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (typeof parsed.x === 'number' && typeof parsed.y === 'number') {
          return parsed
        }
      }
    } catch {
      /* ignore */
    }
    return null
  })

  const [isCurrentlyDragging, setIsCurrentlyDragging] = useState(false)
  const isDragging = useRef(false)
  const dragStart = useRef({ x: 0, y: 0 })
  const widgetStart = useRef({ x: 0, y: 0 })
  const hasMoved = useRef(false)
  const widgetRef = useRef<HTMLDivElement>(null)

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

  // Handlers de arrasto
  const handleDragStart = (clientX: number, clientY: number) => {
    if (!widgetRef.current) return
    const rect = widgetRef.current.getBoundingClientRect()
    isDragging.current = true
    setIsCurrentlyDragging(true)
    hasMoved.current = false
    dragStart.current = { x: clientX, y: clientY }
    widgetStart.current = { x: rect.left, y: rect.top }
  }

  const handleDragMove = (clientX: number, clientY: number) => {
    if (!isDragging.current) return
    const dx = clientX - dragStart.current.x
    const dy = clientY - dragStart.current.y
    if (Math.hypot(dx, dy) > 5) {
      hasMoved.current = true
    }
    if (hasMoved.current) {
      const maxX = Math.max(12, window.innerWidth - 100)
      const maxY = Math.max(12, window.innerHeight - 100)
      const newX = Math.min(Math.max(12, widgetStart.current.x + dx), maxX)
      const newY = Math.min(Math.max(12, widgetStart.current.y + dy), maxY)
      setPosition({ x: newX, y: newY })
    }
  }

  const handleDragEnd = () => {
    if (!isDragging.current) return
    isDragging.current = false
    setIsCurrentlyDragging(false)
    if (hasMoved.current && position) {
      try {
        localStorage.setItem('nexus_pet_widget_pos', JSON.stringify(position))
      } catch {
        /* ignore */
      }
    }
  }

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (isDragging.current) handleDragMove(e.clientX, e.clientY)
    }
    const onMouseUp = () => {
      if (isDragging.current) handleDragEnd()
    }
    const onTouchMove = (e: TouchEvent) => {
      if (isDragging.current && e.touches[0]) {
        handleDragMove(e.touches[0].clientX, e.touches[0].clientY)
      }
    }
    const onTouchEnd = () => {
      if (isDragging.current) handleDragEnd()
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    window.addEventListener('touchmove', onTouchMove, { passive: true })
    window.addEventListener('touchend', onTouchEnd)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
      window.removeEventListener('touchmove', onTouchMove)
      window.removeEventListener('touchend', onTouchEnd)
    }
  }, [position])

  const handleResetPosition = () => {
    setPosition(null)
    localStorage.removeItem('nexus_pet_widget_pos')
  }

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
        ref={widgetRef}
        className="nexus-pet-widget-container"
        style={{
          pointerEvents: 'auto',
          ...(position ? { left: position.x, top: position.y, bottom: 'auto', right: 'auto' } : {}),
        }}
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
      <div
        ref={widgetRef}
        className={`nexus-pet-widget-container ${isCurrentlyDragging ? 'is-dragging' : ''}`}
        style={
          position
            ? {
                left: position.x,
                top: position.y,
                bottom: 'auto',
                right: 'auto',
                transition: isCurrentlyDragging ? 'none' : 'box-shadow 0.2s',
              }
            : undefined
        }
      >
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

          {/* Botão de Reset de Posição (se foi arrastado) */}
          {position && (
            <button
              type="button"
              className="nexus-pet-dock-btn"
              onClick={handleResetPosition}
              title="Restaurar posição original do mascote"
              aria-label="Restaurar posição padrão"
            >
              <RotateCcw size={13} />
            </button>
          )}

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

          {/* Avatar Animado com Física de Molas e Suporte a Arrastar */}
          <div
            onMouseDown={(e) => {
              if (e.button === 0) handleDragStart(e.clientX, e.clientY)
            }}
            onTouchStart={(e) => {
              if (e.touches[0]) handleDragStart(e.touches[0].clientX, e.touches[0].clientY)
            }}
            onClick={(e) => {
              if (hasMoved.current) {
                e.stopPropagation()
                return
              }
              handlePetClick()
            }}
            style={{
              cursor: isCurrentlyDragging ? 'grabbing' : 'grab',
              userSelect: 'none',
              touchAction: 'none',
              transform: isCurrentlyDragging ? 'scale(1.08)' : 'scale(1)',
              transition: isCurrentlyDragging ? 'none' : 'transform 0.15s ease-out',
            }}
            title={`Clique para falar com ${profile.name} ou arraste para mover na tela`}
          >
            <PetAvatar
              mascotId={selectedPet}
              state={petState}
              size={76}
              trackPointer={!isCurrentlyDragging}
            />
          </div>
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
