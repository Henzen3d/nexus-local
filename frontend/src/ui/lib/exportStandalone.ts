/**
 * Exportador Standalone 1-Click para ferramentas interativas geradas em sandbox.
 * Empacota HTML, CSS, JS e Design Tokens em um único arquivo .html autônomo.
 */

import { getThemeTokensCss, PRE_STYLED_CONTROLS_CSS } from '../themeBridge'

function escapeScriptClose(code: string): string {
  return code.replace(/<\/script/gi, '<\\/script')
}

function escapeStyleClose(code: string): string {
  return code.replace(/<\/style/gi, '<\\/style')
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function assembleStandaloneHtml(
  title: string,
  bodyHtml: string,
  css = '',
  js = '',
  isDark = true
): string {
  const safeTitle = title || 'nexus-interactive-tool'
  const themeCss = getThemeTokensCss(isDark)

  const scriptBlock = js
    ? `<script>
(async () => {
${escapeScriptClose(js)}
})();
</script>`
    : ''

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(safeTitle)}</title>
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
${escapeStyleClose(themeCss)}
${escapeStyleClose(PRE_STYLED_CONTROLS_CSS)}
${escapeStyleClose(css)}
  </style>
  <script>
    // Fallback gracioso para a bridge do Nexus quando aberto localmente fora do chat
    window.NexusBridge = {
      sendMessage: function(text) {
        console.log("[NexusBridge Standalone] Ação disparada:", text);
        alert("Ação standalone: " + text);
      }
    };
  </script>
</head>
<body>
  ${bodyHtml}
  ${scriptBlock}
</body>
</html>`
}

export function downloadStandaloneHtml(
  title: string,
  html: string,
  css = '',
  js = '',
  isDark = true
): void {
  const completeHtml = assembleStandaloneHtml(title, html, css, js, isDark)
  const blob = new Blob([completeHtml], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const cleanFilename = (title || 'interactive-tool')
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '_')
  a.download = `${cleanFilename}.html`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
