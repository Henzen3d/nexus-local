# Vision Relay: timeout, cache por modelo, turno não aborta

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uma falha ou lentidão do Vision Relay vira placeholder na mensagem, e a descrição em cache deixa de ser reutilizada quando o modelo de relay muda.

**Architecture:** A chave em RAM passa a ser `hash:modelo`. No SQLite, `file_hash` continua PRIMARY KEY (`database.py:205`); o SELECT só devolve cache se `relay_model` casar. Outra função async descreve ou devolve placeholder. O loop de `load_history` deixa de dar `raise`. O relay ganha `asyncio.wait_for` de 25s por imagem. O teto atual é só o read timeout de 120s do httpx compartilhado.

**Tech Stack:** Python 3.12, FastAPI, pytest, asyncio.

**Spec:** Auditoria cirúrgica NexusLocal, sessão 20261015_102349_bc26b855. Item 2 do TOP 5.

## Global Constraints

- Não trocar stack, framework ou arquitetura.
- Mudança de poucas linhas, reversível e testável.
- Não alterar `backend/nexuslocal.db`. A coluna `file_hash` continua string; a chave nova é só o valor gravado.
- Testes usam banco temporário. Rodar pytest só pelo `.venv`.
- Não logar chaves de API nem o conteúdo da imagem.

---

## Contexto

Quando `supports_vision` é falso, `load_history` chama o relay e, se ele falha, relança a exceção:

`backend/orchestration/handle_attachments.py:325-333` (`raise e`).

A chamada real, linhas 311-317, é:

```python
res = await describe_image_via_relay(
    img["storage_path"],
    img["mime_type"],
    img["file_hash"],
    user_id=user_id,
    conversation_id=conversation_id,
)
desc = res["description"]
```

O import de `describe_image_via_relay` é local, dentro da função (`handle_attachments.py:215`), não no topo do módulo.

O websocket em `backend/routers/chat.py:246-251` transforma a exceção em `Falha ao processar a mensagem`. O turno morre antes do LLM. O retry pós-provedor em `backend/orchestration/resolve_request.py:436-453` já engole falha de relay. O caminho pré-LLM não.

`describe_image_via_relay` faz `async for` em `stream_chat` sem `wait_for` e sem `max_tokens` (`backend/vision_relay/relay.py:143`). O único teto é `httpx.Timeout(..., read=120.0)` em `backend/providers/base.py:29`. Não inventar `max_tokens=1024`: a chamada atual não tem esse argumento.

O cache L1 usa `key = file_hash` (`relay.py:42` e `72`). O SELECT é só `WHERE file_hash = ?` (`relay.py:52-53`). A coluna `relay_model` já é gravada (`relay.py:78-80`, schema em `database.py:207`) e não entra no lookup. Trocar o modelo de relay serve a descrição antiga até o TTL de 1h do L1 (`relay.py:37`).

`file_hash` é PRIMARY KEY. Não gravar `hash:modelo` nessa coluna. Isso quebraria o lookup das linhas já salvas e a unicidade.

`supports_vision` falso quando a linha do modelo não existe (`handle_attachments.py:392-398`) manda toda imagem para o relay. Não mudar essa política neste plano. O plano só impede que a falha desse caminho aborte o chat.

## Mudança exata

Arquivos:

- Modify: `backend/vision_relay/relay.py`
- Modify: `backend/orchestration/handle_attachments.py:309-333`
- Test: `backend/tests/test_vision_relay_fallback.py` (criar)

```python
RELAY_IMAGE_TIMEOUT_S = 25


def vision_cache_key(file_hash: str, relay_model_id: str) -> str:
    return f"{file_hash}:{relay_model_id}"


def image_placeholder(filename: str) -> str:
    return f"[Imagem {filename}: descrição indisponível]"
```

L1 usa `vision_cache_key(file_hash, relay_model)`. O SELECT continua `WHERE file_hash = ?` e só aceita a linha se `relay_model` casar. O INSERT OR REPLACE continua gravando `file_hash` puro mais a coluna `relay_model`. Não mudar a PRIMARY KEY.

O `async for` da linha 143 fica dentro de uma coroutine interna, envolvida por `asyncio.wait_for(..., timeout=RELAY_IMAGE_TIMEOUT_S)`. A chamada de `stream_chat` permanece `model=model_name, messages=messages, temperature=0.2`. Sem `max_tokens` novo.

`TimeoutError` sobe como as outras falhas. Quem chama não relança.

Em `handle_attachments.py`, o `except` das linhas 325-333 deixa de ter `raise e`. Em vez disso anexa o placeholder e segue o loop. `relay_used` só é marcado se o relay devolver dict.

## Como testar

```bash
cd /home/osmar/nexuslocal
.venv/bin/python -m pytest backend/tests/test_vision_relay_fallback.py -v
```

Esperado: PASS.

Prova manual: modelo sem visão, relay desligado, uma imagem. O websocket deve emitir tokens do LLM, não `type: error` com `Falha ao processar a mensagem`. A mensagem do usuário deve conter `descrição indisponível`.

## Rollback

Reverter o commit. Linhas antigas de cache (`file_hash` sem modelo) deixam de casar com a chave nova e geram uma descrição extra na próxima imagem. Não apagar essas linhas.

## Métrica

- Antes: exceção do relay em `handle_attachments.py:333` aborta o turno. Cache casa só por `file_hash` (`relay.py:54`).
- Depois: a mesma falha produz placeholder e o LLM responde. Cache L1 e SELECT só batem se `relay_model` for o mesmo. `file_hash` no banco continua o hash puro.

---

### Task 1: Chave de cache e placeholder

**Files:**
- Create: `backend/tests/test_vision_relay_fallback.py`
- Modify: `backend/vision_relay/relay.py` (funções no topo do módulo, depois dos imports)

**Interfaces:**
- Consumes: nada
- Produces: `vision_cache_key(file_hash: str, relay_model_id: str) -> str` e `image_placeholder(filename: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
from backend.vision_relay.relay import image_placeholder, vision_cache_key


def test_vision_cache_key_separa_modelos():
    a = vision_cache_key("abc", "modelo-a")
    b = vision_cache_key("abc", "modelo-b")
    assert a != b
    assert a == "abc:modelo-a"


def test_image_placeholder_nomeia_o_arquivo():
    assert image_placeholder("foto.png") == "[Imagem foto.png: descrição indisponível]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_vision_relay_fallback.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Write minimal implementation**

```python
def vision_cache_key(file_hash: str, relay_model_id: str) -> str:
    return f"{file_hash}:{relay_model_id}"


def image_placeholder(filename: str) -> str:
    return f"[Imagem {filename}: descrição indisponível]"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_vision_relay_fallback.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/vision_relay/relay.py backend/tests/test_vision_relay_fallback.py
git commit -m "test: chave de cache do Vision Relay inclui o modelo"
```

### Task 2: Timeout e não abortar o turno

**Files:**
- Modify: `backend/vision_relay/relay.py:51-80` e `141-144`
- Modify: `backend/orchestration/handle_attachments.py:309-333`
- Test: `backend/tests/test_vision_relay_fallback.py`

**Interfaces:**
- Consumes: `vision_cache_key`, `image_placeholder`
- Produces: `describe_or_placeholder` não levanta; cache lê/grava a chave composta

- [ ] **Step 1: Write the failing test**

```python
import asyncio
from unittest.mock import patch

from backend.orchestration.handle_attachments import describe_or_placeholder


def test_describe_or_placeholder_nao_levanta():
    img = {
        "filename": "foto.png",
        "storage_path": "u/foto.png",
        "mime_type": "image/png",
        "file_hash": "abc",
    }

    async def boom(*args, **kwargs):
        raise RuntimeError("relay down")

    async def run():
        with patch(
            "backend.vision_relay.relay.describe_image_via_relay",
            new=boom,
        ):
            return await describe_or_placeholder(img, user_id="u1", conversation_id="c1")

    text = asyncio.run(run())
    assert text == "[Imagem foto.png: descrição indisponível]"
```

O patch é em `backend.vision_relay.relay.describe_image_via_relay` porque `describe_or_placeholder` importa esse nome dentro da função. Não patchar `handle_attachments.describe_image_via_relay`: esse nome não existe no topo do módulo.

E um teste de fonte:

```python
from pathlib import Path


def test_relay_tem_timeout_e_nao_serve_cache_de_outro_modelo():
    source = Path("backend/vision_relay/relay.py").read_text(encoding="utf-8")
    assert "asyncio.wait_for" in source
    assert "RELAY_IMAGE_TIMEOUT_S" in source
    assert "vision_cache_key(" in source
    assert "relay_model" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_vision_relay_fallback.py -v`
Expected: FAIL em `describe_or_placeholder` e na string do fonte.

- [ ] **Step 3: Write minimal implementation**

Em `backend/orchestration/handle_attachments.py`, adicionar no nível do módulo:

```python
async def describe_or_placeholder(img: dict, user_id: str, conversation_id: str | None) -> str:
    from backend.vision_relay.relay import describe_image_via_relay, image_placeholder
    try:
        res = await describe_image_via_relay(
            img["storage_path"],
            img["mime_type"],
            img["file_hash"],
            user_id=user_id,
            conversation_id=conversation_id,
        )
        return res["description"]
    except Exception:
        logger.error("vision relay falhou para %s", img.get("filename"), exc_info=True)
        return image_placeholder(img["filename"])
```

No loop das linhas 309-333, trocar o `try/except/raise` por:

```python
desc = await describe_or_placeholder(img, user_id, conversation_id)
image_descriptions.append(f"[Descrição da imagem {img['filename']}]: {desc}")
```

Não relançar. Não marcar `relay_used` nesse ramo: o relay não devolveu `res`.

Em `relay.py`, constante `RELAY_IMAGE_TIMEOUT_S = 25`.

Em `get_cached_description`, a chave L1 passa a ser `vision_cache_key(file_hash, relay_model)`. Acrescentar o argumento `relay_model: str`. O SELECT continua `WHERE file_hash = ?`. Ler também `relay_model`. Se a coluna não casar com o argumento, devolver `None`.

Em `save_description_cache`, a chave L1 usa `vision_cache_key(file_hash, relay_model)`. O INSERT continua `(file_hash, description, relay_model)` com `file_hash` puro. Não mudar a PRIMARY KEY.

A chamada existente na linha 103 passa `config["relay_model_id"]`.

Envolver só o `async for` da linha 143. Variáveis reais: `model_name` e `messages`. Sem `max_tokens`.

```python
async def _collect() -> str:
    chunks: list[str] = []
    async for chunk in provider.stream_chat(
        model=model_name,
        messages=messages,
        temperature=0.2,
    ):
        chunks.append(chunk)
    return "".join(chunks).strip()

try:
    description = await asyncio.wait_for(_collect(), timeout=RELAY_IMAGE_TIMEOUT_S)
except Exception as e:
    error_msg = str(e)
    await check_and_deactivate_model(final_model_id, error_msg, db)
    raise RelayError(f"Erro ao chamar modelo intérprete '{final_model_id}': {error_msg}")
```

O `try` atual das linhas 142-148 sai. Não deixar os dois. `description = "".join(chunks)` das linhas 150-152 sai, porque `_collect` já devolve o texto. O teste de descrição vazia permanece.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_vision_relay_fallback.py backend/tests/test_history_and_failover_resilience.py -v`
Expected: PASS. O segundo arquivo já cobre histórico; não pode quebrar.

- [ ] **Step 5: Commit**

```bash
git add backend/vision_relay/relay.py backend/orchestration/handle_attachments.py backend/tests/test_vision_relay_fallback.py
git commit -m "fix: falha do Vision Relay não aborta o turno"
```
