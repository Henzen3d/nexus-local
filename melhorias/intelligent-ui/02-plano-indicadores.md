# Indicadores e barras — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar barra e lista de etapas na bolha, a partir de bloco `progress` já validado.

**Architecture:** `DynamicRenderer` lê `message.ui_blocks`. `ProgressCard` e `ChecklistCard` só recebem objeto já válido. O host pode atualizar o mesmo `id` com `ui_progress` enquanto o turno corre. Sem SSE.

**Tech Stack:** React 18, tokens em `frontend/src/index.css`. Sem biblioteca nova.

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md` seções 4.1, 5 e 7.

## Global Constraints

- Flag off: `DynamicRenderer` retorna null mesmo se houver payload.
- Não substituir `FusionStatusCard` nem `AIStatusIndicator`.
- Sem animação quando `prefers-reduced-motion: reduce`.
- `role="progressbar"` com valores numéricos quando `value` e `max` existem. Sem eles, não usar progressbar; usar lista de steps.
- Texto via nó React, nunca HTML do modelo.
- Catálogo da spec, seção 8, injetado só com flag on e heurístico verdadeiro.

---

### Task 1: Componente

**Files:**
- Create: `frontend/src/ui/components/ProgressCard.tsx`
- Create: `frontend/src/ui/components/ChecklistCard.tsx`
- Create: `frontend/src/ui/DynamicRenderer.tsx`
- Modify: `frontend/src/components/MessageBubble.tsx` — um nó depois do markdown, só se `ui_blocks` existir.

**Interfaces:**
- Consumes: `UiEnvelope` de `frontend/src/lib/nexusUi.ts`
- Produces: `ProgressCard` quando há `value` e `max`. `ChecklistCard` quando há `steps`. `DynamicRenderer` ignora tipo sem cartão e não quebra. Os dois cartões são `React.lazy`. Sem import estático deles em `MessageBubble`.

- [ ] **Step 1: Teste de render do label e da fração.** "Auditoria SEO" e "7 de 10" aparecem quando `value` é 7 e `max` é 10. Sem `value`, a fração não aparece e os steps aparecem.

- [ ] **Step 2: Implementar.** Largura da barra: `(value / max) * 100` por cento, teto 100. Cor da trilha: `--hairline`. Cor do preenchimento: `--primary`. Step `error`: `--error`. Step `done`: `--success`. Step `active`: `--primary`. Fundo: `--surface-card`.

- [ ] **Step 3: Encaixar `DynamicRenderer` em `MessageBubble` abaixo do markdown, não no lugar dele.** Sem canal SSE. Atualização de barra chega no WebSocket já aberto.

- [ ] **Step 4: Commit** `feat: pintar bloco progress na bolha`

### Task 2: Evento do host

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/store/useStore.ts`
- Modify: `backend/routers/chat.py` apenas se já existir um ponto de fase (Fusion ou busca) barato de espelhar. Se o espelho custar refactor do Fusion, não fazer. Nesta fase o evento basta ser aceito e testado com um payload manual.

**Interfaces:**
- Produces: handler de `{ type: 'ui_progress', block }` que substitui o bloco de mesmo `id` na mensagem em stream. `source` gravado como `host` se persistir.

- [ ] **Step 1: Teste do store.** Dois eventos com o mesmo `id`: o segundo valor substitui o primeiro. Id novo acrescenta, até o teto de 4. O quinto é ignorado.

- [ ] **Step 2: Implementar o handler. Não emitir `ui_progress` a partir de token do modelo.**

- [ ] **Step 3: Commit** `feat: aceitar ui_progress do host`

### Task 3: Catálogo condicional

**Files:**
- Create: `backend/ui_blocks/catalog.txt` com o texto literal da spec, seção 8.
- Create: `backend/ui_blocks/should_offer.py`
- Modify: `backend/routers/chat.py`, depois de `resolve_project_context` (por volta da linha 191) e antes de `history = [{"role": "system", "content": system_instruction}] + history` (linha 197). Acrescentar o catálogo em `system_instruction`. Não criar outro system prompt.

**Interfaces:**
- Produces: `should_offer_ui(user_text: str) -> bool` com as duas regras da spec, seção 8.

- [ ] **Step 1: Testes do heurístico.** "compare os custos" retorna true. "bom dia" retorna false. Três números mais a palavra custo retorna true.

- [ ] **Step 2: Injetar o arquivo só se flag on e `should_offer_ui` true.** Medir `len(catalog) / 4`. Se passar de 400, não injetar.

- [ ] **Step 3: Commit** `feat: oferecer catálogo nexus-ui só quando o turno pede visual`
