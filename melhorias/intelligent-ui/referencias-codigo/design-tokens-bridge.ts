/**
 * OpenIntelligentUI (CopilotKit) — Design Tokens Bridge
 * Adaptado para os tokens nativos do Multi+ / Nexus Local (`frontend/src/index.css`)
 * Fonte: CopilotKit/OpenIntelligentUI (packages/design-system/src/index.ts)
 */

/**
 * Variáveis de tema para o sandbox geradas dinamicamente com base no tema ativo do Multi+
 */
export function getThemeTokensCss(isDark: boolean): string {
  // Nota: o iframe sandbox roda isolado (sem allow-same-origin), logo não herda
  // as variáveis CSS do documento pai. Injetamos aqui os valores literais exatos
  // do design system do Multi+ (frontend/src/index.css), expondo tanto as variáveis
  // padronizadas do OpenIntelligentUI quanto os aliases nativos do Multi+.
  if (isDark) {
    return `
:root {
  /* Multi+ Native Design Tokens (Dark) */
  --canvas: #1f1f1e;
  --surface-card: #2c2c2a;
  --surface-soft: #252320;
  --hairline: #33312d;
  --ink: #f8f8f6;
  --body: #c3c2b7;
  --primary: #cc785c;
  --cyan: #5db8a6;
  --warning: #d4a017;
  --success: #5db872;
  --error: #c64545;

  /* Mapeamento OpenIntelligentUI Bridge */
  --color-background-primary: #1f1f1e;
  --color-background-secondary: #2c2c2a;
  --color-background-tertiary: #252320;
  --color-text-primary: #f8f8f6;
  --color-text-secondary: #c3c2b7;
  --color-text-tertiary: #97958c;
  --color-border-primary: #33312d;
  --color-border-secondary: rgba(255, 255, 255, 0.15);
  --color-border-tertiary: rgba(255, 255, 255, 0.08);

  --color-brand: #cc785c;
  --color-cyan: #5db8a6;
  --color-warning: #d4a017;
  --color-success: #5db872;
  --color-danger: #c64545;

  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  --border-radius-md: 8px;
  --border-radius-lg: 12px;
}
`;
  }

  return `
:root {
  /* Multi+ Native Design Tokens (Light) */
  --canvas: #f8f8f6;
  --surface-card: #ffffff;
  --surface-soft: #f1f1ee;
  --hairline: #e5e5df;
  --ink: #1d1d1c;
  --body: #575653;
  --primary: #cc785c;
  --cyan: #319795;
  --warning: #b8860b;
  --success: #2e854b;
  --error: #c64545;

  /* Mapeamento OpenIntelligentUI Bridge */
  --color-background-primary: #f8f8f6;
  --color-background-secondary: #ffffff;
  --color-background-tertiary: #f1f1ee;
  --color-text-primary: #1d1d1c;
  --color-text-secondary: #575653;
  --color-text-tertiary: #8c8a82;
  --color-border-primary: #e5e5df;
  --color-border-secondary: rgba(0, 0, 0, 0.15);
  --color-border-tertiary: rgba(0, 0, 0, 0.06);

  --color-brand: #cc785c;
  --color-cyan: #319795;
  --color-warning: #b8860b;
  --color-success: #2e854b;
  --color-danger: #c64545;

  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  --border-radius-md: 8px;
  --border-radius-lg: 12px;
}
`;
}

/**
 * Estilos pré-definidos para controles de formulário dentro do sandbox
 * Garante que botões, inputs, sliders e caixas de texto já nasçam com a identidade visual do Multi+
 */
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
button.primary:hover {
  filter: brightness(1.1);
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
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
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
`;

/**
 * Paleta de cores para diagramas SVG e gráficos manuais
 */
export const SVG_DIAGRAM_CLASSES_CSS = `
svg text.t  { font: 400 13px var(--font-sans); fill: var(--color-text-primary); }
svg text.ts { font: 400 11px var(--font-sans); fill: var(--color-text-secondary); }
svg text.th { font: 600 13px var(--font-sans); fill: var(--color-text-primary); }
svg .box    { fill: var(--color-background-secondary); stroke: var(--color-border-primary); }
svg .arr    { stroke: var(--color-text-secondary); stroke-width: 1.5; fill: none; }
`;
