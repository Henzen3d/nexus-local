/**
 * Documento (srcdoc) de uma cena: CSP sem rede, runtime local, setup, código do modelo, start().
 *
 * Adaptado de AnswerUI — https://github.com/0xcro3dile/answerui (src/scene/document.ts),
 * MIT License, Copyright (c) 2026 0xcro3dile.
 */

import type { SceneSetup } from './sceneProtocol'

export function sceneDocument(
  setup: SceneSetup,
  code: string,
  runtimeUrl: string,
  lang = 'pt-BR',
): string {
  const policy = [
    "default-src 'none'",
    `script-src 'unsafe-inline' ${runtimeUrl}`,
    "style-src 'unsafe-inline'",
    'img-src data: blob:',
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ')

  return `<!doctype html>
<html lang="${lang}">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="${policy}">
<meta name="color-scheme" content="${setup.theme.dark ? 'dark' : 'light'}">
<style>html,body{margin:0;height:100%;overflow:hidden;background:transparent}</style>
<script src="${runtimeUrl}"></script>
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

/** O código do modelo não pode fechar o <script> em que está nem abrir comentário HTML. */
export function escapeScript(code: string): string {
  return code.replace(/<\/(script)/gi, '<\\/$1').replace(/<!--/g, '<\\!--')
}

/** JSON embutido em <script>: `<` vira `\u003c` para não fechar a tag. */
export function embed(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c')
}
