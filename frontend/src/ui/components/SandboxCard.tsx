import React, { useEffect, useMemo, useRef, useState } from 'react'
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
import { useResolvedTheme } from '../hooks/useResolvedTheme'

interface Props {
  block: SandboxBlock
}

const RESIZE_MESSAGE_TYPE = '__nexus_ogui_resize'
const ACTION_MESSAGE_TYPE = 'nexus_action'

/** Evita que o conteúdo do bloco feche o <script> do host por acidente. */
function escapeScriptClose(code: string): string {
  return code.replace(/<\/script/gi, '<\\/script')
}

export function SandboxCard({ block }: Props) {
  const { t, i18n } = useTranslation()
  const { sendMessage } = useChatContext()
  const { image_hosts } = useIntelligentUiConfig()
  const { title, initial_height = 300, html, css = '', js = '', standalone_download = true } = block

  const [currentHeight, setCurrentHeight] = useState<number>(initial_height)
  const iframeRef = useRef<HTMLIFrameElement>(null)

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
  }, [themeMode, srcDoc])

  // Listener para eventos postMessage originados do sandbox
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      // Valida que a mensagem veio do iframe esperado
      if (iframeRef.current && event.source === iframeRef.current.contentWindow) {
        const data = event.data
        if (!data || typeof data !== 'object') return

        if (data.type === RESIZE_MESSAGE_TYPE && typeof data.height === 'number') {
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
  }, [sendMessage])

  // Ao carregar (ou recarregar) o iframe, reenvia o tema atual
  const handleIframeLoad = () => {
    iframeRef.current?.contentWindow?.postMessage(
      { type: THEME_MESSAGE_TYPE, mode: themeMode, tokens: readLiveThemeTokens() },
      '*'
    )
  }

  const handleDownload = () => {
    downloadStandaloneHtml(title, html, css, js, isDark, lang)
  }

  return (
    <div
      style={{
        marginTop: '12px',
        backgroundColor: 'var(--surface-card)',
        border: '1px solid var(--hairline)',
        borderRadius: '10px',
        overflow: 'hidden',
        boxShadow: '0 2px 10px rgba(0, 0, 0, 0.06)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header com título e botão de exportação standalone */}
      <div
        style={{
          padding: '6px 8px 6px 14px',
          borderBottom: '1px solid var(--hairline)',
          backgroundColor: 'var(--surface-soft)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '8px',
          minHeight: '44px',
        }}
      >
        <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--ink)' }}>
          {title}
        </span>

        {standalone_download && (
          <button
            type="button"
            onClick={handleDownload}
            title={t('intelligentUi.exportTooltip') || 'Baixar como HTML autônomo'}
            aria-label={t('intelligentUi.exportTooltip') || 'Baixar como HTML autônomo'}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '12px',
              fontWeight: 500,
              minHeight: '44px',
              minWidth: '44px',
              padding: '0 12px',
              borderRadius: '8px',
              border: '1px solid var(--hairline)',
              backgroundColor: 'var(--surface-card)',
              color: 'var(--ink)',
              cursor: 'pointer',
            }}
          >
            <span aria-hidden="true">↓</span> {t('intelligentUi.exportStandalone') || 'Baixar HTML'}
          </button>
        )}
      </div>

      {/* Container iframe sandbox estrito (SEM allow-same-origin) */}
      <div
        style={{
          width: '100%',
          height: `${currentHeight}px`,
          position: 'relative',
          transition: 'height 0.2s ease',
        }}
      >
        <iframe
          ref={iframeRef}
          srcDoc={srcDoc}
          sandbox="allow-scripts allow-forms"
          referrerPolicy="no-referrer"
          title={title}
          onLoad={handleIframeLoad}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            display: 'block',
            backgroundColor: 'transparent',
            colorScheme: isDark ? 'dark' : 'light',
          }}
        />
      </div>
    </div>
  )
}

export default SandboxCard
