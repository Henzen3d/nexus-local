import React, { useState } from 'react'
import { isAllowedImageUrl } from '../../lib/nexusUi'
import type { CardBlock } from '../../types'

interface Props {
  block: CardBlock
}

export function ImageCard({ block }: Props) {
  const { title, body, facts, image } = block
  const [imgError, setImgError] = useState(false)

  const isImgValid =
    image &&
    !imgError &&
    isAllowedImageUrl(image.url, [], typeof window !== 'undefined' ? window.location.host : undefined)

  return (
    <div
      style={{
        marginTop: '12px',
        padding: '14px 16px',
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '10px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        boxShadow: '0 2px 8px rgba(0, 0, 0, 0.05)',
      }}
    >
      <div style={{ display: 'flex', gap: '14px', alignItems: 'flex-start' }}>
        {isImgValid && (
          <div
            style={{
              flexShrink: 0,
              width: '96px',
              height: '96px',
              borderRadius: '8px',
              overflow: 'hidden',
              backgroundColor: 'var(--surface-soft)',
              border: '1px solid var(--hairline)',
            }}
          >
            <img
              src={image.url}
              alt={image.alt}
              loading="lazy"
              referrerPolicy="no-referrer"
              onError={() => setImgError(true)}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                display: 'block',
              }}
            />
          </div>
        )}

        <div style={{ flex: 1, minWidth: 0 }}>
          <h4
            style={{
              margin: '0 0 6px 0',
              fontSize: '14px',
              fontWeight: 600,
              color: 'var(--ink)',
              lineHeight: 1.3,
            }}
          >
            {title}
          </h4>

          {body && (
            <p
              style={{
                margin: 0,
                fontSize: '13px',
                color: 'var(--body)',
                lineHeight: 1.45,
              }}
            >
              {body}
            </p>
          )}
        </div>
      </div>

      {facts && facts.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '8px',
            marginTop: '4px',
            paddingTop: '8px',
            borderTop: '1px solid var(--hairline)',
          }}
        >
          {facts.map((fact, idx) => (
            <div
              key={idx}
              style={{
                fontSize: '11px',
                padding: '4px 8px',
                borderRadius: '6px',
                backgroundColor: 'var(--surface-soft)',
                color: 'var(--ink)',
                display: 'inline-flex',
                gap: '4px',
              }}
            >
              <span style={{ color: 'var(--body)' }}>{fact.label}:</span>
              <strong>{fact.value}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default ImageCard
