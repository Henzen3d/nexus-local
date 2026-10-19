# 📋 Mapeamento Arquitetural de Failover, Roteamento e Quotas (F0)
**NexusLocal / Multi+** · Documento Oficial de Diagnóstico Técnico (F0 — Somente Leitura)
**Data:** 19 de Outubro de 2026  
**Referência:** `melhorias/failover/GOLDEN_PROMPT_v3.md`

---

## 1. Respostas Técnicas às 14 Questões do F0

### 1. Quais status de erro/saúde, tabelas e colunas de quota/cooldown/quarentena/ranking existem hoje? Existe alguma estatística de latência/saúde persistida?

* **`model_quota_status` ([backend/database.py:302-309](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L302-L309) e migrações [1369-1388](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1369-L1388)):**
  - **Chave Primária:** `model_id TEXT`
  - **Colunas base:** `status` (`'available'`, `'degraded'`, `'exhausted'`), `consecutive_errors INTEGER`, `exhausted_at TEXT`, `estimated_reset_at TEXT`, `last_error_message TEXT`.
  - **Colunas de quota free adicionadas por migração:** `known_rpm`, `known_rpd`, `known_tpm`, `known_tpd`, `current_minute_count`, `current_day_count`, `minute_window_reset`, `day_window_reset`, `confirmed_free`, `registry_source`.
* **`model_rankings` ([backend/database.py:293-300](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L293-L300)):**
  - `model_id TEXT PRIMARY KEY`, `quality_score REAL`, `popularity_rank INTEGER`, `nexuslocal_score REAL`, `source TEXT`, `updated_at TEXT`.
* **`model_usage_log` ([backend/database.py:311-327](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L311-L327)):**
  - `id`, `model_id`, `provider_id`, `conversation_id`, `user_id`, `tokens_est`, `was_fallback`, `fallback_from_model_id`, `fallback_reason`, `was_auto_routed`, `route_intent`, `route_confidence`, `route_latency_ms`, `route_policy`, `created_at`.
* **Estatísticas de latência/saúde persistidas atualmente:**
  - Apenas `route_latency_ms` em `model_usage_log` (que mede a latência da classificação regex de intenção do AutoRouter, $< 2\text{ms}$). **NENHUMA** estatística de latência real de provedor (TTFT), taxa de tokens/segundo (TPS) ou taxa de sucesso/erro multi-janela é persistida hoje no banco.

---

### 2. Por que `database.py:3762` tratou 404 como billing? Qual é o critério atual?

* **Diagnóstico Histórico:**
  Na implementação anterior a 18/10, a função `check_and_deactivate_model` (linha ~3762) utilizava uma lista única e estática `deactivate_triggers` que mesclava termos como `"not found"`, `"model not found"` e `"billing limit"`. Toda desativação caía em um único `logger.error("🚫 Model '%s' automatically disabled due to billing/subscription error: %s", model_id, error_msg)`. Com isso, respostas HTTP 404 do Gemini (`"This model models/gemini-2.5-pro is no longer available to new users..."`) eram marcadas erroneamente como falha de faturamento e a sugestão de substituto (`models/gemini-3.1-pro-preview`) era descartada.
* **Critério Atual ([backend/database.py:3781-3880](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L3781-L3880)):**
  Implementado na etapa F1: `classify_model_error` divide explicitamente em 4 categorias:
  1. `model_deprecated`: HTTP 404 com `"no longer available"`, `"deprecated"`, `"sunset"`, `"discontinued"` (extrai `suggested_model` via regex [3764-3778](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L3764-L3778)).
  2. `model_not_found`: `"model not found"`, `"not_found"`, `"invalid_model"`, `"404 page not found"`.
  3. `quota_exhausted`: HTTP 402, `"usage limit reached"`, `"quota_exceeded"`.
  4. `billing_error`: `"requires a subscription"`, `"billing_limit_reached"`, `"insufficient_quota"`.

---

### 3. Por que o 402 com "Usage limit reached" virou `error` genérico em vez de acionar `quota.py`?

* **Diagnóstico:**
  No arquivo [backend/orchestration/resolve_request.py:406-421](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L406-L421), apenas `RateLimitError` (HTTP 429 gerado no `OpenAICompatProvider`) entrava no bloco de rate limit. Códigos HTTP 402 levantavam `RuntimeError(f"Provider error 402: {detail}")` em [backend/providers/base.py:156](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py#L156), caindo no bloco `except Exception as e:` genérico com `next_failover_reason = "error"`.
* **Situação Atual e Escopo:**
  Na etapa F3, adicionou-se `is_quota_exhausted_error(error_msg)` em [resolve_request.py:491](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L491), acionando `mark_model_exhausted(..., retry_after=3600)`.
  **Gargalo Restante:** O erro da LongCat (`"AppId:**jt51 Usage limit reached."`) atinge a **conta/credencial inteira do provedor** (`provider_id` ou app-key), mas hoje o registro só marca o `current_model_id` individual, permitindo tentativas inúteis em outros modelos da mesma conta.

---

### 4. O que `resolve_request.py:346` faz com 0 tokens? Registra cooldown? O que o stream do Nemotron realmente devolve?

* **Comportamento Atual ([backend/orchestration/resolve_request.py:345-364](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L345-L364)):**
  Quando `full_response.strip()` é vazio após o término do loop assíncrono:
  - Registra cooldown temporário de 600s: `await mark_model_exhausted(current_model_id, db, retry_after=600, error_msg="Silent failure: 0 tokens returned")`.
  - Adiciona `current_model_id` em `attempted_model_ids` e define `next_failover_reason = "silent_failure"`.
* **O que o stream do Nemotron realmente devolve:**
  O endpoint da Nvidia NIM / OpenRouter para o Nemotron devolve **Caso (a) e Caso (d):** Conexão HTTP 200 SSE onde os chunks contêm apenas metadados de `usage` ou `choices[0].delta` vazio/sem campo `content` e sem `reasoning_content` ([backend/providers/base.py:170-271](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py#L170-L271)), encerrando imediatamente com `data: [DONE]`. Nenhum token de conteúdo textual é emitido.

---

### 5. Como `failover.py:338` identifica família? Como os IDs ganham prefixos duplicados (`nvidia/nvidia/`) e `:free`? Onde colocar o normalizador canônico?

* **Como identifica família ([backend/ranking/failover.py:118-197](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py#L118-L197)):**
  Busca primeiro correspondência exata em `model_family_members.model_id = ?`. Se não encontrar, faz matching usando `canonical_model_id` contra membros da família e prefixos em `model_families`.
* **Origem dos prefixos duplicados e sufixos:**
  - Provedores como Nvidia NIM expõem modelos já prefixados com sua organização no `/v1/models` (ex: `nvidia/nemotron-3-ultra-550b-a55b`).
  - No `model_fetcher.py` e catálogo, o NexusLocal cria IDs no formato `{provider_id}/{upstream_model_id}`, resultando em `nvidia/nvidia/nemotron-...`.
  - No OpenRouter, variantes gratuitas trazem o sufixo `:free` (ex: `openrouter/nvidia/nemotron-...:free`).
* **Localização do Normalizador Canônico:**
  Atualmente implementado em [backend/ranking/failover.py:28-66](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/failover.py#L28-L66). Na etapa A2, ele deve ser extraído para um módulo compartilhado central `backend/ranking/canonical.py` e exportado em `backend/ranking/__init__.py`.

---

### 6. Por que o boot grava ~11.460 linhas (sync.py + scorer.py)? Proponha como colapsar para uma única execução.

* **Causa Raiz ([backend/main.py:106-130](file:///j:/Arquivos%20Osmar/Multi+/backend/main.py#L106-L130) e [backend/routers/admin.py:244-249](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/admin.py#L244-L249)):**
  No startup, `run_auto_sync()` dispara tarefas em paralelo com `asyncio.create_task(sync_task(provider_id))` para cada provedor habilitado (6 a 12 provedores simultâneos). Cada `sync_provider_models` executa:
  `scored_models = await compute_all_scores(db)`
  `await persist_scores(db, scored_models)`
  Em [backend/ranking/scorer.py:253-268](file:///j:/Arquivos%20Osmar/Multi+/backend/ranking/scorer.py#L253-L268), `persist_scores` faz um loop com `UPDATE model_rankings ... WHERE model_id = ?` individual para **todos os 1910 modelos cadastrados**!
  Multiplicando: $6 \text{ tarefas} \times 1910 \text{ updates} = \mathbf{11.460 \text{ escritas concorrentes}}$ disputando lock no SQLite em menos de 4 segundos.
* **Proposta de Colapso (Etapa B2):**
  1. Remover a chamada de `compute_all_scores` + `persist_scores` de dentro do loop de cada provedor individual em `sync_provider_models`.
  2. Em `run_auto_sync`, aguardar a conclusão de todas as sincronizações de provedores com `asyncio.gather(*tasks)` e disparar **uma única execução final** de recálculo de scores.
  3. Refatorar `persist_scores` para usar `db.executemany` em uma única transação, em vez de 1910 `execute` individuais.

---

### 7. Quantos workers/processos o backend roda (compose/uvicorn/gunicorn)? Qual a versão do Python?

* **Configuração Docker ([Dockerfile:32](file:///j:/Arquivos%20Osmar/Multi+/backend/Dockerfile#L32) e [docker-compose.yml:7](file:///j:/Arquivos%20Osmar/Multi+/docker-compose.yml#L7)):**
  `CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]`
  O Uvicorn roda com **1 único worker / processo** (sem flag `--workers`).
  O container roda com `init: true` (tini como PID 1 para colheita de zumbis).
* **Versão do Python:**
  `Python 3.11-slim` ([Dockerfile:2](file:///j:/Arquivos%20Osmar/Multi+/backend/Dockerfile#L2) e Python 3.11.15 no `.venv` local).

---

### 8. Como o streaming é feito (httpx, aiohttp, SDK)? O cliente é global e compartilhado? Usa `async with ...stream(...)` ou `aclose()` em `finally`? Há `except Exception`/`BaseException` que possa engolir `CancelledError`? Sobram tarefas ou conexões abertas quando um provedor falha?

* **Cliente HTTP ([backend/providers/base.py:23-55](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py#L23-L55)):**
  Usa `httpx.AsyncClient` com pool compartilhado por event loop via `_pooled_client` (`max_connections=64, max_keepalive_connections=20, timeout=120.0s`).
* **Streaming ([backend/providers/base.py:136-141](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py#L136-L141)):**
  Usa `async with client.stream("POST", ...) as response:`.
* **Fechamento e Tarefas Órfãs em Exceção:**
  No [resolve_request.py:287](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L287), o gerador é instanciado via `stream_iter = provider.stream_chat(...).__aiter__()`.
  O `await stream_iter.aclose()` é chamado apenas no bloco de timeout TTFT (linha 310). Se ocorrer `RateLimitError` ou exceção genérica no meio do streaming, `stream_iter.aclose()` **não** é chamado em `finally`, deixando a conexão presa no pool até o garbage collector liberá-la.
* **Propagação de `CancelledError`:**
  O bloco em `resolve_request.py:419` usa `except Exception as e:`. Como no Python 3.8+ `asyncio.CancelledError` herda de `BaseException`, ele **não** é engolido por `except Exception`. Contudo, a ausência de um `try/finally` para fechar `stream_iter` no cancelamento deixa o gerador aberto.

---

### 9. Quais timeouts existem (TTFT, total)? Qual o tempo percebido por tentativa vazia? Os intervalos de ~20–30 s dos logs eram retries do usuário ou da cascata? Traga p50/p95 de TTFT por provedor, se houver dados.

* **Timeouts Atuais ([backend/orchestration/resolve_request.py:272, 325](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L272-L325)):**
  - TTFT Timeout: `STREAM_TTFT_TIMEOUT_SECONDS = 25.0s`.
  - Inter-token Timeout: `35.0s`.
  - HTTP Client Read Timeout: `120.0s`.
  - **Orçamento total de turno:** **NÃO EXISTE**. Cada tentativa de failover inicia um novo cronômetro de 25s TTFT + 120s stream. Três tentativas lentas podem somar mais de 75 segundos.
* **Intervalos de ~20–30s dos logs:**
  Eram exatamente o tempo do `STREAM_TTFT_TIMEOUT_SECONDS = 25.0s` expirando na primeira tentativa antes de acionar a segunda tentativa da cascata.
* **Métricas p50/p95 de TTFT por provedor:**
  Não há série temporal de TTFT gravada em banco (confirmado na Questão 1).

---

### 10. O sync de catálogo no startup (12 provedores) pode reabilitar um modelo desativado por `MODEL_DEPRECATED`?

* **Sim ([backend/routers/admin.py:190-195, 214-223](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/admin.py#L190-L195)):**
  Se a API do provedor (ex: Google Gemini `/v1/models`) continuar listando o modelo `gemini-2.5-pro` mesmo após ele retornar 404 de descontinuação em geração, o sync em `admin.py:190` reavalia:
  `new_enabled = 1 if should_confirm_free else old_enabled`
  Se `should_confirm_free` for True, ele **reabilita o modelo (`enabled = 1`)**, ignorando a desativação prévia por `MODEL_DEPRECATED`!
  **Correção necessária na Etapa A1:** Modelos desativados por `MODEL_DEPRECATED` ou gravados em quarentena devem ter bloqueio respeitado pelo sync.

---

### 11. Os provedores usam function calling nativo? Ferramentas são executadas pelo `ToolDispatcher`/sandbox no servidor? Existe efeito colateral que um retry possa repetir (code exec, gravações)?

* **Function Calling Nativo:** Não. Os provedores não usam deltas de function calling nativo no stream.
* **Execução de Ferramentas ([backend/routers/chat.py:601-620](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/chat.py#L601-L620)):**
  As ferramentas são executadas **antes** da chamada do modelo: o sistema detecta intenção via regex (`detect_intents`), despacha pelo `ToolDispatcher` no servidor e injeta o resultado textual bruto no system prompt sob tags `<dados_ferramentas>`.
* **Efeito Colateral em Retry:**
  Como o disparo de ferramentas ocorre na fase pré-LLM (linhas 601-620), o retry de failover do LLM em `resolve_and_stream` (linha 746) **não repete** a execução da ferramenta.

---

### 12. Quais eventos WebSocket existem (`failover_notice`, `stream_end`, `message_id`) e qual a semântica do terminal? Onde o toast é renderizado? Quais arquivos de frontend seriam tocados (e se colidem com os loops de Usabilidade e Projetos)?

* **Eventos WebSocket Atuais ([backend/orchestration/resolve_request.py](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py)):**
  - `stream_start`: `{"type": "stream_start", "conversation_id": ..., "from_cache": bool}`
  - `token`: `{"type": "token", "content": ...}`
  - `failover_notice`: `{"type": "failover_notice", "original_model": ..., "fallback_model": ..., "reason": ...}`
  - `effort_dropped`: `{"type": "effort_dropped", "reason": ..., "model_id": ...}`
  - `stream_end`: Terminal de sucesso emitido em [backend/routers/chat.py:838](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/chat.py#L838) contendo `message_id`, `conversation_id`, `final_model_id`, `final_model_name`, `final_provider_id`, `was_fallback`.
  - `error`: Terminal de falha emitido em [resolve_request.py:521](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/resolve_request.py#L521) e [chat.py:794](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/chat.py#L794).
* **Onde o Toast é Renderizado:**
  Em [frontend/src/hooks/useChat.ts:245-273](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/hooks/useChat.ts#L245-L273):
  `s.showToast(i18n.t('chat.failoverNotice', ...), 'info')`
* **Arquivos do Frontend Tocados e Verificação de Conflitos:**
  - `frontend/src/hooks/useChat.ts` (remover toast em fallback com sucesso, processar novos campos de metadata).
  - `frontend/src/types.ts` (ampliar tipagem de `stream_end`).
  - `frontend/src/components/MessageBubble.tsx` (badge com micro-ícone e tooltip discreto).
  - **Atenção:** `useChat.ts` e `MessageBubble.tsx` são tocados pelos loops de Usabilidade e Projetos. As edições da etapa C2 devem ser cirúrgicas, restritas à chave `failover_notice` e metadados de modelo.

---

### 13. Quais adapters suportam assistant prefill e `Retry-After`? (Só leitura; não presumir.)

* **`Retry-After`:**
  Apenas `OpenAICompatProvider` em [backend/providers/base.py:143-146](file:///j:/Arquivos%20Osmar/Multi+/backend/providers/base.py#L143-L146) lê o header `Retry-After` no caso de HTTP 429. Os demais adapters (`CloudflareProvider`, `GeminiProvider`) não capturam esse cabeçalho.
* **Assistant Prefill:**
  **NENHUM** adapter atual possui capability flag nem suporte a assistant prefill (se a última mensagem for `role: "assistant"`, a maioria das APIs OpenAI-compat retorna HTTP 400).

---

### 14. Proposta (sem aplicar): DDL Mínimo, Migração Incremental, Parâmetros de Configuração e Backup

* **Procedimento Oficial de Backup:**
  ```bash
  sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
  cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"
  ```
* **DDL Mínimo Incremental (Padrão `backend/database.py:1369`):**
  Adicionar colunas em `model_quota_status` via blocos `try/except aiosqlite.OperationalError`:
  ```sql
  ALTER TABLE model_quota_status ADD COLUMN breaker_state TEXT DEFAULT 'CLOSED';
  ALTER TABLE model_quota_status ADD COLUMN penalty_score REAL DEFAULT 0.0;
  ALTER TABLE model_quota_status ADD COLUMN half_life_sec REAL DEFAULT 180.0;
  ALTER TABLE model_quota_status ADD COLUMN last_failure_ts REAL DEFAULT 0.0;
  ALTER TABLE model_quota_status ADD COLUMN consecutive_failures INTEGER DEFAULT 0;
  ALTER TABLE model_quota_status ADD COLUMN ewma_ttft_ms REAL DEFAULT 1500.0;
  ALTER TABLE model_quota_status ADD COLUMN ewma_tps REAL DEFAULT 30.0;
  ALTER TABLE model_quota_status ADD COLUMN sr_10m REAL DEFAULT 1.0;
  ALTER TABLE model_quota_status ADD COLUMN sr_1h REAL DEFAULT 1.0;
  ALTER TABLE model_quota_status ADD COLUMN sr_24h REAL DEFAULT 1.0;
  ALTER TABLE model_quota_status ADD COLUMN canonical_id TEXT;
  ```
  Tabela para quarentena no escopo de credencial/provedor (Escopo 1):
  ```sql
  CREATE TABLE IF NOT EXISTS provider_quarantine (
      provider_id        TEXT PRIMARY KEY,
      quarantined_until  TEXT NOT NULL,
      reason             TEXT,
      updated_at         TEXT DEFAULT (datetime('now'))
  );
  ```
* **Parâmetros de Configuração com Valores Iniciais (Tabela `meta`):**
  - `failover_total_budget_sec`: `45.0` (orçamento máximo total da requisição inteira)
  - `precommit_min_chars`: `24` (mínimo de caracteres para o flush inicial)
  - `precommit_max_hold_ms`: `450` (tempo máximo de retenção do buffer pré-commit)
  - `health_w_rel`: `0.45`
  - `health_w_latency`: `0.15`
  - `health_w_quota`: `0.20`
  - `health_w_breaker`: `0.20`
  - `health_shadow_mode`: `1` (modo sombra ativado por padrão nas etapas B2/B4)

---

## 2. Histórico de Etapas Concluídas (F1–F3 Anteriores)

| Etapa | Commit | Mensagem | Escopo |
|---|---|---|---|
| **F0** | `ce4f85c` | `docs(failover): F0 mapeamento de erros, quotas e cascata` | `melhorias/failover/00-mapeamento.md` |
| **F1** | `adff37a` | `fix(failover): F1 classifica 404 model deprecated separado de billing` | `backend/database.py`, `backend/tests/test_failover_deprecated_404.py` |
| **F2** | `2f119bd` | `fix(failover): F2 cooldown para 0 tokens, exclusao cross-provider e match de familia tier 1` | `backend/ranking/failover.py`, `backend/orchestration/resolve_request.py`, `backend/tests/test_failover_f2_silent_and_families.py` |
| **F3** | `2962ed1` | `fix(failover): F3 trata HTTP 402 usage limit com cooldown de quota` | `backend/ranking/quota.py`, `backend/ranking/__init__.py`, `backend/orchestration/resolve_request.py`, `backend/database.py`, `backend/tests/test_failover_f3_http402_quota.py` |

---
**F0 Concluído com sucesso.** Pronto para avançar para a Etapa **A1 (Taxonomia única de falhas)**.
