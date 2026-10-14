# Plano 12 — validação do passo 5 (12.2 e 12.8)

**Data:** 2026-10-14. Base: `main` no commit `9bb87a6` (PR #18 mesclado). Implementação no branch da sessão `arena/3faf891b-nexus-local`; sem merge automático nem deploy.

## Resultados reais

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **512 passed, 1 skipped, 14 warnings**, exit 0, 72,99 s |
| `cd frontend && npm test` | **117 testes unitários + 4 testes de componente React**, todos passaram, exit 0 |
| `cd frontend && npx tsc --noEmit` | Sem erros, exit 0 |
| `cd frontend && npm run build` | TypeScript + Vite + service worker/PWA gerados (`TableCard` em chunk lazy de 4,14 kB), exit 0 |
| `cd frontend && npm run check:i18n` | Subárvore `proactive`, 253 chaves, oito locales OK, exit 0 |
| `cd frontend && node scripts/check-i18n.mjs intelligentUi` | **42 chaves**, oito locales OK (0 faltando, 0 extras, 0 duplicadas), exit 0 |
| `cd frontend && npm run check:i18n:all` | **Falhou**, exit 1, pendência global preexistente em seis locales; veja issue #17 |
| `git diff --check` | Sem problemas de whitespace |

O pytest foi executado pelo Python da `.venv`, com `backend/tests/conftest.py` redirecionando `DB_PATH` antes de importar `backend.database` para um SQLite em diretório temporário (`nexuslocal-tests-*`), removido ao final. Nenhum teste foi executado contra `nexuslocal.db` de produção.

### Avisos observados (não ocultados)

- Pytest: deprecações de `pydantic` (`protected_namespaces`, `dict()`), eventos `on_event` do FastAPI, e `PytestUnhandledThreadExceptionWarning` de thread do aiosqlite fechando event loop. Nenhum filtro foi alterado para escondê-los.
- Build: aviso de chunks maiores que 500 kB após minificação.
- Não foi realizado smoke E2E em navegador real. O teste de UI usa componentes React reais com `react-test-renderer` e stubs determinísticos no Node runner.

## i18n global — pendência separada

[Issue #17 — completar traduções ausentes em seis locales](https://github.com/Henzen3d/nexus-local/issues/17).

| Locale | Ausentes |
| --- | ---: |
| de-DE | 277 |
| es-419 | 277 |
| es-ES | 127 |
| fr-FR | 277 |
| ja | 277 |
| ko | 277 |

`en-US` e `pt-BR`: nenhuma ausente. As cinco novas chaves do Passo 5 (`tableTitle`, `tableShowAll`, `tableShowLess`, `tableOthers`, `pieTotal`) foram traduzidas nos oito idiomas (`pt-BR`, `en-US`, `es-ES`, `es-419`, `fr-FR`, `de-DE`, `ja`, `ko`); não se copiou inglês para satisfazer o checker. O checker permanece estrito e intacto.

## Cobertura adicionada

- **Tabela (`table`) no backend e frontend:**
  - Contrato: 2 a 8 colunas tipadas (`text`, `number` com unit opcional, `date` ISO YYYY-MM-DD), até 50 linhas, ordenação opcional `sort: { key, dir: "asc"|"desc" }`.
  - Tolerância e auto-healing: células não conformes convertidas para `None`/`null` (renderizadas como `—`), sem descartar a linha; colunas sem label usam a key.
  - Subteto de 1 bloco de tabela por envelope (`MAX_BLOCKS_PER_TYPE['table'] = 1`).
  - Inferência automática quando há `columns` e `rows`.
  - Módulo de catálogo modular `backend/ui_blocks/catalog_modules/table.txt` integrado a `build_catalog` e gatilhos de `should_offer` (`tabela`, `planilha`, `ranking`, etc.). Orçamento de tokens <= 450 preservado.
- **Melhorias de Gráfico (`chart`) no backend e frontend:**
  - `kind: "pie"` adicionado como tipo válido de chart. Exige 1 série e de 2 a 8 rows.
  - Auto-agregação em fatias de pizza: quando `rows > 8`, as 7 maiores são mantidas e as excedentes somadas em uma 8ª fatia nomeada `"Outros"`.
  - Paleta de pizza (`pieColors`): rampa harmônica derivada dos tokens do sistema via `PIE_RAMP`.
  - Suporte a `stacked: true` em `kind: "compare"`, com cálculo do domínio Y acumulado via `yDomainThroughZero(rows, keys, true)`.
  - Suporte a `unit`, `x_label` e `y_label` nos eixos e tooltips.
- **Componentes React e UX:**
  - `TableCard`: casca `UiCard`, ação "Copiar dados" (CSV com `tableToCsv`), cabeçalhos interativos para ordenação asc/desc com `aria-sort`, alinhamento numérico à direita com `tabular-nums`, colapso acima de 10 linhas com botão "Mostrar todas" / "Mostrar menos".
  - `ChartCard`: renderização de `pie` com `PieChart`/`Pie`/`Cell` do Recharts, tooltip com porcentagem relativa e unidade, legenda e tabela acessível oculta (`nexus-ui-sr-only`).
  - `DynamicRenderer`: registro lazy de `TableCard` com altura reservada para prevenção de layout shift.
  - `index.css`: estilização completa das classes `.nexus-ui-table*` com tokens do Multi+.
