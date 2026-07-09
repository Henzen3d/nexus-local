---
version: beta-2
name: Claude-design-analysis
description: A warm-canvas editorial interface for Anthropic's Claude product. The system anchors on a tinted cream canvas with serif display headlines, warm coral CTAs, and dark navy product surfaces (code editor mockups, model showcase cards). Brand voltage comes from the cream/coral pairing — deliberately warm and humanist where most AI brands use cool blue + slate. Type voice runs a slab-serif display ("Copernicus" / Tiempos Headline) for h1/h2 and a humanist sans for body. The signature Anthropic black-radial-spike mark anchors the wordmark. As of v-beta, the **product/chat app now ships two theme modes — Light and Dark** — controlled by semantic tokens layered on top of the base palette (see "Theme Modes" section). As of v-beta-2, the **sidebar gained a fixed navigation layer** ("Conversas" and "Artefatos" as permanent entries, a pinned "Favoritos" section, and a reusable conversation context menu for favorite/rename/delete — see "Sidebar Navigation" under Product/Chat App Components).
scope: This document covers both the **marketing site** (claude.com — heroes, pricing, feature cards) and the **product/chat app** (NexusLocal — sidebar, chat canvas, message input). Tokens (colors, typography, spacing, radius) are shared; component sections are split by context. The product/chat app additionally defines a **semantic theming layer** (`theme.light.*` / `theme.dark.*`) so every chat-app component resolves its color through the active theme instead of a hardcoded surface, and a **sidebar navigation layer** (fixed entries + favorites + full-page Conversas/Artefatos views) documented alongside the existing chat canvas and message input components.

colors:
  primary: "#cc785c"
  primary-active: "#a9583e"
  primary-disabled: "#e6dfd8"
  ink: "#141413"
  body: "#3d3d3a"
  body-strong: "#252523"
  muted: "#6c6a64"
  muted-soft: "#8e8b82"
  hairline: "#e6dfd8"
  hairline-soft: "#ebe6df"
  canvas: "#faf9f5"
  surface-soft: "#f5f0e8"
  surface-card: "#efe9de"
  surface-cream-strong: "#e8e0d2"
  surface-dark: "#181715"
  surface-dark-elevated: "#252320"
  surface-dark-soft: "#1f1e1b"
  on-primary: "#ffffff"
  on-dark: "#faf9f5"
  on-dark-soft: "#a09d96"
  accent-teal: "#5db8a6"
  accent-amber: "#e8a55a"
  success: "#5db872"
  warning: "#d4a017"
  error: "#c64545"
  # --- New tokens added for Light/Dark theming of the product/chat app ---
  sidebar-light: "#f7f4ee"
  canvas-white: "#ffffff"
  border-light: "#e8e3da"
  surface-dark-input: "#2a2825"
  border-dark: "#33312d"
  canvas-dark: "#21201d"

theme:
  light:
    bg-sidebar: "{colors.sidebar-light}"
    bg-canvas: "{colors.canvas-white}"
    bg-card: "{colors.surface-card}"
    bg-input: "{colors.canvas-white}"
    bg-hover: "{colors.surface-soft}"
    text-primary: "{colors.ink}"
    text-secondary: "{colors.muted}"
    text-tertiary: "{colors.muted-soft}"
    border: "{colors.border-light}"
    accent: "{colors.primary}"
  dark:
    bg-sidebar: "{colors.surface-dark}"
    bg-canvas: "{colors.canvas-dark}"
    bg-card: "{colors.surface-dark-elevated}"
    bg-input: "{colors.surface-dark-input}"
    bg-hover: "{colors.surface-dark-elevated}"
    text-primary: "{colors.on-dark}"
    text-secondary: "{colors.on-dark-soft}"
    text-tertiary: "{colors.on-dark-soft}"
    border: "{colors.border-dark}"
    accent: "{colors.primary}"

typography:
  display-xl:
    fontFamily: "Copernicus, Tiempos Headline, serif"
    fontSize: 64px
    fontWeight: 400
    lineHeight: 1.05
    letterSpacing: -1.5px
  display-lg:
    fontFamily: "Copernicus, Tiempos Headline, serif"
    fontSize: 48px
    fontWeight: 400
    lineHeight: 1.1
    letterSpacing: -1px
  display-md:
    fontFamily: "Copernicus, Tiempos Headline, serif"
    fontSize: 36px
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: -0.5px
  display-sm:
    fontFamily: "Copernicus, Tiempos Headline, serif"
    fontSize: 28px
    fontWeight: 400
    lineHeight: 1.2
    letterSpacing: -0.3px
  title-lg:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 22px
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: 0
  title-md:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 18px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0
  title-sm:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 16px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0
  body-md:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0
  body-sm:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: 0
  caption:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0
  caption-uppercase:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 1.5px
  code:
    fontFamily: "JetBrains Mono, ui-monospace, monospace"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: 0
  button:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1
    letterSpacing: 0
  nav-link:
    fontFamily: "StyreneB, Inter, sans-serif"
    fontSize: 14px
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: 0

rounded:
  xs: 4px
  sm: 6px
  md: 8px
  lg: 12px
  xl: 16px
  pill: 9999px
  full: 9999px

spacing:
  xxs: 4px
  xs: 8px
  sm: 12px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
  section: 96px

components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 12px 20px
    height: 40px
  button-primary-active:
    backgroundColor: "{colors.primary-active}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  button-primary-disabled:
    backgroundColor: "{colors.primary-disabled}"
    textColor: "{colors.muted}"
    rounded: "{rounded.md}"
  button-secondary:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 12px 20px
    height: 40px
  button-secondary-on-dark:
    backgroundColor: "{colors.surface-dark-elevated}"
    textColor: "{colors.on-dark}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 12px 20px
  button-text-link:
    backgroundColor: transparent
    textColor: "{colors.ink}"
    typography: "{typography.button}"
  button-icon-circular:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.full}"
    size: 36px
  text-link:
    backgroundColor: transparent
    textColor: "{colors.primary}"
    typography: "{typography.body-md}"
  top-nav:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.nav-link}"
    height: 64px
  hero-band:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.display-xl}"
    padding: 96px
  hero-illustration-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.xl}"
  feature-card:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.title-md}"
    rounded: "{rounded.lg}"
    padding: 32px
  product-mockup-card-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-dark}"
    typography: "{typography.title-md}"
    rounded: "{rounded.lg}"
    padding: 32px
  code-window-card:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-dark}"
    typography: "{typography.code}"
    rounded: "{rounded.lg}"
    padding: 24px
  model-comparison-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.title-md}"
    rounded: "{rounded.lg}"
    padding: 32px
  pricing-tier-card:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.title-lg}"
    rounded: "{rounded.lg}"
    padding: 32px
  pricing-tier-card-featured:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-dark}"
    typography: "{typography.title-lg}"
    rounded: "{rounded.lg}"
    padding: 32px
  callout-card-coral:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.title-md}"
    rounded: "{rounded.lg}"
    padding: 32px
  connector-tile:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.title-sm}"
    rounded: "{rounded.lg}"
    padding: 20px
  text-input:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: 10px 14px
    height: 40px
  text-input-focused:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  cookie-consent-card:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-dark}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.lg}"
    padding: 24px
  category-tab:
    backgroundColor: transparent
    textColor: "{colors.muted}"
    typography: "{typography.nav-link}"
    padding: 8px 14px
    rounded: "{rounded.md}"
  category-tab-active:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.nav-link}"
    rounded: "{rounded.md}"
  badge-pill:
    backgroundColor: "{colors.surface-card}"
    textColor: "{colors.ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.pill}"
    padding: 4px 12px
  badge-coral:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.caption-uppercase}"
    rounded: "{rounded.pill}"
    padding: 4px 12px
  cta-band-coral:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.display-sm}"
    rounded: "{rounded.lg}"
    padding: 64px
  cta-band-dark:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-dark}"
    typography: "{typography.display-sm}"
    rounded: "{rounded.lg}"
    padding: 64px
  footer:
    backgroundColor: "{colors.surface-dark}"
    textColor: "{colors.on-dark-soft}"
    typography: "{typography.body-sm}"
    padding: 64px
---

## Overview

Claude.com is the warmest, most editorial interface in the AI-product category. The base atmosphere is a **tinted cream canvas** (`{colors.canvas}` — #faf9f5) — distinctly warm, deliberately not the cool gray-white that every other AI brand uses. Headlines run a **slab-serif display** ("Copernicus" / Tiempos Headline) at weight 400 with negative letter-spacing, paired with **StyreneB / Inter** body sans. The combination feels like a literary publication, not a SaaS marketing page.

Brand voltage comes from the **cream + coral pairing** — coral (`{colors.primary}` — #cc785c) is the signature Anthropic accent, used on every primary CTA, on the brand wordmark, and on full-bleed callout cards. The coral is warm, slightly muted, never cyan/blue — a deliberate counter-positioning against OpenAI's cool slate, Google's saturated blue, and Microsoft's corporate cyan.

The system has three surface modes that alternate page-by-page:
1. **Cream canvas** (`{colors.canvas}`) — default body floor
2. **Light cream cards** (`{colors.surface-card}`) — feature card backgrounds
3. **Dark navy product surfaces** (`{colors.surface-dark}`) — code editor mockups, model showcase cards, pre-footer CTAs, footer itself

The dark surfaces are where Claude shows its product chrome — code blocks, terminal output, model comparison tables, agentic-flow diagrams. The cream-to-dark contrast is the page's pacing rhythm.

**Key Characteristics:**
- Warm cream canvas (`{colors.canvas}` — #faf9f5) with dark warm-ink text (`{colors.ink}` — #141413). The brand's defining color choice.
- Coral primary CTA (`{colors.primary}` — #cc785c). Used scarcely on individual buttons, generously on full-bleed coral callout cards.
- Slab-serif display headlines via Copernicus / Tiempos Headline at weight 400 with negative letter-spacing. Pairs with humanist sans body for a literary editorial voice.
- Dark navy product mockup cards (`{colors.surface-dark}` — #181715) carrying code blocks, terminal panels, model comparison data — the brand shows the product chrome at scale rather than abstract marketing illustrations.
- Light cream feature cards (`{colors.surface-card}` — #efe9de) — slightly darker than canvas, used for content-driven feature explanations.
- Anthropic radial-spike mark — a small black asterisk-like glyph (4-spoke radial) — appears as the brand wordmark prefix and as a content marker.
- Border radius is hierarchical: `{rounded.md}` (8px) for buttons + inputs, `{rounded.lg}` (12px) for content + product cards, `{rounded.xl}` (16px) for the hero illustration container, `{rounded.pill}` for badges.
- Section rhythm `{spacing.section}` (96px) — modern-SaaS standard. Internal card padding stays generous at `{spacing.xl}` (32px).

## Colors

### Brand & Accent
- **Coral / Primary** (`{colors.primary}` — #cc785c): The signature Anthropic warm coral. Used on every primary CTA background, on full-bleed coral callout cards, on the brand wordmark accent. The most-recognized Anthropic color outside of the spike-mark logo.
- **Coral Active** (`{colors.primary-active}` — #a9583e): The press / hover-darker variant.
- **Coral Disabled** (`{colors.primary-disabled}` — #e6dfd8): A desaturated cream-tinted disabled state.
- **Accent Teal** (`{colors.accent-teal}` — #5db8a6): Used sparingly on secondary product surfaces (terminal status indicators, "active connection" dots in connectors page).
- **Accent Amber** (`{colors.accent-amber}` — #e8a55a): A small companion warm-tone used on category badges and inline highlights.

### Surface
- **Canvas** (`{colors.canvas}` — #faf9f5): The default page floor. Tinted cream — warm, deliberately not pure white.
- **Surface Soft** (`{colors.surface-soft}` — #f5f0e8): Section dividers, very-soft band backgrounds.
- **Surface Card** (`{colors.surface-card}` — #efe9de): Feature cards, content cards. One step darker than canvas.
- **Surface Cream Strong** (`{colors.surface-cream-strong}` — #e8e0d2): A strongest-cream variant used on selected category tabs and emphasized section bands.
- **Surface Dark** (`{colors.surface-dark}` — #181715): Code editor mockups, model showcase cards, footer. The dominant dark surface.
- **Surface Dark Elevated** (`{colors.surface-dark-elevated}` — #252320): Elevated cards inside dark bands (settings panels in mockups).
- **Surface Dark Soft** (`{colors.surface-dark-soft}` — #1f1e1b): Slightly lighter dark, used for code block backgrounds inside larger dark cards.
- **Hairline** (`{colors.hairline}` — #e6dfd8): The 1px border tone on cream surfaces. Same hex as `{colors.primary-disabled}` — borders feel like one elevation step rather than ink lines.
- **Hairline Soft** (`{colors.hairline-soft}` — #ebe6df): Barely-visible divider used inside the same band.

### Text
- **Ink** (`{colors.ink}` — #141413): All headlines and primary text. Warm dark, slightly off-pure-black.
- **Body Strong** (`{colors.body-strong}` — #252523): Emphasized paragraphs, lead text.
- **Body** (`{colors.body}` — #3d3d3a): Default running-text color.
- **Muted** (`{colors.muted}` — #6c6a64): Sub-headings, breadcrumbs, footer-adjacent secondary text.
- **Muted Soft** (`{colors.muted-soft}` — #8e8b82): Captions, fine-print, copyright lines.
- **On Primary** (`{colors.on-primary}` — #ffffff): Text on coral buttons.
- **On Dark** (`{colors.on-dark}` — #faf9f5): Cream-tinted white used on dark surfaces (echoes the canvas tone).
- **On Dark Soft** (`{colors.on-dark-soft}` — #a09d96): Footer body text, secondary labels in dark mockups.

### Semantic
- **Success** (`{colors.success}` — #5db872): Green status dots, "available" indicators.
- **Warning** (`{colors.warning}` — #d4a017): Warning callouts (rare on marketing surfaces).
- **Error** (`{colors.error}` — #c64545): Validation errors.

## Theme Modes (Light / Dark)

> Added in v-beta. This is the piece that was missing from the alpha spec: the alpha version hardcoded the sidebar to `{colors.surface-dark}` with no light counterpart, so there was no real "Light Mode" — only one fixed dark-sidebar/cream-canvas hybrid. The reference screenshot (claude.ai, light theme) shows the **real light mode**: sidebar and chat canvas are both light, distinguished from each other by a very subtle one-step elevation, not by a dark/light split.

### How theming works
Every chat-app component color now resolves through a **semantic token** (`{theme.light.*}` / `{theme.dark.*}`) instead of a raw palette color. The semantic layer maps to the same base palette in both directions — nothing in `colors:` was thrown away, dark mode still uses the existing navy tokens (`surface-dark`, `surface-dark-elevated`, `on-dark`, etc.), it's just addressed by role now (`bg-sidebar`, `text-primary`...) so a component can be written once and rendered in either mode.

### Light Mode (from the reference screenshot)
| Role | Token | Value | Notes |
|---|---|---|---|
| Sidebar background | `{theme.light.bg-sidebar}` | `#f7f4ee` (new: `{colors.sidebar-light}`) | A warm off-white, one step darker than the chat canvas — same elevation logic as `surface-card` vs `canvas`, just applied to the sidebar instead of only to feature cards. |
| Chat canvas background | `{theme.light.bg-canvas}` | `#ffffff` (new: `{colors.canvas-white}`) | The reference screenshot's main content area reads closer to pure white than the marketing site's tinted `{colors.canvas}` (#faf9f5) — product surfaces run slightly cooler/whiter than marketing pages. |
| Cards (chips, dropdowns, DESIGN.md file card) | `{theme.light.bg-card}` | `{colors.surface-card}` #efe9de | Unchanged from alpha spec. |
| Message input | `{theme.light.bg-input}` | `{colors.canvas-white}` #ffffff | White card with hairline border, matches the file-attachment card in the screenshot. |
| Hover state | `{theme.light.bg-hover}` | `{colors.surface-soft}` #f5f0e8 | Sidebar nav-item and recent-chat hover. |
| Primary text | `{theme.light.text-primary}` | `{colors.ink}` #141413 | Greeting, sidebar item labels. |
| Secondary text | `{theme.light.text-secondary}` | `{colors.muted}` #6c6a64 | "Fazer Upgrade", plan badge, section labels ("Recentes"). |
| Border / hairline | `{theme.light.border}` | new: `{colors.border-light}` #e8e3da | Slightly warmer/darker than `{colors.hairline}` so it stays visible against the whiter card backgrounds. |
| Accent | `{theme.light.accent}` | `{colors.primary}` #cc785c | Unchanged — the sun/spike-mark icon and "Fazer Upgrade" underline in the screenshot are this coral. |

### Dark Mode (existing alpha spec, now formalized as a mode rather than the only option)
| Role | Token | Value | Notes |
|---|---|---|---|
| Sidebar background | `{theme.dark.bg-sidebar}` | `{colors.surface-dark}` #181715 | Unchanged from alpha spec. |
| Chat canvas background | `{theme.dark.bg-canvas}` | new: `{colors.canvas-dark}` #21201d | **New token.** Alpha spec left the chat canvas cream even in the dark sidebar state, which isn't a true dark mode. This is one step lighter than the sidebar so the canvas still reads as the "floor" against the sidebar. |
| Cards (chips, dropdowns) | `{theme.dark.bg-card}` | `{colors.surface-dark-elevated}` #252320 | Unchanged. |
| Message input | `{theme.dark.bg-input}` | new: `{colors.surface-dark-input}` #2a2825 | **New token.** Slightly lighter than the card color so the input reads as the most "elevated" surface, mirroring the white input card in light mode. |
| Hover state | `{theme.dark.bg-hover}` | `{colors.surface-dark-elevated}` | Unchanged. |
| Primary text | `{theme.dark.text-primary}` | `{colors.on-dark}` #faf9f5 | Unchanged. |
| Secondary text | `{theme.dark.text-secondary}` | `{colors.on-dark-soft}` #a09d96 | Unchanged. |
| Border / hairline | `{theme.dark.border}` | new: `{colors.border-dark}` #33312d | **New token.** Alpha spec had no dark-mode border color; dropdowns/cards relied on background-color contrast alone. |
| Accent | `{theme.dark.accent}` | `{colors.primary}` #cc785c | The coral send-button / accent never changes between modes — it's the one constant brand signal. |

### Principles
- **The coral accent, typography choices, spacing, and radius scale never change between modes.** Only surface, text, and border colors swap. This keeps the brand recognizable regardless of theme.
- **Elevation logic stays consistent across modes:** sidebar is always one step "further" from the accent than the canvas; the input/card is always the most elevated surface. Light mode expresses this with white-vs-off-white; dark mode expresses it with three progressively lighter near-blacks.
- **Default mode:** Light, to match the reference screenshot and claude.ai's default. Dark remains available as a user preference.
- **Persistence:** theme choice should persist per-user (e.g. `localStorage.theme`) and default to `prefers-color-scheme` on first load if no stored preference exists.

### New Component: Theme Toggle
**`theme-toggle-button`** — Small icon button (sun/moon), lives in the sidebar footer near the user card or inside a settings menu. Size 32×32px, `{rounded.md}`, background transparent, hover `{theme.*.bg-hover}`. Icon color `{theme.*.text-secondary}`. Toggling swaps the active `{theme.*}` set app-wide; no page reload required.

## Typography

### Font Family
The system runs **Copernicus** (or **Tiempos Headline** as substitute) as the slab-serif display face for headlines, and **StyreneB** (or **Inter** as substitute) as the humanist sans for body, navigation, and UI labels. **JetBrains Mono** handles code blocks. The fallback stack walks `Tiempos Headline, Garamond, "Times New Roman", serif` for display and `Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif` for body.

The display/body split is editorial:
- Copernicus serif (weight 400, negative tracking) → h1, h2, h3, hero display
- StyreneB sans (weight 400-500) → body, navigation, buttons, captions, labels
- JetBrains Mono → all code blocks and terminal text

### Hierarchy

| Token | Size | Weight | Line Height | Letter Spacing | Use |
|---|---|---|---|---|---|
| `{typography.display-xl}` | 64px | 400 | 1.05 | -1.5px | Homepage h1 ("Meet your thinking partner") — Copernicus serif |
| `{typography.display-lg}` | 48px | 400 | 1.1 | -1px | Section heads — Copernicus |
| `{typography.display-md}` | 36px | 400 | 1.15 | -0.5px | Sub-section heads, model names — Copernicus |
| `{typography.display-sm}` | 28px | 400 | 1.2 | -0.3px | Pricing tier names, callout headlines — Copernicus |
| `{typography.title-lg}` | 22px | 500 | 1.3 | 0 | Pricing plan size labels — StyreneB |
| `{typography.title-md}` | 18px | 500 | 1.4 | 0 | Feature card titles, intro paragraphs |
| `{typography.title-sm}` | 16px | 500 | 1.4 | 0 | Connector tile titles, list labels |
| `{typography.body-md}` | 16px | 400 | 1.55 | 0 | Default running-text — StyreneB |
| `{typography.body-sm}` | 14px | 400 | 1.55 | 0 | Footer body, fine-print |
| `{typography.caption}` | 13px | 500 | 1.4 | 0 | Badge labels, captions |
| `{typography.caption-uppercase}` | 12px | 500 | 1.4 | 1.5px | Category tags, "NEW" badges |
| `{typography.code}` | 14px | 400 | 1.6 | 0 | Code blocks — JetBrains Mono |
| `{typography.button}` | 14px | 500 | 1.0 | 0 | Standard button labels |
| `{typography.nav-link}` | 14px | 500 | 1.4 | 0 | Top-nav menu items |

### Principles
Display sizes use weight 400 (regular), never bold. Negative letter-spacing (-0.3 to -1.5px) is essential — Copernicus without it reads as off-brand. The serif character is what gives Anthropic its literary, considered voice; switching to a sans-serif display would make Claude feel like every other AI tool.

Body type stays at weight 400 for paragraphs, weight 500 for labels and emphasized phrases. The sans body is humanist (StyreneB) — never geometric. Inter is an acceptable substitute because of its similar humanist proportions; Helvetica or Arial would be too neutral and break the warm-editorial feel.

### Note on Font Substitutes
If Copernicus / Tiempos Headline is unavailable, **Cormorant Garamond** at weight 500 with -0.02em letter-spacing is the closest open-source approximation. **EB Garamond** is a fallback. For StyreneB, **Inter** is the closest match — both are humanist sans designed for screen reading. **Söhne** is another close alternative if licensed.

### Typography Application in NexusLocal (Product/Chat App)

| NexusLocal Element | Token | Size | Weight | Line-height | Letter-spacing |
|---|---|---|---|---|---|
| Greeting "Boa noite, Osmar" | `display-sm` / `display-md` | 28-36px | 400 (serif) | 1.15-1.2 | -0.3 to -0.5px |
| Section titles (e.g., "Recentes") | `title-sm` | 16px | 500 (sans) | 1.4 | 0 |
| Chat input text | `body-md` | 16px | 400 | 1.55 | 0 |
| Input placeholder | `body-md` (color `muted`) | 16px | 400 | 1.55 | 0 |
| Button labels / chips | `button` | 14px | 500 | 1.0 | 0 |
| Sidebar items | `nav-link` | 14px | 500 | 1.4 | 0 |
| User plan badge ("plano Gratuito") | `caption` | 13px | 500 | 1.4 | 0 |

**Important:** Keep negative `letter-spacing` only for serif headlines; never use bold (700) on serif — Copernicus/Tiempos at 700 "reads as bombastic" per the design guide.

## Layout

### Spacing System
- **Base unit:** 4px.
- **Tokens:** `{spacing.xxs}` 4px · `{spacing.xs}` 8px · `{spacing.sm}` 12px · `{spacing.md}` 16px · `{spacing.lg}` 24px · `{spacing.xl}` 32px · `{spacing.xxl}` 48px · `{spacing.section}` 96px.
- **Section padding:** `{spacing.section}` (96px) — modern-SaaS rhythm.
- **Card internal padding:** `{spacing.xl}` (32px) for feature cards, pricing tier cards, model comparison cards; `{spacing.lg}` (24px) for code-window cards and connector tiles.
- **Callout / CTA bands:** `{spacing.xxl}` (48px) inside coral callout cards; 64px inside the larger dark CTA band.

### Grid & Container
- **Max content width:** ~1200px centered.
- **Editorial body:** Single 12-column grid; hero often uses 6/6 split (h1 left, illustration right).
- **Feature card grids:** 3-up at desktop, 2-up at tablet, 1-up at mobile.
- **Connector tile grids:** 4-up or 6-up at desktop, 2-up at tablet, 1-up at mobile.
- **Pricing grid:** 3-up at desktop (Free / Pro / Team / Enterprise often), 1-up at mobile.

### Whitespace Philosophy
The cream canvas + serif display + generous internal padding create an editorial pacing — Claude reads like a long-form magazine column rather than a marketing template. Whitespace between bands stays uniform at 96px; whitespace inside cards is generous (32px), letting type breathe.

## Elevation & Depth

| Level | Treatment | Use |
|---|---|---|
| Flat | No shadow, no border | Body sections, top nav, hero bands |
| Soft hairline | 1px `{colors.hairline}` border | Inputs, sub-nav, occasionally on cards |
| Cream card | `{colors.surface-card}` background — no shadow | Feature cards, content cards |
| Dark surface card | `{colors.surface-dark}` background — no shadow | Code editor mockups, model showcase cards |
| Subtle drop shadow | Faint shadow at low alpha | Hover-elevated states (the system uses `0 1px 3px rgba(20,20,19,0.08)` rarely) |

The elevation philosophy is **color-block first, shadow rare**. Most depth comes from the cream-vs-dark surface contrast. Shadows are minimal. The dark surface mockups have their own internal product chrome (code editor scrollbars, line numbers, syntax highlighting) which adds detail without needing external shadows.

### Decorative Depth
- The Anthropic spike-mark glyph (4-spoke radial asterisk) appears as a small black mark in the brand wordmark and inline as a content marker.
- Code editor mockups carry their own internal depth: syntax-highlighted text in muted blues / oranges / grays, line numbers in `{colors.muted-soft}`, status bars at the bottom in `{colors.surface-dark-elevated}`.
- Some hero illustrations use simple line-art with coral and dark-navy strokes on cream — minimal, hand-drawn-feeling, never photorealistic.

## Shapes

### Border Radius Scale

| Token | Value | Use |
|---|---|---|
| `{rounded.xs}` | 4px | Reserved for badge accents and tiny dropdowns |
| `{rounded.sm}` | 6px | Small inline buttons, dropdown items |
| `{rounded.md}` | 8px | Standard CTA buttons, text inputs, category tabs |
| `{rounded.lg}` | 12px | Content cards (feature, pricing, code-window, model-comparison) |
| `{rounded.xl}` | 16px | Hero illustration container, the larger marquee components |
| `{rounded.pill}` | 9999px | Badge pills, "NEW" tags |
| `{rounded.full}` | 9999px / 50% | Avatar substitutes, icon buttons |

### Photography & Illustrations
Claude's hero rarely uses photography. Instead it uses:
- Simple line-art illustrations with coral + dark-navy strokes on the cream canvas
- Code editor mockups (the dominant "hero" treatment on developer-focused pages)
- Terminal output mockups with monospace text on dark
- Model comparison cards (Opus / Sonnet / Haiku) with abstract geometric thumbnails

When photography is used (rare — mostly testimonials), avatars crop to perfect circles at 40px diameter.

## Components

### Product/Chat App Components (NexusLocal)

> These are the components for the **chat/product interface** (sidebar + chat canvas + message input), not the marketing site. They reuse the shared tokens above.

#### Sidebar

> **Theming note:** every color below is now expressed as `{theme.*}` (resolves to `{theme.light.*}` or `{theme.dark.*}` depending on active mode — see "Theme Modes" section above). The old alpha spec hardcoded these to the dark-mode values only; that mapping is preserved as the Dark Mode column, Light Mode is the new addition matching the reference screenshot.

**`sidebar`** — Left sidebar, full height, background `{theme.bg-sidebar}` (light: `#f7f4ee` · dark: `#181715`). No right border, or a barely-visible 1px `{theme.border}`. Contains, top to bottom: logo/wordmark + collapse button, "Novo bate-papo" ghost button, the two **fixed navigation items** (`sidebar-fixed-nav-item`: "Conversas", "Artefatos"), the dynamic "Favoritos" section (`sidebar-favorites-section`, renders only when it has content), the dynamic "Recentes" section (`sidebar-recent-section`), and the user card at the footer.

**`sidebar-new-chat-button`** — Ghost pill button at top of sidebar. Background transparent, text `{theme.text-primary}`, hover using `{theme.bg-hover}`. Icon + text, `{typography.nav-link}` (Inter 14px / 500).

**`sidebar-nav-item`** — Navigation items (Conversas, Projetos, etc.). Text `{theme.text-primary}`, icon to the left, hover background `{theme.bg-hover}`. `{typography.nav-link}` (Inter 14px / 500).

> **v-beta-2 addition — Sidebar Navigation (Conversas / Artefatos / Favoritos).** The alpha and beta specs treated "Conversas" and "Artefatos" as generic `sidebar-nav-item` entries with no defined destination. This version formalizes them as permanent, always-visible entries with their own full-page views, plus a pinned Favoritos section and a shared context menu — see the plan doc for the full implementation breakdown (`PLANO_SIDEBAR_CONVERSAS_ARTEFATOS.md`).

**`sidebar-fixed-nav-item`** — Extension of `sidebar-nav-item` used specifically for "Conversas" and "Artefatos", pinned immediately below `sidebar-new-chat-button` and above any dynamic section. Same base styling (`{theme.text-primary}`, icon left, `{typography.nav-link}`, hover `{theme.bg-hover}`), but additionally carries a **persistent selected state** — background stays `{theme.bg-hover}` for as long as its corresponding page (the "Conversas" list or the "Artefatos" grid) is the active view, not just on hover. Unlike `sidebar-nav-item`, it never scrolls out of a "Recentes"-style list — it's structural chrome, not content.

**`sidebar-favorites-section`** — "Favoritos" header + list, positioned between the fixed nav items and "Recentes". Same visual treatment as `sidebar-recent-section` (header in `{theme.text-secondary}`, `{typography.title-sm}`), but with two behavioral differences: (1) it **only renders when at least one conversation has `is_favorite: true`** — no empty-state placeholder, the section and its label disappear entirely rather than showing "Nenhum favorito"; (2) items are sorted by `favorited_at DESC` (most recently favorited first) rather than by conversation activity. Rows use `conversation-list-row`.

**`sidebar-recent-section`** — "Recentes" header in `{theme.text-secondary}`, list of recent conversation items with truncated text, "..." options button visible only on hover. Rows use `conversation-list-row` (shared with Favoritos and the full "Conversas" page).

**`conversation-list-row`** — Reusable row component for any list of conversations: sidebar "Recentes", sidebar "Favoritos", and the full-page "Conversas" view. Title truncates with `text-overflow: ellipsis` + native tooltip on hover, color `{theme.text-primary}`, `{typography.nav-link}` in the sidebar context / `{typography.body-md}` in the full-page context. Optional right-aligned relative timestamp ("há 3 horas", "ontem") in `{theme.text-tertiary}` — shown in the full-page list, omitted in the compact sidebar rows. The `•••` trigger (opens `conversation-context-menu`) is visible only on row hover inside the sidebar, but always visible in the full-page list where hover isn't guaranteed on touch devices.

**`conversation-context-menu`** — Dropdown opened by a row's `•••` trigger. Background `{theme.bg-card}`, border `{theme.border}`, `{rounded.lg}`, shadow matches `chat-model-selector-dropdown`'s recipe (`0 1px 3px rgba(20,20,19,0.08)` light / `0 1px 3px rgba(0,0,0,0.3)` dark). Three items, each `{typography.body-sm}`, hover `{theme.bg-hover}`:
1. **Favoritar** / **Desfavoritar** (label and `star-icon-toggle` state swap based on current `is_favorite`)
2. **Mudar o nome** — triggers inline rename (the row's title becomes an editable `<input>` in place; `Enter` saves, `Esc` cancels, blur auto-saves)
3. **Apagar** — text color `{colors.error}`, opens `confirm-delete-modal` rather than deleting immediately

**`star-icon-toggle`** — 16px star icon used inside `conversation-context-menu` (and optionally inline on a favorited row). Outline stroke in `{theme.text-secondary}` when inactive; filled `{colors.accent-amber}` when active (`is_favorite: true`). This is the one small departure from the coral-only-accent rule — amber reads as "starred/marked" without competing with the coral send-button signal.

**`confirm-delete-modal`** — Centered overlay modal for the "Apagar" action. Dark scrim behind, card `{theme.bg-card}`, `{rounded.lg}`, padding `{spacing.xl}`. Title `{typography.title-md}` ("Apagar esta conversa?"), body copy `{typography.body-md}` in `{theme.text-secondary}` ("Essa ação não pode ser desfeita."), button row: `{component.button-secondary}` ("Cancelar") + a destructive button (background `{colors.error}`, text white, same padding/height/radius as `button-primary`) labeled "Apagar". No destructive action in the system fires without passing through this pattern.

**`sidebar-user-card`** — Footer user card. Circular avatar (initial of name, background `{colors.primary}` / text `{colors.on-primary}` or theme-inverted), user name in `{theme.text-primary}`, plan badge below name (e.g., "plano Gratuito") in `{typography.caption}` (`{theme.text-secondary}`), chevron/expand icon to the right.

#### Chat Canvas

**`chat-canvas`** — Central chat area, background `{theme.bg-canvas}` (light: `#ffffff` · dark: `#21201d`, new token `{colors.canvas-dark}`). One elevation step lighter than the sidebar in both modes — the "floor" pattern.

**`chat-plan-badge`** — Small pill badge at top showing plan status (e.g., "plano Gratuito · Fazer Upgrade"). Background `{theme.bg-card}`, text `{theme.text-secondary}`, upgrade link in `{colors.primary}` (coral, underlined) — matches the reference screenshot exactly.

**`chat-greeting`** — Central greeting ("Boa noite, {nome}"). Brand mark/logo + serif display text using `{typography.display-sm}` or `{typography.display-md}` (Tiempos Headline / Cormorant Garamond, 28-36px, weight 400, letter-spacing -0.3 to -0.5px), color `{theme.text-primary}`. Name portion may be emphasized with a slightly stronger shade of `{theme.text-primary}`. Time-of-day aware (Bom dia / Boa tarde / Boa noite). The sun/spike-mark glyph beside the greeting renders in `{colors.primary}` (coral) in both modes.

**`chat-category-chips`** — Category suggestion pills (Escrever, Aprender, Código, Assuntos pessoais, Sugestões). Background `{theme.bg-card}`, text `{theme.text-primary}`, icon to left in `{theme.text-secondary}`, hover darkening one step further (`{colors.surface-cream-strong}` in light, `{colors.surface-dark-elevated}` in dark). Pill shape, `{typography.button}` (Inter 14px / 500).

#### Message Input

**`chat-input-card`** — Input container card, matches the "DESIGN.md" attachment-card look in the reference screenshot. Background `{theme.bg-input}` (light: `#ffffff` · dark: `#2a2825`, new token `{colors.surface-dark-input}`), large border-radius (~20px, `{rounded.xl}`), 1px `{theme.border}`. On focus: subtle shadow + slight highlight (not a thick coral ring). Shadow: `0 0.25rem 1.25rem rgba(0,0,0,3.5%)` at rest in light mode; dark mode uses a barely-there `0 0.25rem 1.25rem rgba(0,0,0,20%)` instead, since shadows read differently on dark surfaces.

**`chat-model-selector-button`** — Model selector button inside input. Shows current model name (e.g., "Sonnet 5") + optional variant suffix (e.g., "Médio") + chevron (▾). Height 32px, padding 0 10px, border-radius `{rounded.md}` (8px), `{typography.button}` (Inter 14px / 500), color `{theme.text-primary}`, background transparent. Hover: background `{theme.bg-hover}`. Variant text in `{theme.text-secondary}`.

**`chat-model-selector-dropdown`** — Dropdown menu listing **only models of the provider selected at the top**. Background `{theme.bg-card}`, items in `{typography.body-sm}` (14px), active item: background one step lighter/darker than the dropdown itself, text `{theme.text-primary}`, hover: `{theme.bg-hover}`. Border `{theme.border}` (1px), `{rounded.lg}` (12px), light shadow `0 1px 3px rgba(20,20,19,0.08)` in light mode / `0 1px 3px rgba(0,0,0,0.3)` in dark mode. Each item shows model name + short description in `{theme.text-secondary}`.

**`chat-send-button`** — The **only** element (besides upgrade CTA) where coral appears prominently, and it stays identical across both modes — the coral send button is a constant, mode-independent brand anchor. Background `{colors.primary}` (#cc785c), icon `{colors.on-primary}` (white), `{rounded.md}` (8px), pressed state `{colors.primary-active}` (#a9583e).

**`chat-input-attachments`** — Attachment/microphone/voice mode buttons. Icons in `{theme.text-secondary}`/`{theme.text-primary}`, hover with background `{theme.bg-hover}`, `{rounded.md}`.

#### User Name Variable

**`user-name`** — Centralized variable for user name (currently `USER_NAME = "Osmar"`). Used in greeting and sidebar user card avatar initial. When login is implemented, this variable comes from session/auth object (`user.name`) instead of a constant. Avatar shows first initial of this name.

#### Full-Page Views (v-beta-2)

> Destinations for the `sidebar-fixed-nav-item` entries. Both replace the chat canvas area while the sidebar stays put — they are not separate browser tabs or a route that hides the sidebar.

**`list-page-header`** — Shared header pattern for both the "Conversas" and "Artefatos" pages. Background `{theme.bg-canvas}`, title in `{typography.title-lg}`, primary action button (`{component.button-primary}`) top-right ("Novo bate-papo" / "Novo artefato"). The Conversas variant additionally carries a `Filtrar por [Todos ▾]` dropdown and a "Selecionar chats" secondary button to its left of the primary action.

**`list-page-search`** — Search input directly below the header, full-width, using `{component.text-input}` styling with a search icon prefix. Filters the list/grid below as the person types (debounced).

**`bulk-select-toolbar`** — Appears only when "Selecionar chats" is active on the Conversas page. Each `conversation-list-row` gains a checkbox on its left; a toolbar (docked top or bottom of the list) surfaces batch actions — "Favoritar selecionados", "Apagar selecionados" (the latter still routes through `confirm-delete-modal`, batch delete is not exempt from confirmation).

**`artifact-card`** — Grid card for the "Artefatos" page (3-up desktop / 2-up tablet / 1-up mobile, matching the system's standard grid collapse). Background `{theme.bg-card}`, `{rounded.lg}`, no shadow. Preview/thumbnail region at the top (or a centered placeholder glyph when no preview is available), with an optional view-count indicator (eye icon + number) overlaid on the preview's corner. Below the preview: filename in `{typography.title-sm}` / `{theme.text-primary}`, and a metadata line in `{typography.caption}` / `{theme.text-secondary}` combining relative edit time and a visibility `{component.badge-pill}` ("Publicado" / "Privado").

**`empty-state`** — Shared pattern for zero-content moments (no conversations, no artifacts, no search results, no favorites-in-full-page-context). Centered within the content area: a simple line-art or icon glyph in `{theme.text-tertiary}`, a one-line message in `{typography.title-sm}` / `{theme.text-primary}`, and an optional single CTA (`{component.button-secondary}`) when the empty state is actionable (e.g. "Criar primeiro artefato").

### Marketing Site Components (claude.com)

> These components are from the **marketing site** and do **not** apply to the NexusLocal product/chat app. They are documented here for reference only.

### Top Navigation

**`top-nav`** — Cream nav bar pinned to the top of every page. 64px tall, `{colors.canvas}` background. Carries the Anthropic spike-mark + "Claude" wordmark at left, primary horizontal menu (Product, Solutions, Use Cases, Pricing, Research, Company) center-left, right-side cluster with "Sign in" text-link, "Try Claude" `{component.button-primary}` (coral). Menu items in `{typography.nav-link}` (StyreneB 14px / 500).

### Buttons

**`button-primary`** — The signature coral CTA. Background `{colors.primary}` (#cc785c), text `{colors.on-primary}` (white), type `{typography.button}` (StyreneB 14px / 500), padding 12px × 20px, height 40px, rounded `{rounded.md}` (8px). Active state `button-primary-active` darkens to `{colors.primary-active}` (#a9583e).

**`button-secondary`** — Cream button with hairline outline. Background `{colors.canvas}`, text `{colors.ink}`, 1px hairline border, same padding + height + radius as primary.

**`button-secondary-on-dark`** — Used over `{colors.surface-dark}` cards. Background `{colors.surface-dark-elevated}` (#252320), text `{colors.on-dark}`. Stays dark — the system never inverts to a light secondary on dark surfaces.

**`button-text-link`** — Inline text button, no background. Used for "Sign in" in the top nav and inline CTA links.

**`button-icon-circular`** — 36px circular icon button. Background `{colors.canvas}`, hairline border, ink-color icon. Used for carousel arrows, share, "view more".

**`text-link`** — Inline body links in `{colors.primary}` (the coral). Underlined on press; the coral inline link is one of the system's most distinctive small details.

### Cards & Containers

**`hero-band`** — Cream-canvas hero with a 6-6 grid: h1 + sub-headline + button row on the left, hero illustration card or product mockup card on the right. Vertical padding `{spacing.section}` (96px).

**`hero-illustration-card`** — A larger card holding the hero's right-side artifact — sometimes a coral-stroke line illustration on cream background, sometimes a dark code editor mockup. Background `{colors.canvas}` or `{colors.surface-dark}` depending on context, rounded `{rounded.xl}` (16px).

**`feature-card`** — Used in 3-up feature grids. Background `{colors.surface-card}` (#efe9de — slightly darker cream), rounded `{rounded.lg}` (12px), internal padding `{spacing.xl}` (32px). Carries a small icon at top, an `{typography.title-md}` headline, and a body description in `{typography.body-md}`.

**`product-mockup-card-dark`** — Dark navy card showing actual Claude product chrome (chat interface, code editor, agent controls). Background `{colors.surface-dark}`, rounded `{rounded.lg}`, internal padding `{spacing.xl}` (32px). Carries text labels in `{colors.on-dark}` and product UI fragments below.

**`code-window-card`** — A specialized dark card showing a code editor with line numbers, syntax-highlighted code in `{typography.code}` (JetBrains Mono), and sometimes a "Run" button or terminal output panel below. Background `{colors.surface-dark}` with `{colors.surface-dark-soft}` for the inner code block, rounded `{rounded.lg}`, padding `{spacing.lg}` (24px). The signature visual element of Claude Code product pages.

**`model-comparison-card`** — Used on the homepage's "Which problem are you up against?" section comparing Opus / Sonnet / Haiku. Background `{colors.canvas}` with hairline border, rounded `{rounded.lg}`, internal padding `{spacing.xl}` (32px). Carries the model name, a short capability blurb, and a `{component.text-link}` to learn more.

**`pricing-tier-card`** — Standard tier card. Background `{colors.canvas}` with hairline border, rounded `{rounded.lg}`, padding `{spacing.xl}` (32px). Carries the plan name in `{typography.title-lg}` (StyreneB), price in `{typography.display-sm}` (Copernicus serif!), feature checklist in `{typography.body-md}`, and a `{component.button-primary}` at the bottom.

**`pricing-tier-card-featured`** — The featured tier (typically "Pro" or "Team"). Background flips to `{colors.surface-dark}`, text inverts to `{colors.on-dark}`. The dark surface IS the featured-tier signal.

**`callout-card-coral`** — A full-bleed coral card carrying a major call-to-action. Background `{colors.primary}` (#cc785c), text `{colors.on-primary}` (white), rounded `{rounded.lg}`, padding `{spacing.xxl}` (48px). The coral surface IS the voltage; the CTA inside uses an inverted button style (cream/canvas button on coral).

**`connector-tile`** — Used on the connectors page's integration grid. Background `{colors.canvas}` with hairline border, rounded `{rounded.lg}`, padding 20px. Each tile carries a logo at top, a `{typography.title-sm}` connector name, and a short description.

### Inputs & Forms

**`text-input`** — Standard text input. Background `{colors.canvas}`, text `{colors.ink}`, type `{typography.body-md}`, rounded `{rounded.md}` (8px), padding 10px × 14px, height 40px. 1px hairline border in `{colors.hairline}`.

**`text-input-focused`** — Focus state. Border thickens or shifts to `{colors.primary}` (coral) for emphasis. Carries a 3px coral-at-15%-alpha outer ring.

**`cookie-consent-card`** — Bottom-right floating dark cookie banner. Background `{colors.surface-dark}`, text `{colors.on-dark}`, rounded `{rounded.lg}`, padding `{spacing.lg}` (24px). One of the few places dark surface appears at small scale on cream pages.

### Tags / Badges

**`badge-pill`** — Small pill label used for category tags. Background `{colors.surface-card}`, text `{colors.ink}`, type `{typography.caption}` (13px / 500), rounded `{rounded.pill}`, padding 4px × 12px.

**`badge-coral`** — Coral-fill badge for "NEW", "BETA", featured highlights. Background `{colors.primary}`, text `{colors.on-primary}`, type `{typography.caption-uppercase}` (12px / 500 / 1.5px tracking), rounded `{rounded.pill}`, padding 4px × 12px.

### Tab / Filter

**`category-tab`** + **`category-tab-active`** — Used in sub-nav rows on solutions / connectors pages. Inactive: transparent background, `{colors.muted}` text. Active: `{colors.surface-card}` background, `{colors.ink}` text. Padding 8px × 14px, rounded `{rounded.md}`.

### CTA / Footer

**`cta-band-coral`** — A pre-footer "Try Claude" CTA card. Full-width coral fill, white type, rounded `{rounded.lg}`, padding 64px. Carries an h2 in `{typography.display-sm}` (still serif!), a sub-line, and a cream-button CTA.

**`cta-band-dark`** — Alternative pre-footer band on developer-focused pages. Background `{colors.surface-dark}`, text `{colors.on-dark}`, rounded `{rounded.lg}`, padding 64px. Often pairs with a code-window card.

**`footer`** — Dark navy footer that closes every page. Background `{colors.surface-dark}` (#181715), text `{colors.on-dark-soft}`. 4-column link list at desktop covering Product / Company / Resources / Legal. Vertical padding 64px. The Anthropic spike-mark + "Anthropic" wordmark sits at the top in `{colors.on-dark}`. The footer never inverts.

## Do's and Don'ts

### Do
- Anchor every page on the cream canvas. Pure white reads as "any other AI tool"; the warm tint is the brand differentiator.
- Use Copernicus serif for every display headline. Pair with StyreneB sans body. Negative letter-spacing on display sizes is non-negotiable.
- Reserve `{colors.primary}` (coral) for primary CTAs and full-bleed `{component.callout-card-coral}` moments. Don't paint accent moments coral elsewhere.
- Use `{component.product-mockup-card-dark}` and `{component.code-window-card}` to show actual Claude product chrome. Don't paint marketing illustrations of code when you can show real code.
- Pair `{component.feature-card}` (cream) with `{component.product-mockup-card-dark}` (navy) in alternating bands. The cream-to-dark rhythm is the brand's pacing mechanism.
- Use the Anthropic spike-mark glyph as the brand wordmark prefix. Never invert the mark to white-on-dark within the wordmark itself.
- Apply `{spacing.section}` (96px) between major bands.

### Don't
- Don't use cool grays or pure white for canvas. Cream is the brand.
- Don't bold serif display weight. Copernicus at 700 reads as bombastic; the system stays at 400.
- Don't use cool blue or saturated cyan as a brand accent. The coral is the brand voltage.
- Don't put coral everywhere. The coral is scarce on individual elements and generous only on full-bleed coral callout cards.
- Don't use Inter for display headlines. The serif character is the brand voice.
- Don't repeat the same surface mode in two consecutive bands. The pacing alternates: cream → cream-card → dark-mockup → cream → coral-callout → dark-footer.
- Don't add hover state styling beyond what the system already encodes — primary darkens on press; nothing else changes.

## Responsive Behavior

### Breakpoints

| Name | Width | Key Changes |
|---|---|---|
| Mobile | < 768px | Hamburger nav; hero h1 64→32px; hero-illustration-card stacks below content; feature grids 1-up; connector tiles 2-up; pricing 1-up; footer 4 cols → 1 |
| Tablet | 768–1024px | Top nav stays horizontal but tightens; feature cards 2-up; connector tiles 3-up; pricing 2-up |
| Desktop | 1024–1440px | Full top-nav with all menu items; 3-up feature cards; 4-up or 6-up connector tiles; 3-up pricing tiers |
| Wide | > 1440px | Same as desktop with more outer breathing room; max content width caps at 1200px |

### Touch Targets
- `{component.button-primary}` at minimum 40 × 40px.
- `{component.button-icon-circular}` at exactly 36 × 36 — slightly under WCAG 44 but visually centered.
- `{component.text-input}` height is 40px.
- Connector tile entire card area is tappable; effective tap area >> 44px.

### Collapsing Strategy
- Top nav collapses to hamburger at < 768px; menu opens as a full-screen cream sheet.
- Hero band's 6-6 grid collapses to single-column on mobile — h1 + sub-head + buttons first, then the illustration / mockup card below.
- Feature grids reduce columns rather than scaling cards down.
- Pricing tier cards collapse 4 → 2 → 1; featured-tier dark surface stays visually distinct at every breakpoint.
- Code-window cards retain code legibility at every breakpoint by allowing horizontal scroll within the card rather than wrapping code lines.

### Image Behavior
- Code blocks inside dark mockups stay at fixed font-size; horizontal scroll on mobile rather than wrapping.
- Hero illustrations scale proportionally; line-art strokes thin slightly on mobile.
- Avatar photos in testimonials crop to circles at every breakpoint.

## Iteration Guide

1. Focus on ONE component at a time. Reference its YAML key (`{component.feature-card}`, `{component.code-window-card}`).
2. Variants of an existing component (`-active`, `-disabled`, `-focused`) live as separate entries in `components:`.
3. Use `{token.refs}` everywhere — never inline hex.
4. Never document hover. Default and Active/Pressed states only.
5. Display headlines stay Copernicus serif 400 with negative tracking. Body stays StyreneB / Inter 400. The split is unbreakable.
6. Cream + coral + dark navy is the trinity. Don't introduce a fourth surface tone (no purple cards, no green sections).
7. When in doubt about emphasis: bigger Copernicus serif before bolder weight.

## Chat Message Hierarchy (v-beta-3)

> Added in v-beta-3. Formalizes the **visual hierarchy** of AI responses — addressing the gap where reasoning, response text, metadata, and actions all competed for attention at the same visual weight. The goal: the user should immediately identify (1) the main response, (2) the thinking block (optional), (3) metadata, (4) available actions.

### Typography Layers

| Layer | Size | Weight | Line-height | Opacity | Notes |
|---|---|---|---|---|---|
| **Resposta** (response body) | 16px | 400 | 1.7 | 100% | `font-sans` — primary content, maximum legibility |
| **Pensamento** (reasoning/thinking) | 13px | 500 | 1.5 | 65% | `font-body` — secondary, never competes with response |
| **Metadados** (timestamp, model, actions) | 12px | 400 | 1.4 | 55% | `font-body` — appears on hover only (last message always visible) |

### Visual Hierarchy Order

Inside each assistant message:
1. Cache/relay notices (if any) — top, badge style
2. **ThinkingBlock** — collapsed pill, expandable
3. **Response body** — main content, 16px/1.7
4. Artifact cards (if any)
5. **Metadata row** — horário · modelo · copiar (hover-only)

### ThinkingBlock Component

**`thinking-block`** — Universal reasoning display component, **model-agnostic**. Closed by default. Does not depend on any specific LLM output format.

**Visual spec:**
- Header always visible: `🧠 [status]` + chevron (rotates on open)
- Status: `"Pensando..."` (streaming) or `"Concluído"` (finished)
- Header font: 13px / 500 / opacity 65%
- Background: `{colors.surface-soft}` — one step above canvas, never matching the response body
- Border: `1px solid {colors.hairline-soft}` + `border-left: 2px solid {colors.hairline}` — discrete, not coral (neutral signal, not accent)
- Expand animation: CSS `grid-template-rows: 0fr → 1fr` — smooth, no layout jump
- Body: 13px / 1.5 line-height / `color: {colors.muted}` / `white-space: pre-wrap`
- Max body height: 400px with scroll

**Reasoning parser — Universal**

`parseReasoning(content: string)` recognizes and strips all reasoning wrappers automatically:

| Tag | LLM origin |
|---|---|
| `<think>` | DeepSeek R1, Qwen 3 thinking |
| `<thinking>` | Extended thinking models |
| `<reasoning>` | Generic reasoning models |
| `<analysis>` | Analysis-oriented models |
| `<reflection>` | Reflection-tuned models |
| `<assistant_thought>` | Internal/custom formats |

All formats are unified into a single `{ thinking, response, isThinking }` object. The component never changes when a new model/format is added — only the parser regex list is extended.

### Layout Constraints

- **Content max-width:** 760px (reduced from 780px for tighter line length)
- **Message vertical padding:** 16px (increased from 12px for breathing room)
- **Input card border-radius:** 24px (increased from 20px — closer to Claude.ai)
- **Input card padding:** `2px` wrap + `14px 18px` textarea (more spacious)
- **Sidebar conv-item active state:** `border-left: 2px solid {colors.primary}` — coral left accent as selected indicator
- **Sidebar group labels:** `10.5px / 600 / 0.7px tracking / opacity 70%` — more refined, less heavy

### Input Card (Updated)

**`chat-input-card`** (updated from v-beta):
- `border-radius: 24px` (increased from 20px)
- `padding: 2px` outer wrap (creates visual breathing room)
- `textarea border-radius: 18px` (inner follows the outer rounding)
- Light mode shadow: `0 1px 8px rgba(20,20,19,0.07)` — very subtle, editorial
- Dark mode shadow: `0 0.25rem 1rem rgba(0,0,0,0.28)` — warmer tone, less heavy than before

## Known Gaps

- Copernicus and StyreneB are licensed Anthropic typefaces and not available as public web fonts. Substitutes (Tiempos Headline / Cormorant Garamond / EB Garamond for serif; Inter / Söhne for sans) are documented in the typography section.
- The Anthropic radial-spike-mark is a brand glyph rendered as inline SVG; it's not formalized as a system token here. Treat it as a logo asset.
- Animation and transition timings (chat message reveal, code block typewriter effect on the homepage, agentic-flow diagram animations) are not in scope, including the theme-toggle transition itself (recommend a simple 150-200ms `background-color`/`color` cross-fade, no layout shift).
- Form validation states beyond `{component.text-input-focused}` are not extracted — error / success states would need a sign-up or feedback flow to confirm, and haven't been re-verified against dark mode.
- The new light-mode sidebar/canvas hex values (`sidebar-light`, `canvas-white`, `border-light`) and the new dark-mode canvas/input values (`canvas-dark`, `surface-dark-input`, `border-dark`) are estimated from the reference screenshot at normal viewing resolution — worth a pixel-sample pass against a live claude.ai session (light) and a dark-mode screenshot (not yet supplied) to confirm exact hex values before shipping.
- The v-beta-2 sidebar-navigation components (`sidebar-fixed-nav-item`, `sidebar-favorites-section`, `conversation-context-menu`, `confirm-delete-modal`, `artifact-card`) are documented at the visual/token level only; data-model and API details (favoriting, renaming, deleting, list pagination) live in the separate implementation plan (`PLANO_SIDEBAR_CONVERSAS_ARTEFATOS.md`), not in this file.
- Batch-action toolbar (`bulk-select-toolbar`) interaction details — whether it docks top or bottom, and its exact button set beyond "Favoritar selecionados" / "Apagar selecionados" — are a first pass and may need revision once wired up.

## NexusLocal Implementation Notes

### What DOES Apply to NexusLocal (Product/Chat App)
- **All color tokens** from the `colors:` section — these are the shared design system palette.
- **All typography tokens** — applied to chat app elements as documented in "Typography Application in NexusLocal" above.
- **All spacing and radius tokens** — reused for chat input card, sidebar items, chips, buttons.
- **Product/Chat App Components** section — sidebar, chat canvas, message input, model selector, send button, user card.

### What DOES NOT Apply to NexusLocal
The following `DESIGN.md` components are from the **claude.com marketing site** and should **not** be replicated in the NexusLocal chat/product app:

- `top-nav` with menu "Product, Solutions, Use Cases, Pricing, Research, Company"
- `hero-band`, `hero-illustration-card`
- `feature-card` (marketing feature cards in 3-up grids)
- `pricing-tier-card`, `pricing-tier-card-featured`
- `callout-card-coral`, `cta-band-coral`, `cta-band-dark`
- `model-comparison-card` (Opus / Sonnet / Haiku marketing cards)
- `connector-tile`
- `cookie-consent-card`
- `footer` (4-column marketing footer)

From these marketing-only components, we only reuse the **shared tokens** (colors, typography, spacing, radius), not the component structures themselves.

### Implementation Checklist for NexusLocal
- [ ] Update `index.html` / font file: keep Inter (300/400/500/600) and add serif fallback (`Cormorant Garamond` or `EB Garamond`) via Google Fonts for headlines.
- [ ] Create/update theme token file (`theme.css` or `tailwind.config`) with **both** `theme.light.*` and `theme.dark.*` sets from the "Theme Modes" section — expose each as a CSS custom property (e.g. `--bg-sidebar`, `--bg-canvas`, `--text-primary`) so components never reference raw hex.
- [ ] Add a `data-theme="light" | "dark"` attribute on `<html>` (or a `.dark` class toggle) and scope the two token sets under it, e.g. `:root[data-theme="light"] { --bg-sidebar: #f7f4ee; ... }` / `:root[data-theme="dark"] { --bg-sidebar: #181715; ... }`.
- [ ] Build `theme-toggle-button` (sun/moon icon) — on click, flips `data-theme` and writes the choice to `localStorage.theme`.
- [ ] On first load with no stored preference, initialize from `window.matchMedia('(prefers-color-scheme: dark)')`.
- [ ] Sidebar: bind background/text to `var(--bg-sidebar)` / `var(--text-primary)` instead of hardcoded dark values.
- [ ] Chat canvas: bind background to `var(--bg-canvas)`, text to `var(--text-primary)` / `var(--text-secondary)`.
- [ ] Chat input card + model dropdown: bind to `var(--bg-input)` / `var(--bg-card)` and `var(--border)`.
- [ ] Greeting: change font to serif, apply negative `letter-spacing`, use centralized user name variable, color bound to `var(--text-primary)`.
- [ ] Suggestion chips: pill style bound to `var(--bg-card)`.
- [ ] Chat input: apply large radius, subtle shadow (shadow opacity should differ between modes — see `chat-input-card` notes), keep provider selector at top intact.
- [ ] Replace fixed model selector inside input with provider-dependent model selector.
- [ ] Send button: the only coral-highlighted element — stays `{colors.primary}` in both modes, does **not** bind to theme tokens.
- [ ] Review accessibility contrast for both modes: `{theme.light.text-secondary}` (#6c6a64) on `{theme.light.bg-canvas}` (#ffffff), and `{theme.dark.text-secondary}` (#a09d96) on `{theme.dark.bg-canvas}` (#21201d), before finalizing.
- [ ] Sidebar navigation (v-beta-2): pin "Conversas" and "Artefatos" as `sidebar-fixed-nav-item` directly below "Novo bate-papo"; build the "Conversas" (`list-page-header` + `list-page-search` + `conversation-list-row` list + `bulk-select-toolbar`) and "Artefatos" (`list-page-header` + `list-page-search` + `artifact-card` grid) full-page views.
- [ ] Add `conversation-context-menu` (`•••`) to every `conversation-list-row`, with Favoritar/Desfavoritar, Mudar o nome (inline rename), and Apagar (routes through `confirm-delete-modal`, never deletes directly).
- [ ] Add `sidebar-favorites-section` between the fixed nav items and "Recentes" — conditionally rendered, sorted by `favorited_at DESC`, using the same `conversation-list-row` component as Recentes.
- [ ] Full data-model, API endpoint, and QA-edge-case breakdown for this feature lives in `PLANO_SIDEBAR_CONVERSAS_ARTEFATOS.md` — follow its phase order (backend → context menu → favorites section → fixed nav items → full pages).
