import React from 'react'
import type { ProactivePersonaStyle } from '../types'

export type MascotState = 'idle' | 'researching' | 'ready' | 'sleep'

interface ProactiveMascotProps {
  state?: MascotState
  style?: ProactivePersonaStyle
  size?: number
  className?: string
  onClick?: () => void
  title?: string
}

export const ProactiveMascot: React.FC<ProactiveMascotProps> = ({
  state = 'idle',
  style = 'lumi',
  size = 40,
  className = '',
  onClick,
  title,
}) => {
  if (style === 'core') {
    // Estilo minimalista editorial / geométrico corporativo ("Nexus Core")
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`proactive-mascot proactive-mascot--core proactive-mascot--${state} ${className}`}
        onClick={onClick}
        role="img"
        aria-label={title || `Nexus Core (${state})`}
      >
        <circle cx="24" cy="24" r="20" stroke="var(--primary)" strokeWidth="2" strokeDasharray={state === 'researching' ? '4 4' : 'none'} className="core-outer-ring" />
        <circle cx="24" cy="24" r="14" fill="var(--surface-soft)" stroke="var(--hairline)" strokeWidth="1.5" />
        <circle
          cx="24"
          cy="24"
          r={state === 'ready' ? '8' : state === 'researching' ? '6' : '5'}
          fill="var(--primary)"
          className="core-inner-orb"
        />
        {state === 'ready' && (
          <path
            d="M24 16L25.5 22.5L32 24L25.5 25.5L24 32L22.5 25.5L16 24L22.5 22.5Z"
            fill="var(--text-on-primary, #fff)"
          />
        )}
      </svg>
    )
  }

  // Estilo amigável ("Nexus Lumi" — Kawaii Tech)
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={`proactive-mascot proactive-mascot--lumi proactive-mascot--${state} ${className}`}
      onClick={onClick}
      role="img"
      aria-label={title || `Nexus Lumi (${state})`}
    >
      <defs>
        {/* Gradiente do corpo metálico suave */}
        <linearGradient id="lumi-body-grad" x1="16" y1="8" x2="48" y2="56" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--surface, #232326)" />
          <stop offset="1" stopColor="var(--surface-soft, #18181b)" />
        </linearGradient>
        {/* Brilho da antena */}
        <radialGradient id="lumi-antenna-glow" cx="32" cy="10" r="6" gradientUnits="userSpaceOnUse">
          <stop stopColor="var(--primary, #E06C53)" stopOpacity="0.9" />
          <stop offset="1" stopColor="var(--primary, #E06C53)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Antena / Auréola */}
      <line x1="32" y1="14" x2="32" y2="7" stroke="var(--hairline)" strokeWidth="2.5" strokeLinecap="round" />
      <circle cx="32" cy="7" r="4.5" fill="var(--primary)" className="lumi-antenna-orb" />
      {state === 'researching' && <circle cx="32" cy="7" r="8" fill="url(#lumi-antenna-glow)" className="lumi-pulse-ring" />}

      {/* Orelhas / Fones laterais */}
      <rect x="8" y="26" width="5" height="14" rx="2.5" fill="var(--hairline)" />
      <rect x="51" y="26" width="5" height="14" rx="2.5" fill="var(--hairline)" />

      {/* Cabeça / Corpo do Robô */}
      <rect
        x="12"
        y="14"
        width="40"
        height="38"
        rx="19"
        fill="url(#lumi-body-grad)"
        stroke="var(--hairline)"
        strokeWidth="2"
      />

      {/* Visor / Tela Escura */}
      <rect
        x="16"
        y="21"
        width="32"
        height="22"
        rx="11"
        fill="#0D0D11"
        stroke="var(--hairline)"
        strokeWidth="1.2"
        className="lumi-screen"
      />

      {/* Expressões dos Olhos por Estado */}
      {state === 'idle' && (
        <g className="lumi-eyes lumi-eyes--idle">
          {/* Olho esquerdo */}
          <ellipse cx="25" cy="31" rx="3.5" ry="4.5" fill="var(--primary)" />
          <circle cx="26.5" cy="29.5" r="1.3" fill="#ffffff" />
          {/* Olho direito */}
          <ellipse cx="39" cy="31" rx="3.5" ry="4.5" fill="var(--primary)" />
          <circle cx="40.5" cy="29.5" r="1.3" fill="#ffffff" />
          {/* Boquinha sorrindo */}
          <path d="M30 36.5 Q32 38.5 34 36.5" stroke="var(--primary)" strokeWidth="1.6" strokeLinecap="round" fill="none" />
        </g>
      )}

      {state === 'researching' && (
        <g className="lumi-eyes lumi-eyes--researching">
          {/* Olho esquerdo com lupa / visor de foco */}
          <circle cx="25" cy="31" r="5" stroke="var(--primary)" strokeWidth="2" fill="none" />
          <line x1="28.5" y1="34.5" x2="31" y2="37" stroke="var(--primary)" strokeWidth="2" strokeLinecap="round" />
          {/* Olho direito concentrado */}
          <ellipse cx="40" cy="31" rx="3" ry="3.5" fill="var(--primary)" />
          <circle cx="41" cy="30" r="1" fill="#ffffff" />
          {/* Linha de pensamento */}
          <path d="M30 37 Q32 36 34 37" stroke="var(--primary)" strokeWidth="1.5" strokeLinecap="round" fill="none" />
        </g>
      )}

      {state === 'ready' && (
        <g className="lumi-eyes lumi-eyes--ready">
          {/* Olho esquerdo estrelinha ✦ */}
          <path d="M25 26 L26.2 29.8 L30 31 L26.2 32.2 L25 36 L23.8 32.2 L20 31 L23.8 29.8 Z" fill="var(--primary)" />
          {/* Olho direito estrelinha ✦ */}
          <path d="M39 26 L40.2 29.8 L44 31 L40.2 32.2 L39 36 L37.8 32.2 L34 31 L37.8 29.8 Z" fill="var(--primary)" />
          {/* Sorriso feliz aberto */}
          <path d="M29 36 Q32 40 35 36" stroke="var(--primary)" strokeWidth="1.8" strokeLinecap="round" fill="none" />
        </g>
      )}

      {state === 'sleep' && (
        <g className="lumi-eyes lumi-eyes--sleep">
          {/* Olhos fechados descansando ⌒ ⌒ */}
          <path d="M22 32 Q25 29 28 32" stroke="var(--text-muted, #71717a)" strokeWidth="2" strokeLinecap="round" fill="none" />
          <path d="M36 32 Q39 29 42 32" stroke="var(--text-muted, #71717a)" strokeWidth="2" strokeLinecap="round" fill="none" />
          {/* zZz flutuando */}
          <text x="46" y="24" fill="var(--primary)" fontSize="9" fontWeight="bold" fontFamily="sans-serif">z</text>
          <text x="52" y="17" fill="var(--primary)" fontSize="11" fontWeight="bold" fontFamily="sans-serif" opacity="0.8">Z</text>
        </g>
      )}

      {/* Pequenos blushs rosados sutis */}
      <ellipse cx="20" cy="36" rx="2" ry="1.2" fill="var(--primary)" opacity="0.4" />
      <ellipse cx="44" cy="36" rx="2" ry="1.2" fill="var(--primary)" opacity="0.4" />
    </svg>
  )
}
