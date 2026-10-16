/**
 * ComputerActionBlock.tsx — Painel do Sandbox de Computador & Feed de Ações (F8.3.3)
 */
import React, { useState } from 'react'
import {
  Monitor,
  CheckCircle,
  AlertTriangle,
  Camera,
  RotateCcw,
  Globe,
  ExternalLink,
  ShieldCheck,
  Terminal,
} from 'lucide-react'
import type { ProactiveBot } from '../../types'

interface ComputerActionBlockProps {
  activeBot: ProactiveBot | null
}

interface ActionLogItem {
  id: string
  action: string
  target: string
  status: 'success' | 'error'
  latencyMs: number
  time: string
}

export const ComputerActionBlock: React.FC<ComputerActionBlockProps> = ({ activeBot }) => {
  const [urlInput, setUrlInput] = useState('https://news.ycombinator.com')
  const [currentUrl, setCurrentUrl] = useState('https://news.ycombinator.com')
  const [isNavigating, setIsNavigating] = useState(false)
  const [logs, setLogs] = useState<ActionLogItem[]>([
    {
      id: 'log-1',
      action: 'navigate',
      target: 'https://news.ycombinator.com',
      status: 'success',
      latencyMs: 142,
      time: 'Agora há pouco',
    },
    {
      id: 'log-2',
      action: 'extract_dom',
      target: '30 itens de notícias',
      status: 'success',
      latencyMs: 48,
      time: 'Agora há pouco',
    },
  ])

  const handleNavigate = (e: React.FormEvent) => {
    e.preventDefault()
    if (!urlInput.trim()) return

    // Checagem básica client-side anti-SSRF
    const lower = urlInput.toLowerCase()
    if (
      lower.includes('127.0.0.1') ||
      lower.includes('localhost') ||
      lower.includes('192.168.') ||
      lower.includes('10.') ||
      lower.includes('172.16.')
    ) {
      setLogs((prev) => [
        {
          id: `log-${Date.now()}`,
          action: 'navigate',
          target: urlInput,
          status: 'error',
          latencyMs: 12,
          time: 'Agora',
        },
        ...prev,
      ])
      alert('Bloqueio Anti-SSRF: Redes locais e endereços privados não são permitidos no sandbox.')
      return
    }

    setIsNavigating(true)
    setTimeout(() => {
      setCurrentUrl(urlInput)
      setIsNavigating(false)
      setLogs((prev) => [
        {
          id: `log-${Date.now()}`,
          action: 'navigate',
          target: urlInput,
          status: 'success',
          latencyMs: 110,
          time: 'Agora',
        },
        ...prev,
      ])
    }, 600)
  }

  const handleScreenshot = () => {
    setLogs((prev) => [
      {
        id: `log-${Date.now()}`,
        action: 'screenshot',
        target: 'viewport 1280x800',
        status: 'success',
        latencyMs: 85,
        time: 'Agora',
      },
      ...prev,
    ])
  }

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        borderLeft: '1px solid var(--hairline)',
        background: 'var(--surface)',
      }}
    >
      {/* Header do Sandbox */}
      <div
        style={{
          padding: '1rem',
          borderBottom: '1px solid var(--hairline)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Monitor size={18} color="var(--primary)" />
          <div>
            <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600 }}>
              Computador Sandbox
            </h3>
            <span style={{ fontSize: '0.72rem', color: '#10B981', display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: '#10B981' }} />
              nexus_computer: Ativo
            </span>
          </div>
        </div>
        <div
          style={{
            fontSize: '0.72rem',
            padding: '2px 8px',
            borderRadius: 12,
            background: 'var(--surface-soft)',
            color: 'var(--ink-muted)',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <ShieldCheck size={12} color="#10B981" />
          Anti-SSRF
        </div>
      </div>

      {/* Barra de Endereço URL */}
      <form
        onSubmit={handleNavigate}
        style={{
          padding: '0.75rem',
          borderBottom: '1px solid var(--hairline)',
          display: 'flex',
          gap: 6,
        }}
      >
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            background: 'var(--surface-soft)',
            padding: '4px 8px',
            borderRadius: 6,
            border: '1px solid var(--hairline)',
          }}
        >
          <Globe size={14} color="var(--ink-muted)" />
          <input
            type="url"
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            placeholder="https://..."
            style={{
              width: '100%',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: '0.8rem',
              color: 'var(--ink)',
            }}
          />
        </div>
        <button
          type="submit"
          className="settings-secondary-btn"
          style={{ padding: '4px 10px', fontSize: '0.75rem' }}
          disabled={isNavigating}
        >
          {isNavigating ? '...' : 'Ir'}
        </button>
      </form>

      {/* Preview Visual da Viewport do Navegador */}
      <div
        style={{
          margin: '0.75rem',
          height: 190,
          borderRadius: 8,
          border: '1px solid var(--hairline)',
          background: '#0f172a',
          position: 'relative',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Janela Chrome */}
        <div
          style={{
            height: 24,
            background: '#1e293b',
            display: 'flex',
            alignItems: 'center',
            padding: '0 8px',
            gap: 6,
          }}
        >
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#ef4444' }} />
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#f59e0b' }} />
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#10b981' }} />
          <span
            style={{
              marginLeft: 8,
              fontSize: '0.65rem',
              color: '#94a3b8',
              whiteSpace: 'nowrap',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {currentUrl}
          </span>
        </div>

        {/* Conteúdo Renderizado (Mock de Navegação Isolada) */}
        <div
          style={{
            flex: 1,
            padding: 12,
            color: '#f8fafc',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'center',
            alignItems: 'center',
            textAlign: 'center',
          }}
        >
          <Globe size={28} color="#38bdf8" style={{ marginBottom: 6 }} />
          <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>Sessão Playwright Isolada</div>
          <div style={{ fontSize: '0.7rem', color: '#94a3b8', maxWidth: 220 }}>
            {activeBot
              ? `Controlado por: ${activeBot.name}`
              : 'Nenhum bot conectado ao sandbox'}
          </div>
        </div>

        {/* Barra de Ações Rápidas */}
        <div
          style={{
            position: 'absolute',
            bottom: 6,
            right: 6,
            display: 'flex',
            gap: 4,
          }}
        >
          <button
            type="button"
            onClick={handleScreenshot}
            style={{
              background: 'rgba(0,0,0,0.6)',
              border: '1px solid rgba(255,255,255,0.2)',
              color: '#fff',
              borderRadius: 4,
              padding: '3px 6px',
              fontSize: '0.68rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
            title="Capturar screenshot da tela"
          >
            <Camera size={11} />
            Snapshot
          </button>
        </div>
      </div>

      {/* Feed de Ações e Auditoria */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div
          style={{
            padding: '0.5rem 0.75rem',
            borderTop: '1px solid var(--hairline)',
            borderBottom: '1px solid var(--hairline)',
            fontSize: '0.78rem',
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            color: 'var(--ink-muted)',
          }}
        >
          <Terminal size={13} />
          Feed de Operações em Execução
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 0.75rem' }}>
          {logs.map((item) => (
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 8,
                padding: '6px 0',
                borderBottom: '1px solid var(--hairline)',
                fontSize: '0.75rem',
              }}
            >
              {item.status === 'success' ? (
                <CheckCircle size={14} color="#10B981" style={{ flexShrink: 0, marginTop: 1 }} />
              ) : (
                <AlertTriangle size={14} color="#EF4444" style={{ flexShrink: 0, marginTop: 1 }} />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{item.action}</span>
                  <span style={{ color: 'var(--ink-muted)', fontSize: '0.68rem' }}>
                    {item.latencyMs}ms
                  </span>
                </div>
                <div
                  style={{
                    color: 'var(--ink-muted)',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {item.target}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
