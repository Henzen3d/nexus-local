# Plano 12 — validação do passo 7 (12.3 Bloco options)

**Data:** 2026-10-14. Base: `main` no commit `9bb87a6` (PR #18 mesclado) + commit `40433cf` (passo 5) + commit `fda70da` (passo 6). Implementação no branch da sessão `arena/3faf891b-nexus-local`; sem merge automático nem deploy.

## Resultados reais

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **517 passed, 1 skipped, 14 warnings**, exit 0, 74,98 s |
| `cd frontend && npm test` | **125 testes unitários + 8 testes de componente React**, todos passaram, exit 0 |
| `cd frontend && npx tsc --noEmit` | Sem erros, exit 0 |
| `cd frontend && npm run build` | TypeScript + Vite + service worker/PWA gerados com sucesso em 11,24 s, chunk `OptionsCard` isolado de 2,64 kB, exit 0 |
| `cd frontend && npm run check:i18n` | Subárvore `proactive`, 253 chaves, oito locales OK, exit 0 |
| `cd frontend && node scripts/check-i18n.mjs intelligentUi` | **47 chaves** (+5 novas chaves para options), oito locales OK (0 faltando, 0 extras, 0 duplicadas), exit 0 |
| `cd frontend && npm run check:i18n:all` | **Falhou**, exit 1, pendência global preexistente em seis locales; veja issue #17 |
| `git diff --check` | Sem problemas de whitespace, exit 0 |

O pytest foi executado pelo Python da `.venv`, com `backend/tests/conftest.py` redirecionando `DB_PATH` antes de importar `backend.database` para um SQLite em diretório temporário (`nexuslocal-tests-*`), removido ao final. Nenhum teste foi executado contra `nexuslocal.db` de produção.

### Avisos observados (não ocultados)

- Pytest: deprecações de `pydantic` (`protected_namespaces`, `dict()`), eventos `on_event` do FastAPI, e `PytestUnhandledThreadExceptionWarning` de thread do aiosqlite fechando event loop. Nenhum filtro foi alterado para escondê-los.
- Build: aviso de chunks maiores que 500 kB após minificação.
- Testes de UI utilizam `react-test-renderer` e stubs determinísticos no Node test runner (`scripts/test-correction-ui.mjs` executando `scripts/tests/options.ui.tsx` e `scripts/tests/*.ui.tsx`).

## i18n global — pendência separada

[Issue #17 — completar traduções ausentes em seis locales](https://github.com/Henzen3d/nexus-local/issues/17).

5 novas chaves traduzidas nos 8 idiomas para a subárvore `intelligentUi`:
- `optionsSingleHint`: dica para seleção única ("Selecione uma opção").
- `optionsMultipleHint`: dica para seleção múltipla ("Selecione uma ou mais opções").
- `optionsOther`: rótulo para a alternativa livre ("Outro: especifique").
- `optionsSubmit`: rótulo do botão de confirmação ("Enviar resposta").
- `optionsAnswered`: indicação de resposta já submetida ("Respondido: {choice}").

Total de 47 chaves de `intelligentUi` 100% completas nos oito locales (`de-DE`, `en-US`, `es-419`, `es-ES`, `fr-FR`, `ja`, `ko`, `pt-BR`).

## Cobertura adicionada

- **Contrato e Catálogo Modular (`backend/ui_blocks/catalog_modules/options.txt`):**
  - Módulo `options` adicionado ao catálogo sob demanda via gatilhos de `should_offer.py` (`escolh`, `selecion`, `prefer`, `qual dos/das`, `opções`, `enquetes`, `alternativas`).
  - Orçamento respeitado: módulo com 170 caracteres / ~43 tokens.
- **Validação e Paridade Backend/Frontend (`backend/ui_blocks/validate.py` e `frontend/src/lib/nexusUi.ts`):**
  - Validação de `question` (1 a 160 caracteres), `options` (2 a 6 itens, `label` obrigatório com 1 a 80 caracteres, `description` opcional até 160 caracteres).
  - Auto-healing tolerante: se `value` for omitido em uma opção, preenche automaticamente a partir de `id` ou `label`.
  - Modos suportados: `mode: "single"` (padrão) e `mode: "multiple"`.
  - Suporte a campo aberto: `allow_other: boolean` (padrão `false`).
  - Ação associada: `action: { type: "send_message", text_template: "..." }`, exigindo que `text_template` contenha `{choice}`.
  - Subteto estrito: máximo de 1 bloco `options` por envelope (`MAX_BLOCKS_PER_TYPE['options'] = 1`).
  - Diagnósticos estruturados amigáveis mapeados em `diagnostics.py` e espelhados em `nexusUi.ts`.
- **Componente Visual (`frontend/src/ui/components/OptionsCard.tsx`):**
  - Casca padrão `UiCard` com ícone temático de opções e título.
  - Layout em grade responsiva `.nexus-ui-options__grid` com cards selecionáveis `.nexus-ui-option-card`.
  - Comportamento de envio por gesto explícito do usuário:
    - No modo `single` sem `allow_other`: clique direto na opção seleciona e envia imediatamente via `onSendMessage`.
    - No modo `multiple` ou quando `allow_other` é utilizado com texto digitado: botão primário "Enviar resposta" exige clique explícito.
  - Bloqueio e estado pós-submissão: uma vez enviada a resposta, o card desabilita as opções, marca `data-submitted="true"` e exibe badge de check com a resposta escolhida (`optionsAnswered`).
  - Respeito à transmissão de stream: prop `streaming?: boolean` desabilita interações prematuras antes do envelope fechar.
- **Testes Abrangentes:**
  - 5 novos testes de validação, limites, auto-healing, rejeições e gatilhos em `backend/tests/test_ui_blocks.py`.
  - Testes unitários de paridade em `frontend/src/lib/nexusUi.test.ts`.
  - Testes visuais e de interação React com `react-test-renderer` em `frontend/scripts/tests/options.ui.tsx`.
