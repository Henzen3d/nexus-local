# Streaming: parar de redesenhar a lista a cada token

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada token do stream deixa de assinar o store inteiro dentro de `MessageBubble` e deixa de fazer `scrollIntoView({ behavior: 'smooth' })` na lista.

**Architecture:** `MessageBubble` passa a selecionar só as actions que usa. A política de scroll vira função pura em `src/lib/scrollPolicy.ts`, testada com `node --test`. O efeito de scroll do `ChatWindow` usa `auto` enquanto `streamingContent` muda, e `smooth` só quando a lista de mensagens fechadas muda.

**Tech Stack:** React, TypeScript, Zustand, Node test runner já usado em `frontend/package.json` (`node --experimental-strip-types --test`).

**Spec:** Auditoria cirúrgica NexusLocal, sessão 20261015_102349_bc26b855. Item 5 do TOP 5.

## Global Constraints

- Não trocar stack, framework ou arquitetura.
- Não adicionar `react-virtuoso` nem outra dependência. Virtualização fica fora deste plano.
- Mudança de poucas linhas, reversível e testável.
- Não alterar backend nem banco.

---

## Contexto

`useStore.ts:1310` faz `streamingContent: state.streamingContent + token` a cada token.

`ChatWindow.tsx:232-235` seleciona `streamingContent`, então o componente re-renderiza a cada token. O efeito das linhas 379-397 depende de `streamingContent` e chama `endRef.current?.scrollIntoView({ behavior: 'smooth' })`. Smooth a cada token é o travamento visível.

`MessageBubble` em `frontend/src/components/MessageBubble.tsx:361` faz:

```typescript
const { setActiveArtifact, setArtifactPanelOpen, loadArtifactHistory } = useStore()
```

Sem seletor, o Zustand assina o store inteiro. Cada token re-renderiza cada bolha, e cada bolha volta a parsear markdown. `React.memo` sozinho não resolve enquanto esse hook existir.

`StreamingBubble` (`MessageBubble.tsx:728`) recebe `content` por prop. Ele precisa re-renderizar. Não memoizar essa bolha de um jeito que congele o texto.

O `messages.map` está em `ChatWindow.tsx:610-626`. Não virtualizar neste plano.

## Mudança exata

Arquivos:

- Create: `frontend/src/lib/scrollPolicy.ts`
- Create: `frontend/src/lib/scrollPolicy.test.ts`
- Modify: `frontend/src/components/MessageBubble.tsx:361`
- Modify: `frontend/src/components/ChatWindow.tsx:379-397`

```typescript
export function streamScrollBehavior(isStreaming: boolean): ScrollBehavior {
  return isStreaming ? "auto" : "smooth"
}
```

Em `MessageBubble.tsx:361`, substituir o `useStore()` nu por:

```typescript
const setActiveArtifact = useStore((s) => s.setActiveArtifact)
const setArtifactPanelOpen = useStore((s) => s.setArtifactPanelOpen)
const loadArtifactHistory = useStore((s) => s.loadArtifactHistory)
```

Não há outro `useStore()` sem seletor nesse componente. O da linha 360 já é seletor.

No efeito de scroll, calcular:

```typescript
const behavior = streamScrollBehavior(Boolean(streamingContent))
endRef.current?.scrollIntoView({ behavior })
```

Tirar `streamingContent` do array de dependências não é o objetivo. O objetivo é `behavior: 'auto'` enquanto houver stream. Dependência pode continuar, desde que o behavior não seja `smooth` nesse caso.

## Como testar

```bash
cd /home/osmar/nexuslocal/frontend
node --experimental-strip-types --test src/lib/scrollPolicy.test.ts
```

Esperado: PASS.

Prova manual: conversa com mais de 20 mensagens, iniciar um stream. O scroll não deve animar a cada token. No React DevTools, `MessageBubble` das mensagens antigas não deve piscar a cada token. `StreamingBubble` pisca. Isso é o esperado.

## Rollback

Reverter o commit. Sem migração.

## Métrica

- Antes: `MessageBubble.tsx:361` assina o store inteiro. `ChatWindow.tsx:394` usa `smooth` no efeito que depende de `streamingContent`.
- Depois: a linha 361 não existe mais como `useStore()` sem argumento. O teste de `streamScrollBehavior(true)` devolve `"auto"`.

---

### Task 1: Política de scroll

**Files:**
- Create: `frontend/src/lib/scrollPolicy.ts`
- Create: `frontend/src/lib/scrollPolicy.test.ts`

**Interfaces:**
- Consumes: nada
- Produces: `streamScrollBehavior(isStreaming: boolean): ScrollBehavior`

- [ ] **Step 1: Write the failing test**

```typescript
import assert from "node:assert/strict"
import test from "node:test"
import { streamScrollBehavior } from "./scrollPolicy.ts"

test("stream usa auto para não animar a cada token", () => {
  assert.equal(streamScrollBehavior(true), "auto")
})

test("lista parada usa smooth", () => {
  assert.equal(streamScrollBehavior(false), "smooth")
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --experimental-strip-types --test src/lib/scrollPolicy.test.ts`
Working directory: `/home/osmar/nexuslocal/frontend`
Expected: FAIL, módulo não encontrado.

- [ ] **Step 3: Write minimal implementation**

```typescript
export function streamScrollBehavior(isStreaming: boolean): ScrollBehavior {
  return isStreaming ? "auto" : "smooth"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --experimental-strip-types --test src/lib/scrollPolicy.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/scrollPolicy.ts frontend/src/lib/scrollPolicy.test.ts
git commit -m "test: scroll do stream não usa smooth"
```

### Task 2: Seletor do store e uso da política

**Files:**
- Modify: `frontend/src/components/MessageBubble.tsx:361`
- Modify: `frontend/src/components/ChatWindow.tsx:379-397`
- Test: `frontend/src/lib/scrollPolicy.test.ts` (já existe; acrescentar teste de fonte)

**Interfaces:**
- Consumes: `streamScrollBehavior`
- Produces: `MessageBubble` sem `useStore()` nu; `ChatWindow` importa a política

- [ ] **Step 1: Write the failing test**

Acrescentar em `frontend/src/lib/scrollPolicy.test.ts`:

```typescript
import { readFileSync } from "node:fs"

test("MessageBubble não assina o store inteiro", () => {
  const source = readFileSync(
    new URL("../components/MessageBubble.tsx", import.meta.url),
    "utf8",
  )
  assert.equal(source.includes("} = useStore()"), false)
  assert.equal(source.includes("s.setActiveArtifact"), true)
})

test("ChatWindow usa a política de scroll", () => {
  const source = readFileSync(
    new URL("../components/ChatWindow.tsx", import.meta.url),
    "utf8",
  )
  assert.equal(source.includes("streamScrollBehavior"), true)
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --experimental-strip-types --test src/lib/scrollPolicy.test.ts`
Expected: FAIL. `} = useStore()` ainda está em `MessageBubble.tsx:361`.

- [ ] **Step 3: Write minimal implementation**

Trocar a linha 361 de `MessageBubble.tsx` pelos três seletores da seção Mudança exata.

Em `ChatWindow.tsx`, importar `streamScrollBehavior` de `../lib/scrollPolicy`. No efeito que hoje chama `scrollIntoView({ behavior: 'smooth' })`, usar:

```typescript
endRef.current?.scrollIntoView({
  behavior: streamScrollBehavior(Boolean(streamingContent)),
})
```

Não adicionar dependência. Não envolver `MessageBubble` em `memo` neste plano: o seletor é o que corta a assinatura. `memo` sem o seletor não bastaria, e com o seletor é opcional.

- [ ] **Step 4: Run test to verify it passes**

Run: `node --experimental-strip-types --test src/lib/scrollPolicy.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/MessageBubble.tsx frontend/src/components/ChatWindow.tsx frontend/src/lib/scrollPolicy.test.ts
git commit -m "fix: token do stream não redesenha as bolhas antigas"
```

## Medição do paint (commit extra, depois de e14fb06)

e14fb06 tirou o `useStore()` nu de `MessageBubble` e trocou o scroll do stream de `smooth` para `auto`. Não parou a pintura das bolhas antigas: `ChatWindow` ainda chamava `useStore()` sem seletor e lia `streamingContent`.

Comando (cwd `frontend/`): `node scripts/run-streaming-paint-probe.mjs`

Probe no HEAD `e14fb06ad744638b45e16ebbeb9eb8cddd6db6c1`, antes de mudar essa assinatura. Harness: `ChatProvider` + `ChatWindow`, 50 mensagens curtas, `isStreaming: true`, 20 appends em `streamingContent`. Números lidos do stdout, não estimados:

```json
{"head":"probe","messages":50,"tokens":20,"commitsAfterMount":8,"commitsDuringTokens":41,"chatWindowCommitsAfterMount":8,"chatWindowCommitsDuringTokens":41,"bubblesAfterMount":150,"bubblesDuringTokens":1000,"bubblesTotal":1150}
```

`bubblesDuringTokens: 1000` é a pintura das bolhas antigas (50 por token no stderr do probe). `chatWindowCommits*` nessa corrida usava `fiber.actualDuration` e acompanhava o Profiler da subárvore; não é contagem de execução da função `ChatWindow`.

Depois do commit de paint, o mesmo probe:

```json
{"head":"probe","messages":50,"tokens":20,"commitsAfterMount":6,"commitsDuringTokens":41,"chatWindowCommitsAfterMount":1,"chatWindowCommitsDuringTokens":0,"chatWindowRendersDuringTokens":0,"bubblesAfterMount":50,"bubblesDuringTokens":0,"bubblesTotal":50}
```

`chatWindowCommitsDuringTokens` passou a contar callback do Profiler só quando a função `ChatWindow` rodou. Durante os 20 tokens: 0. Renders de `MessageBubble`: 0. O Profiler da subárvore continua em 41 porque `StreamingTail` e filhos ainda atualizam. A prova comparável entre as duas corridas continua 1000 → 0 renders de `MessageBubble`. O 41 do Profiler da subárvore e o 0 de execução de `ChatWindow` não são a mesma métrica.

## 41 commits do Profiler (inerente, não agrupar)

20 tokens geram 41 commits `update` na subárvore. O primeiro token soma 3; cada token seguinte soma 2. O efeito de scroll em `StreamingTail` não chama `setState`: só lê a distância de 180px e chama `scrollIntoView({ behavior: 'auto' })`. Não há `setState` extra para agrupar nesse efeito.

Medição no mesmo probe, com `useDeferredValue(answer)` trocado por `answer` e o arquivo restaurado em seguida:

- com deferred: `commitsDuringTokens` 41 (token 1 = 3, depois +2)
- sem deferred: `commitsDuringTokens` 21 (token 1 = 2, depois +1)

Os 20 commits a mais são o segundo passe do `useDeferredValue` em `StreamingBubble`. É inerente à renderização progressiva do markdown. O 1 commit por token que sobra é a atualização do próprio tail. O commit extra só no primeiro token casa com o efeito de `ExecutionSequence`, que chama `setIsOpen` quando `isWorking` vira falso ao chegar o primeiro texto. Também não está no efeito de scroll. Não alterar.
