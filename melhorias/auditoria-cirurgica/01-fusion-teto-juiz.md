# Fusion: teto no texto do Juiz e persistir timeout

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada resposta de proposer que entra no Juiz fica limitada a 4000 caracteres, e um timeout do Juiz salva o texto já emitido em vez de descartá-lo.

**Architecture:** Duas funções puras em `backend/fusion/orchestrator.py` concentram a regra. O join do Juiz passa a usá-las. O timeout deixa de dar `return` quando já há texto. A detecção de claims, que já corta em 1500 caracteres, só ganha `max_tokens=256` para não gerar 4096 tokens de saída numa lista JSON.

**Tech Stack:** Python 3.12, FastAPI, pytest, asyncio.

**Spec:** Auditoria cirúrgica NexusLocal, sessão 20261015_102349_bc26b855. Item 1 do TOP 5. Não há spec file separado; o contexto abaixo é a spec.

## Global Constraints

- Não trocar stack, framework ou arquitetura.
- Mudança de poucas linhas, reversível e testável.
- Não alterar `backend/nexuslocal.db` nem dados de produção.
- Testes usam banco temporário. Rodar pytest só pelo `.venv`.
- Não logar chaves de API.
- `stream_chat` já tem `max_tokens=4096` por omissão em `backend/providers/base.py:82`. Não tratar a ausência do argumento no Juiz como o bug. O bug é o tamanho da entrada.

---

## Contexto

O fan-out já é paralelo (`asyncio.gather` em `backend/fusion/orchestrator.py:457`) e cada proposer já tem timeout de 90s (`TIMEOUT_MODELO_PARALELO`, `wait_for` na linha 414). Falha de um modelo não derruba os outros: o `except Exception` em `chamar_modelo` devolve status de erro.

O Juiz, porém, concatena a resposta inteira de cada modelo:

```python
blocos = "\n\n".join([
    f"{_cabecalho_resposta(r)}\n{r['response']}"
    for r in respostas_validas
])
```

Arquivo `backend/fusion/orchestrator.py`, linhas 510-513. Esse bloco entra nas mensagens do Juiz junto com o histórico já podado e o system prompt. Quatro respostas longas passam do orçamento que o chat acabou de aplicar.

A detecção de claims já corta em 1500 caracteres (`orchestrator.py:91`). Não repetir esse corte no Juiz com o mesmo limite: 4000 preserva mais síntese.

No timeout de 180s (`orchestrator.py:594-603`) o handler envia `error` e dá `return` antes do `stream_end` e do INSERT (linhas 605-610). O usuário viu tokens que somem no reload.

## Mudança exata

Arquivos:

- Modify: `backend/fusion/orchestrator.py` (helpers novos perto da linha 80; join nas linhas 510-513; timeout nas linhas 590-603; `stream_chat` da detecção nas linhas 111-114)
- Test: `backend/tests/test_fusion_judge_budget.py` (criar)

```python
JUDGE_BLOCK_MAX_CHARS = 4000
JUDGE_TRUNCATION_MARK = "\n…[truncado para o Juiz]"


def cap_judge_block(text: str, limit: int = JUDGE_BLOCK_MAX_CHARS) -> str:
    body = text or ""
    if len(body) <= limit:
        return body
    return body[:limit] + JUDGE_TRUNCATION_MARK


def judge_timeout_action(full_response: str) -> str:
    return "persist" if (full_response or "").strip() else "error"
```

No join, trocar `r['response']` por `cap_judge_block(r['response'])`.

No timeout, não retornar se `judge_timeout_action(full_response) == "persist"`. Nesse caso enviar `fusion_status` com a frase `Juiz interrompido no limite de 180s. Resposta parcial salva.` e cair no `stream_end` + INSERT que já existem. Se a ação for `error`, manter o `send_json` de erro e o `return` atuais.

Na detecção de claims, acrescentar `max_tokens=256` na chamada `provider_juiz.stream_chat` das linhas 111-114. Não mudar o corte de 1500 da linha 91.

## Como testar

Não usar `backend/nexuslocal.db`.

```bash
cd /home/osmar/nexuslocal
.venv/bin/python -m pytest backend/tests/test_fusion_judge_budget.py -v
```

Esperado: PASS.

Prova manual, só depois dos testes, com uma conversa Fusion descartável: quatro proposers longos. No log, o prompt do Juiz não deve carregar resposta acima de 4000 caracteres mais o marcador. Não medir isso lendo a chave.

## Rollback

Reverter o commit. Não há migração. Respostas já salvas ficam como estão.

## Métrica

- Antes: `len(r['response'])` entra inteiro no bloco do Juiz (`orchestrator.py:511`). Timeout de 180s descarta `full_response` (`orchestrator.py:603`).
- Depois: cada bloco do Juiz tem no máximo 4000 caracteres mais o marcador. Timeout com texto parcial persiste a mensagem e emite `stream_end`.

---

### Task 1: Teto puro do bloco do Juiz

**Files:**
- Create: `backend/tests/test_fusion_judge_budget.py`
- Modify: `backend/fusion/orchestrator.py` (inserir as duas funções depois da linha 82, antes de `_detectar_claims_verificaveis`)

**Interfaces:**
- Consumes: nada
- Produces: `cap_judge_block(text: str, limit: int = 4000) -> str` e `judge_timeout_action(full_response: str) -> str` com retorno `"persist"` ou `"error"`

- [ ] **Step 1: Write the failing test**

```python
from backend.fusion.orchestrator import cap_judge_block, judge_timeout_action


def test_cap_judge_block_deixa_texto_curto_intacto():
    assert cap_judge_block("curto") == "curto"


def test_cap_judge_block_corta_em_4000_e_marca():
    texto = "a" * 5000
    saida = cap_judge_block(texto)
    assert saida.startswith("a" * 4000)
    assert saida.endswith("…[truncado para o Juiz]")
    assert len(saida) == 4000 + len("\n…[truncado para o Juiz]")


def test_cap_judge_block_none_vira_vazio():
    assert cap_judge_block(None) == ""


def test_judge_timeout_persiste_se_houver_texto():
    assert judge_timeout_action("  resposta  ") == "persist"
    assert judge_timeout_action("   ") == "error"
    assert judge_timeout_action("") == "error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_fusion_judge_budget.py -v`
Expected: FAIL with `ImportError` em `cap_judge_block`.

- [ ] **Step 3: Write minimal implementation**

Inserir em `backend/fusion/orchestrator.py` imediatamente antes de `async def _detectar_claims_verificaveis`:

```python
JUDGE_BLOCK_MAX_CHARS = 4000
JUDGE_TRUNCATION_MARK = "\n…[truncado para o Juiz]"


def cap_judge_block(text: str, limit: int = JUDGE_BLOCK_MAX_CHARS) -> str:
    body = text or ""
    if len(body) <= limit:
        return body
    return body[:limit] + JUDGE_TRUNCATION_MARK


def judge_timeout_action(full_response: str) -> str:
    return "persist" if (full_response or "").strip() else "error"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_fusion_judge_budget.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/fusion/orchestrator.py backend/tests/test_fusion_judge_budget.py
git commit -m "test: teto puro do bloco do Juiz Fusion"
```

### Task 2: Usar o teto e persistir o timeout

**Files:**
- Modify: `backend/fusion/orchestrator.py:111-114` (max_tokens da detecção)
- Modify: `backend/fusion/orchestrator.py:510-513` (join)
- Modify: `backend/fusion/orchestrator.py:590-610` (timeout)

**Interfaces:**
- Consumes: `cap_judge_block`, `judge_timeout_action`
- Produces: bloco do Juiz limitado; timeout com texto chama o mesmo INSERT/stream_end já existente

- [ ] **Step 1: Write the failing test**

Acrescentar em `backend/tests/test_fusion_judge_budget.py`:

```python
from backend.fusion.orchestrator import cap_judge_block


def test_join_do_juiz_nao_carrega_resposta_inteira():
    respostas = [
        {"model_id": "a", "response": "x" * 8000, "confidence": None},
        {"model_id": "b", "response": "y" * 100, "confidence": None},
    ]
    blocos = "\n\n".join(
        f"--- RESPOSTA: {r['model_id']} ---\n{cap_judge_block(r['response'])}"
        for r in respostas
    )
    assert "x" * 4001 not in blocos
    assert "yyyy" in blocos
    assert blocos.count("…[truncado para o Juiz]") == 1
```

Esse teste já passa se a Task 1 passou, porque exercita o helper e não o join do arquivo. O teste que trava o join é este, no mesmo arquivo:

```python
from pathlib import Path


def test_orchestrator_aplica_cap_no_join_do_juiz():
    source = Path("backend/fusion/orchestrator.py").read_text(encoding="utf-8")
    assert "cap_judge_block(r['response'])" in source
    assert "judge_timeout_action(full_response)" in source
    assert "max_tokens=256" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_fusion_judge_budget.py::test_orchestrator_aplica_cap_no_join_do_juiz -v`
Expected: FAIL porque as strings ainda não estão no fonte.

- [ ] **Step 3: Write minimal implementation**

Trocar o join das linhas 510-513 por:

```python
    blocos = "\n\n".join([
        f"{_cabecalho_resposta(r)}\n{cap_judge_block(r['response'])}"
        for r in respostas_validas
    ])
```

Na chamada das linhas 111-114, acrescentar o argumento:

```python
        async for token in provider_juiz.stream_chat(
            model=judge_model_name,
            messages=[{"role": "user", "content": prompt_deteccao}],
            max_tokens=256,
        ):
```

Substituir o bloco do timeout (linhas 590-603) por:

```python
    timed_out = False
    try:
        async for chunk in asyncio.wait_for(_stream_juiz(), timeout=180):
            full_response += chunk
            await ws.send_json({"type": "token", "content": chunk})
    except asyncio.TimeoutError:
        timed_out = True
        logger.error(
            "Fusion: timeout do juiz (180s) conversation=%s judge=%s",
            conversation_id, judge_model_id,
        )
        if judge_timeout_action(full_response) == "error":
            await ws.send_json({
                "type": "error",
                "message": "O juiz do Fusion excedeu o tempo limite (180s). Tente novamente.",
            })
            return
        await ws.send_json({
            "type": "fusion_status",
            "message": "Juiz interrompido no limite de 180s. Resposta parcial salva.",
        })
```

O `stream_end` e o INSERT que já vêm em seguida permanecem. Não duplicar `stream_end`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_fusion_judge_budget.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/fusion/orchestrator.py backend/tests/test_fusion_judge_budget.py
git commit -m "fix: limita o prompt do Juiz Fusion e salva timeout parcial"
```
