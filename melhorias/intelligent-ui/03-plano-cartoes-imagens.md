# Cartões e imagens — plano

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pintar cartão com título, texto curto, fatos e foto opcional, sem deixar URL ruim quebrar a bolha.

**Architecture:** `CardBlock` consome bloco já validado. A foto é `<img>` direto no browser. Sem proxy.

**Tech Stack:** React 18. Sem lib nova.

**Spec:** `melhorias/intelligent-ui/00-visao-e-spec.md` seções 4.2 e 6.

## Global Constraints

- URL fora da seção 6: cartão sem imagem, resto intacto.
- `alt` obrigatório quando há imagem. Sem alt, o validador da fase 1 já tirou a imagem.
- `referrerPolicy="no-referrer"`, `loading="lazy"`.
- Não buscar a imagem no backend.
- Não usar o painel de artefatos para este cartão.
- Texto é nó React.

---

### Task 1: Cartão sem foto

**Files:**
- Create: `frontend/src/ui/components/ImageCard.tsx`
- Modify: `frontend/src/ui/DynamicRenderer.tsx`

**Interfaces:**
- Consumes: tipo `card` de `nexusUi.ts`
- Produces: `ImageCard({ block })` com `title`, `body` opcional e até 6 `facts`. Carga via `React.lazy` no `DynamicRenderer`.

- [ ] **Step 1: Teste.** Título "ESP32-S3" e fato "Flash / 8 MB" aparecem. Sem `image`, não há `<img>`.

- [ ] **Step 2: Implementar.** Fundo `--surface-card`, borda `--hairline`, título `--ink`, corpo `--body`.

- [ ] **Step 3: Registrar em `DynamicRenderer`.** Tipo desconhecido continua ignorado.

- [ ] **Step 4: Commit** `feat: cartão textual na bolha`

### Task 2: Foto com URL filtrada

**Files:**
- Modify: `frontend/src/lib/nexusUi.ts` se a checagem de URL ainda não estiver no validador da Task 5 da fundação. Se já estiver, não duplicar.
- Modify: `ImageCard.tsx`

**Interfaces:**
- Produces: `isAllowedImageUrl(url: string): boolean` com as regras da spec, seção 6. O componente chama de novo antes de montar o `<img>`, mesmo que o backend já tenha filtrado.

- [ ] **Step 1: Testes de URL, iguais no Python e no TS.** Aceitar `/attachments/foto.jpg`. Aceitar URL cujo host é o da página. Aceitar host presente em `INTELLIGENT_UI_IMAGE_HOSTS`. Recusar `https://exemplo.com/a.jpg` com lista vazia. Recusar `http://192.168.0.20/foto.jpg` com a flag privada desligada. Aceitar esse IP só com `INTELLIGENT_UI_ALLOW_PRIVATE_HTTP=true`. Recusar `javascript:alert(1)`, `data:text/html,hi` e URL com userinfo.

- [ ] **Step 2: No erro de carga (`onError`), esconder a imagem e manter título e fatos.**

- [ ] **Step 3: Commit** `feat: foto no cartão só com URL permitida`

### Task 3: Exemplo de produto, não de dado inventado no código

Não hardcodar placa ESP32 no app. O exemplo da spec é só contrato. O teste usa o JSON do contrato, não uma foto real embutida.
