/**
 * Theme Bridge para injeção de tokens do Multi+ dentro do sandbox isolado.
 * Garante que micro-ferramentas geradas tenham harmonia visual com o app.
 *
 * Duas camadas:
 * 1. Tokens estáticos dos dois temas, escolhidos por `html[data-theme]` dentro do
 *    iframe (e por `prefers-color-scheme` no arquivo standalone). O host troca o
 *    `data-theme` do iframe via postMessage — sem recarregar o documento.
 * 2. Tokens ao vivo lidos com `getComputedStyle(document.documentElement)` do app
 *    e aplicados como `style` inline no `<html>` do iframe. Assim o sandbox segue
 *    o `index.css` real e os valores abaixo viram só fallback (ex.: standalone).
 */

export type ThemeMode = 'dark' | 'light'

/** Tipo de mensagem host → iframe com o tema atual. */
export const THEME_MESSAGE_TYPE = '__nexus_theme'

interface TokenSet {
  canvas: string
  surfaceCard: string
  surfaceSoft: string
  hairline: string
  ink: string
  body: string
  inkMuted: string
  primary: string
  cyan: string
  warning: string
  success: string
  error: string
  borderSecondary: string
  borderTertiary: string
}

const DARK: TokenSet = {
  canvas: '#1f1f1e',
  surfaceCard: '#2c2c2a',
  surfaceSoft: '#252320',
  hairline: '#33312d',
  ink: '#f8f8f6',
  body: '#c3c2b7',
  inkMuted: '#97958c',
  primary: '#cc785c',
  cyan: '#5db8a6',
  warning: '#d4a017',
  success: '#5db872',
  error: '#c64545',
  borderSecondary: 'rgba(255, 255, 255, 0.15)',
  borderTertiary: 'rgba(255, 255, 255, 0.08)',
}

const LIGHT: TokenSet = {
  canvas: '#f8f8f6',
  surfaceCard: '#ffffff',
  surfaceSoft: '#f1f1ee',
  hairline: '#e5e5df',
  ink: '#1d1d1c',
  body: '#575653',
  inkMuted: '#8c8a82',
  primary: '#cc785c',
  cyan: '#319795',
  warning: '#b8860b',
  success: '#2e854b',
  error: '#c64545',
  borderSecondary: 'rgba(0, 0, 0, 0.15)',
  borderTertiary: 'rgba(0, 0, 0, 0.06)',
}

/**
 * Variáveis do app (index.css) → variáveis do bridge. A primeira coluna é lida
 * ao vivo de `document.documentElement`; a segunda é o nome dentro do sandbox.
 */
const LIVE_TOKEN_MAP: ReadonlyArray<readonly [appVar: string, key: keyof TokenSet]> = [
  ['--canvas', 'canvas'],
  ['--surface-card', 'surfaceCard'],
  ['--surface-soft', 'surfaceSoft'],
  ['--hairline', 'hairline'],
  ['--ink', 'ink'],
  ['--body', 'body'],
  ['--ink-muted', 'inkMuted'],
  ['--primary', 'primary'],
  ['--cyan', 'cyan'],
  ['--warning', 'warning'],
  ['--success', 'success'],
  ['--error', 'error'],
]

function tokenDeclarations(t: TokenSet): string {
  return `
  /* Multi+ Native Design Tokens */
  --canvas: ${t.canvas};
  --surface-card: ${t.surfaceCard};
  --surface-soft: ${t.surfaceSoft};
  --hairline: ${t.hairline};
  --ink: ${t.ink};
  --body: ${t.body};
  --ink-muted: ${t.inkMuted};
  --primary: ${t.primary};
  --cyan: ${t.cyan};
  --warning: ${t.warning};
  --success: ${t.success};
  --error: ${t.error};

  /* Mapeamento OpenIntelligentUI Bridge */
  --color-background-primary: var(--canvas);
  --color-background-secondary: var(--surface-card);
  --color-background-tertiary: var(--surface-soft);
  --color-text-primary: var(--ink);
  --color-text-secondary: var(--body);
  --color-text-tertiary: var(--ink-muted);
  --color-border-primary: var(--hairline);
  --color-border-secondary: ${t.borderSecondary};
  --color-border-tertiary: ${t.borderTertiary};

  --color-brand: var(--primary);
  --color-cyan: var(--cyan);
  --color-warning: var(--warning);
  --color-success: var(--success);
  --color-danger: var(--error);

  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  --border-radius-md: 8px;
  --border-radius-lg: 12px;
  color-scheme: ${t === DARK ? 'dark' : 'light'};
`
}

/** Tokens de um tema só (compatibilidade; usado como fallback estático). */
export function getThemeTokensCss(isDark: boolean): string {
  return `\n:root {${tokenDeclarations(isDark ? DARK : LIGHT)}}\n`
}

/**
 * Tokens dos dois temas. `data-theme` no `<html>` escolhe; sem atributo, segue o
 * sistema (`prefers-color-scheme`) — é o caso do arquivo standalone aberto fora do chat.
 */
export function getThemeBridgeCss(): string {
  return `
:root {${tokenDeclarations(DARK)}}
html[data-theme="light"] {${tokenDeclarations(LIGHT)}}
@media (prefers-color-scheme: light) {
  html:not([data-theme="dark"]) {${tokenDeclarations(LIGHT)}}
}
`
}

/**
 * Lê os tokens reais do app em `document.documentElement`. Devolve só os que
 * existem no CSS carregado — o que faltar fica com o fallback estático do bridge.
 */
export function readLiveThemeTokens(): Record<string, string> {
  if (typeof window === 'undefined' || typeof document === 'undefined') return {}
  const styles = window.getComputedStyle(document.documentElement)
  const out: Record<string, string> = {}
  for (const [appVar] of LIVE_TOKEN_MAP) {
    const value = styles.getPropertyValue(appVar).trim()
    if (value) out[appVar] = value
  }
  return out
}

/** Tema efetivo do app: `data-theme` resolvido pelo App.tsx; sem atributo, sistema. */
export function getResolvedThemeMode(): ThemeMode {
  if (typeof document === 'undefined') return 'dark'
  const attr = document.documentElement.getAttribute('data-theme')
  if (attr === 'light' || attr === 'dark') return attr
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
  return 'dark'
}

export const PRE_STYLED_CONTROLS_CSS = `
* { box-sizing: border-box; margin: 0; }
html { background: transparent; }
body {
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  color: var(--color-text-primary);
  background: transparent;
  -webkit-font-smoothing: antialiased;
  padding: 12px;
}

button {
  font-family: inherit;
  font-size: 13px;
  font-weight: 500;
  min-height: 44px;
  padding: 8px 16px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--border-radius-md);
  background: var(--color-background-secondary);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: all 0.15s ease;
}
button:hover {
  background: var(--color-background-tertiary);
  border-color: var(--color-border-secondary);
}
button.primary {
  background: var(--color-brand);
  color: #ffffff;
  border-color: var(--color-brand);
}

input[type="text"],
input[type="number"],
select,
textarea {
  font-family: inherit;
  font-size: 13px;
  padding: 6px 12px;
  height: 36px;
  border: 1px solid var(--color-border-primary);
  border-radius: var(--border-radius-md);
  background: var(--color-background-primary);
  color: var(--color-text-primary);
  outline: none;
  transition: border-color 0.15s;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--color-brand);
  box-shadow: 0 0 0 2px rgba(204, 120, 92, 0.2);
}

input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  height: 6px;
  background: var(--color-background-tertiary);
  border-radius: 3px;
  outline: none;
  cursor: pointer;
}
input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--color-brand);
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; }
}
`

/**
 * Hosts externos que o sandbox pode usar para módulos ES (importmap). Lista
 * fechada: é o que a CSP libera em `script-src`/`connect-src`.
 */
export const SANDBOX_MODULE_CDN = 'https://esm.sh'

export const SANDBOX_IMPORTMAP = {
  imports: {
    three: `${SANDBOX_MODULE_CDN}/three`,
    gsap: `${SANDBOX_MODULE_CDN}/gsap`,
    d3: `${SANDBOX_MODULE_CDN}/d3`,
    'chart.js': `${SANDBOX_MODULE_CDN}/chart.js`,
  },
} as const

/**
 * Content-Security-Policy do documento do sandbox (meta http-equiv).
 * Fecha tudo e reabre só o necessário: scripts inline do bloco + módulos do CDN
 * homologado; imagens só `data:`/`blob:` e os hosts confiáveis do Intelligent UI
 * (mesma lista dos cartões) — sem canal de saída para URL arbitrária.
 */
export function buildSandboxCsp(imageHosts: string[] = []): string {
  const imgHosts = imageHosts
    .map((h) => h.trim().toLowerCase())
    .filter((h) => /^[a-z0-9.-]+(?::\d+)?$/.test(h))
    .map((h) => `https://${h}`)
  return [
    "default-src 'none'",
    `script-src 'unsafe-inline' ${SANDBOX_MODULE_CDN}`,
    "style-src 'unsafe-inline'",
    `img-src data: blob:${imgHosts.length ? ' ' + imgHosts.join(' ') : ''}`,
    'font-src data:',
    'media-src data: blob:',
    `connect-src ${SANDBOX_MODULE_CDN}`,
    "frame-src 'none'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'none'",
  ].join('; ')
}

/**
 * Injeta o bridge no documento: tokens dos dois temas + estilos base + o
 * receptor de `__nexus_theme` (troca `data-theme` e aplica tokens ao vivo).
 */
export function injectThemeTokens(html: string, isDark: boolean, liveTokens: Record<string, string> = {}): string {
  const initialInline = Object.entries(liveTokens)
    .map(([k, v]) => `${k}: ${v}`)
    .join('; ')
  const fullStyle = `
<style id="nexus-theme-bridge">
${getThemeBridgeCss()}
${PRE_STYLED_CONTROLS_CSS}
</style>
<script>
  // Receptor do tema do host: troca data-theme e aplica tokens ao vivo sem recarregar.
  (function () {
    var root = document.documentElement;
    root.setAttribute('data-theme', ${JSON.stringify(isDark ? 'dark' : 'light')});
    ${initialInline ? `root.setAttribute('style', ${JSON.stringify(initialInline)});` : ''}
    window.addEventListener('message', function (ev) {
      var d = ev.data;
      if (!d || d.type !== ${JSON.stringify(THEME_MESSAGE_TYPE)}) return;
      if (d.mode === 'dark' || d.mode === 'light') root.setAttribute('data-theme', d.mode);
      if (d.tokens && typeof d.tokens === 'object') {
        for (var k in d.tokens) {
          if (/^--[a-z0-9-]+$/.test(k) && typeof d.tokens[k] === 'string') root.style.setProperty(k, d.tokens[k]);
        }
      }
    });
  })();
</script>
`

  if (html.includes('</head>')) {
    return html.replace('</head>', `${fullStyle}\n</head>`)
  }

  return `${fullStyle}\n${html}`
}
