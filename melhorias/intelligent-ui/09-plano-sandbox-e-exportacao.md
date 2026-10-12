# Sandbox e Exportação Standalone — plano (Fase 7)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Executar micro-ferramentas dinâmicas geradas sob demanda (Nível 2 — Open Generative UI) em sandbox isolado, com injeção dos design tokens do Multi+, comunicação bidirecional segura e exportação standalone com 1 clique (inspirado no [CopilotKit Open Intelligent UI](https://github.com/CopilotKit/OpenIntelligentUI)).

**Architecture:** `SandboxCard` renderiza um `<iframe>` com atributos de segurança restritos (`allow-scripts allow-forms`, sem `allow-same-origin`). O host injeta as variáveis CSS de tema (`themeBridge.ts`) e reserva a altura vertical imediata (`initial_height`) para garantir zero layout shift (CLS). Interações locais rodam em JS puro no sandbox; se o usuário aciona um botão de ação, o sandbox dispara `postMessage` capturado e validado pelo host, integrando-se ao WebSocket de chat existente.

**Tech Stack:** React 18, TypeScript, Vanilla CSS Tokens, PostMessage Bridge.

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md` seções 4.5 e 7; `melhorias/intelligent-ui/08-open-intelligent-ui-referencia.md`.
**Código-base de referência já extraído:** `melhorias/intelligent-ui/referencias-codigo/` (`sandbox-core.ts`, `design-tokens-bridge.ts`, `export-standalone.ts`).

## Global Constraints

- **Segurança Absoluta:** O iframe NUNCA deve conter `allow-same-origin`. Zero acesso a cookies, tokens de sessão ou `localStorage` do host.
- **Zero Layout Shift:** Altura reservada (`initial_height`) imediatamente no wrapper externo para evitar saltos durante o streaming.
- **Harmonia Visual:** Injeção automática das variáveis CSS de `frontend/src/index.css` (`--primary`, `--surface-card`, `--ink`, etc.) e classe de tema `.dark` / `.light`.
- **Ações Autorizadas:** O host só processa mensagens com schema `{ type: 'nexus_action', action: 'send_message', text: string }`. Ações arbitrárias são ignoradas.
- **Exportação Standalone:** O botão de exportação empacota HTML, CSS e JS em um único arquivo `.html` autônomo baixável.
- **Aproveitamento de Código:** Não reescrever do zero; importar ou basear-se diretamente nos módulos pré-estruturados em `referencias-codigo/`.

---

### Task 1: Componente `SandboxCard` com Isolamento e Altura Reservada

**Files:**
- Create: `frontend/src/ui/components/SandboxCard.tsx`
- Modify: `frontend/src/ui/DynamicRenderer.tsx`

**Interfaces:**
- Produces: Renderização de `<iframe>` seguro com `sandbox="allow-scripts allow-forms"`, dimensões controladas e indicador de carregamento (placeholder).

- [ ] **Step 1: Teste.** Valida que o container aplica a altura de `initial_height` (com fallback de 300px) e os atributos restritos de sandbox.
- [ ] **Step 2: Implementar `SandboxCard.tsx` com `srcDoc` gerado e wrapper CSS com `overflow: hidden` e `border-radius: var(--radius-md)`.**
- [ ] **Step 3: Conectar no `DynamicRenderer.tsx` via `React.lazy`.**
- [ ] **Step 4: Commit** `feat: componente SandboxCard com iframe isolado e altura reservada`

---

### Task 2: Injeção de Design Tokens (`themeBridge.ts`)

**Files:**
- Create: `frontend/src/ui/themeBridge.ts`
- Modify: `frontend/src/ui/components/SandboxCard.tsx`

**Interfaces:**
- Produces: `injectThemeTokens(html: string, isDark: boolean): string`.
- Injeta uma folha de estilo `<style id="nexus-theme-bridge">` no `<head>` do documento interno com todas as variáveis ativas do Multi+ (`--primary`, `--surface-card`, `--ink`, `--body`, `--hairline`, fontes do sistema e background).

- [ ] **Step 1: Teste.** Valida que o HTML resultante contém o bloco de estilo injetado e a classe correspondente (`dark` ou `light`) no nó `<html>`.
- [ ] **Step 2: Implementar `injectThemeTokens` lendo as variáveis computadas ou tokens padrão de `index.css`.**
- [ ] **Step 3: Commit** `feat: theme bridge para harmonização visual de ferramentas em sandbox`

---

### Task 3: Host-Sandbox Bridge Bidirecional (`postMessage`)

**Files:**
- Modify: `frontend/src/ui/components/SandboxCard.tsx`

**Interfaces:**
- Consumes: `useChatContext().sendMessage`
- Produces: Listener de evento `message` validando a origem e o schema `{ type: 'nexus_action', action: 'send_message', text: string }`.

- [ ] **Step 1: Teste.** Simula mensagem de postMessage válida e verifica a chamada de `sendMessage`. Mensagens inválidas ou de tipo desconhecido não disparam nada.
- [ ] **Step 2: Implementar listener com limpeza no `useEffect` unmount do componente.**
- [ ] **Step 3: Commit** `feat: bridge bidirecional postMessage para ferramentas em sandbox`

---

### Task 4: Exportação Standalone 1-Click

**Files:**
- Create: `frontend/src/ui/lib/exportStandalone.ts`
- Modify: `frontend/src/ui/components/SandboxCard.tsx`

**Interfaces:**
- Produces: Função `downloadStandaloneHtml(title: string, html: string, css: string, js: string)` que gera um Blob do tipo `text/html;charset=utf-8` e dispara o download automático no browser com o nome `[title].html`.

- [ ] **Step 1: Teste.** Valida a montagem do documento completo e a inclusão das tags corretas.
- [ ] **Step 2: Adicionar botão de download discreto no cabeçalho do `SandboxCard`.**
- [ ] **Step 3: Strings e i18n.** Incluir chaves de internacionalização para os botões e tooltips de exportação em `pt-BR.json`, `en-US.json` e `es-ES.json` (`intelligentUi.exportStandalone`, `intelligentUi.exportTooltip`).
- [ ] **Step 4: Commit** `feat: exportação standalone 1-click para ferramentas sob demanda com i18n`
