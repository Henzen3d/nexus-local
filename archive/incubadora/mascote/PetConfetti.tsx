/**
 * PetConfetti.tsx — Efeito de celebração vetorial leve (F9.2.4)
 * Dispara confetes e fitas ao redor do pet sem dependência de bibliotecas externas.
 */
import React, { useEffect, useState } from 'react'

const CONFETTI_COLORS = [
  '#F472B6',
  '#C084FC',
  '#818CF8',
  '#38BDF8',
  '#34D399',
  '#FACC15',
  '#FB7185',
]

interface Particle {
  id: number
  x: number
  y: number
  vx: number
  vy: number
  color: string
  size: number
  rotation: number
  vRot: number
}

interface PetConfettiProps {
  active: boolean
  onComplete?: () => void
}

export const PetConfetti: React.FC<PetConfettiProps> = ({ active, onComplete }) => {
  const [particles, setParticles] = useState<Particle[]>([])

  useEffect(() => {
    if (!active) {
      setParticles([])
      return
    }

    // Criar 24 partículas explodindo para cima
    const initialParticles: Particle[] = Array.from({ length: 24 }).map((_, i) => ({
      id: i,
      x: 0,
      y: 0,
      vx: (Math.random() - 0.5) * 12,
      vy: -8 - Math.random() * 8,
      color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      size: 4 + Math.random() * 6,
      rotation: Math.random() * 360,
      vRot: (Math.random() - 0.5) * 18,
    }))

    setParticles(initialParticles)

    let animationFrame: number
    const startTime = performance.now()

    const animate = (time: number) => {
      const elapsed = time - startTime
      if (elapsed > 1800) {
        setParticles([])
        onComplete?.()
        return
      }

      setParticles((prev) =>
        prev.map((p) => ({
          ...p,
          x: p.x + p.vx * 0.96,
          y: p.y + p.vy * 0.96 + 0.35, // gravidade
          rotation: p.rotation + p.vRot,
        }))
      )

      animationFrame = requestAnimationFrame(animate)
    }

    animationFrame = requestAnimationFrame(animate)
    return () => cancelAnimationFrame(animationFrame)
  }, [active, onComplete])

  if (!particles.length) return null

  return (
    <div
      style={{
        position: 'absolute',
        top: '50%',
        left: '50%',
        pointerEvents: 'none',
        overflow: 'visible',
        zIndex: 1100,
      }}
    >
      {particles.map((p) => (
        <div
          key={p.id}
          style={{
            position: 'absolute',
            width: p.size,
            height: p.size * 0.6,
            backgroundColor: p.color,
            borderRadius: 2,
            transform: `translate(${p.x}px, ${p.y}px) rotate(${p.rotation}deg)`,
            opacity: Math.max(0, 1 - Math.abs(p.y) / 160),
            transition: 'opacity 0.2s',
          }}
        />
      ))}
    </div>
  )
}
