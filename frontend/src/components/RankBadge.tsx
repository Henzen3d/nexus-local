import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Award } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface RankBadgeProps {
  score?: number | null
  rank?: number | null
  popularityRank?: number | null
  qualityScore?: number | null
  internalUsageCount?: number | null
  breakdown?: {
    quality_contribution?: number
    popularity_contribution?: number
    usage_contribution?: number
    popularity_normalized?: number
    usage_normalized?: number
  } | null
}

export function RankBadge({ score, rank, popularityRank, qualityScore, internalUsageCount, breakdown }: RankBadgeProps) {
  const { t } = useTranslation()
  const [showTooltip, setShowTooltip] = useState(false)
  const [tooltipCoords, setTooltipCoords] = useState({ bottom: 0, left: 0 })

  if (score === undefined || score === null) return null

  // Cores dinâmicas e texto baseado no rank global
  let badgeColor = 'var(--muted)'
  let badgeBg = 'rgba(138, 138, 138, 0.08)'
  let badgeBorder = 'rgba(138, 138, 138, 0.18)'
  let displayLabel = ''
  let isMedal = false

  if (rank === 1) {
    badgeColor = '#d97706' // Gold
    badgeBg = 'rgba(217, 119, 6, 0.15)'
    badgeBorder = 'rgba(217, 119, 6, 0.4)'
    displayLabel = '🥇 #1'
    isMedal = true
  } else if (rank === 2) {
    badgeColor = '#708090' // Silver
    badgeBg = 'rgba(112, 128, 144, 0.15)'
    badgeBorder = 'rgba(112, 128, 144, 0.4)'
    displayLabel = '🥈 #2'
    isMedal = true
  } else if (rank === 3) {
    badgeColor = '#b45309' // Bronze
    badgeBg = 'rgba(180, 83, 9, 0.15)'
    badgeBorder = 'rgba(180, 83, 9, 0.4)'
    displayLabel = '🥉 #3'
    isMedal = true
  } else if (rank !== undefined && rank !== null && rank <= 10) {
    badgeColor = 'var(--primary)' // Neutral top 10 style
    badgeBg = 'rgba(204, 120, 92, 0.08)'
    badgeBorder = 'rgba(204, 120, 92, 0.25)'
    displayLabel = `#${rank}`
  } else {
    // For models outside top 10, show the score as before
    if (score >= 80) {
      badgeColor = 'var(--primary)'
      badgeBg = 'rgba(204, 120, 92, 0.12)'
      badgeBorder = 'rgba(204, 120, 92, 0.3)'
    } else if (score >= 70) {
      badgeColor = 'var(--cyan)'
      badgeBg = 'rgba(93, 184, 166, 0.12)'
      badgeBorder = 'rgba(93, 184, 166, 0.3)'
    }
    displayLabel = score.toFixed(0)
  }

  // Estimativa de contribuição
  const q_contrib = breakdown?.quality_contribution ?? ((qualityScore ?? 0) * 0.5)
  const p_contrib = breakdown?.popularity_contribution ?? (
    popularityRank !== null && popularityRank !== undefined
      ? (100 - Math.min(popularityRank, 100)) * 0.3
      : 50.0 * 0.3
  )
  const u_contrib = breakdown?.usage_contribution ?? (
    internalUsageCount !== null && internalUsageCount !== undefined
      ? Math.min((internalUsageCount / 500) * 100, 100) * 0.2
      : 0
  )

  const handleMouseEnter = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setTooltipCoords({
      bottom: window.innerHeight - rect.top + 8,
      left: rect.left + rect.width / 2
    })
    setShowTooltip(true)
  }

  return (
    <div
      className="rank-badge-container"
      style={{ 
        position: 'relative', 
        display: 'inline-flex', 
        alignItems: 'center',
        minWidth: '55px', // Width fixa para garantir alinhamento perfeito do context length!
        justifyContent: 'center'
      }}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: isMedal ? '2px' : '4px',
          padding: '2px 6px',
          borderRadius: '4px',
          fontSize: '11px',
          fontWeight: 600,
          color: badgeColor,
          backgroundColor: badgeBg,
          border: `1px solid ${badgeBorder}`,
          cursor: 'help',
          transition: 'all 0.2s ease',
          userSelect: 'none',
          width: '100%',
          textAlign: 'center'
        }}
      >
        {!isMedal && <Award size={10} style={{ flexShrink: 0 }} />}
        <span>{displayLabel}</span>
      </span>

      {showTooltip && createPortal(
        <div
          style={{
            position: 'fixed',
            bottom: `${tooltipCoords.bottom}px`,
            left: `${tooltipCoords.left}px`,
            transform: 'translateX(-50%)',
            zIndex: 99999, // Super elevado para não ser cortado
            width: '230px',
            padding: '10px 12px',
            backgroundColor: 'var(--surface-card)',
            border: '1px solid var(--hairline)',
            borderRadius: '6px',
            boxShadow: '0 4px 14px rgba(0,0,0,0.3)',
            fontSize: '12px',
            color: 'var(--ink)',
            pointerEvents: 'none',
            lineHeight: '1.4',
            fontFamily: 'var(--font-body)'
          }}
        >
          <div
            style={{
              fontWeight: 600,
              marginBottom: '6px',
              borderBottom: '1px solid var(--hairline)',
              paddingBottom: '4px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center'
            }}
          >
            <span>{t('chat.rankGeneral')} {rank ? `#${rank}` : '—'}</span>
            <span style={{ color: badgeColor, fontWeight: 700 }}>{t('common.score')}: {score.toFixed(1)}</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--body)' }}>{t('chat.quality50')}</span>
                <span style={{ fontWeight: 500 }}>
                  {qualityScore !== null && qualityScore !== undefined
                    ? t('chat.pts', { value: qualityScore.toFixed(0) })
                    : '—'}
                </span>
              </div>
              <div style={{ fontSize: '10px', color: 'var(--muted)', textAlign: 'right' }}>
                {t('chat.contribution', { value: q_contrib.toFixed(1) })}
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--body)' }}>{t('chat.popularity30')}</span>
                <span style={{ fontWeight: 500 }}>
                  {popularityRank ? `#${popularityRank}` : t('chat.noRank')}
                </span>
              </div>
              <div style={{ fontSize: '10px', color: 'var(--muted)', textAlign: 'right' }}>
                {t('chat.contribution', { value: p_contrib.toFixed(1) })}
              </div>
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--body)' }}>{t('chat.usage20')}</span>
                <span style={{ fontWeight: 500 }}>
                  {t('chat.usesCount', { count: internalUsageCount ?? 0 })}
                </span>
              </div>
              <div style={{ fontSize: '10px', color: 'var(--muted)', textAlign: 'right' }}>
                {t('chat.contribution', { value: u_contrib.toFixed(1) })}
              </div>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}
