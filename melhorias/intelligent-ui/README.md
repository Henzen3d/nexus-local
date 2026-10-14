# Intelligent UI — documentação e planos

Spec, planos e registro de auditoria do Intelligent UI. **O código das Fases 1 a 7 está implementado no repositório** (ver seção *Estado*). A flag nasce desligada (`INTELLIGENT_UI_ENABLED` no `.env`, ou o toggle em Configurações → Ferramentas → Interface Inteligente, que manda sobre o `.env`) e, desde as correções de 2026-10-14, desliga o recurso inteiro: catálogo, extração, persistência, `stream_end.ui_blocks` e render.

O Multi+ continua o frontend atual (React 18, Vite, Zustand, Vanilla CSS). O sistema adota a estratégia do **Generative UI Spectrum** (inspirada nos lançamentos de outubro de 2026: ChatGPT Intelligent UI e [CopilotKit Open Intelligent UI](https://github.com/CopilotKit/OpenIntelligentUI)):
1. **Nível 1 — Controlled Generative UI (Fases 1 a 6):** O modelo entrega um JSON pequeno e validado (`nexus-ui/1`). O frontend renderiza através de componentes nativos rápidos e seguros, 100% integrados aos design tokens do Multi+ (`var(--primary)`, `var(--surface-card)`, etc.).
2. **Nível 2 — Open Generative UI & Sandboxed Tools (Fase 7):** Micro-ferramentas dinâmicas (calculadoras reativas, simulações, algoritmos interativos, gráficos avançados) geradas sob demanda e isoladas em iframe sandbox seguro, com bridge de temas do Nexus, prevenção de layout shifts e exportação standalone com 1 clique.

## O que esta pasta cobre

Famílias de blocos nativos (Nível 1) e ferramentas sob demanda (Nível 2):

1. Indicadores e barras de progresso (`progress`, `checklist`)
2. Cartões e imagens (`card`)
3. Gráficos nativos com Recharts (`chart`)
4. Botões, formulários e calculadoras reativas com controle local (`controls`)
5. Extensão de ferramentas interativas em sandbox seguro com bridge bidirecional (`sandbox`)

Fora desta pasta: reescrever o Multi+, substituir o painel de artefatos lateral, Thesys, instalar SDKs pesados de terceiros, SSE paralelo ou executar scripts desprotegidos na bolha principal.

## Leitura

| Arquivo | Para quê |
|---|---|
| [00-visao-e-spec.md](00-visao-e-spec.md) | Contrato e especificação geral. Leia antes de codar. |
| [01-plano-fundacao.md](01-plano-fundacao.md) | Parser, validador, tabela, flag. Sem isso os outros planos não começam. |
| [02-plano-indicadores.md](02-plano-indicadores.md) | Progresso. Primeiro bloco visível. |
| [03-plano-cartoes-imagens.md](03-plano-cartoes-imagens.md) | Cartão e foto confiável. |
| [04-plano-graficos.md](04-plano-graficos.md) | Gráficos com o Recharts já instalado no projeto. |
| [05-plano-controles.md](05-plano-controles.md) | Formulários, calculadoras reativas e ações autorizadas. |
| [06-criterios-aceite.md](06-criterios-aceite.md) | Critérios rigorosos antes de ligar a flag. |
| [07-chatkit-referencia.md](07-chatkit-referencia.md) | Referência conceitual do ChatKit da OpenAI. |
| [08-open-intelligent-ui-referencia.md](08-open-intelligent-ui-referencia.md) | Referência profunda do CopilotKit OpenIntelligentUI (spectrum, sandbox, streaming anti-shift, theme bridge). |
| [09-plano-sandbox-e-exportacao.md](09-plano-sandbox-e-exportacao.md) | Fase 7: Micro-ferramentas sob demanda em sandbox isolado, theme bridge e exportação 1-click HTML. |
| [10-referencias-answerui-openui-openwebui.md](10-referencias-answerui-openui-openwebui.md) | Leitura de três repositórios de referência (AnswerUI, OpenUI, Open WebUI) com tabela de paridade contra o Intelligent UI do ChatGPT e o que adotar de cada um. |
| [11-plano-camada-visual.md](11-plano-camada-visual.md) | Camada visual compartilhada dos cartões nativos (`UiCard`, tokens, formatação por locale, movimento reduzido, montagem adiada). **Primeira fatia entregue em 2026-10-14.** |
| [12-plano-paridade-intelligent-ui.md](12-plano-paridade-intelligent-ui.md) | Paridade de funcionalidades: blocos `metric`, `table`, `callout`, `options`, `follow_up`; `chart` com `pie`; estado compartilhado; render progressivo; laço "Pedir correção"; catálogo modular; `Origin` no WebSocket. |
| [13-plano-cenas-2d-3d.md](13-plano-cenas-2d-3d.md) | Cenas 2D/3D: `sandbox` com `kind: "scene"`, runtime local three.js/canvas sem rede, `params`/`report`, barra Pausar/Reiniciar/Tela cheia. |
| [referencias-codigo/](referencias-codigo/) | Módulos prontos para uso: do OpenIntelligentUI (`sandbox-core.ts`, `design-tokens-bridge.ts`, `export-standalone.ts`, `visualization-criteria.py`, `open-gen-ui-prompt-skill.txt`), do AnswerUI/MIT para o plano 13 (`scene-protocol.ts`, `scene-runtime-core.ts`, `scene-document.ts`) e próprio para o plano 12 (`partial-json.ts`, scanner de envelope parcial). |

Ordem de execução: 01, depois 02, 03, 04, 05. O 06 acompanha cada fase, não espera o fim. A Fase 7 (plano 09) entra após a estabilização das fases nativas, aproveitando diretamente o código de `referencias-codigo/`. Os planos 11, 12 e 13 são aditivos e entram nessa ordem: 11 (visual, já iniciado), 12 (paridade, em passos independentes com flag desligada) e 13 (cenas, depois do laço de correção do 12).

## Estado

**Auditoria de código em 2026-10-14** (checkboxes atualizados em cada plano, com evidência e pendências anotadas).

| Fase | Plano | Situação | Evidência |
|---|---|---|---|
| 1 | 01-plano-fundacao | Implementada | `backend/ui_blocks/validate.py`, `extract.py`, `config.py`; tabelas `message_ui_blocks` e `intelligent_ui_config` em `database.py`; `save_ui_blocks` em `persist_turn.py`; `routers/intelligent_ui.py`; `frontend/src/lib/nexusUi.ts`, `ui/hooks/useIntelligentUi.ts`, `components/IntelligentUiSettings.tsx`. Flag fecha o recurso inteiro; teste de turno em `tests/test_intelligent_ui_turn.py`. |
| 2 | 02-plano-indicadores | Implementada | `ProgressCard.tsx`, `ChecklistCard.tsx`, `DynamicRenderer.tsx` (gate da flag + skeleton), `handleUiProgress` no store (buffer `streamingUiBlocks` durante o stream, mescla no `finalizeStream`), `should_offer.py`, `catalog.txt`, gate em `chat.py`, telemetria em `ui_blocks/telemetry.py`. |
| 3 | 03-plano-cartoes-imagens | Implementada | `ImageCard.tsx`, `isAllowedImageUrl` nos dois lados; hosts e flag privada chegam ao frontend por `GET /api/intelligent-ui/config`. Falta só teste de render do cartão. |
| 4 | 04-plano-graficos | Implementada | `ChartCard.tsx` (bar/line/compare, tabela sr-only). `AdminPanel` lazy em `App.tsx`: `recharts` em chunk próprio, fora do chat. |
| 5 | 05-plano-controles | Implementada | `ControlsCard.tsx`, `lib/safeMath.ts`. `set_model` lista `models` do store, some com lista vazia, erro curto para id desconhecido; a11y (`htmlFor`, `aria-live`, `role=alert`), `maxLength` 200, clamp de número/range. |
| 6 | 06-criterios-aceite | 37 de 44 itens atendidos | Bloqueadores para ligar em produção listados no topo do arquivo. |
| 7 | 09-plano-sandbox-e-exportacao | Implementada | `SandboxCard.tsx`, `themeBridge.ts`, `hooks/useResolvedTheme.ts`, `lib/exportStandalone.ts` + testes de função pura. Tema reativo por `postMessage`, CSP `default-src 'none'` (esm.sh só para módulos), `lang` do i18n. |

Testes que passam: `backend/tests/test_ui_blocks.py` (15), `frontend/src/lib/nexusUi.test.ts` (7), `frontend/src/ui/lib/safeMath.test.ts` (4), `frontend/src/ui/lib/chartFormat.test.ts` (14). `tsc` e `vite build` limpos. Não há testes de render dos componentes (só smoke de SSR manual; o `test:dom` com jsdom está previsto no plano 11 §4.5).

**Camada visual (plano 11, primeira fatia em 2026-10-14):** os seis cartões (`ProgressCard`, `ChecklistCard`, `ImageCard`, `ChartCard`, `ControlsCard`, `SandboxCard`) passaram a compartilhar `ui/components/UiCard.tsx` (cabeçalho, ícone, ações, rodapé, erro) e as classes `nexus-ui-*` do `index.css`, só com tokens do Nexus; números formatados por locale (`ui/lib/chartFormat.ts`), ticks por altura, paleta derivada de `--primary`, tooltip e legenda próprios, `prefers-reduced-motion` respeitado (`ui/hooks/useMotionAndViewport.ts`), sandbox monta só perto da vista e nunca desmonta, alvos de 44 px em toque. Dez chaves novas de i18n (`intelligentUi.*`) nos oito idiomas.

Desvios de contrato adotados como "auto-healing" nos dois validadores (fora da spec, mas simétricos): `v` é forçado para 1; bloco sem `type` é inferido pelos campos; `kind` inválido de chart vira `bar`; `controls` aceita até 6 fields; fences ```` ```chart ````/```` ```ui ```` são aceitos como fallback. Assimetria conhecida: ação desconhecida em `controls` descarta o bloco no Python e vira `send_message` com template padrão no TS.

Site em multi.mob.tec.br só muda após rebuild da imagem.

