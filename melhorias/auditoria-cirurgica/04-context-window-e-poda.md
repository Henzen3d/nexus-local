# Janela de contexto: parar de inflar por nome e avisar a poda

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sync de modelos deixa de inventar 128k/131k pelo nome, e uma poda de histórico falha fechada (últimas 12 mensagens) com evento visível no websocket.

**Architecture:** Uma função pura decide o `context_length` a gravar. A heurística por substring sai. O registry antigo (versão `2026-07` em `backend/data/context_registry.json:2`) não sobe um valor que a API já devolveu, salvo entrada com `verified_at >= 2026-10-01`. O chat, se `trim_history_to_budget` lançar, corta para as últimas 12 em vez de mandar o histórico inteiro, e emite `history_trimmed`.

**Tech Stack:** Python 3.12, FastAPI, pytest, React/TypeScript no cliente do evento.

**Spec:** Auditoria cirúrgica NexusLocal, sessão 20261015_102349_bc26b855. Item 4 do TOP 5.

## Global Constraints

- Não trocar stack, framework ou arquitetura.
- Mudança de poucas linhas, reversível e testável.
- Não alterar `backend/nexuslocal.db` neste plano. O sync grava `context_length` só quando o admin rodar sync de novo.
- Testes usam banco temporário. Rodar pytest só pelo `.venv`.
- Não logar chaves de API.
- Não reescrever o RAG. Chunking e embeddings já existem em `backend/projects/context_builder.py:461`.

---

## Contexto

`models.context_length` nasce em 8192 (`backend/database.py:38`).

`sync_provider_models` em `backend/routers/admin.py:144-160` sobe a janela por substring de `model_name`, mesmo se a API já devolveu `context_length`. O bloco exato: `deepseek` com `r1`, `v3` ou `v4` vira 131072, senão 64000; `qwen3` ou `qwen2.5` vira 131072, senão 32768; `llama-3` ou `llama-4` vira 131072. A linha 159 só aumenta (`reg_ctx > context_length`), então um valor inflado não volta. O lookup do registry é por `model_name` (linhas 139-142), e várias entradas têm `verified_at` no formato `2026-07` ou `2026-10` (`context_registry.json:10` e `:22`). A versão do arquivo é `2026-07` (linha 2). Comparar `verified_at` com `"2026-10"`, não com `"2026-10-01"`: a string `"2026-10"` é menor que `"2026-10-01"` e rejeitaria as entradas recentes.

`compute_safe_input_tokens` (`backend/projects/context_builder.py:77-108`) e `resolve_input_budget` (`handle_attachments.py:515-520`, teto `HISTORY_INPUT_TOKEN_CAP` default 32000) usam esse número. Janela inflada deixa passar histórico demais e o provedor responde 413. Janela presa em 8192 poda conversa longa sem aviso.

`trim_history_to_budget` já existe e tem testes em `backend/tests/test_security_hardening.py:93` e `backend/tests/test_history_and_failover_resilience.py:98`. Não reescrever essa função.

O chat carrega o histórico inteiro (`handle_attachments.py:218-221`) e, se a poda lança, segue com a lista completa (`backend/routers/chat.py:645-648`). O único registro é `set_memo("history_trimmed", ...)`, que o front não lê. `frontend/src/hooks/useChat.ts` não tem `default` no switch (o switch começa na linha 158). Tipo desconhecido é ignorado. Dá para acrescentar `history_trimmed` sem quebrar o cliente.

## Mudança exata

Arquivos:

- Create: `backend/orchestration/context_window.py`
- Modify: `backend/routers/admin.py:144-160` para chamar a função e apagar o bloco de heurística por nome
- Modify: `backend/routers/chat.py:637-648`
- Modify: `frontend/src/hooks/useChat.ts` (case novo depois de `fusion_refined_prompt`, linha 265)
- Test: `backend/tests/test_context_window_policy.py`

```python
REGISTRY_TRUST_FROM = "2026-10"
TRIM_FAIL_KEEP = 12


def resolve_context_length(
    api_context: int | None,
    registry_ctx: int | None = None,
    verified_at: str | None = None,
) -> int:
    base = api_context if api_context and api_context > 0 else 8192
    if not registry_ctx or registry_ctx <= 0:
        return base
    if not verified_at or verified_at < REGISTRY_TRUST_FROM:
        return base
    return max(base, registry_ctx)


def history_after_trim_failure(history: list, keep: int = TRIM_FAIL_KEEP) -> list:
    if not history:
        return []
    return history[-keep:]
```

Apagar o bloco das linhas 137-160 (`reg_ctx` por nome e o `if reg_ctx and reg_ctx > context_length`). O loop já tem `model_name = item["model_name"]` e `registry_models`. No lugar:

```python
reg = registry_models.get(model_name) or registry_models.get(model_name.split("/")[-1]) or {}
context_length = resolve_context_length(
    api_context=item["context_length"],
    registry_ctx=reg.get("context_length"),
    verified_at=reg.get("verified_at"),
)
```

Não usar `registry_by_id` nem `model_id`. Esses nomes não existem nesse loop.

No `except` de `chat.py:647-648`:

```python
history = history_after_trim_failure(history)
await ws.send_json({
    "type": "history_trimmed",
    "removed": "unknown",
    "kept": len(history),
    "reason": "trim_failed",
})
```

Quando `trimmed_count` for verdadeiro, além do `set_memo`, enviar:

```python
await ws.send_json({
    "type": "history_trimmed",
    "removed": trimmed_count,
    "kept": len(history),
    "reason": "budget",
})
```

No `useChat.ts`, case:

```typescript
case 'history_trimmed':
  s.showToast(
    i18n.t('chat.historyTrimmed', {
      defaultValue: 'Parte antiga da conversa ficou de fora para caber no modelo.',
    }),
    'info'
  )
  break
```

## Como testar

```bash
cd /home/osmar/nexuslocal
.venv/bin/python -m pytest backend/tests/test_context_window_policy.py backend/tests/test_history_and_failover_resilience.py -v
```

Esperado: PASS.

Não rodar sync contra provedor real neste plano.

## Rollback

Reverter o commit. `context_length` já gravado no banco não volta sozinho. Se um sync inflado já rodou, o rollback de código impede o próximo sync de inflar de novo; não faz UPDATE em massa.

## Métrica

- Antes: `llama-3` ou `llama-4` no nome força 131072 (`admin.py:156-157`). Exceção da poda envia o histórico inteiro (`chat.py:647-648`).
- Depois: API 8192 permanece 8192 sem heurística de nome. Registry com `verified_at` anterior a `2026-10` não sobe o valor. `verified_at == "2026-10"` pode subir. Exceção da poda deixa 12 mensagens e emite `history_trimmed`.

---

### Task 1: Política pura da janela

**Files:**
- Create: `backend/orchestration/context_window.py`
- Create: `backend/tests/test_context_window_policy.py`

**Interfaces:**
- Consumes: nada
- Produces: `resolve_context_length(api_context: int | None, registry_ctx: int | None = None, verified_at: str | None = None) -> int` e `history_after_trim_failure(history: list, keep: int = 12) -> list`

- [ ] **Step 1: Write the failing test**

```python
from backend.orchestration.context_window import (
    history_after_trim_failure,
    resolve_context_length,
)


def test_nome_nao_entra_na_funcao_api_8192_fica_8192():
    assert resolve_context_length(8192) == 8192


def test_registry_velho_nao_sobe_o_valor_da_api():
    assert resolve_context_length(8192, registry_ctx=131072, verified_at="2026-07-15") == 8192


def test_registry_recente_pode_subir():
    assert resolve_context_length(8192, registry_ctx=32768, verified_at="2026-10") == 32768


def test_api_ausente_cai_no_default():
    assert resolve_context_length(None) == 8192
    assert resolve_context_length(0) == 8192


def test_falha_de_poda_guarda_as_ultimas_12():
    history = [{"i": i} for i in range(20)]
    kept = history_after_trim_failure(history)
    assert len(kept) == 12
    assert kept[0]["i"] == 8
    assert kept[-1]["i"] == 19


def test_falha_de_poda_com_lista_curta_nao_inventa():
    history = [{"i": 1}]
    assert history_after_trim_failure(history) == [{"i": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_context_window_policy.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Criar `backend/orchestration/context_window.py` com as duas funções da seção Mudança exata. Sem heurística de nome. Sem import de FastAPI.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_context_window_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/orchestration/context_window.py backend/tests/test_context_window_policy.py
git commit -m "test: política de janela de contexto sem inflar por nome"
```

### Task 2: Ligar a política no sync, na poda e no toast

**Files:**
- Modify: `backend/routers/admin.py:144-160`
- Modify: `backend/routers/chat.py:637-648`
- Modify: `frontend/src/hooks/useChat.ts:263-265`
- Test: `backend/tests/test_context_window_policy.py`

**Interfaces:**
- Consumes: `resolve_context_length`, `history_after_trim_failure`
- Produces: sync sem bloco `llama-3`; websocket `history_trimmed`; toast no cliente

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


def test_admin_nao_infla_llama_por_nome():
    source = Path("backend/routers/admin.py").read_text(encoding="utf-8")
    assert 'elif "llama-3" in name_lower or "llama-4" in name_lower:' not in source
    assert "resolve_context_length" in source


def test_chat_nao_manda_historico_inteiro_se_a_poda_falha():
    source = Path("backend/routers/chat.py").read_text(encoding="utf-8")
    assert "history_after_trim_failure" in source
    assert '"history_trimmed"' in source
```

A string que existe hoje é `elif "llama-3" in name_lower or "llama-4" in name_lower:` (`admin.py:156`). Não procurar `if "llama-3"`: essa forma não está no arquivo, e o teste passaria antes da correção.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_context_window_policy.py::test_admin_nao_infla_llama_por_nome backend/tests/test_context_window_policy.py::test_chat_nao_manda_historico_inteiro_se_a_poda_falha -v`
Expected: FAIL. O fonte ainda tem `elif "llama-3" in name_lower or "llama-4" in name_lower:`.

- [ ] **Step 3: Write minimal implementation**

Apagar o bloco de heurística por nome em `admin.py:144-160`. Chamar `resolve_context_length` com o valor que a API devolveu e, se houver hit exato no registry, `context_length` e `verified_at` dessa entrada. Não passar o nome do modelo.

Em `chat.py`, importar `history_after_trim_failure`. No `except` das linhas 647-648, substituir o "segue com history original" pela chamada e pelo `send_json` de `history_trimmed` descritos acima. No ramo `if trimmed_count`, enviar o mesmo tipo com `reason: "budget"`.

Em `useChat.ts`, adicionar o `case 'history_trimmed'` imediatamente depois do `case 'fusion_refined_prompt'`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_context_window_policy.py backend/tests/test_history_and_failover_resilience.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/admin.py backend/routers/chat.py frontend/src/hooks/useChat.ts backend/tests/test_context_window_policy.py
git commit -m "fix: não infla janela por nome e avisa poda de histórico"
```
