/**
 * PetAvatar.tsx — Motor procedural de Mascote com Física de Molas SVG (F9.2.1)
 * Engenharia reversa e adaptação de animação do OpenMausBot para os 32 Mascotes do NexusLocal.
 */
import React, { useEffect, useRef, useState, useId } from 'react'
import type { MascotId } from '../../types'
import { getMascotProfile, type MascotProfile } from './mascotProfiles'

export type PetState =
  | 'idle'
  | 'happy'
  | 'curious'
  | 'thinking'
  | 'searching'
  | 'working'
  | 'celebrate'
  | 'sleeping'
  | 'alerting'

interface PetAvatarProps {
  mascotId?: MascotId | string
  state?: PetState
  size?: number
  trackPointer?: boolean
  className?: string
  onClick?: () => void
  title?: string
}

export const PetAvatar: React.FC<PetAvatarProps> = ({
  mascotId = 'lumi',
  state = 'idle',
  size = 72,
  trackPointer = true,
  className = '',
  onClick,
  title,
}) => {
  const profile = getMascotProfile(mascotId)
  const [gaze, setGaze] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const [isBlinking, setIsBlinking] = useState(false)
  const [isClicked, setIsClicked] = useState(false)
  const containerRef = useRef<SVGSVGElement | null>(null)
  const gradientId = useId()

  // 1. Gaze Tracking: Olhos seguem o cursor do mouse suavemente
  useEffect(() => {
    if (!trackPointer || state === 'sleeping') {
      setGaze({ x: 0, y: 0 })
      return
    }

    const handlePointerMove = (e: MouseEvent) => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      const centerX = rect.left + rect.width / 2
      const centerY = rect.top + rect.height / 2

      const deltaX = (e.clientX - centerX) / (window.innerWidth / 2)
      const deltaY = (e.clientY - centerY) / (window.innerHeight / 2)

      // Clamping para não sair da órbita dos olhos
      const clampedX = Math.max(-1, Math.min(1, deltaX)) * 3.5
      const clampedY = Math.max(-1, Math.min(1, deltaY)) * 2.5

      setGaze({ x: clampedX, y: clampedY })
    }

    window.addEventListener('mousemove', handlePointerMove, { passive: true })
    return () => window.removeEventListener('mousemove', handlePointerMove)
  }, [trackPointer, state])

  // 2. Ciclo de Piscada Natural (a cada 3.5s - 6s)
  useEffect(() => {
    if (state === 'sleeping') {
      setIsBlinking(true)
      return
    }

    let timeoutId: number
    const scheduleBlink = () => {
      const delay = 3000 + Math.random() * 3000
      timeoutId = window.setTimeout(() => {
        setIsBlinking(true)
        window.setTimeout(() => {
          setIsBlinking(false)
          scheduleBlink()
        }, 160)
      }, delay)
    }

    scheduleBlink()
    return () => window.clearTimeout(timeoutId)
  }, [state])

  const handleClick = () => {
    setIsClicked(true)
    window.setTimeout(() => setIsClicked(false), 300)
    onClick?.()
  }

  // 3. Renderizador da Silhueta do Corpo
  const renderBodySilhouette = (shape: MascotProfile['shape']) => {
    const fill = `url(#${gradientId})`

    switch (shape) {
      case 'robot':
      case 'monitor':
        return (
          <>
            {/* Orelhas/Antenas do robô */}
            <rect x="22" y="4" width="4" height="8" rx="2" fill={profile.accentColor} />
            <circle cx="24" cy="4" r="3" fill={profile.accentColor} />
            {/* Cabeça retangular curvada */}
            <rect x="6" y="11" width="36" height="30" rx="10" fill={fill} stroke={profile.accentColor} strokeWidth="1.5" />
            {/* Visor digital escuro */}
            <rect x="10" y="16" width="28" height="20" rx="6" fill="#0F172A" />
          </>
        )
      case 'bot_headphone':
        return (
          <>
            {/* Arco do fone de ouvido */}
            <path d="M7 24 C7 12 41 12 41 24" fill="none" stroke={profile.accentColor} strokeWidth="3" strokeLinecap="round" />
            {/* Conchas do headphone */}
            <rect x="4" y="20" width="5" height="12" rx="2.5" fill={profile.accentColor} />
            <rect x="39" y="20" width="5" height="12" rx="2.5" fill={profile.accentColor} />
            {/* Cabeça esférica */}
            <circle cx="24" cy="24" r="16" fill={fill} />
            {/* Visor escuro com reflexo */}
            <rect x="12" y="17" width="24" height="14" rx="7" fill="#090D16" />
          </>
        )
      case 'sprout':
        return (
          <>
            {/* Brotinho no topo */}
            <path d="M24 10 C24 5 18 5 18 9 C18 13 24 10 24 10 Z" fill="#22C55E" />
            <path d="M24 10 C24 5 30 5 30 9 C30 13 24 10 24 10 Z" fill="#4ADE80" />
            {/* Corpo arredondado orgânico */}
            <ellipse cx="24" cy="27" rx="17" ry="16" fill={fill} />
          </>
        )
      case 'droplet':
      case 'flame':
        return (
          <>
            {/* Ponta da gota/chama */}
            <path
              d="M24 5 C24 5 38 18 38 29 C38 37 32 43 24 43 C16 43 10 37 10 29 C10 18 24 5 24 5 Z"
              fill={fill}
              stroke={profile.accentColor}
              strokeWidth="1.2"
            />
          </>
        )
      case 'cloud':
        return (
          <>
            {/* Nuvem fofinha */}
            <path
              d="M14 36 C9 36 6 32 6 28 C6 24 9 21 13 21 C14 15 20 11 26 12 C30 13 33 16 34 19 C38 19 41 22 41 26 C41 31 38 36 32 36 Z"
              fill={fill}
              stroke="rgba(255,255,255,0.4)"
              strokeWidth="1.5"
            />
          </>
        )
      case 'cat_bot':
      case 'fox':
      case 'bunny':
        return (
          <>
            {/* Orelhas triangulares/longas */}
            <polygon points={shape === 'bunny' ? "12,18 15,2 19,18" : "9,20 13,8 19,17"} fill={profile.accentColor} />
            <polygon points={shape === 'bunny' ? "29,18 33,2 36,18" : "29,17 35,8 39,20"} fill={profile.accentColor} />
            {/* Cabeça fofinha */}
            <circle cx="24" cy="27" r="16" fill={fill} />
          </>
        )
      case 'fluff':
      default:
        return (
          <>
            {/* Criatura felpuda/esférica suave */}
            <circle cx="24" cy="24" r="18" fill={fill} />
            {/* Brilho de volume superior */}
            <ellipse cx="20" cy="15" rx="8" ry="4" fill="rgba(255,255,255,0.22)" />
          </>
        )
    }
  }

  // 4. Renderizador dos Olhos e Expressão Emocional
  const renderEyesAndFace = () => {
    const isVisor = profile.shape === 'robot' || profile.shape === 'bot_headphone' || profile.shape === 'monitor'
    const eyeColor = isVisor ? profile.accentColor : '#0F172A'

    // Estado: Dormindo
    if (state === 'sleeping' || isBlinking) {
      return (
        <g className="pet-face--sleeping">
          <path d="M16 25 Q20 28 22 25" stroke={eyeColor} strokeWidth="2.2" strokeLinecap="round" fill="none" />
          <path d="M26 25 Q28 28 32 25" stroke={eyeColor} strokeWidth="2.2" strokeLinecap="round" fill="none" />
          {state === 'sleeping' && (
            <text x="32" y="14" fill={profile.accentColor} fontSize="8" fontWeight="bold" className="pet-sleep-zzz">
              zZ
            </text>
          )}
        </g>
      )
    }

    // Estado: Feliz / Celebrando
    if (state === 'happy' || state === 'celebrate') {
      return (
        <g className="pet-face--happy">
          <path d="M16 26 Q19 21 22 26" stroke={eyeColor} strokeWidth="2.4" strokeLinecap="round" fill="none" />
          <path d="M26 26 Q29 21 32 26" stroke={eyeColor} strokeWidth="2.4" strokeLinecap="round" fill="none" />
          {/* Boquinha sorridente aberta */}
          <path d="M21 29 Q24 33 27 29 Z" fill="#F43F5E" />
          {/* Blush fofinho */}
          <circle cx="14" cy="28" r="2.5" fill="#FDA4AF" opacity="0.6" />
          <circle cx="34" cy="28" r="2.5" fill="#FDA4AF" opacity="0.6" />
        </g>
      )
    }

    // Estado: Curioso / Pensando / Pesquisando / Padrão com Gaze Tracking
    const eyeBaseX1 = 18
    const eyeBaseX2 = 30
    const eyeBaseY = 24

    return (
      <g className="pet-face--interactive">
        {/* Olho Esquerdo */}
        <circle cx={eyeBaseX1} cy={eyeBaseY} r="3.2" fill={isVisor ? 'rgba(0,0,0,0.4)' : '#FFFFFF'} />
        <circle
          cx={eyeBaseX1 + gaze.x * 0.4}
          cy={eyeBaseY + gaze.y * 0.4}
          r={state === 'curious' ? '3' : '2.4'}
          fill={eyeColor}
        />
        {/* Brilho da pupila */}
        <circle cx={eyeBaseX1 + gaze.x * 0.4 - 0.8} cy={eyeBaseY + gaze.y * 0.4 - 0.8} r="0.8" fill="#FFFFFF" />

        {/* Olho Direito */}
        <circle cx={eyeBaseX2} cy={eyeBaseY} r="3.2" fill={isVisor ? 'rgba(0,0,0,0.4)' : '#FFFFFF'} />
        <circle
          cx={eyeBaseX2 + gaze.x * 0.4}
          cy={eyeBaseY + gaze.y * 0.4}
          r={state === 'curious' ? '3' : '2.4'}
          fill={eyeColor}
        />
        {/* Brilho da pupila */}
        <circle cx={eyeBaseX2 + gaze.x * 0.4 - 0.8} cy={eyeBaseY + gaze.y * 0.4 - 0.8} r="0.8" fill="#FFFFFF" />

        {/* Boquinha sutil */}
        <path d="M22 28 Q24 30 26 28" stroke={eyeColor} strokeWidth="1.5" strokeLinecap="round" fill="none" />
      </g>
    )
  }

  // 5. Classes de Física de Molas (Springs)
  const getPhysicsClass = () => {
    if (isClicked) return 'pet-anim--squash'
    switch (state) {
      case 'happy':
      case 'celebrate':
        return 'pet-anim--bob-excited'
      case 'curious':
        return 'pet-anim--sway'
      case 'thinking':
        return 'pet-anim--thinking'
      case 'searching':
      case 'working':
        return 'pet-anim--pulse-work'
      case 'alerting':
        return 'pet-anim--jitter'
      case 'sleeping':
        return 'pet-anim--sleeping'
      case 'idle':
      default:
        return 'pet-anim--pulse-idle'
    }
  }

  return (
    <div
      className={`nexus-pet-avatar-wrapper ${className}`}
      onClick={handleClick}
      title={title || `${profile.name} — ${profile.role}`}
      style={{
        width: size,
        height: size,
        cursor: onClick ? 'pointer' : 'default',
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <svg
        ref={containerRef}
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`nexus-pet-svg ${getPhysicsClass()}`}
        style={{ overflow: 'visible', filter: 'drop-shadow(0 6px 12px rgba(0,0,0,0.18))' }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={profile.accentColor} />
            <stop offset="100%" stopColor={profile.color} />
          </linearGradient>
        </defs>

        {/* Halo sutil de atenção em working ou alerting */}
        {(state === 'working' || state === 'alerting' || state === 'celebrate') && (
          <circle
            cx="24"
            cy="24"
            r="22"
            fill="none"
            stroke={profile.accentColor}
            strokeWidth="1.5"
            strokeDasharray={state === 'working' ? '4 4' : 'none'}
            className="pet-halo-pulse"
          />
        )}

        {/* Silhueta do corpo */}
        {renderBodySilhouette(profile.shape)}

        {/* Rosto & Expressões */}
        {renderEyesAndFace()}
      </svg>
    </div>
  )
}
