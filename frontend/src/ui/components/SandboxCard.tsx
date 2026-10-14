import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Download, Maximize2, RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import type { SandboxBlock } from '../../types'
import { downloadStandaloneHtml } from '../lib/exportStandalone'
import {
  buildSandboxCsp,
  injectThemeTokens,
  readLiveThemeTokens,
  SANDBOX_IMPORTMAP,
  THEME_MESSAGE_TYPE,
} from '../themeBridge'
import { useIntelligentUiConfig } from '../hooks/useIntelligentUi'
import { useNearScreen } from '../hooks/useMotionAndViewport'
import { useResolvedTheme } from '../hooks/useResolvedTheme'
import { UiCard, UiCardAction } from './UiCard'

interface Props {
  block: SandboxBlock
  streaming?: boolean
  onRuntimeError?: (title: string, message: string) => void
}

const RESIZE_MESSAGE_TYPE = '__nexus_ogui_resize'
const ACTION_MESSAGE_TYPE = 'nexus_action'

/** Evita que o conteúdo do bloco feche o <script> do host por acidente. */
function escapeScriptClose(code: string): string {
  return code.replace(/<\/script/gi, '<\\/script')
}

export function SandboxCard({ block, streaming, onRuntimeError }: Props) {
  const { t, i18n } = useTranslation()
  const { sendMessage } = useChatContext()
  const { image_hosts } = useIntelligentUiConfig()
  const { title, initial_height = 300, html, css = '', js = '', standalone_download = true } = block

  const [currentHeight, setCurrentHeight] = useState<number>(initial_height)
  const [run, setRun] = useState(0)
  const [escaped, setEscaped] = useState(false)
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const loads = useRef(0)
  const [card, setCard] = useState<HTMLElement | null>(null)
  // O iframe só monta quando o cartão chega a uma tela de distância do viewport
  // (conversas longas não pagam por sandboxes fora da vista). Depois fica montado.
  const near = useNearScreen(card)

  // Tema efetivo do app, reativo (data-theme no <html>, resolvido pelo App.tsx)
  const themeMode = useResolvedTheme()
  const isDark = themeMode === 'dark'
  const lang = i18n.resolvedLanguage || i18n.language || 'pt-BR'

  // Tema de montagem: o srcDoc NÃO depende do tema atual — trocar tema não pode
  // recarregar o iframe (perderia o estado da ferramenta). O tema vai por postMessage.
  const mountTheme = useRef({ isDark, tokens: readLiveThemeTokens() })

  // Constrói o HTML completo com CSP, theme bridge, importmap e medição automática
  const srcDoc = useMemo(() => {
    const csp = buildSandboxCsp(image_hosts)
    const rawDocument = `<!DOCTYPE html>
<html lang="${lang}">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="${csp}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script type="importmap">${JSON.stringify(SANDBOX_IMPORTMAP)}</script>
  <style>
    html, body {
      margin: 0;
      padding: 10px;
      overflow-x: hidden;
      background: transparent;
    }
    ${css.replace(/<\/style/gi, '<\\/style')}
  </style>
  <script>
    // Runtime errors remain untrusted text, never HTML or automatic requests.
    function reportError(message) {
      parent.postMessage({ type: '__nexus_ogui_error', message: String(message || 'Runtime error').slice(0, 500) }, '*');
    }
    window.addEventListener('error', function(e) { reportError(e.message); });
    window.addEventListener('unhandledrejection', function(e) { reportError(e.reason && e.reason.message || e.reason); });
    // Bridge para envio de ações de volta ao chat
    window.NexusBridge = {
      sendMessage: function(text) {
        if (typeof text === 'string' && text.trim()) {
          parent.postMessage({ type: '${ACTION_MESSAGE_TYPE}', action: 'send_message', text: text }, '*');
        }
      }
    };

    // Medição contínua para auto-ajuste de altura sem layout shift
    (function() {
      function reportHeight() {
        var h = document.body.scrollHeight;
        parent.postMessage({ type: '${RESIZE_MESSAGE_TYPE}', height: Math.ceil(h) }, '*');
      }
      var ro = new ResizeObserver(reportHeight);
      window.addEventListener('load', function() {
        ro.observe(document.body);
        reportHeight();
      });
      setTimeout(reportHeight, 300);
      setTimeout(reportHeight, 1000);
    })();
  </script>
</head>
<body>
  ${html}
  ${js ? `<script>\n(async () => {\n${escapeScriptClose(js)}\n})();\n</script>` : ''}
</body>
</html>`

    return injectThemeTokens(rawDocument, mountTheme.current.isDark, mountTheme.current.tokens)
    // image_hosts entra na CSP; lang no <html>. Tema de propósito fora das deps.
  }, [html, css, js, lang, image_hosts])

  // Tema ao vivo: a cada troca, manda data-theme + tokens reais do app para o iframe
  useEffect(() => {
    const win = iframeRef.current?.contentWindow
    if (!win) return
    win.postMessage({ type: THEME_MESSAGE_TYPE, mode: themeMode, tokens: readLiveThemeTokens() }, '*')
  }, [themeMode, srcDoc, run, near])

  // Listener para eventos postMessage originados do sandbox
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Valida que a mensagem veio do iframe esperado
      if (iframeRef.current && event.source === iframeRef.current.contentWindow) {
        const data = event.data
        if (!data || typeof data !== 'object') return

        if (data.type === '__nexus_ogui_error' && typeof data.message === 'string') {
          onRuntimeError?.(title, data.message.slice(0, 500))
        } else if (data.type === RESIZE_MESSAGE_TYPE && typeof data.height === 'number') {
          const boundedHeight = Math.min(1000, Math.max(120, data.height + 20))
          setCurrentHeight(boundedHeight)
        } else if (
          data.type === ACTION_MESSAGE_TYPE &&
          data.action === 'send_message' &&
          typeof data.text === 'string'
        ) {
          if (sendMessage && data.text.trim()) {
            sendMessage(data.text.trim())
          }
        }
      }
    }

    window.addEventListener('message', handleMessage)
    return () => {
      window.removeEventListener('message', handleMessage)
    }
  }, [sendMessage, onRuntimeError, title])

  // Ao carregar o iframe, reenvia o tema atual. Um SEGUNDO load no mesmo iframe
  // significa que o conteúdo navegou para fora do srcdoc (o sandbox bloqueia a
  // navegação do topo, mas não a do próprio frame): em vez de deixar uma página de
  // erro do navegador, avisamos e oferecemos Reiniciar. Ideia do AnswerUI (MIT).
  const handleIframeLoad = () => {
    loads.current += 1
    if (loads.current > 1) {
      setEscaped(true)
      return
    }
    iframeRef.current?.contentWindow?.postMessage(
      { type: THEME_MESSAGE_TYPE, mode: themeMode, tokens: readLiveThemeTokens() },
      '*'
    )
  }

  const handleRestart = useCallback(() => {
    loads.current = 0
    setEscaped(false)
    setCurrentHeight(initial_height)
    setRun((n) => n + 1)
  }, [initial_height])

  const handleFullscreen = () => {
    const target = card as (HTMLElement & { webkitRequestFullscreen?: () => void }) | null
    if (!target || streaming) return
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
    downloadStandaloneHtml(title, html, css, js, isDark, lang)
  }

  const restartLabel = t('intelligentUi.restart') || 'Reiniciar'

  return (
    <UiCard
      ref={setCard}
      as="figure"
      variant="flush"
      className="nexus-ui-sandbox"
      title={title}
      actions={
        <>
          <UiCardAction
            icon={<RotateCcw size={14} />}
            label={restartLabel}
            onClick={handleRestart}
            hideLabel
            disabled={streaming}
          />
          <UiCardAction
            icon={<Maximize2 size={14} />}
            label={t('intelligentUi.fullscreen') || 'Tela cheia'}
            onClick={handleFullscreen}
            hideLabel
            disabled={streaming}
          />
          {standalone_download && (
            <UiCardAction
              icon={<Download size={14} />}
              label={t('intelligentUi.exportStandalone') || 'Baixar HTML'}
              onClick={handleDownload}
              disabled={streaming}
            />
          )}
        </>
      }
    >
      {/* Container iframe sandbox estrito (SEM allow-same-origin) */}
      <div className="nexus-ui-sandbox__stage" style={{ height: `${currentHeight}px` }}>
        {escaped ? (
          <div className="nexus-ui-sandbox__notice" role="alert">
            <p>{t('intelligentUi.sandboxEscaped') || 'O conteúdo tentou sair do sandbox e foi interrompido.'}</p>
            <button type="button" className="nexus-ui-button" onClick={handleRestart} disabled={streaming}>
              <RotateCcw size={14} aria-hidden="true" /> {restartLabel}
            </button>
          </div>
        ) : streaming ? (
          <div className="nexus-ui-sandbox__placeholder" aria-hidden="true" />
        ) : near ? (
          <iframe
            key={run}
            ref={iframeRef}
            srcDoc={srcDoc}
            sandbox="allow-scripts allow-forms"
            referrerPolicy="no-referrer"
            title={title}
            onLoad={handleIframeLoad}
            style={{ colorScheme: isDark ? 'dark' : 'light' }}
          />
        ) : (
          <div className="nexus-ui-sandbox__placeholder" aria-hidden="true" />
        )}
      </div>
    </UiCard>
  )
}

export default SandboxCard
