/**
 * OpenIntelligentUI (CopilotKit) — Standalone HTML Exporter
 * Adaptado para o Multi+ / Nexus Local (Fase 7 - Exportação 1-Click)
 * Fonte: CopilotKit/OpenIntelligentUI (apps/app/src/components/generative-ui/export-utils.ts)
 */

import { IMPORTMAP_SCRIPT_TAG } from "./sandbox-core";

function escapeScriptClose(js: string): string {
  return js.replace(/<\/script/gi, "<\\/script");
}

function escapeStyleClose(css: string): string {
  return css.replace(/<\/style/gi, "<\\/style");
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export interface StandaloneWidgetContent {
  title?: string;
  html: string;
  css?: string;
  js?: string; // Campo direto do contrato nexus-ui/1 (Fase 7)
  jsFunctions?: string;
  jsExpressions?: string[];
  themeCss?: string;
}

/**
 * Empacota a ferramenta gerada em um arquivo HTML standalone
 * que funciona perfeitamente ao ser aberto localmente em qualquer navegador.
 */
export function assembleStandaloneHtml(
  content: StandaloneWidgetContent
): string {
  const title = content.title || "nexus-interactive-tool";
  const body = content.html || "";
  const expressions = content.jsExpressions || [];

  const scriptParts = [
    ...(content.js ? [escapeScriptClose(content.js)] : []),
    ...(content.jsFunctions ? [escapeScriptClose(content.jsFunctions)] : []),
    ...(expressions.length > 0
      ? [
          `(async () => {\n${expressions.map(escapeScriptClose).join("\n")}\n})();`,
        ]
      : []),
  ];

  const generatedScript =
    scriptParts.length > 0
      ? `<script>\n${scriptParts.join("\n")}\n</script>`
      : "";

  return `<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  ${IMPORTMAP_SCRIPT_TAG}
  ${content.themeCss ? `<style>\n${escapeStyleClose(content.themeCss)}\n</style>` : ""}
  ${content.css ? `<style>\n${escapeStyleClose(content.css)}\n</style>` : ""}
  <script>
    // Fallback gracioso para a bridge quando aberto fora do Nexus
    window.NexusBridge = {
      sendMessage: function(text) {
        console.log("[NexusBridge Standalone] Ação disparada:", text);
        alert("Ação standalone: " + text);
      }
    };
  </script>
</head>
<body>
  ${body}
  ${generatedScript}
</body>
</html>`;
}

/**
 * Dispara o download imediato do arquivo HTML no navegador
 */
export function downloadHtmlFile(filename: string, htmlContent: string): void {
  const blob = new Blob([htmlContent], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename.endsWith(".html") ? filename : `${filename}.html`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
