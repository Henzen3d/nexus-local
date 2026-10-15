# Plano 12 — validação do passo 8 (12.7 Estado compartilhado / expressões no safeMath)

**Data:** 2026-10-15. Base: `main` no commit `9bb87a6` (PR #18 mesclado) + commit `40433cf` (passo 5) + commit `fda70da` (passo 6) + commit `5fd0094` (passo 7). Implementação no branch da sessão `arena/3faf891b-nexus-local`; sem merge automático nem deploy.

## Resultados reais

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **525 passed, 1 skipped, 14 warnings**, exit 0, 75,42 s |
| `cd frontend && npm test` | **129 testes unitários + 9 testes de componente React**, todos passaram, exit 0 |
| `cd frontend && npx tsc --noEmit` | Sem erros, exit 0 |
| `cd frontend && npm run build` | TypeScript + Vite + service worker/PWA gerados com sucesso em 10,96 s, chunk `messageUiState` isolado de 0,58 kB, exit 0 |
| `cd frontend && npm run check:i18n` | Subárvore `proactive`, 253 chaves, oito locales OK, exit 0 |
| `cd frontend && node scripts/check-i18n.mjs intelligentUi` | 47 chaves, oito locales OK (0 faltando, 0 extras, 0 duplicadas), exit 0 |
| `cd frontend && npm run check:i18n:all` | **Falhou**, exit 1, pendência global preexistente em seis locales; veja issue #17 |
| `git diff --check` | Sem problemas de whitespace, exit 0 |

O pytest foi executado pelo Python da `.venv`, com `backend/tests/conftest.py` redirecionando `DB_PATH` antes de importar `backend.database` para um SQLite em diretório temporário (`nexuslocal-tests-*`), removido ao final. Nenhum teste foi executado contra `nexuslocal.db` de produção.

### Avisos observados (não ocultados)

- Pytest: deprecações de `pydantic` (`protected_namespaces`, `dict()`), eventos `on_event` do FastAPI, e `PytestUnhandledThreadExceptionWarning` de thread do aiosqlite fechando event loop. Nenhum filtro foi alterado para escondê-los.
- Build: aviso de chunks maiores que 500 kB após minificação.
- Testes de UI utilizam `react-test-renderer` e stubs determinísticos no Node test runner (`scripts/test-correction-ui.mjs` executando `scripts/tests/reactive.ui.tsx` e demais suítes).

## i18n global — pendência separada

[Issue #17 — completar traduções ausentes em seis locales](https://github.com/Henzen3d/nexus-local/issues/17).

Total de 47 chaves de `intelligentUi` 100% completas nos oito locales (`de-DE`, `en-US`, `es-419`, `es-ES`, `fr-FR`, `ja`, `ko`, `pt-BR`).

## Cobertura adicionada

- **Fixtures Compartilhadas (`backend/tests/fixtures/expressions.json`):**
  - 17 casos de teste canônicos cobrindo expressões aritméticas válidas (`+`, `-`, `*`, `/`), funções permitidas (`round`, `pow`, `abs`, `floor`, `ceil`, `sqrt`, `min`, `max`), divisão por zero segura, precedência de operadores e erros sintáticos/proibidos (`^`, `unknown_function`, `invalid_arity`, `unbalanced_parentheses`, `invalid_identifier`, `syntax_error`, `empty_expression`).
- **Validador Sintático e de Ciclos no Backend (`backend/ui_blocks/expr.py` e `backend/tests/test_ui_expr.py`):**
  - Parser recursivo descendente para expressões matemáticas com teto de 160 caracteres e 40 tokens.
  - Ordenação topológica e detecção estática de ciclos entre campos computados (`check_dependency_cycles`).
  - Integração em `backend/ui_blocks/validate.py` para permitir expressões `=...` em campos numéricos de `metric`, `card`, `progress`, `table` e `chart`.
  - Suporte à lista de computeds (`computed: list[dict]`) no bloco `controls` e validação de dependências circulares.
  - Pós-validação de variáveis usadas em expressões contra `all_control_ids` do envelope.
  - Diagnósticos estruturados em `backend/ui_blocks/diagnostics.py` para erros de expressão e controles duplicados.
- **Motor Matemático e Paridade no Frontend (`frontend/src/ui/lib/safeMath.ts` e `safeMath.test.ts`):**
  - Tokenizador e avaliador seguro com paridade exata aos casos de teste da fixture `expressions.json`.
  - Funções matemáticas permitidas: `round`, `pow`, `abs`, `floor`, `ceil`, `sqrt`, `min`, `max`.
  - Divisão por zero retorna 0 de forma segura sem lançar exceções.
  - Detecção e rejeição do operador ambíguo `^`.
- **Estado Reativo por Mensagem (`frontend/src/ui/state/messageUiState.ts`):**
  - Store Zustand isolado por mensagem (`states[messageId][fieldId]`), prevenindo vazamento de estado entre turnos de conversa.
  - Hook reativo `useResolvedValue(messageId, rawValue)` para reavaliação automática e eficiente de expressões quando sliders ou campos de `controls` mudam.
- **Integração Visual nos Componentes (`frontend/src/ui/components/`):**
  - `ControlsCard`: publicação instantânea de valores de campos e computeds encadeados no store reativo; interpolação de campos e computeds no template de ação.
  - `MetricCard`: resolução de valores numéricos via `useResolvedValue`.
  - `ProgressCard`: resolução reativa de `value` via `useResolvedValue` com `aria-valuenow` numérico.
  - `TableCard`: resolução memoizada de células numéricas com expressões aritméticas contra o estado do envelope; ordenação e exportação CSV sobre valores resolvidos.
  - `ChartCard`: avaliação reativa memoizada de linhas numéricas; desativação de animações de transição Recharts (`isAnimationActive={false}`) em dados dinâmicos para prevenir layout shifts/CLS ao arrastar sliders (spec §7).
  - `DynamicRenderer` e `MessageBubble`: encaminhamento de `messageId` para todos os cartões do envelope.
- **Testes Abrangentes:**
  - 4 novos testes em `test_ui_expr.py` e 4 novos testes em `test_ui_blocks.py` (totalizando 525 testes backend aprovados).
  - Testes de paridade de expressões e computeds em `safeMath.test.ts` e `nexusUi.test.ts` (129 testes unitários frontend aprovados).
  - Teste de integração de UI reativa em `frontend/scripts/tests/reactive.ui.tsx` (9 testes de UI aprovados).
