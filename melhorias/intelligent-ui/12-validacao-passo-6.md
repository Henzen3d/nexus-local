# Plano 12 — validação do passo 6 (12.5 Render progressivo / partial JSON no stream)

**Data:** 2026-10-14. Base: `main` no commit `9bb87a6` (PR #18 mesclado) + commit `40433cf` (passo 5). Implementação no branch da sessão `arena/3faf891b-nexus-local`; sem merge automático nem deploy.

## Resultados reais

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **512 passed, 1 skipped, 14 warnings**, exit 0, 73,19 s |
| `cd frontend && npm test` | **123 testes unitários + 5 testes de componente React**, todos passaram, exit 0 |
| `cd frontend && npx tsc --noEmit` | Sem erros, exit 0 |
| `cd frontend && npm run build` | TypeScript + Vite + service worker/PWA gerados com sucesso em 11,12 s, exit 0 |
| `cd frontend && npm run check:i18n` | Subárvore `proactive`, 253 chaves, oito locales OK, exit 0 |
| `cd frontend && node scripts/check-i18n.mjs intelligentUi` | **42 chaves**, oito locales OK (0 faltando, 0 extras, 0 duplicadas), exit 0 |
| `cd frontend && npm run check:i18n:all` | **Falhou**, exit 1, pendência global preexistente em seis locales; veja issue #17 |
| `git diff --check` | Sem problemas de whitespace |

O pytest foi executado pelo Python da `.venv`, com `backend/tests/conftest.py` redirecionando `DB_PATH` antes de importar `backend.database` para um SQLite em diretório temporário (`nexuslocal-tests-*`), removido ao final. Nenhum teste foi executado contra `nexuslocal.db` de produção.

### Avisos observados (não ocultados)

- Pytest: deprecações de `pydantic` (`protected_namespaces`, `dict()`), eventos `on_event` do FastAPI, e `PytestUnhandledThreadExceptionWarning` de thread do aiosqlite fechando event loop. Nenhum filtro foi alterado para escondê-los.
- Build: aviso de chunks maiores que 500 kB após minificação.
- Testes de UI utilizam `react-test-renderer` e stubs determinísticos no Node test runner (`scripts/test-correction-ui.mjs` executando `scripts/tests/*.ui.tsx`).

## i18n global — pendência separada

[Issue #17 — completar traduções ausentes em seis locales](https://github.com/Henzen3d/nexus-local/issues/17).

Nenhuma nova string voltada ao usuário foi introduzida no passo 6 (o esqueleto de carregamento é puramente visual e marcado com `aria-hidden="true"`). As 42 chaves existentes de `intelligentUi` seguem 100% completas nos oito locales.

## Cobertura adicionada

- **Scanner de Stream (`frontend/src/lib/nexusUiStream.ts`):**
  - Autômato tolerante que inspeciona o fence ````nexus-ui```` durante a transmissão token a token de SSE.
  - Extrai blocos individuais assim que a chave de fechamento `}` correspondente é encontrada dentro de `blocks: [ ... ]`.
  - Ignora chaves `}` aninhadas e chaves literais dentro de strings (com tratamento de escapes `\"`).
  - Identifica `pendingType`: quando um bloco abriu `{ "type": "..."` mas ainda não fechou, detecta o tipo em construção para que a UI possa reservar o esqueleto com a altura exata.
  - Invariante de prefixo validado por teste de propriedade: para qualquer corte no stream, `scanPartialEnvelope(prefix).blocks` é prefixo exato de `scanPartialEnvelope(full).blocks`.
- **Renderização Progressiva e Bloqueio de Interações:**
  - `ControlsCard`: prop `streaming?: boolean`. Enquanto `streaming=true`, campos de texto, número, faixa (`range`), seleção e o botão de submissão ficam `disabled` e o `onSubmit` ignora tentativas de envio prematuras.
  - `FollowUpCard`: prop `streaming?: boolean`. Botões de sugestão ficam `disabled` enquanto `streaming=true` ou `isStreaming=true`, impedindo cliques acidentais durante a resposta.
  - `SandboxCard`: prop `streaming?: boolean`. Iframe não monta enquanto `streaming=true` (renderiza placeholder com altura reservada); botões de reiniciar, tela cheia e download HTML permanecem desabilitados até a conclusão da mensagem.
  - `DynamicRenderer`: recebe `streaming?: boolean` e `pendingType?: string | null`. Repassa `streaming` aos componentes filhos e renderiza o cartão esqueleto com altura reservada (`reservedHeight`) quando `pendingType` está ativo.
  - `MessageBubble` / `StreamingBubble`: integra `scanPartialEnvelope(deferredResponse)`, valida blocos parciais com `parseUiEnvelope({ v: 1, blocks })`, mescla com blocos do host via `mergeUiEnvelopes(streamingUiBlocks, modelEnvelope)` e alimenta o `DynamicRenderer` durante o stream.
