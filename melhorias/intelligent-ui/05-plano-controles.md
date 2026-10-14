# Controles — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** O usuário ajusta um valor ou dispara um pedido sem redigitar, e nada acontece antes do clique.

**Architecture:** `ControlsCard` renderiza fields e um botão. A ação é só `send_message` ou `set_model`. As duas já têm caminho no app: envio de chat e `selectModel`. Nome fora dessa lista morre em `validate_envelope`, no backend.

**Tech Stack:** React 18, Zustand (`useStore`).

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md` seção 4.4.

**Estado (correções 2026-10-14):** implementado nas Tasks 1–4. `set_model` agora lista `models` do store (valor interno `provider_id::id`, rótulo `display_name · provider_name`), pré-seleciona o modelo atual, some com `models` vazio e mostra `intelligentUi.modelNotInList` se o id não existir. Também: `text` com `maxLength=200`, `number`/`range` cortados em `[min, max]`, `label htmlFor`/`id`, `aria-live` no resultado calculado, `role="alert"` no erro, seletores pontuais do store (sem re-render por token).

## Global Constraints

- Sem auto-submit no fim do stream.
- Uma ação por bloco.
- `set_model` ignora opções do modelo e lista `models` do store. Id fora da lista não chama `selectModel`.
- `send_message` interpola e envia pelo caminho atual do composer. A bolha do usuário mostra o texto final.
- Alvo de toque mínimo 44×44 px.
- Não abrir URL, não rodar código, não mudar chave, não apagar conversa.

---

### Task 1: Fields sem ação (text, select, number e range/slider)

**Files:**
- Create: `frontend/src/ui/components/ControlsCard.tsx`
- Modify: `frontend/src/ui/DynamicRenderer.tsx`

**Interfaces:**
- Produces: fields `text`, `select`, `number` e `range` (slider com min, max e step) controlados em state local do componente. `number` e `range` cortam para `[min, max]`.

- [ ] **Step 1: Teste.** Select mostra as options do bloco. Number e range cortam para o intervalo `[min, max]`. Range exibe o valor atual ao lado do slider. *(**Pendente** como teste de render. Observação de código: `range` corta naturalmente; `number` só tem `min`/`max` como atributos do input, sem corte em JS; `text` não aplica `maxLength={200}`.)*

- [x] **Step 2: Implementar os quatro kinds. Botão ainda não envia. Label do botão é `submit_label`.** *(`frontend/src/ui/components/ControlsCard.tsx`: `text`, `number`, `range` (com valor ao lado) e `select` em state local; botão com `minHeight: 44px`.)*

- [x] **Step 3: Strings e i18n.** *(`intelligentUi.controlsSubmitDefault`, `controlsSelectPlaceholder`, `controlsError` e `computedResult` nos três locales. `controlsSelectPlaceholder` e `controlsError` ainda não são usados pelo componente.)* Incluir chaves de internacionalização em `pt-BR.json`, `en-US.json` e `es-ES.json` (`intelligentUi.controlsSubmitDefault`, `intelligentUi.controlsSelectPlaceholder`, `intelligentUi.controlsError`).

- [x] **Step 4: Commit** `feat: fields de controle e slider na bolha com i18n, sem disparo`

### Task 2: send_message

**Files:**
- Modify: `ControlsCard.tsx`
- Modify: nenhum cliente WS novo. `MessageInput` recebe `onSend={sendMessage}` de `ChatWindow.tsx`. O contexto é `useChatContext()` em `frontend/src/context/ChatContext.tsx`, método `sendMessage(text: string, displayText?: string)`. `ControlsCard` chama esse método. `MessageBubble` já está dentro de `ChatProvider`, porque `ChatWindow` usa o mesmo hook.

**Interfaces:**
- Consumes: template com `{field_id}`
- Produces: no clique, string interpolada. Placeholder sem field já foi barrado na fase 1. Valor de select entra como o `value`, não como o label.

- [ ] **Step 1: Teste da interpolação pura, sem WS.** *(**Pendente.** A interpolação está inline em `handleSubmit` (`split('{id}').join(valor)`), não é função pura exportada nem tem teste.)* Template `Execute {agente}` com agente `seo` vira `Execute seo`.

- [x] **Step 2: Ligar o botão ao envio existente.** *(`useChatContext().sendMessage(msg)`; `submitted` desabilita campos e botão após o clique; nada dispara no `stream_end`.)* Depois do clique, desabilitar o botão deste bloco para não mandar duas vezes. Novo turno pode trazer outro bloco.

- [x] **Step 3: Commit** `feat: controle envia follow-up pelo composer`

### Task 3: set_model

**Files:**
- Modify: `ControlsCard.tsx`

**Interfaces:**
- Consumes: `selectModel(modelId, providerId)` e `models` de `useStore.ts`
- Produces: select preenchido pelo host. Clique chama `selectModel` só se o par existir em `models`.

- [ ] **Step 1: Teste.** Options do JSON são ignoradas. A lista visível é a do store. Id `nao-existe` não chama `selectModel`. *(**Pendente.** Sem teste; e a lista visível ainda é a do JSON.)*

- [x] **Step 2: Implementar.** Se `models` estiver vazio, não renderizar o bloco `set_model`. *(Feito 2026-10-14 em `ControlsCard.tsx`: `<select>` preenchido com `models` do store (options do JSON ignoradas), `return null` com lista vazia, `intelligentUi.modelNotInList` quando o id não bate.)*

- [ ] **Step 3: Commit** `feat: controle troca modelo só entre os já habilitados` *(Aguarda o Step 2.)*

### Task 4: Reatividade local (Calculadora reativa e live computation)

Modelado a partir do *Bill Splitter* do OpenIntelligentUI ("Split a bill with controls for total, tip and group size. Calculations update as you change the inputs").

**Files:**
- Create: `frontend/src/ui/lib/safeMath.ts`
- Modify: `ControlsCard.tsx`

**Interfaces:**
- Consumes: opcional `computed: { template: string, formula: string }` no bloco de controls.
- Produces: parser aritmético recursivo seguro (operações `+`, `-`, `*`, `/`, `()`, estritamente números, sem `eval`), atualizando o badge de resultado em tempo real conforme o usuário altera os campos ou arrasta sliders. O resultado também fica disponível como `{resultado}` no template do `send_message`.

- [x] **Step 1: Teste de `safeMath`.** *(`frontend/src/ui/lib/safeMath.test.ts`: precedência, parênteses, substituição de variáveis, rejeição de `console.log`/`alert`/`process.exit`, divisão por zero. Passa.)* Valida precedência de operadores e substituição de variáveis numéricas. Rejeita qualquer caractere não aritmético.
- [x] **Step 2: Ligar ao `ControlsCard`.** *(`useMemo` recalcula `evaluateSafeFormula` a cada mudança de campo; badge com `computed.template`; `{resultado}` também é interpolado no `send_message`. Parser recursivo sem `eval`/`Function`, só `+ - * / ( )` e números.)* Exibe card reativo com visualização imediata do cálculo antes do clique.
- [x] **Step 3: Commit** `feat: calculadora reativa e live computation no ControlsCard`

