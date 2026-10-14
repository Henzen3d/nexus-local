# Intelligent UI — documentação e planos

Spec, planos e registro de auditoria do Intelligent UI. **O código das Fases 1 a 7 está implementado no repositório** (ver seção *Estado*). A flag `INTELLIGENT_UI_ENABLED` nasce desligada e hoje controla apenas a injeção do catálogo no prompt.

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
| [referencias-codigo/](referencias-codigo/) | Módulos e rotinas extraídos do OpenIntelligentUI prontos para uso (`sandbox-core.ts`, `design-tokens-bridge.ts`, `export-standalone.ts`, etc.). |

Ordem de execução: 01, depois 02, 03, 04, 05. O 06 acompanha cada fase, não espera o fim. A Fase 7 (plano 09) entra após a estabilização das fases nativas, aproveitando diretamente o código de `referencias-codigo/`.

## Estado

**Auditoria de código em 2026-10-14** (checkboxes atualizados em cada plano, com evidência e pendências anotadas).

| Fase | Plano | Situação | Evidência |
|---|---|---|---|
| 1 | 01-plano-fundacao | Implementada, 1 pendência | `backend/ui_blocks/validate.py`, `extract.py`; tabela `message_ui_blocks` em `database.py`; `save_ui_blocks` em `persist_turn.py`; `frontend/src/lib/nexusUi.ts`. Pendência: a flag não desliga extração/persistência/render. |
| 2 | 02-plano-indicadores | Implementada | `ProgressCard.tsx`, `ChecklistCard.tsx`, `DynamicRenderer.tsx`, `handleUiProgress` no store, `should_offer.py`, `catalog.txt`, gate em `chat.py`. |
| 3 | 03-plano-cartoes-imagens | Implementada, 1 pendência | `ImageCard.tsx`, `isAllowedImageUrl` nos dois lados. Pendência: frontend não recebe `INTELLIGENT_UI_IMAGE_HOSTS`/`ALLOW_PRIVATE_HTTP`. |
| 4 | 04-plano-graficos | Implementada, 1 pendência | `ChartCard.tsx` (bar/line/compare, tabela sr-only). Pendência: `recharts` ainda no chunk principal via `AdminPanel` estático. |
| 5 | 05-plano-controles | Implementada, `set_model` parcial | `ControlsCard.tsx`, `lib/safeMath.ts`. Pendência: select de `set_model` usa options do modelo, não `models` do store. |
| 6 | 06-criterios-aceite | 37 de 44 itens atendidos | Bloqueadores para ligar em produção listados no topo do arquivo. |
| 7 | 09-plano-sandbox-e-exportacao | Implementada, sem testes | `SandboxCard.tsx`, `themeBridge.ts`, `lib/exportStandalone.ts`. Desvio: `importmap` para `esm.sh`. |

Testes que passam: `backend/tests/test_ui_blocks.py` (15), `frontend/src/lib/nexusUi.test.ts` (7), `frontend/src/ui/lib/safeMath.test.ts` (4). `tsc` e `vite build` limpos. Não há testes de render dos componentes.

Desvios de contrato adotados como "auto-healing" nos dois validadores (fora da spec, mas simétricos): `v` é forçado para 1; bloco sem `type` é inferido pelos campos; `kind` inválido de chart vira `bar`; `controls` aceita até 6 fields; fences ```` ```chart ````/```` ```ui ```` são aceitos como fallback. Assimetria conhecida: ação desconhecida em `controls` descarta o bloco no Python e vira `send_message` com template padrão no TS.

Site em multi.mob.tec.br só muda após rebuild da imagem.

