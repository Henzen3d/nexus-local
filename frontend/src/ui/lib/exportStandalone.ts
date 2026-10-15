/**
 * Exportador Standalone 1-Click para ferramentas interativas geradas em sandbox.
 * Empacota HTML, CSS, JS e Design Tokens em um único arquivo .html autônomo.
 */

import { getThemeBridgeCss, PRE_STYLED_CONTROLS_CSS, SANDBOX_IMPORTMAP } from '../themeBridge.ts'
import type { SceneSetup } from '../scene/sceneProtocol.ts'
import { embed, escapeScript } from '../scene/sceneDocument.ts'

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
  isDark = true,
  lang = 'pt-BR'
): string {
  const safeTitle = title || 'nexus-interactive-tool'
  // Os dois temas vão no arquivo: data-theme fixa o tema de quando foi baixado,
  // e quem abrir pode trocar editando o atributo (ou removê-lo para seguir o sistema).
  const themeCss = getThemeBridgeCss()
  const safeLang = /^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$/.test(lang) ? lang : 'pt-BR'

  const scriptBlock = js
    ? `<script>
(async () => {
${escapeScriptClose(js)}
})();
</script>`
    : ''

  return `<!DOCTYPE html>
<html lang="${safeLang}" data-theme="${isDark ? 'dark' : 'light'}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(safeTitle)}</title>
  <script type="importmap">${JSON.stringify(SANDBOX_IMPORTMAP)}</script>
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
  isDark = true,
  lang = 'pt-BR'
): void {
  const completeHtml = assembleStandaloneHtml(title, html, css, js, isDark, lang)
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

export async function assembleStandaloneSceneHtml(
  title: string,
  setup: SceneSetup,
  code: string,
  runtimeCode?: string,
  lang = 'pt-BR'
): Promise<string> {
  let runtime = runtimeCode
  if (!runtime && typeof fetch === 'function') {
    try {
      const resp = await fetch('/scene/runtime.js')
      if (resp.ok) {
        runtime = await resp.text()
      }
    } catch {
      // offline or fetch failed
    }
  }
  runtime = runtime || '/* NexusScene runtime not embedded */'
  const safeTitle = title || 'nexus-scene'
  const safeLang = /^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$/.test(lang) ? lang : 'pt-BR'

  return `<!doctype html>
<html lang="${safeLang}" data-theme="${setup.theme.dark ? 'dark' : 'light'}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${escapeHtml(safeTitle)}</title>
<meta name="color-scheme" content="${setup.theme.dark ? 'dark' : 'light'}">
<style>
html,body{margin:0;height:100%;overflow:hidden;background:${setup.theme.dark ? '#1f1f1e' : '#f8f8f6'}}
</style>
<script>
${escapeScriptClose(runtime)}
</script>
</head>
<body>
<script>NexusScene.setup(${embed(setup)})</script>
<script>
${escapeScript(code)}
</script>
<script>NexusScene.start(typeof scene === "object" ? scene : null, typeof camera === "object" ? camera : null)</script>
</body>
</html>`
}

export async function downloadStandaloneSceneHtml(
  title: string,
  setup: SceneSetup,
  code: string,
  lang = 'pt-BR'
): Promise<void> {
  const completeHtml = await assembleStandaloneSceneHtml(title, setup, code, undefined, lang)
  const blob = new Blob([completeHtml], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  const cleanFilename = (title || 'interactive-scene')
    .toLowerCase()
    .replace(/[^a-z0-9_-]/g, '_')
  a.download = `${cleanFilename}.html`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
