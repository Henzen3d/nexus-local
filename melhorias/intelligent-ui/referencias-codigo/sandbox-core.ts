/**
 * OpenIntelligentUI (CopilotKit) — Sandbox Runtime Core
 * Adaptado para o Multi+ / Nexus Local (Fase 7 - Open Generative UI)
 * Fonte: CopilotKit/OpenIntelligentUI (apps/app/src/components/generative-ui/open-generative-ui/)
 */

export const RESIZE_MESSAGE_TYPE = "__nexus_ogui_resize";
export const ACTION_MESSAGE_TYPE = "nexus_action";

/**
 * CSP estrita para o iframe sandbox:
 * - default-src 'self'
 * - script-src e connect-src limitados a CDNs seguras homologadas (esm.sh, cdnjs, jsdelivr, unpkg)
 * - img-src seguro (self, data:, blob:, wikimedia, basemap)
 */
export const CSP_META_TAG = `<meta http-equiv="Content-Security-Policy" content="
  default-src 'self';
  script-src 'unsafe-inline' 'unsafe-eval'
    https://cdnjs.cloudflare.com
    https://esm.sh
    https://cdn.jsdelivr.net
    https://unpkg.com;
  style-src 'unsafe-inline';
  img-src 'self' data: blob: https://basemap.nationalmap.gov https://upload.wikimedia.org https://thumb.wikimedia.org;
  font-src 'self' data:;
  connect-src 'self'
    https://cdnjs.cloudflare.com
    https://esm.sh
    https://cdn.jsdelivr.net
    https://unpkg.com;
">`;

/**
 * Importmap padronizado para resolução instantânea de módulos modernos em vanilla JS
 * Permite ao modelo usar `import * as THREE from 'three'` ou `import * as d3 from 'd3'`
 */
export const IMPORTMAP = {
  imports: {
    "three": "https://esm.sh/three",
    "three/": "https://esm.sh/three/",
    "gsap": "https://esm.sh/gsap",
    "gsap/": "https://esm.sh/gsap/",
    "d3": "https://esm.sh/d3",
    "d3/": "https://esm.sh/d3/",
    "chart.js": "https://esm.sh/chart.js",
    "chart.js/": "https://esm.sh/chart.js/",
  },
} as const;

export const IMPORTMAP_SCRIPT_TAG = `<script type="importmap">
${JSON.stringify(IMPORTMAP, null, 2)}
</script>`;

/**
 * Script de dimensionamento contínuo automático injetado no sandbox:
 * Monitora document.body com ResizeObserver e avisa o host via parent.postMessage
 * para eliminar layout shifts e barras de rolagem desnecessárias.
 */
export const MEASUREMENT_JS = `
(function() {
  if (window.__nexusResizeInstalled) return;
  window.__nexusResizeInstalled = true;
  var style = document.createElement('style');
  style.textContent = 'html, body { overflow: hidden !important; height: auto !important; min-height: 0 !important; }';
  document.head.appendChild(style);

  function reportHeight() {
    var h = document.body.scrollHeight;
    var cs = getComputedStyle(document.body);
    h += parseFloat(cs.marginTop) || 0;
    h += parseFloat(cs.marginBottom) || 0;
    parent.postMessage({ type: '${RESIZE_MESSAGE_TYPE}', height: Math.ceil(h) }, '*');
  }

  var ro = new ResizeObserver(reportHeight);
  ro.observe(document.body);
  window.addEventListener('resize', reportHeight);
  window.addEventListener('load', reportHeight);
  var interval = setInterval(reportHeight, 200);
  setTimeout(function() { clearInterval(interval); }, 3000);
  reportHeight();
})();
`;

/**
 * Bridge de comunicação do Sandbox para o Chat:
 * Permite que botões na ferramenta gerada disparem prompts no chat principal.
 */
export const HOST_BRIDGE_STUB = `
window.NexusBridge = {
  sendMessage: function(text) {
    if (typeof text === 'string' && text.trim()) {
      parent.postMessage({ type: '${ACTION_MESSAGE_TYPE}', action: 'send_message', text: text }, '*');
    }
  }
};
`;

/**
 * Construtor do documento final completo para o iframe
 */
export function buildFinalSandboxDocument(
  html: string,
  css?: string,
  js?: string,
  themeCss?: string
): string {
  return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  ${CSP_META_TAG}
  ${IMPORTMAP_SCRIPT_TAG}
  ${themeCss ? `<style>${themeCss}</style>` : ""}
  ${css ? `<style>${css}</style>` : ""}
  <script>${HOST_BRIDGE_STUB}</script>
  <script>${MEASUREMENT_JS}</script>
</head>
<body>
  ${html}
  ${js ? `<script>\n(async () => {\n${js}\n})();\n</script>` : ""}
</body>
</html>`;
}
