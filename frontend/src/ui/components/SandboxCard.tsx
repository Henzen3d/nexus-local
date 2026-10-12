import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useChatContext } from '../../context/ChatContext'
import type { SandboxBlock } from '../../types'
import { downloadStandaloneHtml } from '../lib/exportStandalone'
import { injectThemeTokens } from '../themeBridge'

interface Props {
  block: SandboxBlock
}

const RESIZE_MESSAGE_TYPE = '__nexus_ogui_resize'
const ACTION_MESSAGE_TYPE = 'nexus_action'

export function SandboxCard({ block }: Props) {
  const { t } = useTranslation()
  const { sendMessage } = useChatContext()
  const { title, initial_height = 300, html, css = '', js = '', standalone_download = true } = block

  const [currentHeight, setCurrentHeight] = useState<number>(initial_height)
  const iframeRef = useRef<HTMLIFrameElement>(null)

  // Detecta se o app está em modo escuro
  const isDark = typeof document !== 'undefined'
    ? !document.documentElement.classList.contains('light')
    : true

  // Constrói o HTML completo com theme bridge, importmap e medição automática
  const srcDoc = useMemo(() => {
    const rawDocument = `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script type="importmap">
  {
    "imports": {
      "three": "https://esm.sh/three",
      "gsap": "https://esm.sh/gsap",
      "d3": "https://esm.sh/d3",
      "chart.js": "https://esm.sh/chart.js"
    }
  }
  </script>
  <style>
    html, body {
      margin: 0;
      padding: 10px;
      overflow-x: hidden;
      background: transparent;
    }
    ${css}
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
  ${js ? `<script>\n(async () => {\n${js}\n})();\n</script>` : ''}
</body>
</html>`

    return injectThemeTokens(rawDocument, isDark)
  }, [html, css, js, isDark])

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

  const handleDownload = () => {
    downloadStandaloneHtml(title, html, css, js, isDark)
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
          padding: '10px 14px',
          borderBottom: '1px solid var(--hairline)',
          backgroundColor: 'var(--surface-soft)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
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
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              fontWeight: 500,
              padding: '4px 8px',
              borderRadius: '6px',
              border: '1px solid var(--hairline)',
              backgroundColor: 'var(--surface-card)',
              color: 'var(--ink)',
              cursor: 'pointer',
              transition: 'background 0.15s ease',
            }}
          >
            <span>↓</span> {t('intelligentUi.exportStandalone') || 'Baixar HTML'}
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
          title={title}
          style={{
            width: '100%',
            height: '100%',
            border: 'none',
            display: 'block',
            backgroundColor: 'transparent',
          }}
        />
      </div>
    </div>
  )
}

export default SandboxCard
