"""Dream payload: aliases curtos, fatiamento e heartbeat SSE."""
import asyncio
import json

import pytest

from backend.memory_dream import (
    DreamLLMError,
    DreamOperation,
    DreamSafetyError,
    analyze_facts,
    estimate_tokens,
    extract_json_payload,
    iter_sse_events,
    remap_operation_ids,
    render_facts_payload,
    split_facts_for_budget,
    verify_dream_safety,
)


def _fact(fid: str, text: str = "Usa Linux") -> dict:
    return {
        "id": fid,
        "fact": text,
        "is_pinned": 0,
        "category": "tech",
        "fact_key": "",
        "created_at": "2026-10-01",
    }


def test_payload_uses_short_alias_not_uuid():
    uid = "d5518ef9-e82a-45ca-bccd-b7a623c6e101"
    alias_map, payload = render_facts_payload([_fact(uid)], "2026-10-10")
    assert alias_map == {"f1": uid}
    assert "[ID: f1 |" in payload
    assert uid not in payload
    assert "d5518ef9" not in payload


def test_alias_roundtrip_before_safety():
    uid = "d5518ef9-e82a-45ca-bccd-b7a623c6e101"
    facts = [_fact(uid)]
    alias_map, _payload = render_facts_payload(facts, "2026-10-10")
    ops = [DreamOperation(action="keep", fact_id="f1")]
    remap_operation_ids(ops, alias_map, facts)
    assert ops[0].fact_id == uid
    verify_dream_safety(facts, ops)


def test_unique_uuid_prefix_resolves():
    uid = "d5518ef9-e82a-45ca-bccd-b7a623c6e101"
    facts = [_fact(uid)]
    ops = [DreamOperation(action="keep", fact_id="d5518ef9")]
    remap_operation_ids(ops, {"f1": uid}, facts)
    assert ops[0].fact_id == uid


def test_invented_short_id_is_not_guessed():
    facts = [_fact("d5518ef9-e82a-45ca-bccd-b7a623c6e101")]
    ops = [DreamOperation(action="keep", fact_id="fbebb04f")]
    remap_operation_ids(ops, {"f1": facts[0]["id"]}, facts)
    assert ops[0].fact_id == "fbebb04f"
    with pytest.raises(DreamSafetyError, match="ID inexistente"):
        verify_dream_safety(facts, ops)


def test_chunks_stay_under_token_budget():
    facts = [_fact(f"id-{i}", "palavra " * 400) for i in range(12)]
    system = "instrucao " * 80
    chunks = split_facts_for_budget(facts, system, max_tokens=1500)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) == len(facts)
    for chunk in chunks:
        _alias, payload = render_facts_payload(chunk, "2026-10-10")
        request_tokens = estimate_tokens(system) + estimate_tokens("Fatos para Consolidação:\n" + payload)
        assert request_tokens <= 1500 or len(chunk) == 1


@pytest.mark.asyncio
async def test_413_splits_chunk_and_remaps_aliases():
    facts = [_fact(f"uuid-{i}-aaaa-bbbb-cccc", "fato " * 180) for i in range(6)]

    async def caller(_system: str, payload: str) -> str:
        if estimate_tokens(payload) > 700:
            raise DreamLLMError(
                "Provider error 413: Request too large for model, Requested 8900, Limit 8000"
            )
        aliases = []
        for line in payload.splitlines():
            if line.startswith("[ID: "):
                aliases.append(line.split(" ", 2)[1])
        return json.dumps(
            {
                "summary_of_changes": "manteve o lote",
                "operations": [{"action": "keep", "fact_id": alias} for alias in aliases],
            }
        )

    ops, notes = await analyze_facts(facts, "sys " * 20, caller, max_tokens=900)
    assert notes
    assert len(ops) == 6
    assert {op.fact_id for op in ops} == {f["id"] for f in facts}


def test_json_after_think_tag_is_extracted():
    raw = '<think>vou fundir f1 e f2</think>\n{"summary_of_changes":"ok","operations":[{"action":"keep","fact_id":"f1"}]}'
    parsed = json.loads(extract_json_payload(raw))
    assert parsed["operations"][0]["fact_id"] == "f1"


def test_json_only_inside_think_is_extracted():
    raw = '<think>{"summary_of_changes":"dentro","operations":[]}</think>'
    parsed = json.loads(extract_json_payload(raw))
    assert parsed["summary_of_changes"] == "dentro"


@pytest.mark.asyncio
async def test_sse_keepalive_while_model_is_silent():
    queue: asyncio.Queue = asyncio.Queue()
    gen = iter_sse_events(queue, heartbeat_s=0.05)
    first = await asyncio.wait_for(gen.__anext__(), 1)
    assert first.startswith(": keepalive")
    await queue.put({"step": "reasoning", "pct": 60, "msg": "analisando"})
    second = await asyncio.wait_for(gen.__anext__(), 1)
    assert second.startswith("data: ")
    assert "reasoning" in second
    await queue.put(None)
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(gen.__anext__(), 1)
