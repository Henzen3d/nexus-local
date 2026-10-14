# Indicadores e barras — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar barra e lista de etapas na bolha, a partir de bloco `progress` já validado.

**Architecture:** `DynamicRenderer` lê `message.ui_blocks`. `ProgressCard` e `ChecklistCard` só recebem objeto já válido. O host pode atualizar o mesmo `id` com `ui_progress` enquanto o turno corre. Sem SSE.

**Tech Stack:** React 18, tokens em `frontend/src/index.css`. Sem biblioteca nova.

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md` seções 4.1, 5 e 7.

**Estado (correções 2026-10-14):** implementado. Gate da flag fechado (`DynamicRenderer` devolve `null` sem `intelligentUiConfig.enabled`); `Suspense` com skeleton que reserva a altura do bloco (Zero CLS); `prefers-reduced-motion` em `index.css`. Pendência: testes de render/store dos cartões.

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

- [ ] **Step 1: Teste de render do label e da fração.** *(**Pendente.** Não há teste de componente React no projeto; só o validador é testado.)* "Auditoria SEO" e "7 de 10" aparecem quando `value` é 7 e `max` é 10. Sem `value`, a fração não aparece e os steps aparecem.

- [x] **Step 2: Implementar.** *(`frontend/src/ui/components/ProgressCard.tsx` e `ChecklistCard.tsx`: tokens exatamente como listados; `role="progressbar"` com `aria-valuenow/min/max/label`; lista com `role="list"`.)* Largura da barra: `(value / max) * 100` por cento, teto 100. Cor da trilha: `--hairline`. Cor do preenchimento: `--primary`. Step `error`: `--error`. Step `done`: `--success`. Step `active`: `--primary`. Fundo: `--surface-card`.

- [x] **Step 3: Encaixar `DynamicRenderer` em `MessageBubble` abaixo do markdown, não no lugar dele.** *(`MessageBubble.tsx`: `<DynamicRenderer envelope={effectiveUiEnvelope} />` após o `ReactMarkdown`/`SourceShelf`. Todos os cartões entram por `React.lazy` em `frontend/src/ui/DynamicRenderer.tsx`; o build gera chunks separados `ProgressCard-*.js`, `ChecklistCard-*.js` etc.)* Sem canal SSE. Atualização de barra chega no WebSocket já aberto.
- [x] **Step 4: Strings e i18n.** *(`intelligentUi.progressOf` em `pt-BR.json`, `en-US.json` e `es-ES.json`.)* Incluir termos fixos (como conectivo "de" em "7 de 10") nos arquivos de tradução `pt-BR.json`, `en-US.json` e `es-ES.json` (`intelligentUi.progressOf`).
- [x] **Step 5: Commit** `feat: pintar bloco progress na bolha com i18n`

### Task 2: Evento do host

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/store/useStore.ts`
- Modify: `backend/routers/chat.py` apenas se já existir um ponto de fase (Fusion ou busca) barato de espelhar. Se o espelho custar refactor do Fusion, não fazer. Nesta fase o evento basta ser aceito e testado com um payload manual.

**Interfaces:**
- Produces: handler de `{ type: 'ui_progress', block }` que substitui o bloco de mesmo `id` na mensagem em stream. `source` gravado como `host` se persistir.

- [ ] **Step 1: Teste do store.** *(**Pendente.** A lógica existe em `useStore.handleUiProgress` — mesmo `id` substitui, id novo acrescenta até 4, o quinto é ignorado — mas sem teste.)* Dois eventos com o mesmo `id`: o segundo valor substitui o primeiro. Id novo acrescenta, até o teto de 4. O quinto é ignorado.

- [x] **Step 2: Implementar o handler. Não emitir `ui_progress` a partir de token do modelo.** *(`useChat.ts` roteia `ui_progress` → `handleUiProgress`. O backend ainda não emite `ui_progress` em nenhum ponto — conforme previsto no plano, o espelho do Fusion/busca ficou de fora.)*

- [x] **Step 3: Commit** `feat: aceitar ui_progress do host`

### Task 3: Catálogo condicional

**Files:**
- Create: `backend/ui_blocks/catalog.txt` com o texto literal da spec, seção 8.
- Create: `backend/ui_blocks/should_offer.py`
- Modify: `backend/routers/chat.py`, depois de `resolve_project_context` (linha ~406+) e antes de `history = [{"role": "system", "content": system_instruction}] + history` (linha ~415). Acrescentar o catálogo em `system_instruction`. Não criar outro system prompt.

**Interfaces:**
- Produces: `should_offer_ui(user_text: str) -> bool` com as duas regras da spec, seção 8.

- [x] **Step 1: Testes do heurístico.** *(`test_should_offer_ui_triggers`: cobre "compare os custos", "bom dia", 3 números + custo, e o caso negativo com 3 números sem palavra-chave.)* "compare os custos" retorna true. "bom dia" retorna false. Três números mais a palavra custo retorna true.

- [x] **Step 2: Injetar o arquivo só se flag on e `should_offer_ui` true.** *(`chat.py`, bloco "oferta de catálogo condicional": flag + heurístico + teto `len/4 <= 400`. O `catalog.txt` atual tem ~1006 chars ≈ 251 tokens. Observação: o texto do catálogo **não é a cópia literal** da seção 8 da spec — foi reescrito com um exemplo de `chart` preenchido e instrução para nunca usar fences ```` ```chart ````. Funcional, mas diverge do "copiar literal".)* Medir `len(catalog) / 4`. Se passar de 400, não injetar.

- [x] **Step 3: Commit** `feat: oferecer catálogo nexus-ui só quando o turno pede visual`
