import asyncio
import json
import logging
import os
import tempfile
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite
import httpx
import pytest

from backend import database as dbmod
from backend.memory_dream import (
    DREAM_MAX_RESPONSE_CHARS,
    DreamLLMError,
    DreamSafetyError,
    call_dream_llm,
    execute_dream_consolidation,
    parse_dream_response,
    resolve_dream_candidates,
    run_dream_analysis,
    simulate_dream_consolidation,
)
from backend.providers import base as provider_base
from backend.providers.base import OpenAICompatProvider, ProviderHTTPError
from backend.ranking import smart_router


@pytest.fixture
async def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    original_db = dbmod.DB_PATH
    dbmod.DB_PATH = Path(path)
    smart_router._MODEL_CACHE = None
    smart_router._MODEL_CACHE_TIME = 0.0
    await dbmod.init_db()
    try:
        yield Path(path)
    finally:
        dbmod.DB_PATH = original_db
        smart_router._MODEL_CACHE = None
        smart_router._MODEL_CACHE_TIME = 0.0
        try:
            os.remove(path)
        except OSError:
            pass


class FakeDreamProvider:
    def __init__(self, handler, *, supports_response_format: bool = False):
        self._handler = handler
        self.supports_response_format = supports_response_format
        self.calls = 0
        self.received_kwargs = []

    async def stream_chat(self, model, messages, temperature=0.05, response_format=None, **kwargs):
        self.calls += 1
        self.received_kwargs.append({"model": model, "response_format": response_format, **kwargs})
        res = await self._handler(model=model, messages=messages, call_num=self.calls)
        if isinstance(res, list):
            for chunk in res:
                yield chunk
        else:
            yield res


class LegacyNoFormatProvider:
    supports_response_format = False

    def __init__(self, handler):
        self._handler = handler
        self.calls = 0

    async def stream_chat(self, model, messages, temperature=0.05):
        self.calls += 1
        yield await self._handler(model=model, messages=messages, call_num=self.calls)


def _aliases_from_messages(messages: list[dict]) -> list[str]:
    user_msg = messages[-1]["content"]
    aliases = []
    for line in user_msg.splitlines():
        if line.startswith("[ID: "):
            aliases.append(line.split(" ", 2)[1])
    return aliases


def _keep_all_json(messages: list[dict], note: str = "Mantido com sucesso") -> str:
    aliases = _aliases_from_messages(messages)
    return json.dumps({
        "summary_of_changes": note,
        "operations": [{"action": "keep", "fact_id": a} for a in aliases],
    })


# ── Parser unit tests ────────────────────────────────────────────────────────

def test_parse_dream_response_fences_reasoning_and_extra_text():
    raw = (
        "<thought>analisando os fatos</thought>\n"
        "Aqui está o resultado:\n"
        "```json\n"
        '{"summary_of_changes": "ok", "operations": [{"action": "keep", "fact_id": "f1"}]}\n'
        "```\n"
        "Fim da resposta."
    )
    schema = parse_dream_response(raw)
    assert schema.summary_of_changes == "ok"
    assert len(schema.operations) == 1
    assert schema.operations[0].action == "keep"
    assert schema.operations[0].fact_id == "f1"


def test_parse_dream_response_rejects_root_array():
    with pytest.raises(DreamLLMError, match="array"):
        parse_dream_response('[{"action": "keep", "fact_id": "f1"}]')


@pytest.mark.parametrize("end", ["]", ""])
def test_parse_dream_response_rejects_prefixed_array_with_valid_plan(end):
    obj = json.dumps({"summary_of_changes": "hypothesis", "operations": []})
    with pytest.raises(DreamLLMError, match="array"):
        parse_dream_response(f"Resultado:\n[{obj}{end}")


@pytest.mark.parametrize("end", ["</think>Minha resposta foi interrompida.", ""])
def test_parse_dream_response_does_not_apply_hypothetical_plan_from_reasoning(end):
    obj = json.dumps({"summary_of_changes": "hypothesis", "operations": []})
    with pytest.raises(DreamLLMError, match="compatível"):
        parse_dream_response(f"<think>{obj}{end}")


def test_parse_dream_response_rejects_valid_json_invalid_schema():
    # Valid JSON, missing required new_fact for merge
    bad_merge = json.dumps({
        "summary_of_changes": "merge quebrado",
        "operations": [{"action": "merge", "source_fact_ids": ["f1", "f2"]}],
    })
    with pytest.raises(DreamLLMError):
        parse_dream_response(bad_merge)

    # Valid JSON, unknown action
    bad_action = json.dumps({
        "summary_of_changes": "acao invalida",
        "operations": [{"action": "delete_everything", "fact_id": "f1"}],
    })
    with pytest.raises(DreamLLMError):
        parse_dream_response(bad_action)


def test_parse_dream_response_rejects_conflicting_objects():
    obj1 = json.dumps({"summary_of_changes": "um", "operations": [{"action": "keep", "fact_id": "f1"}]})
    obj2 = json.dumps({"summary_of_changes": "dois", "operations": [{"action": "archive", "fact_id": "f1"}]})
    with pytest.raises(DreamLLMError, match="conflitantes"):
        parse_dream_response(f"{obj1}\n\n{obj2}")


def test_parse_dream_response_rejects_oversized_output():
    huge = "x" * (DREAM_MAX_RESPONSE_CHARS + 10)
    with pytest.raises(DreamLLMError, match="limite"):
        parse_dream_response(huge)


# ── Routing, fallback, timeout, 413, cancellation, safety, atomicity ─────────

@pytest.mark.asyncio
async def test_fallback_on_503_timeout_and_invalid_schema_no_duplicates(temp_db, caplog):
    uid = "u_route_fb"
    f1 = await dbmod.add_memory_fact(uid, "tech", "Usa Python 3.11 no backend", "tech.python")
    f2 = await dbmod.add_memory_fact(uid, "tech", "Usa FastAPI com SQLite", "tech.fastapi")

    async def fail_503(**kwargs):
        raise ProviderHTTPError(503, "503 Service Unavailable SECRET_API_BODY_SHOULD_NOT_LOG", provider="prov_a")

    async def fail_invalid_schema(**kwargs):
        return '{"summary_of_changes": "bad", "operations": [{"action": "merge"}]}'

    async def succeed_b(messages, **kwargs):
        aliases = _aliases_from_messages(messages)
        return json.dumps({
            "summary_of_changes": "Consolidou stack Python",
            "operations": [
                {
                    "action": "merge",
                    "source_fact_ids": aliases,
                    "new_fact": {
                        "category": "tech",
                        "fact_key": "tech.backend",
                        "fact": "Usa Python 3.11 com FastAPI e SQLite no backend",
                        "confidence": 0.96,
                        "is_pinned": False,
                    },
                }
            ],
        })

    prov_a = FakeDreamProvider(fail_503, supports_response_format=True)
    prov_b_bad = FakeDreamProvider(fail_invalid_schema, supports_response_format=False)
    prov_c = FakeDreamProvider(succeed_b, supports_response_format=True)

    candidates = [
        {"provider": prov_a, "provider_id": "prov_a", "model_id": "prov_a/m1", "model_name": "m1"},
        {"provider": prov_b_bad, "provider_id": "prov_b", "model_id": "prov_b/m2", "model_name": "m2"},
        {"provider": prov_c, "provider_id": "prov_c", "model_id": "prov_c/m3", "model_name": "m3"},
    ]

    with caplog.at_level(logging.WARNING):
        res = await execute_dream_consolidation(uid, candidates=candidates)

    assert res["status"] == "success"
    assert res["provider_id"] == "prov_c"
    assert res["model_id"] == "prov_c/m3"
    # Provider A must be attempted ONCE (not 3x!) on 503
    assert prov_a.calls == 1
    assert prov_b_bad.calls == 1
    assert prov_c.calls == 1
    # Structured response_format only passed to supporting adapters
    assert prov_a.received_kwargs[0]["response_format"] == {"type": "json_object"}
    assert prov_b_bad.received_kwargs[0]["response_format"] is None
    assert prov_c.received_kwargs[0]["response_format"] == {"type": "json_object"}

    # No duplicate operations; 2 facts merged cleanly into 1
    active = await dbmod.get_user_memory(uid, active_only=True)
    assert len(active) == 1
    assert "Python 3.11" in active[0]["fact"]

    # Logs record effective model and never leak raw body or facts
    logs = await dbmod.list_dream_logs(uid)
    assert logs[0]["provider_id"] == "prov_c"
    assert logs[0]["model_id"] == "prov_c/m3"
    all_log_text = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRET_API_BODY_SHOULD_NOT_LOG" not in all_log_text
    assert "FastAPI com SQLite" not in all_log_text


@pytest.mark.asyncio
async def test_fallback_on_timeout_and_legacy_adapter_without_response_format(temp_db):
    uid = "u_timeout_fb"
    await dbmod.add_memory_fact(uid, "tech", "Usa Linux no servidor", "tech.os")
    await dbmod.add_memory_fact(uid, "tech", "Usa Docker Compose", "tech.docker")

    async def slow_a(**kwargs):
        await asyncio.sleep(2.0)
        return "{}"

    async def fast_b(messages, **kwargs):
        return _keep_all_json(messages, note="Ok via fallback B")

    prov_a = FakeDreamProvider(slow_a)
    prov_b = LegacyNoFormatProvider(fast_b)
    candidates = [
        {"provider": prov_a, "provider_id": "slow", "model_id": "slow/m", "model_name": "m"},
        {"provider": prov_b, "provider_id": "legacy", "model_id": "legacy/m", "model_name": "m"},
    ]

    preview = await simulate_dream_consolidation(
        uid, candidates=candidates, per_call_timeout_s=0.1, execution_deadline_s=5.0
    )
    assert preview["provider_id"] == "legacy"
    assert preview["model_id"] == "legacy/m"
    assert prov_a.calls == 1
    assert prov_b.calls == 1


@pytest.mark.asyncio
async def test_413_splits_batch_within_same_deadline(temp_db):
    facts = [
        {"id": f"id-{i}", "fact": f"Fato longo {i} " + ("palavra " * 120), "is_pinned": 0, "category": "tech", "fact_key": "", "created_at": "2026-10-01"}
        for i in range(4)
    ]

    async def split_on_big(messages, **kwargs):
        aliases = _aliases_from_messages(messages)
        if len(aliases) > 2:
            raise ProviderHTTPError(413, "413 Request Entity Too Large", provider="p1")
        return _keep_all_json(messages, note=f"lote_{len(aliases)}")

    prov = FakeDreamProvider(split_on_big)
    candidates = [{"provider": prov, "provider_id": "p1", "model_id": "p1/m1", "model_name": "m1"}]
    res = await run_dream_analysis(
        facts, candidates, max_tokens=50000, execution_deadline_s=5.0, per_call_timeout_s=2.0
    )
    assert len(res["operations"]) == 4
    assert {op.fact_id for op in res["operations"]} == {f["id"] for f in facts}


@pytest.mark.asyncio
async def test_413_for_one_fact_attempts_fallback_and_omits_provider_body(caplog):
    facts = [{"id": "id-1", "fact": "Usa Python", "is_pinned": 0, "category": "tech", "fact_key": ""}]
    marker = "UNSAFE_TEXT_FROM_PROVIDER_BODY"

    async def too_large(**kwargs):
        raise ProviderHTTPError(413, marker)

    async def succeed(messages, **kwargs):
        return _keep_all_json(messages)

    first = {"provider": FakeDreamProvider(too_large), "provider_id": "a", "model_id": "a/m", "model_name": "m"}
    second = {"provider": FakeDreamProvider(succeed), "provider_id": "b", "model_id": "b/m", "model_name": "m"}
    result = await run_dream_analysis(facts, [first, second])
    assert result["effective_model_id"] == "b/m"
    assert [op.fact_id for op in result["operations"]] == ["id-1"]

    with pytest.raises(DreamLLMError, match="413") as err:
        await run_dream_analysis(facts, [first])
    assert marker not in "".join(traceback.format_exception(err.value))
    assert marker not in caplog.text


@pytest.mark.asyncio
async def test_ollama_compatible_adapter_retries_rejected_json_object_format(monkeypatch):
    payloads = []
    valid_plan = json.dumps({"summary_of_changes": "ok", "operations": []})
    frame = json.dumps({"choices": [{"delta": {"content": valid_plan}, "finish_reason": "stop"}]})

    def send(request):
        payload = json.loads(request.content)
        payloads.append(payload)
        if "response_format" in payload:
            return httpx.Response(400, text="response_format json_object is unsupported by this model")
        return httpx.Response(200, text=f"data: {frame}\n\ndata: [DONE]\n\n")

    @asynccontextmanager
    async def pooled_client(**kwargs):
        async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as client:
            yield client

    monkeypatch.setattr(provider_base, "_pooled_client", pooled_client)
    provider = OpenAICompatProvider("", "http://127.0.0.1:11434/v1")
    result = await call_dream_llm(provider, "some/ollama-model", "ollama", "Respond in JSON.", "facts")
    assert json.loads(result)["summary_of_changes"] == "ok"
    assert len(payloads) == 2
    assert payloads[0]["response_format"] == {"type": "json_object"}
    assert "response_format" not in payloads[1]
    assert all("options" not in payload for payload in payloads)


@pytest.mark.asyncio
async def test_all_candidates_fail_or_second_batch_fails_no_partial_mutation(temp_db):
    uid = "u_no_partial"
    for i in range(6):
        await dbmod.add_memory_fact(uid, "tech", f"Fato grande numero {i} " + ("detalhe " * 80))

    before = await dbmod.get_user_memory(uid, active_only=True)

    # First batch succeeds, second batch fails across all candidates
    async def fail_after_first(messages, call_num, **kwargs):
        if call_num == 1:
            return _keep_all_json(messages)
        raise ProviderHTTPError(503, "503 down", provider="p1")

    async def always_503(**kwargs):
        raise ProviderHTTPError(503, "503 down", provider="p2")

    candidates = [
        {"provider": FakeDreamProvider(fail_after_first), "provider_id": "p1", "model_id": "p1/m1", "model_name": "m1"},
        {"provider": FakeDreamProvider(always_503), "provider_id": "p2", "model_id": "p2/m2", "model_name": "m2"},
    ]

    with pytest.raises(DreamLLMError):
        await execute_dream_consolidation(uid, candidates=candidates, max_tokens=1000)

    after = await dbmod.get_user_memory(uid, active_only=True)
    assert {f["id"] for f in after} == {f["id"] for f in before}
    logs = await dbmod.list_dream_logs(uid)
    assert logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_pinned_protection_and_safety_abort_leave_memory_untouched(temp_db):
    uid = "u_pinned_safe"
    f1 = await dbmod.add_memory_fact(uid, "personal", "Alergico a amendoim", "health.allergy")
    await dbmod.set_memory_fact_pinned(uid, f1, True)
    f2 = await dbmod.add_memory_fact(uid, "tech", "Usa VS Code", "tech.ide")

    async def archive_pinned(messages, **kwargs):
        aliases = _aliases_from_messages(messages)
        return json.dumps({
            "summary_of_changes": "tentando arquivar fixado",
            "operations": [
                {"action": "archive", "fact_id": aliases[0], "reason": "teste"},
                {"action": "keep", "fact_id": aliases[1]},
            ],
        })

    candidates = [
        {"provider": FakeDreamProvider(archive_pinned), "provider_id": "p1", "model_id": "p1/m1", "model_name": "m1"}
    ]
    with pytest.raises(DreamSafetyError, match="PINNED"):
        await execute_dream_consolidation(uid, candidates=candidates)

    active = await dbmod.get_user_memory(uid, active_only=True)
    assert {f["id"] for f in active} == {f1, f2}
    logs = await dbmod.list_dream_logs(uid)
    assert logs[0]["status"] == "aborted_safety"


@pytest.mark.asyncio
async def test_resolution_failure_closes_terminal_dream_log(temp_db):
    uid = "u_no_keys"
    async with aiosqlite.connect(temp_db) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, username, password_hash, role) VALUES (?, 'nokey', 'h', 'user')", (uid,))
        # Disable all providers so no candidate can resolve
        await db.execute("UPDATE providers SET enabled = 0")
        await db.commit()

    await dbmod.add_memory_fact(uid, "tech", "Usa Git diariamente", "tech.git")
    await dbmod.add_memory_fact(uid, "tech", "Usa Docker localmente", "tech.docker")

    with pytest.raises(DreamLLMError):
        await execute_dream_consolidation(uid)

    logs = await dbmod.list_dream_logs(uid)
    assert len(logs) == 1
    assert logs[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_route_dream_candidates_respects_keys_user_prefs_and_exclusions(temp_db):
    uid = "u_router_filter"
    async with aiosqlite.connect(temp_db) as db:
        await db.execute("INSERT OR IGNORE INTO users (id, username, password_hash, role) VALUES (?, 'rf', 'h', 'user')", (uid,))
        await db.execute("UPDATE providers SET enabled = 0")
        await db.execute("UPDATE models SET enabled = 0")
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, api_key, enabled, is_free, is_local) VALUES ('p_keyed', 'Keyed', 'https://example.com/v1', '', 1, 0, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, api_key, enabled, is_free, is_local) VALUES ('p_nokey', 'NoKey', 'https://example.com/v1', '', 1, 0, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, 'p_keyed', 'sk-real-key-123')",
            (uid,),
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, provider_id, name, display_name, context_length, enabled, confirmed_free) VALUES ('p_keyed/m1', 'p_keyed', 'm1', 'M1', 32768, 1, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, provider_id, name, display_name, context_length, enabled, confirmed_free) VALUES ('p_keyed/m2', 'p_keyed', 'm2', 'M2', 65536, 1, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, provider_id, name, display_name, context_length, enabled, confirmed_free) VALUES ('p_nokey/m3', 'p_nokey', 'm3', 'M3', 128000, 1, 0)"
        )
        await db.commit()

        cands = await smart_router.route_dream_candidates(
            db, uid, preferred_model_id="p_keyed/m1", excluded_ids=()
        )
        cand_ids = [c["model_id"] for c in cands]
        assert "p_nokey/m3" not in cand_ids
        assert cand_ids[0] == "p_keyed/m1"
        assert "p_keyed/m2" in cand_ids

        # Excluding m1 promotes m2
        cands_excl = await smart_router.route_dream_candidates(
            db, uid, preferred_model_id="p_keyed/m1", excluded_ids=("p_keyed/m1",)
        )
        assert [c["model_id"] for c in cands_excl] == ["p_keyed/m2"]

        # Disabling m2 for this user excludes it
        await db.execute(
            "INSERT OR REPLACE INTO user_model_settings (user_id, model_id, enabled) VALUES (?, 'p_keyed/m2', 0)",
            (uid,),
        )
        await db.commit()
        cands_disabled = await smart_router.route_dream_candidates(db, uid)
        assert [c["model_id"] for c in cands_disabled] == ["p_keyed/m1"]

        # Global _MODEL_CACHE untouched by user-scoped routing
        assert smart_router._MODEL_CACHE is None


@pytest.mark.asyncio
async def test_preferred_local_dream_filters_remote_and_ineligible_models(temp_db):
    uid = "u_local_dream"
    async with aiosqlite.connect(temp_db) as db:
        await db.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, 'local_dream', 'unused')",
            (uid,),
        )
        await db.execute("UPDATE providers SET enabled = 0")
        await db.execute("UPDATE models SET enabled = 0")
        await db.executemany(
            """INSERT INTO providers (id, name, base_url, enabled, is_local)
               VALUES (?, ?, ?, 1, ?)""",
            [
                ("dream-local", "Local", "http://localhost:8001/v1", 1),
                ("dream-remote", "Remote", "https://example.invalid/v1", 0),
            ],
        )
        await db.executemany(
            """INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, ?, ?)""",
            [(uid, "dream-local", "fake-local-key"), (uid, "dream-remote", "fake-remote-key")],
        )
        await db.executemany(
            """INSERT INTO models (id, provider_id, name, display_name, context_length, enabled)
               VALUES (?, ?, ?, ?, ?, 1)""",
            [
                ("dream-local/chat", "dream-local", "chat", "Chat", 16384),
                ("dream-local/small", "dream-local", "small", "Small", 4096),
                ("dream-local/text-embedding-3-large", "dream-local", "text-embedding-3-large", "Embedding", 16384),
                ("dream-remote/chat", "dream-remote", "chat", "Chat", 16384),
            ],
        )
        await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('dream_provider_id', 'dream-remote')")
        await db.commit()

    result = await resolve_dream_candidates(uid, custom_model="dream-local/chat")
    assert [candidate["model_id"] for candidate in result] == ["dream-local/chat"]

    async with aiosqlite.connect(temp_db) as db:
        await db.execute("UPDATE models SET enabled = 0 WHERE id = 'dream-local/chat'")
        await db.commit()
    with pytest.raises(DreamLLMError, match="elegível"):
        await resolve_dream_candidates(uid, "dream-local", "dream-local/chat")


@pytest.mark.asyncio
async def test_cancellation_propagates_cleanly(temp_db):
    facts = [{"id": "id-1", "fact": "Usa Python", "is_pinned": 0, "category": "tech", "fact_key": "", "created_at": "2026-10-01"}]

    async def cancel_me(**kwargs):
        raise asyncio.CancelledError()

    candidates = [
        {"provider": FakeDreamProvider(cancel_me), "provider_id": "p1", "model_id": "p1/m1", "model_name": "m1"},
        {"provider": FakeDreamProvider(lambda **kw: _keep_all_json(kw["messages"])), "provider_id": "p2", "model_id": "p2/m2", "model_name": "m2"},
    ]
    with pytest.raises(asyncio.CancelledError):
        await run_dream_analysis(facts, candidates)
