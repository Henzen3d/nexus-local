# Validação do Plano 13 — Cenas 2D e 3D Interativas em Sandbox Local

Data da validação: 15 de outubro de 2026  
Escopo: Implementação completa de ponta a ponta do Plano 13 (`sandbox` com `kind: "scene"`), cobrindo runtime Three.js/2D isolado, protocolo estrito, validadores com paridade Python/TS, componente `SceneCard`, exportação standalone offline, catálogo modular, fixtures canônicas, telemetria e suítes de testes.

---

## 1. Evidências de Execução dos Testes

### A. Testes do Backend (Pytest)
Executado em ambiente virtual isolado (`.venv`):
```bash
.venv/Scripts/python.exe -m pytest backend/tests -q
```
**Resultado:**
```
529 passed, 1 skipped, 14 warnings in 74.80s
```
- Cobertura de cenas em `backend/tests/test_ui_blocks.py`:
  - `test_validate_scene_valid`: validação de cenas 3D e 2D, parâmetros (range e select), leituras numéricas, inferência automática de tipo `sandbox` quando `code` existe sem `html`.
  - `test_validate_scene_forbidden_terms`: bloqueio determinístico de todos os termos proibidos (`while`, `import`, `fetch`, `WebSocket`, `XMLHttpRequest`, `document.cookie`, `localStorage`, `window.parent`, `postMessage`, `eval`, `Function(`) retornando código de diagnóstico `invalid_scene_code`.
  - `test_validate_scene_limits_and_params`: tetos de código (> 6000 caracteres), linhas (> 120 linhas), rejeição de IDs duplicados em parâmetros e exigência de `default`.
  - `test_scene_triggers_should_offer`: gatilhos modulares de cena (`órbita`, `pêndulo`, `partícula`, `passo a passo animado`).
- Telemetria de cena em `backend/ui_blocks/telemetry.py` e rota `/api/intelligent-ui/scene-event`.

---

### B. Testes Unitários do Frontend (Node:Test)
Executado via `npm test`:
```bash
npm test
```
**Resultado:**
```
✔ cenas canonicas sao aceitas pelo validador do frontend (7.31ms)
✔ termos proibidos em cenas sao rejeitados com invalid_scene_code (4.78ms)
✔ limites de cena: tamanho do codigo e linhas (0.71ms)
✔ subteto de sandbox no envelope: no maximo 1 sandbox/cena (0.26ms)
✔ assembleStandaloneSceneHtml embute runtime, setup e escapa codigo (0.76ms)
✔ escapeScript escapes </script> and <!-- correctly (0.42ms)
✔ embed encodes < as \u003c (0.35ms)
✔ sceneDocument generates strict CSP and valid HTML without network (0.68ms)
✔ readSceneMessage validates messages according to scene protocol (0.55ms)
...
ℹ tests 134
ℹ suites 10
ℹ pass 134
ℹ fail 0
```
- **134 testes unitários passaram com 0 falhas.**

---

### C. Testes de Interface (React Test Renderer)
Executado como parte do `npm test` (`node scripts/test-correction-ui.mjs`):
```
✔ SceneCard: renders 3D orbit scene with controls, iframe, actions and readout (4.36ms)
✔ SceneCard: renders 2D pendulum scene with multiple parameters and updates value (3.36ms)
✔ SceneCard: handles runtime error and sends correction prompt (42.02ms)
...
ℹ tests 12
ℹ suites 0
ℹ pass 12
ℹ fail 0
```
- **12 testes de UI passaram com 0 falhas.**

---

### D. Checagem de Tipagem Estrita (TypeScript)
```bash
npx tsc --noEmit
```
**Resultado:** Código de saída 0 (zero erros de tipagem em todo o projeto).

---

### E. Compilação de Produção e Isolamento do Three.js
Executado via `npm run build`:
```
> nexuslocal-frontend@1.0.0 prebuild
> npm run build:scene

vite v5.4.21 building for production...
public/scene/runtime.js  773.24 kB │ gzip: 199.05 kB
✓ built in 2.78s

> nexuslocal-frontend@1.0.0 build
> tsc && vite build

dist/assets/SceneCard-Bju5csRD.js                   11.49 kB │ gzip:   4.08 kB
dist/assets/index-CYK7HgrK.js                    1,106.35 kB │ gzip: 363.52 kB
✓ built in 11.37s
```
- **Auditoria de imports Three.js:** Verificado com `grep_search`. Zero importações de `three` no código do app principal. Apenas `frontend/src/ui/scene-runtime/stage3d.ts` importa `three`, gerando o bundle isolado `public/scene/runtime.js`. O app principal carrega apenas a casca `SceneCard` (11.49 kB).

---

### F. Internacionalização (i18n) Rigorosa
Executado via `node scripts/check-i18n.mjs intelligentUi`:
```
i18n check — referência pt-BR (53 chaves em "intelligentUi")
  de-DE   ok  faltando=0 extras=0 duplicadas=0
  en-US   ok  faltando=0 extras=0 duplicadas=0
  es-419  ok  faltando=0 extras=0 duplicadas=0
  es-ES   ok  faltando=0 extras=0 duplicadas=0
  fr-FR   ok  faltando=0 extras=0 duplicadas=0
  ja      ok  faltando=0 extras=0 duplicadas=0
  ko      ok  faltando=0 extras=0 duplicadas=0
  pt-BR   ok  faltando=0 extras=0 duplicadas=0

i18n check: OK
```
- Todas as 53 chaves traduzidas nos 8 idiomas sem duplicações ou chaves faltantes.

---

### G. Auditoria de Espaços e Formatação (git diff --check)
```bash
git diff --check
```
**Resultado:** Saída limpa, zero alertas de espaços em branco ou quebras de linha espúrias.

---

## 2. Status dos Critérios de Aceite do Plano 13

| Critério de Aceite | Status | Verificação |
|---|---|---|
| **Cena sem rede** | ✅ Aprovado | CSP `default-src 'none'`, runtime Three.js 100% local em `public/scene/runtime.js`. Zero chamadas externas. |
| **Código proibido rejeitado** | ✅ Aprovado | Ambos os validadores (Python e TS) rejeitam `fetch`, `import`, `while`, etc. com `invalid_scene_code`. |
| **Protocolo postMessage estrito** | ✅ Aprovado | `readSceneMessage` sanitiza todos os payloads; mensagens fora do contrato são descartadas. |
| **Segundo load do iframe vira erro** | ✅ Aprovado | Detectado por contador de cargas; exibe alerta visual de sandbox e bloqueia navegação. |
| **prefers-reduced-motion** | ✅ Aprovado | Cena inicia pausada (`setup.paused = true`); ação "Continuar" retoma animação. |
| **Desmontagem fora do viewport** | ✅ Aprovado | `useSceneViewport` desmonta o iframe ao rolar para longe, liberando contexto WebGL escasso. |
| **Erro de runtime e pedido de correção** | ✅ Aprovado | Faixa de erro exibe mensagem e botão "Pedir correção" envia prompt estruturado ao chat. |
| **Exportação standalone offline** | ✅ Aprovado | `downloadStandaloneSceneHtml` embute o runtime, setup e código escapado em HTML autônomo. |
| **Bundle principal isolado** | ✅ Aprovado | `three` presente estritamente em `public/scene/runtime.js` como devDependency; bundle React inalterado. |
