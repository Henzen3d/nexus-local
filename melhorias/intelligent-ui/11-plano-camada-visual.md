# Plano 11 — Camada visual dos cartões nativos

**Data:** 2026-10-14
**Estado:** primeira fatia implementada (seção 3). O restante está em checkboxes na seção 4.
**Depende de:** Fases 1–7 implementadas. Não muda o contrato `nexus-ui/1`.
**Referências:** [10-referencias-answerui-openui-openwebui.md](10-referencias-answerui-openui-openwebui.md) §3.3 (OpenUI react-ui) e §2.3 (barra da cena do AnswerUI).

## 1. Diagnóstico (código em `a0c2e74`)

Os seis cartões (`ProgressCard`, `ChecklistCard`, `ImageCard`, `ChartCard`, `ControlsCard`, `SandboxCard`) funcionavam, mas cada um desenhava a própria "casca" com estilo inline: margem, borda, raio, sombra e título repetidos seis vezes com valores levemente diferentes (raio 10 px, sombra `0 2px 8px` ou `0 2px 10px`, título 13 px ou 14 px, padding 12/14/16). Consequências:

- Não dava para ajustar o visual de todos de uma vez (tema, densidade, `:fullscreen`, movimento reduzido).
- O gráfico usava tooltip padrão do Recharts com `contentStyle` inline, paleta fixa de 4 cores, números sem locale (`12000` em vez de `12 mil`), eixo Y com margem negativa, animação de entrada sempre ligada.
- A lista de passos era um `<ul>` com glifos de texto (`✓`, `✕`) sem conector; não parecia uma linha do tempo.
- Facts do cartão eram chips de texto; um número não se destacava de um rótulo.
- O formulário era uma coluna única de inputs 36 px com `backgroundColor: var(--canvas, #1f1f1e)`; o `range` não mostrava limites; o botão enviado virava um `✓` solto.
- O sandbox só tinha "Baixar HTML": sem reiniciar, sem tela cheia, sem aviso quando o conteúdo navegava para fora do `srcdoc`, e montava o iframe mesmo a 50 mensagens de distância.
- Não havia testes de nada visual (nem de função pura de formatação).

## 2. Princípios

1. **Uma casca.** `UiCard` (cabeçalho com ícone, título, subtítulo e ações; corpo; rodapé) é o único lugar que sabe o que é "um cartão do Nexus". Modelo: `Card` + `CardHeader` do OpenUI.
2. **CSS em classes, não inline.** Tudo em `frontend/src/index.css`, seção "Intelligent UI", prefixo `nexus-ui-`. Variantes por `data-*` (`data-state`, `data-kind`, `data-variant`, `data-numeric`). Inline só para valores calculados (largura da barra, altura do iframe).
3. **Só tokens existentes** (spec §7, "sem cor nova"): `--surface-card`, `--surface-soft`, `--canvas`, `--hairline`, `--ink`, `--body`, `--muted`, `--muted-soft`, `--primary`, `--primary-active`, `--accent-dim`, `--success`, `--warning`, `--error`, `--cyan`. Tons intermediários via `color-mix()` dos mesmos tokens.
4. **Número é número.** `Intl.NumberFormat` com o locale do i18n em eixos, tooltip, caption de progresso e `range`; `font-variant-numeric: tabular-nums` onde há dígitos.
5. **Acessível por padrão.** Alvos ≥ 44 px no toque, `:focus-visible` com anel de 2 px no `--primary`, `aria-current="step"`, `aria-valuetext`, tabela `sr-only` do gráfico, `role="alert"` para erros, estado dos passos lido por leitor de tela.
6. **Movimento reduzido respeitado.** `prefers-reduced-motion` desliga transição da barra, pulso do passo ativo, animação de entrada do gráfico e esqueleto.
7. **Zero CLS mantido.** O esqueleto do `DynamicRenderer` reserva a altura real dos cartões novos; o sandbox fora da vista mostra um placeholder da mesma altura.

## 3. Entregue nesta fatia (2026-10-14)

Arquivos:

| Arquivo | O que mudou |
|---|---|
| `frontend/src/ui/components/UiCard.tsx` | **Novo.** `UiCard` (`as` div/section/form/figure, `icon`, `title`, `subtitle`, `actions`, `footer`, `variant` card/flush, `titleId`) e `UiCardAction` (botão de cabeçalho com ícone, rótulo, estado "pressionado" temporário). |
| `frontend/src/ui/lib/chartFormat.ts` + `.test.ts` | **Novo.** Funções puras: `distributeColors` (rampa do meio para fora, como o OpenUI), `seriesColors`, `tickCountFor` (1 tick a cada 40 px), `yDomainThroughZero`, `formatNumber` (locale, compacto ≥ 10 000), `truncateLabel`, `yAxisWidthFor`, `looksNumeric`, `chartToCsv`. 14 testes em node. |
| `frontend/src/ui/hooks/useMotionAndViewport.ts` | **Novo.** `useReducedMotion` e `useNearScreen` (IntersectionObserver com `rootMargin: 100%`, liga uma vez e não desliga). |
| `frontend/src/ui/components/ProgressCard.tsx` | Casca `UiCard`; percentual como métrica grande no cabeçalho; barra 8 px com `data-state` (verde ao chegar em 100%); caption "7 de 10" formatada; `aria-valuetext`. |
| `frontend/src/ui/components/ChecklistCard.tsx` | Linha do tempo: `<ol>` com círculo de 24 px (número, check, X ou pulso), conector vertical que some no último item, `aria-current="step"`, texto de estado `sr-only`, resumo "2 de 5" no cabeçalho. Ícones lucide (já dependência). |
| `frontend/src/ui/components/ChartCard.tsx` | Tooltip e legenda próprios (`nexus-ui-chart-tooltip`, `nexus-ui-chart-legend`), números por locale nos eixos/tooltip/tabela sr-only, eixo Y com piso 0 quando não há negativo e largura calculada pelo maior rótulo, 5 ticks para 220 px, rótulos do eixo X cortados com reticências e `preserveStartEnd`, grade só horizontal, cursor discreto, animação só sem `prefers-reduced-motion`, `maxBarSize` 48, ação "Copiar dados" (CSV no clipboard). `compare` continua barras agrupadas; `bar` usa só a primeira série. |
| `frontend/src/ui/components/ImageCard.tsx` | Mídia 96×96 (100% de largura e 140 px em telas ≤ 420 px), título/corpo em classes, facts em `<dl>` com grade `auto-fit` 110 px; fact numérico (`looksNumeric`) vira mini-métrica de 17 px. |
| `frontend/src/ui/components/ControlsCard.tsx` | `UiCard as="form"`; campos em grade `auto-fit` 170 px (texto e range ocupam a linha toda); inputs/select 38 px com hover e foco; `range` com valor em chip e limites min/max embaixo; resultado calculado em chip de acento no cabeçalho (reserva espaço quando vazio); botão primário 44 px que vira "✓ Enviado"; erro em `role="alert"`. Lógica de `send_message`/`set_model`/clamp/teto de 200 caracteres intacta. |
| `frontend/src/ui/components/SandboxCard.tsx` | `UiCard as="figure" variant="flush"`; barra com Reiniciar, Tela cheia e Baixar HTML; guarda de navegação (segundo `load` → aviso `role="alert"` + Reiniciar); iframe só monta quando o cartão chega a uma tela do viewport (placeholder com a mesma altura antes disso); `key={run}` remonta no Reiniciar; bridges de tema, altura e `nexus_action` iguais. |
| `frontend/src/ui/DynamicRenderer.tsx` | Esqueleto usa as classes da casca e as alturas novas (progress 88, passos 60 + 32 n, card 72/124 + 64 com facts, chart 280, controls 128 + 62 n, sandbox altura + 44). Container em classe. |
| `frontend/src/index.css` | Seção Intelligent UI reescrita: casca, ação, métrica, chip, progresso, passos, gráfico (tooltip, legenda), infocard/facts, campos, botão, sandbox (stage, placeholder, aviso, `:fullscreen`), `sr-only`, esqueleto, `prefers-reduced-motion`. |
| `frontend/src/i18n/locales/*.json` (8) | Chaves `intelligentUi.copyData`, `copied`, `restart`, `fullscreen`, `sandboxEscaped`, `stepsSummary`, `stepDone`, `stepActive`, `stepPending`, `stepError`. |

Validação: `npm test` (80 testes, 14 novos), `tsc --noEmit`, `vite build` (cartões continuam em chunks próprios: `UiCard` 1,4 kB, `chartFormat` 1,7 kB; `recharts` segue fora do chunk principal), `check-i18n.mjs intelligentUi` OK. Render dos seis cartões conferido por `renderToStaticMarkup` (sem erro de runtime) e num showcase local com os blocos de exemplo da spec nos dois temas.

Decisões tomadas na fatia:

- **Domínio do eixo Y.** O OpenUI força `[min(0, dataMin), max(0, dataMax)]`. No Recharts, domínio fixo nos dois extremos desliga os ticks "redondos" (daria 0 · 6 250 · 12 500). Por isso o piso é `0` quando não há negativo e o teto fica `'auto'`; com negativo, os dois ficam `'auto'` e o zero cai num tick de qualquer forma. `yDomainThroughZero` continua sendo usada para estimar a largura do eixo.
- **Paleta.** A primeira série é sempre `--primary` (identidade do Multi+); as demais seguem `--cyan`, `--warning`, `--success` e dois tons `color-mix`. `distributeColors` (meio para fora) fica disponível para quando houver rampa monocromática (gráfico de pizza, mapa de calor), não é usada no bar/line de hoje.
- **Sandbox fora da vista.** Diferente do AnswerUI, que desmonta cenas distantes por causa do teto de contextos WebGL, o `SandboxCard` só **adia** a montagem e depois mantém o iframe, para não perder o estado de uma calculadora quando o usuário rola a conversa. A cena 3D (plano 13) usará a versão que desmonta.
- **Ações do cabeçalho com 32 px no mouse e 44 px no toque** (`@media (pointer: coarse)`): o requisito de 44×44 da spec §7 vale para toque; no desktop 44 px deixava o cabeçalho alto demais.

## 4. Próximas fatias

### 4.1 Gráfico

- [ ] Rótulos do eixo X em duas linhas quando couber (medir com `getComputedTextLength` como o `xAxisLabelLayout.ts` do OpenUI) em vez de só cortar com reticências.
- [ ] `kind: "line"` com área suave opcional (`Area` com `fillOpacity` 0,08) quando há uma série só.
- [ ] Rótulo de eixo (`x_label`, `y_label`) e unidade (`unit`) como campos **opcionais** do bloco `chart` (plano 12 define o contrato); a tabela sr-only e o tooltip mostram a unidade.
- [ ] Esqueleto específico do gráfico (barras de altura variada), como o `Skeleton` do OpenUI, em vez do retângulo liso.
- [ ] Botão "Baixar CSV" além de copiar, quando `navigator.clipboard` não existir (http sem contexto seguro na rede local).

### 4.2 Casca e cartões

- [ ] `subtitle` nos blocos (campo opcional `subtitle` em `progress`, `chart`, `controls`, `sandbox`; `card` já tem `body`).
- [ ] Ícone por tipo de bloco no cabeçalho (lucide: `BarChart3`, `ListChecks`, `SlidersHorizontal`, `Box`), desligável.
- [ ] `ImageCard` com variante "capa" (`image.layout: "cover"`) para imagem larga em cima do texto.
- [ ] Facts com tendência (`delta: "+8%"`, `trend: "up" | "down"`), ao estilo `MetricIndicator`; define-se junto com o bloco `metric` do plano 12.
- [ ] Densidade compacta quando a bolha tem menos de 360 px (reduzir padding para 10/12).

### 4.3 Controles

- [ ] Validação de campo (`required`, `min`/`max` já existem; `pattern` para texto) com mensagem sob o campo, no padrão `rules` do OpenUI.
- [ ] `range` com marcas (`datalist`) quando `step` divide o intervalo em ≤ 10 partes.
- [ ] Vários resultados calculados (`computed[]`) — contrato no plano 12 (estado compartilhado).

### 4.4 Sandbox

- [ ] Play/Pause para conteúdo com `requestAnimationFrame` (hoje só a cena do plano 13 terá).
- [ ] Botão "Pedir correção" quando o iframe emite erro (`window.onerror` no bootstrap → `postMessage` tipado) — faz par com o laço de correção do plano 12.
- [ ] Abrir no painel de artefatos (`ArtifactPanel`) para o usuário editar o HTML.

### 4.5 Testes e ferramentas

- [ ] Testes de render com `@testing-library/react` + `jsdom` (devDependencies) para os seis cartões: estrutura, `aria-*`, estados (`data-state`), clique em Copiar/Reiniciar, `set_model` com lista vazia. Hoje o `npm test` roda em node puro (`--experimental-strip-types`), sem DOM; a adição é um script `test:dom` separado para não misturar.
- [ ] Página de showcase em dev (`frontend/src/ui/dev/Showcase.tsx`, só atrás de `import.meta.env.DEV`) com os blocos de exemplo da spec nos dois temas e larguras de bolha de 320 a 900 px. O harness usado nesta fatia ficou fora do repositório.
- [ ] Captura de tela automatizada (Playwright) dos cartões em claro/escuro para revisar regressão visual no PR.

## 5. Critérios de aceite da camada visual

- [x] Nenhum cartão tem `style={{ backgroundColor | border | borderRadius | boxShadow }}` próprio; tudo vem de `nexus-ui-card`.
- [x] Trocar o tema do app muda os seis cartões sem recarregar iframe (tema vai por `postMessage`).
- [x] `prefers-reduced-motion: reduce` → barra sem transição, passo ativo sem pulso, gráfico sem animação, esqueleto parado.
- [x] Números em eixos, tooltip, caption e `range` seguem o locale do i18n (`pt-BR` → `1.234,5`; `en-US` → `1,234.5`).
- [x] Gráfico com 1 série usa `--primary`; com 2+ séries, cores distintas e legenda.
- [x] Passo ativo tem `aria-current="step"`; estado de cada passo é lido por leitor de tela.
- [x] Sandbox: Reiniciar remonta o iframe; navegação para fora vira aviso com Reiniciar; iframe só monta perto do viewport; placeholder tem a mesma altura.
- [x] `tsc`, `vite build`, `npm test` e `check-i18n.mjs intelligentUi` limpos.
- [x] Testes de render dos cartões (cobertos na suíte `scripts/tests/*.ui.tsx` via `npm run test:ui` para os cartões nativos, tabelas, gráficos, controles, sandbox e cenas 2D/3D).
- [ ] Captura visual em claro/escuro revisada no PR (4.5).
