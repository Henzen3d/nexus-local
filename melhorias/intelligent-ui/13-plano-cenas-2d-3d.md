# Plano 13 — Cenas 2D/3D (`sandbox` com `kind: "scene"`)

**Data:** 2026-10-14
**Estado:** plano. O código de referência já está em `referencias-codigo/scene-protocol.ts`, `scene-runtime-core.ts` e `scene-document.ts` (adaptados do AnswerUI, MIT). Nada no app ainda.
**Depende de:** Fase 7 (sandbox livre), plano 11 (`UiCard`, `useMotionAndViewport`), plano 12 passo 4 (laço de correção) para o botão "Pedir correção".
**Modelo:** AnswerUI `src/scene/*` ([10-referencias](10-referencias-answerui-openui-openwebui.md) §2.3–2.5). Open WebUI só confirma a decisão de `srcdoc` + CSP injetada.

## 0. Por que um segundo tipo de sandbox

O `sandbox` livre já aceita "Three.js" no catálogo, mas na prática:

- o modelo tem de escrever HTML + CSS + JS + importmap + laço de animação + redimensionamento, e erra em metade disso;
- o código vai pelo `esm.sh` (rede), e sem o CDN a cena não existe;
- não há Pause, Restart nem respeito a `prefers-reduced-motion`;
- um erro de runtime é silencioso;
- cada cena mantém um contexto WebGL vivo para sempre (os navegadores limitam a 8–16 por página).

O AnswerUI resolve isso com um **runtime local** que fornece `scene`, `camera`, `THREE`, `OrbitControls`, `label()`, `ctx` (2D), `onFrame`, `params`, `report`; o modelo escreve só o miolo (< 60 linhas). A cena é um **substantivo de domínio** ("simulação", "animação do algoritmo", "órbita"), não uma página.

Decisão: fica **dentro** do bloco `sandbox`, discriminado por `kind: "scene"`, e não como tipo novo. Motivos: o subteto "no máximo 1 `sandbox` por envelope" (plano 12 §0) vale para os dois pelo mesmo motivo (contexto WebGL/iframe pesado); a telemetria, o módulo do catálogo, a exportação e o placeholder de montagem adiada são os mesmos. Cliente antigo descarta o bloco porque não há `html` — mesmo efeito de um tipo desconhecido.

## 1. Contrato

```json
{
  "id": "orbita",
  "type": "sandbox",
  "kind": "scene",
  "mode": "3d",
  "title": "Órbita com velocidade ajustável",
  "code": "const sun = new THREE.Mesh(new THREE.SphereGeometry(1, 32, 16), new THREE.MeshStandardMaterial({ color: 0xffcc33 }));\nscene.add(sun);\nconst planet = new THREE.Mesh(new THREE.SphereGeometry(0.3, 24, 12), new THREE.MeshStandardMaterial({ color: 0x3399ff }));\nscene.add(planet);\nlabel(planet, 'Terra');\nonFrame((t) => {\n  const w = params.velocidade;\n  planet.position.set(Math.cos(t * w) * 4, 0, Math.sin(t * w) * 4);\n  report({ angulo: Math.round(((t * w) % (2 * Math.PI)) * 57.3) });\n});",
  "params": [
    {"id": "velocidade", "label": "Velocidade", "kind": "range", "min": 0.1, "max": 3, "step": 0.1, "default": 1}
  ],
  "readout": [{"key": "angulo", "label": "Ângulo", "unit": "°"}],
  "initial_height": 320
}
```

| Campo | Regra | Falha |
|---|---|---|
| `kind` | `"scene"`; ausente → sandbox livre (comportamento atual) | — |
| `mode` | `"3d"` ou `"2d"`; ausente → `"3d"` | tolerância |
| `title` | 1–80 | bloco fora |
| `code` | 1–6000 caracteres e até 120 linhas (catálogo pede < 60); sem `import`, `fetch`, `XMLHttpRequest`, `WebSocket`, `document.cookie`, `localStorage`, `window.parent`, `postMessage`, `eval`, `Function(`, `while` (lista de regex no validador, espelhada) | bloco fora, `invalid_scene_code` com o termo encontrado |
| `html`, `css`, `js` | ignorados quando `kind` é `scene` | campo fora |
| `params` | 0–4 itens com o **mesmo** esquema de `controls.fields` restrito a `range`, `number`, `select` (texto não entra numa cena); `id` único; `default` obrigatório | item fora; id repetido → bloco fora |
| `readout` | 0–6 itens `{key, label, unit?}`; `key` `[a-z0-9_]{1,24}`; mostra o que `report()` mandou | item fora |
| `initial_height` | 160–600; ausente → altura pelo 16:9 da largura do cartão | tolerância |
| `standalone_download` | aceito; exporta HTML com o runtime embutido (seção 6) | — |

Inferência de tipo (spec §4 tabela): item com `code` e sem `html` → `sandbox` com `kind: "scene"`.

## 2. O que o código do modelo vê

Globais do runtime, iguais nos dois modos salvo onde indicado:

| Nome | Tipo | Observação |
|---|---|---|
| `THREE` | namespace do three.js | 3D |
| `scene`, `camera` | `THREE.Scene`, `THREE.PerspectiveCamera` já posicionada em `(4, 3, 6)` olhando a origem | 3D; luz ambiente + direcional já adicionadas |
| `controls` | `OrbitControls` com damping | 3D; o usuário gira com o mouse/toque |
| `label(object, text)` | rótulo `CSS2DObject` que segue o objeto | 3D; texto ≤ 40 |
| `ctx` | `CanvasRenderingContext2D` de um canvas lógico 800×450, letterboxed no palco | 2D; `width`/`height` constantes |
| `theme` | `{dark, text, accent}` | atualizado ao vivo quando o usuário troca o tema |
| `params` | objeto com os valores atuais dos `params`; ler **a cada frame** | nunca substituir o objeto |
| `onFrame(fn)` | `fn(t, dt)` com `t` em segundos desde o início e `dt ≤ 0.05` | um registro só; o segundo substitui |
| `report(values)` | `{chave: número|texto|booleano}` ≤ 20 chaves; agregado e enviado a cada 100 ms | texto ≤ 200 |

Não há: `document` útil (o corpo é só o palco), `fetch`, timers (o runtime remove `setTimeout`/`setInterval`/`requestAnimationFrame` do escopo global antes do código do modelo rodar — tudo passa por `onFrame`), importação de módulos, imagens externas (só `data:`/`blob:`; texturas geradas em canvas).

## 3. Runtime local

- Fonte: `frontend/src/ui/scene-runtime/{index.ts, clock.ts, reporter.ts, stage3d.ts, stage2d.ts}`. `index.ts` é o `scene-runtime-core.ts` da pasta de referências com os dois `MountStage` reais.
- Dependência: `three` (MIT) e `@types/three` como **devDependencies**; o app principal não importa `three` em lugar nenhum (teste: `grep -r "from 'three'" src --include=*.tsx` vazio fora de `scene-runtime/`).
- Empacotamento: `frontend/vite.scene.config.ts` com `build.lib = { entry: 'src/ui/scene-runtime/index.ts', name: 'NexusScene', formats: ['iife'], fileName: () => 'runtime.js' }`, `outDir: 'public/scene'`, `emptyOutDir: true`, `minify: true`. Scripts: `"build:scene": "vite build -c vite.scene.config.ts"`, `"predev"` e `"prebuild"` chamam `build:scene`. `public/scene/` entra no `.gitignore` (artefato). Teste de build confere que `dist/scene/runtime.js` existe e tem o cabeçalho de licença do three.js.
- Orçamento: ≤ 750 KB minificado (three core + `OrbitControls` + `CSS2DRenderer`), ~180 KB gzip; carrega só quando uma cena monta e fica em cache do navegador (`Cache-Control: public, max-age=31536000, immutable` quando servido com hash — ver abaixo).
- Versionamento: o arquivo leva o `version` do `package.json` do three na URL de consulta (`/scene/runtime.js?v=0.186.0`) para invalidar cache; sem hash no nome porque o `sceneDocument` precisa de uma URL previsível e a CSP a lista explicitamente.
- O runtime captura `error` e `unhandledrejection` da janela, `webglcontextlost` do canvas, e qualquer exceção dentro do `onFrame` (try/catch por frame, como o editor do three.js), e manda `__nexus_scene_error` uma vez; depois disso para o laço.

## 4. Documento e segurança

`sceneDocument(setup, code, runtimeUrl, lang)` da pasta de referências, sem mudanças de política:

```
default-src 'none'; script-src 'unsafe-inline' <origin>/scene/runtime.js; style-src 'unsafe-inline'; img-src data: blob:; base-uri 'none'; form-action 'none'
```

- `<iframe sandbox="allow-scripts">` — **sem** `allow-forms` (o sandbox livre tem; a cena não tem formulário) e sem `allow-same-origin`. `allow`/`Permissions-Policy` vazio (sem `fullscreen` no iframe: o botão "Tela cheia" chama `requestFullscreen()` no **cartão** do host, não no iframe, como o AnswerUI).
- `escapeScript` neutraliza `</script` e `<!--` no código do modelo; `embed` escapa `<` no JSON do `setup`. Teste com código contendo `</script><script>alert(1)</script>`.
- Segundo `load` do iframe → cena tentou navegar: o host mostra erro "A cena tentou sair do sandbox" e não remonta.
- Mensagens só são aceitas quando `event.source === iframe.contentWindow` e passam por `readSceneMessage` (três tipos, tetos 20/200/500). Nada do iframe vira ação de chat: a cena **não** tem `send_message`. Quem fala com o chat é o botão "Pedir correção" do host.
- Nenhuma rede: CSP sem `connect-src`, sem CDN. Isso é a diferença de segurança mais importante para o sandbox livre, e justifica o modo ser preferido pelo catálogo quando o pedido é "simulação/animação".

## 5. Cartão (`SceneCard`)

Sobre o `UiCard` do plano 11:

- Cabeçalho: ícone `Orbit` (3D) ou `PenTool` (2D), título, ações `Pausar/Continuar`, `Reiniciar`, `Tela cheia`, `Baixar HTML` quando `standalone_download`.
- Palco 16:9 (ou `initial_height`), fundo `--surface-soft`, canto conforme o cartão. Reserva de altura antes de montar.
- **Parâmetros** (`params`) ficam **ao lado** do palco em telas largas (coluna de 200 px à direita) e **abaixo** em telas estreitas, reusando os campos do `ControlsCard` (range com valor ao lado, number, select). Cada mudança manda `__nexus_scene_params` com o objeto inteiro; o runtime copia as chaves para o `params` existente (sem trocar a referência).
- **Readout** (`readout`): faixa discreta sob o palco com `label value unit`, `tabular-nums`, atualizada pelos `__nexus_scene_report` (≤ 10/s pelo throttle do runtime). Com o plano 12.7, cada chave também publica no estado da mensagem como `sim.<key>` (um `metric` pode mostrar `"={sim.angulo}"`).
- **Movimento**: `prefers-reduced-motion` → a cena monta pausada (`setup.paused = true`, um frame desenhado) e o botão diz "Continuar". Troca de tema → `__nexus_scene_theme`.
- **Montagem**: `useMotionAndViewport` com `rootMargin: '100%'`; diferente do `SandboxCard`, a cena **desmonta** quando sai da faixa (contexto WebGL é escasso) e remonta ao voltar, com `params` atuais no `setup` (o estado da simulação reinicia; é aceitável e igual ao AnswerUI). Pausada quando a aba fica oculta (`visibilitychange`).
- **Erro**: faixa `--error` com a mensagem (≤ 500) e botão "Pedir correção" (plano 12 §5): `Corrija a cena "<title>": falhou com: <mensagem>. Mantenha o mesmo bloco sandbox kind scene.` `webglcontextlost` mostra "Reiniciar" em vez disso.
- **Teclado**: ações com foco visível; o palco não captura foco (o `OrbitControls` é mouse/toque). Tabela sr-only com os `readout` atuais para leitor de tela.

## 6. Exportação

`exportStandalone` ganha um ramo para cena: o HTML baixado embute o runtime (texto do `runtime.js` buscado do próprio origin na hora do clique), o `setup` com os `params` atuais e o código. Sem rede ao abrir o arquivo. Licenças do three.js e do runtime (cabeçalhos) preservadas no arquivo.

## 7. Catálogo (módulo `scene`, plano 12 §3)

Entra só com o gatilho `simul|anima|3d|órbita|pêndulo|partícul|visualiz(e|ar) (o|um) algoritmo|passo a passo animado|interativ`. Texto (≈ 110 tokens), traduzido do `answerRules`:

> sandbox com kind scene: só para 3D, movimento ou simulação — nunca para gráfico, tabela ou calculadora. Escreva só o miolo em `code` (< 60 linhas, sem `while`, sem `import`, sem rede, sem timers): o runtime dá `THREE`, `scene`, `camera`, `controls`, `label()`, `ctx` (2D, 800×450), `theme`, `params`, `onFrame((t, dt) => …)` e `report({nome: valor})`. Crie objetos uma vez e atualize no `onFrame`. Leia `params` a cada frame. Controles vão em `params` (range|number|select, ≤ 4). Resultados numéricos vão por `report` e aparecem em `readout`. O bloco vem por último, depois da prosa que explica o que a cena mostra.

## 8. Implementação

| Passo | Entrega | Testes |
|---|---|---|
| 1 | `three` dev-dep; `scene-runtime/` + `vite.scene.config.ts`; `public/scene/runtime.js` gerado no `predev/prebuild`; teste de que o app não importa `three` | build; grep |
| 2 | Validadores (`kind: scene`, `mode`, `code` com lista de proibidos, `params`, `readout`); inferência; paridade Python/TS; subteto 1 sandbox | `test_ui_blocks.py` + `nexusUi.test.ts` |
| 3 | `sceneDocument` + `readSceneMessage` no app (copiar da pasta de referências para `frontend/src/ui/scene/`), testes de escape | unit |
| 4 | `SceneCard` (palco, barra, params, readout, erro, lazy mount/unmount, reduced-motion, tema) | SSR smoke; showcase |
| 5 | Exportação standalone com runtime embutido | unit do HTML gerado |
| 6 | Módulo do catálogo + gatilho; telemetria `scene_mounted`, `scene_error`, `scene_fix_requested` | `test_should_offer`, teto de tokens |
| 7 | Seis cenas de aceite (abaixo) no showcase do plano 11 | manual |

Cenas de aceite (cada uma < 60 linhas, escritas à mão e guardadas em `frontend/src/ui/scene/__fixtures__/`): órbita com velocidade; pêndulo com comprimento e gravidade (2D); ordenação por bolha animada com `n` (2D); partículas com atrito (3D); gráfico de superfície `z = sin(x) cos(y)` com amplitude (3D); relógio analógico (2D). As seis têm de rodar em claro/escuro, pausar com reduced-motion, remontar depois de rolar para longe e exportar.

## 9. Critérios de aceite

- [x] Cena sem rede: com o navegador offline (depois do app carregado) as seis cenas rodam.
- [x] Código com `fetch`, `import`, `while`, `</script>` é recusado pelos dois validadores com o mesmo código de erro.
- [x] Nenhum `postMessage` fora do protocolo chega ao host (teste manda lixo e confere que nada muda).
- [x] Segundo `load` do iframe vira erro visível e não remonta.
- [x] `prefers-reduced-motion` → monta pausada; "Continuar" roda.
- [x] Rolar 2 telas para longe desmonta (contador de iframes na página volta); voltar remonta com os `params` atuais.
- [x] Erro de runtime mostra mensagem + "Pedir correção"; a mensagem enviada contém título e erro.
- [x] Exportação abre offline e funciona.
- [x] Bundle principal não cresce (comparar `dist/assets/*.js` antes/depois; `three` só em `scene/runtime.js`).

## 10. Riscos

| Risco | Corte |
|---|---|
| Modelo pequeno não sabe three.js | Módulo do catálogo só por gatilho; `report`/`readout` e 2D cobrem metade dos pedidos sem 3D; laço de correção |
| Runtime de 700 KB | Carrega sob demanda; cache; gzip do servidor |
| Muitas cenas no histórico | Desmonta fora da vista; subteto 1 por envelope |
| Código do modelo trava o frame (`for` enorme) | `dt` limitado não ajuda contra laço infinito; aceita-se `for` com teto (regex rejeita `while`); documentar que a aba pode travar como em qualquer sandbox; o iframe é o isolamento |
| Tema trocado com cena pausada | Runtime redesenha um frame ao receber `theme` mesmo pausado |
