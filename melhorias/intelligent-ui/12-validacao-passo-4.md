# Plano 12 — validação do passo 4 (12.6)

**Data:** 2026-10-14. Base: `main` no commit `5f5c23e` (PR #16 mesclado). Implementação no branch da sessão `arena/a716e476-nexus-local`; sem merge automático.

## Resultados reais

| Comando | Resultado |
| --- | --- |
| `.venv/bin/python -m pytest backend/tests -q` | **505 passed, 1 skipped, 16 warnings**, exit 0, 77,56 s |
| `cd frontend && npm test` | **113 testes unitários + 2 testes de componente/ponte de runtime**, todos passaram, exit 0 |
| `cd frontend && npx tsc --noEmit` | Sem erros, exit 0 |
| `cd frontend && npm run build` | TypeScript + Vite + service worker/PWA gerados, exit 0 |
| `cd frontend && npm run check:i18n` | Subárvore `proactive`, 238 chaves, oito locales OK, exit 0 |
| `cd frontend && node scripts/check-i18n.mjs intelligentUi` | 37 chaves, oito locales OK, exit 0 |
| `cd frontend && npm run check:i18n:all` | **Falhou**, exit 1, pendência preexistente em seis locales; veja issue #17 |
| `git diff --check` | Sem problemas de whitespace |

O pytest foi executado pelo Python da `.venv`, com `backend/tests/conftest.py` redirecionando `DB_PATH` antes de importar `backend.database` para um SQLite em diretório temporário (`nexuslocal-tests-*`), removido ao final. Nenhum teste foi executado contra `nexuslocal.db` de produção.

### Avisos observados (não ocultados)

- Pytest: deprecações de `crypt`, eventos `on_event` do FastAPI, BlockingPortal do AnyIO e `dict()` do Pydantic. A execução final também reportou dois `PytestUnhandledThreadExceptionWarning` de threads do aiosqlite com `RuntimeError: Event loop is closed`, atribuídos a `test_reasoning_effort.py` e `test_ws_origin.py`. Não causaram falha; os novos testes focados de diagnósticos/turno passaram sem esses avisos. Não se alterou filtro de warnings para ocultá-los.
- Build: aviso de chunks maiores que 500 kB após minificação. Nenhum limite/checker foi enfraquecido.
- Não foi realizado smoke E2E em navegador real. O teste de UI usa componentes React reais com `react-test-renderer`, hooks/API determinísticos e execução em VM do bootstrap real do sandbox; não é apresentado como E2E.

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

`en-US` e `pt-BR`: nenhuma ausente. Uma chave extra em cada locale não-base é aviso, não a causa da falha. As oito chaves novas do laço de correção foram traduzidas nos oito idiomas; não se copiou inglês para satisfazer o checker. `check-i18n.mjs` permanece intacto.

## Cobertura adicionada

- Fixtures compartilhadas Python/TS para o mesmo JSON e fence: diagnóstico, subtetos/teto, rejeição parcial/total, versão, ações, URLs, inferência e manutenção do auto-healing de IDs.
- Integração WebSocket: flag desligada sem campos novos; rejeição total/JSON inválido com erros limitados; prosa persistida sem fence; oferta → pedido → resposta corrigida; replay não infla contadores; catálogo no turno de correção.
- Endpoint de runtime: autenticação, owner-only (404), flag desligada, sandbox persistido e deduplicação.
- Componente React: nenhum envio ao montar, flag, desabilitado no stream, retry offline, clique duplo, remount e trava compartilhada entre erro de validação/runtime.
- Sandbox: captura de `error`/`unhandledrejection`, limite 500, `event.source` incorreto ignorado e CSP/sandbox preservados.
- Telemetria: contagens por modelo/códigos sem payload, correlação owner-scoped, limite de 2048 mensagens.
