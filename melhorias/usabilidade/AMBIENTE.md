# Ambiente — NexusLocal (status pós-item 0)

> Atualizado automaticamente pelo loop de iteração. Não reimplemente o que já está verde.

---

## 1. Estado da Base (main commit `30dff45`)

| Verificação | Resultado |
|-------------|-----------|
| `judge.sh` | ✅ criado, 6/6 checks verdes (playwright skip — sem smoke.spec.ts) |
| Playwright | ✅ instalado (`frontend/package.json` devDependency `^1.64.1`), chromium headless-shell baixado |
| `test_computer_sandbox.py` | ✅ mock de `_capture_via_cdp` + `_capture_via_web_render`, decodifica base64 do `screenshot_url` |
| `safeMath.test.ts` | ✅ path relativo via `import.meta.url` |
| Backend pytest (container) | ✅ **641 passed, 1 skipped** |
| Frontend node tests | ✅ 7/7 verdes |
| `tsc --noEmit` | ✅ zero erros |
| Vite build | ✅ ~8s |
| streaming-paint-probe | ✅ 0 renders extras em bolhas antigas |
| message-actions-after-stream | ✅ copy/edit/delete funcionais |

---

## 2. Status dos Planos 01–05 da Auditoria Cirúrgica

| Plano | Commit | Arquivos-chave | Status |
|-------|--------|----------------|--------|
| **01** — Fusion: teto 4000 chars no Juiz + timeout salva texto parcial | `63a671e` | `fusion/orchestrator.py:84` (`JUDGE_BLOCK_MAX_CHARS=4000`), `:619` (`TIMEOUT_JUIZ=180`), `test_fusion_judge_budget.py` | ✅ 100% merged |
| **02** — Vision Relay: cache por `file_hash:model`, placeholder, timeout 25s | `4f6703f` + `458c22b` | `vision_relay/relay.py:21` (`vision_cache_key`), `:18` (`RELAY_IMAGE_TIMEOUT_S=25`), `:25` (`image_placeholder`), `test_vision_relay_fallback.py` (+222 linhas no merge) | ✅ 100% merged |
| **03** — Web Search: texto cercado em `<dados_web>` / `</dados_web>`, instrução não como ordem | `458c22b` | `web_search/formatter.py:1-5` (`WEB_FENCE_OPEN/CLOSE`, `fence_untrusted_web`), `orchestration/handle_attachments.py:279/286` (template injetado) | ✅ 100% merged |
| **04** — Context Window: resolve por API+registry (sem heurística por substring), poda salva últimas 12 msgs + evento `history_trimmed` | `458c22b` | `orchestration/context_window.py:8` (`resolve_context_length`), `handle_attachments.py:436` (`trim_history_to_budget`) | ✅ 100% merged |
| **05** — Streaming: scroll `auto` durante token, `smooth` só quando lista para; `MessageBubble` seleciona só actions necessárias | `89d33e6` | `lib/scrollPolicy.ts` (`streamScrollBehavior`), `ChatWindow.tsx:422` (`behavior: streamScrollBehavior(false)`), `MessageBubble.tsx:365-367` (seletores específicos) | ✅ 100% merged |

**Veredito:** todos os 5 planos estão **100% implementados e testados** na main. Nenhum pendente.

---

## 3. Comandos de Teste (registados para reuse)

```bash
# Backend (dentro do container, PYTHONPATH correto)
docker exec nexus_backend bash -c "cd /app && PYTHONPATH=/app/backend python -m pytest backend/tests/ -q --tb=line"

# Frontend node tests
cd frontend && node --experimental-strip-types --test 'src/lib/*.test.ts' 'src/ui/*.test.ts' 'src/ui/lib/*.test.ts'

# Type-check
cd frontend && npx tsc --noEmit

# Build
cd frontend && npm run build

# Probes
cd frontend && node scripts/run-streaming-paint-probe.mjs
cd frontend && node scripts/run-message-actions-after-stream.mjs

# Judge completo
bash judge.sh
```

---

## 4. Endereços de Teste

| Serviço | URL |
|---------|-----|
| Vite dev server | `http://localhost:5173` |
| Backend API | `http://localhost:8000` (via nginx → `https://multi.mob.tec.br`) |
| Nginx + Cloudflare Tunnel | `https://multi.mob.tec.br` (build em cache; **nunca validar mudanças aqui sem rebuild**) |

---

## 5. Proibições Recordadas

- ❌ Nunca ler/alterar `.env`, chaves, dados de usuário.
- ❌ Nunca force push.
- ❌ Nunca commitar em main sem aprovação explícita.
- ✅ `melhorias/TASK_ATUAL.md` no `.gitignore`.
- ✅ máximo 5 iterações por rodada.
