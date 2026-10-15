import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import {
  AlertCircle,
  Download,
  Maximize2,
  Minimize2,
  Orbit,
  Pause,
  PenTool,
  Play,
  RotateCcw,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import type { SandboxBlock, SceneParam, SceneReadout } from '../../types'
import { downloadStandaloneSceneHtml } from '../lib/exportStandalone'
import { useReducedMotion, useSceneViewport } from '../hooks/useMotionAndViewport'
import { useResolvedTheme } from '../hooks/useResolvedTheme'
import { sceneDocument } from '../scene/sceneDocument'
import type { SceneSetup, SceneTheme, SceneValues } from '../scene/sceneProtocol'
import { MAX_ERROR_TEXT, readSceneMessage, SCENE_MSG } from '../scene/sceneProtocol'
import { useMessageUiStore } from '../state/messageUiState'
import { readLiveThemeTokens } from '../themeBridge'
import { UiCard, UiCardAction } from './UiCard'

function trackSceneEvent(event: 'scene_mounted' | 'scene_error' | 'scene_fix_requested') {
  try {
    if (typeof fetch === 'function') {
      void fetch('/api/intelligent-ui/scene-event', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event }),
      }).catch(() => {})
    }
  } catch {
    // Ignore in tests or offline
  }
}

interface Props {
  block: SandboxBlock
  streaming?: boolean
  messageId?: string
  onRuntimeError?: (title: string, message: string) => void
}

export function SceneCard({ block, streaming, messageId, onRuntimeError }: Props) {
  const { t, i18n } = useTranslation()
  const { sendMessage } = useChatContext()
  const setUiValues = useMessageUiStore((s) => s.setUiValues)
  const msgId = messageId || block.id
  const uid = useId()

  const {
    title = 'Cena',
    mode = '3d',
    code = '',
    params = [],
    readout = [],
    initial_height = 320,
    standalone_download = true,
  } = block

  const themeMode = useResolvedTheme()
  const isDark = themeMode === 'dark'
  const lang = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  const reducedMotion = useReducedMotion()
  const [paused, setPaused] = useState<boolean>(() => reducedMotion)
  const [runKey, setRunKey] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [escaped, setEscaped] = useState(false)
  const [isFullscreen, setIsFullscreen] = useState(false)

  const [card, setCard] = useState<HTMLElement | null>(null)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const loads = useRef(0)

  // Desmonta quando rola 2 telas para longe do viewport para liberar o escasso contexto WebGL
  const inViewport = useSceneViewport(card)

  // Valores atuais dos parâmetros da cena
  const [paramValues, setParamValues] = useState<Record<string, unknown>>(() => {
    const initial: Record<string, unknown> = {}
    if (Array.isArray(params)) {
      for (const p of params) {
        initial[p.id] = p.default
      }
    }
    return initial
  })

  // Leituras recebidas por __nexus_scene_report
  const [readoutValues, setReadoutValues] = useState<SceneValues>({})

  // Tema efetivo passado à cena
  const sceneTheme = useMemo<SceneTheme>(() => {
    const tokens = readLiveThemeTokens()
    return {
      dark: isDark,
      text: tokens.ink || (isDark ? '#f8f8f6' : '#1d1d1c'),
      accent: tokens.primary || '#cc785c',
    }
  }, [isDark])

  // Setup inicial embutido no srcDoc
  const setup = useMemo<SceneSetup>(() => {
    return {
      title,
      mode,
      theme: sceneTheme,
      params: paramValues,
      paused,
    }
  }, [title, mode, sceneTheme, paramValues, paused])

  // srcdoc gerado com CSP estrita sem rede
  const srcDoc = useMemo(() => {
    return sceneDocument(setup, code, '/scene/runtime.js', lang)
  }, [setup, code, lang])

  // Envia atualização de tema dinamicamente sem recarregar o iframe
  useEffect(() => {
    if (!iframeRef.current?.contentWindow) return
    try {
      iframeRef.current.contentWindow.postMessage(
        { type: SCENE_MSG.theme, theme: sceneTheme },
        '*'
      )
    } catch {
      // Ignora se o frame não estiver pronto
    }
  }, [sceneTheme])

  // Envia toggle de play/pause
  const togglePlayPause = useCallback(() => {
    if (streaming) return
    const nextPaused = !paused
    setPaused(nextPaused)
    if (iframeRef.current?.contentWindow) {
      try {
        iframeRef.current.contentWindow.postMessage(
          { type: nextPaused ? SCENE_MSG.pause : SCENE_MSG.play },
          '*'
        )
      } catch {
        // Falha silenciosa
      }
    }
  }, [paused, streaming])

  // Reiniciar cena com valores padrões
  const handleRestart = useCallback(() => {
    if (streaming) return
    setError(null)
    setEscaped(false)
    loads.current = 0
    const initial: Record<string, unknown> = {}
    if (Array.isArray(params)) {
      for (const p of params) {
        initial[p.id] = p.default
      }
    }
    setParamValues(initial)
    setReadoutValues({})
    setRunKey((k) => k + 1)
  }, [params, streaming])

  // Atualizar parâmetro da cena
  const handleParamChange = useCallback(
    (paramId: string, value: unknown) => {
      setParamValues((prev) => {
        const next = { ...prev, [paramId]: value }
        if (iframeRef.current?.contentWindow) {
          try {
            iframeRef.current.contentWindow.postMessage(
              { type: SCENE_MSG.params, values: next },
              '*'
            )
          } catch {
            // Falha silenciosa
          }
        }
        return next
      })
    },
    []
  )

  // Escuta mensagens vindas do iframe
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (iframeRef.current && event.source === iframeRef.current.contentWindow) {
        const msg = readSceneMessage(event.data)
        if (!msg) return

        if (msg.type === SCENE_MSG.report) {
          setReadoutValues((prev) => ({ ...prev, ...msg.values }))
          // Publica no store de UI como sim.<key> e <key> para outros blocos
          const simValues: Record<string, number | string> = {}
          for (const [k, v] of Object.entries(msg.values)) {
            if (typeof v === 'number' || typeof v === 'string') {
              simValues[`sim.${k}`] = v
              simValues[k] = v
            }
          }
          setUiValues(msgId, simValues)
        } else if (msg.type === SCENE_MSG.error) {
          const safeMsg = msg.message.slice(0, MAX_ERROR_TEXT)
          setError(safeMsg)
          trackSceneEvent('scene_error')
          onRuntimeError?.(title, safeMsg)
        }
      }
    }

    if (typeof window !== 'undefined') {
      window.addEventListener('message', handleMessage)
      return () => {
        window.removeEventListener('message', handleMessage)
      }
    }
  }, [msgId, onRuntimeError, setUiValues, title])

  // Pausa quando a aba fica oculta (visibilitychange)
  useEffect(() => {
    if (typeof document === 'undefined') return
    function handleVisibility() {
      if (document.hidden && !paused && iframeRef.current?.contentWindow) {
        setPaused(true)
        try {
          iframeRef.current.contentWindow.postMessage({ type: SCENE_MSG.pause }, '*')
        } catch {
          // Ignora
        }
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [paused])

  // Monitora fullscreen
  useEffect(() => {
    if (typeof document === 'undefined') return
    function onFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === card)
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => {
      document.removeEventListener('fullscreenchange', onFullscreenChange)
    }
  }, [card])

  const handleFullscreen = () => {
    const target = card as (HTMLElement & { webkitRequestFullscreen?: () => void }) | null
    if (!target || streaming || typeof document === 'undefined') return
    if (document.fullscreenElement === target) {
      void document.exitFullscreen?.()
    } else if (target.requestFullscreen) {
      void target.requestFullscreen()
    } else {
      target.webkitRequestFullscreen?.()
    }
  }

  const handleDownload = () => {
    if (streaming) return
    void downloadStandaloneSceneHtml(title, setup, code, lang)
  }

  const handleRequestFix = () => {
    if (!sendMessage || !error) return
    trackSceneEvent('scene_fix_requested')
    const prompt =
      t('intelligentUi.sceneCorrectionPrompt', { title, message: error }) ||
      `Corrija a cena "${title}": falhou com: ${error}. Mantenha o mesmo bloco sandbox kind scene.`
    sendMessage(prompt)
  }

  const handleIframeLoad = () => {
    loads.current += 1
    if (loads.current > 1) {
      setEscaped(true)
    } else {
      trackSceneEvent('scene_mounted')
    }
  }

  const hasParams = Array.isArray(params) && params.length > 0
  const hasReadout = Array.isArray(readout) && readout.length > 0
  const ModeIcon = mode === '2d' ? PenTool : Orbit

  return (
    <UiCard
      ref={setCard}
      as="figure"
      variant="flush"
      className="nexus-ui-scene"
      title={
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <ModeIcon size={16} aria-hidden="true" style={{ opacity: 0.8 }} />
          <span>{title}</span>
        </span>
      }
      actions={
        <>
          <UiCardAction
            icon={paused ? <Play size={14} /> : <Pause size={14} />}
            label={paused ? (t('intelligentUi.scenePlay') || 'Continuar') : (t('intelligentUi.scenePause') || 'Pausar')}
            disabled={streaming || Boolean(error) || escaped}
            onClick={togglePlayPause}
          />
          <UiCardAction
            icon={<RotateCcw size={14} />}
            label={t('intelligentUi.restart') || 'Reiniciar'}
            disabled={streaming}
            onClick={handleRestart}
          />
          <UiCardAction
            icon={isFullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
            label={t('intelligentUi.fullscreen') || 'Tela cheia'}
            disabled={streaming}
            onClick={handleFullscreen}
          />
          {standalone_download && (
            <UiCardAction
              icon={<Download size={14} />}
              label={t('intelligentUi.exportStandalone') || 'Baixar HTML'}
              disabled={streaming}
              onClick={handleDownload}
            />
          )}
        </>
      }
    >
      <div className={`nexus-ui-scene__container ${hasParams ? 'nexus-ui-scene__container--with-params' : ''}`}>
        <div className="nexus-ui-scene__main">
          <div
            className="nexus-ui-scene__stage"
            style={{ height: isFullscreen ? '100%' : `${initial_height}px` }}
          >
            {escaped ? (
              <div className="nexus-ui-sandbox__notice" role="alert">
                <p>{t('intelligentUi.sandboxEscaped') || 'O conteúdo tentou sair do sandbox e foi interrompido.'}</p>
                <button
                  type="button"
                  className="nexus-ui-button nexus-ui-button--primary"
                  onClick={handleRestart}
                >
                  {t('intelligentUi.restart') || 'Reiniciar'}
                </button>
              </div>
            ) : inViewport ? (
              <iframe
                key={runKey}
                ref={iframeRef}
                title={title}
                sandbox="allow-scripts"
                srcDoc={srcDoc}
                onLoad={handleIframeLoad}
              />
            ) : (
              <div className="nexus-ui-sandbox__placeholder" aria-hidden="true" />
            )}
          </div>

          {/* Faixa de readout */}
          {hasReadout && (
            <div className="nexus-ui-scene__readout" aria-live="polite">
              <span className="sr-only">{t('intelligentUi.sceneReadoutTitle') || 'Valores da cena'}:</span>
              {readout.map((r: SceneReadout) => {
                const rawVal = readoutValues[r.key]
                const valDisplay =
                  typeof rawVal === 'number'
                    ? rawVal.toLocaleString(lang, { maximumFractionDigits: 3 })
                    : rawVal !== undefined
                      ? String(rawVal)
                      : '—'
                return (
                  <div key={r.key} className="nexus-ui-scene__readout-item">
                    <span className="nexus-ui-scene__readout-label">{r.label}:</span>
                    <span className="nexus-ui-scene__readout-value">{valDisplay}</span>
                    {r.unit && <span className="nexus-ui-scene__readout-unit">{r.unit}</span>}
                  </div>
                )
              })}
              {/* Tabela sr-only para leitores de tela conforme critério de acessibilidade */}
              <table className="sr-only">
                <caption>{title} - {t('intelligentUi.sceneReadoutTitle') || 'Valores da cena'}</caption>
                <thead>
                  <tr>
                    <th>Métrica</th>
                    <th>Valor</th>
                    <th>Unidade</th>
                  </tr>
                </thead>
                <tbody>
                  {readout.map((r: SceneReadout) => (
                    <tr key={r.key}>
                      <td>{r.label}</td>
                      <td>{readoutValues[r.key] !== undefined ? String(readoutValues[r.key]) : '—'}</td>
                      <td>{r.unit || ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Coluna / área de parâmetros */}
        {hasParams && (
          <div className="nexus-ui-scene__params">
            {params.map((p: SceneParam) => {
              const domId = `${uid}-${p.id}`
              const val = paramValues[p.id] ?? p.default

              if (p.kind === 'range') {
                const numVal = Number(val)
                return (
                  <div key={p.id} className="nexus-ui-scene__param">
                    <div className="nexus-ui-field__row">
                      <label htmlFor={domId} className="nexus-ui-field__label">
                        {p.label}
                      </label>
                      <span className="nexus-ui-scene__param-val">
                        {Number.isFinite(numVal) ? numVal.toLocaleString(lang) : String(val)}
                      </span>
                    </div>
                    <input
                      id={domId}
                      type="range"
                      className="nexus-ui-range"
                      min={p.min ?? 0}
                      max={p.max ?? 100}
                      step={p.step ?? 1}
                      value={Number.isFinite(numVal) ? numVal : (p.min ?? 0)}
                      disabled={Boolean(streaming || error || escaped)}
                      onChange={(e) => handleParamChange(p.id, parseFloat(e.target.value))}
                    />
                  </div>
                )
              }

              if (p.kind === 'number') {
                const numVal = Number(val)
                return (
                  <div key={p.id} className="nexus-ui-scene__param">
                    <label htmlFor={domId} className="nexus-ui-field__label">
                      {p.label}
                    </label>
                    <input
                      id={domId}
                      type="number"
                      className="nexus-ui-input"
                      min={p.min}
                      max={p.max}
                      step={p.step ?? 1}
                      value={Number.isFinite(numVal) ? numVal : ''}
                      disabled={Boolean(streaming || error || escaped)}
                      onChange={(e) => handleParamChange(p.id, parseFloat(e.target.value))}
                    />
                  </div>
                )
              }

              if (p.kind === 'select' && Array.isArray(p.options)) {
                return (
                  <div key={p.id} className="nexus-ui-scene__param">
                    <label htmlFor={domId} className="nexus-ui-field__label">
                      {p.label}
                    </label>
                    <select
                      id={domId}
                      className="nexus-ui-select"
                      value={String(val)}
                      disabled={Boolean(streaming || error || escaped)}
                      onChange={(e) => handleParamChange(p.id, e.target.value)}
                    >
                      {p.options.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )
              }

              return null
            })}
          </div>
        )}
      </div>

      {/* Faixa de erro de runtime */}
      {error && (
        <div className="nexus-ui-scene__error" role="alert">
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: 0 }}>
            <AlertCircle size={16} style={{ color: 'var(--error)', flexShrink: 0 }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--error)', wordBreak: 'break-word' }}>
              {error === 'webglcontextlost'
                ? (t('intelligentUi.sceneWebGlLost') || 'O contexto gráfico 3D foi perdido.')
                : (t('intelligentUi.sceneError', { message: error }) || `Falha na cena: ${error}`)}
            </span>
          </div>
          {error === 'webglcontextlost' ? (
            <button
              type="button"
              className="nexus-ui-button nexus-ui-button--primary"
              style={{ fontSize: '0.75rem', padding: '4px 10px' }}
              onClick={handleRestart}
            >
              {t('intelligentUi.restart') || 'Reiniciar'}
            </button>
          ) : (
            <button
              type="button"
              className="nexus-ui-button nexus-ui-button--primary"
              style={{ fontSize: '0.75rem', padding: '4px 10px' }}
              onClick={handleRequestFix}
            >
              {t('intelligentUi.requestCorrection') || 'Pedir correção'}
            </button>
          )}
        </div>
      )}
    </UiCard>
  )
}

export default SceneCard
