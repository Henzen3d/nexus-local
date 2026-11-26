import os
import tempfile
import aiosqlite
import pytest

import backend.database as db_mod
import backend.routers.chat as chat_router
import backend.tools.dispatcher as disp_mod
from backend.context.request_context import RequestContext
from backend.tools.base import ToolResult
from backend.tools.intent import (
    detect_dependent_weather_after_web,
    detect_intents,
    extract_validated_location_from_search,
)


@pytest.fixture
async def tool_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(db_mod, "DB_PATH", path)
    await db_mod.init_db()
    yield path
    for ext in ("", "-wal", "-shm"):
        p = path + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


def test_detect_dependent_weather_ignores_placeholder_city():
    prompt = "busca na web onde é o congresso BrasilJS e depois me dá a previsão do tempo da cidade encontrada"
    assert detect_dependent_weather_after_web(prompt) is True
    assert not any(i.family == "weather" for i in detect_intents(prompt))

    direct = "Qual a previsão do tempo em Florianópolis hoje?"
    assert detect_dependent_weather_after_web(direct) is False
    intents = detect_intents(direct)
    assert any(i.family == "weather" and i.params["city"] == "Florianópolis" for i in intents)

    loc = extract_validated_location_from_search(
        [{"title": "BrasilJS", "snippet": "O evento será sediado em Porto Alegre, RS neste mês."}]
    )
    assert loc == "Porto Alegre"


@pytest.mark.asyncio
async def test_chained_search_then_weather_success(tool_db, monkeypatch):
    frames = []
    calls = []

    class _DummyWS:
        async def send_json(self, payload):
            frames.append(payload)

    async def _fake_search(*args, **kwargs):
        sources = [{"index": 1, "title": "BrasilJS Oficial", "url": "https://brasiljs.example"}]
        results = [{"title": "BrasilJS", "snippet": "O congresso acontece em Porto Alegre, RS no auditório central."}]
        steps = [{"id": "search-1", "type": "search", "title": "Pesquisado na web", "detail": "congresso BrasilJS", "status": "completed"}]
        return True, "onde é o congresso BrasilJS", sources, results, {}, steps

    async def _fake_dispatch(family, params, user_id=None, db=None, conversation_id=None):
        calls.append((family, dict(params)))
        return ToolResult(
            success=True,
            data={"city": params.get("city"), "temp_c": 21},
            provider_id="open-meteo",
            family=family,
            cached=True,
        )

    monkeypatch.setattr(chat_router, "_resolve_web_search", _fake_search)
    monkeypatch.setattr(disp_mod, "dispatch_tool", _fake_dispatch)

    req_ctx = RequestContext(user_id="u1", conversation_id="c1")
    web, results, attempted, _ = await chat_router._resolve_turn_evidence(
        _DummyWS(),
        {"web_search": True},
        "busca na web onde é o congresso BrasilJS e depois me dá a previsão do tempo da cidade encontrada",
        "u1",
        "c1",
        intent_res=None,
        history=[],
        intent_routing=None,
        turn_ref={"conversation_id": "c1"},
        request_context=req_ctx,
    )

    assert attempted is True
    assert len(calls) == 1
    assert calls[0][0] == "weather"
    assert calls[0][1]["city"] == "Porto Alegre"
    assert len(results) == 1
    assert web[0] is True
    assert len(web[2]) == 1

    # Passos incluem Etapa 1 (search) + Etapa 2 (tool-weather completed)
    step_ids = {s["id"]: s for s in web[5]}
    assert step_ids["search-1"]["status"] == "completed"
    assert step_ids["tool-weather"]["status"] == "completed"
    assert "open-meteo" in step_ids["tool-weather"]["detail"]

    frame_types = [f["type"] for f in frames]
    assert "tool_executing" in frame_types
    assert "tool_executed" in frame_types
    executed = next(f for f in frames if f["type"] == "tool_executed")
    assert executed["provider"] == "open-meteo"
    assert executed["cached"] is True
    assert req_ctx.get_memo("failed_tools") == []


@pytest.mark.asyncio
async def test_chained_search_preserves_sources_when_weather_fails(tool_db, monkeypatch):
    frames = []

    class _DummyWS:
        async def send_json(self, payload):
            frames.append(payload)

    async def _fake_search(*args, **kwargs):
        sources = [{"index": 1, "title": "Site Evento", "url": "https://evento.example"}]
        results = [{"title": "Encontro Dev", "snippet": "O encontro será realizado em Curitiba, PR."}]
        steps = [{"id": "search-1", "type": "search", "title": "Pesquisado na web", "detail": "encontro dev", "status": "completed"}]
        return True, "onde é o encontro dev", sources, results, {}, steps

    async def _failing_dispatch(family, params, user_id=None, db=None, conversation_id=None):
        return ToolResult(success=False, data=None, provider_id="open-meteo", family=family, error="timeout")

    monkeypatch.setattr(chat_router, "_resolve_web_search", _fake_search)
    monkeypatch.setattr(disp_mod, "dispatch_tool", _failing_dispatch)

    req_ctx = RequestContext(user_id="u1", conversation_id="c1")
    web, results, attempted, _ = await chat_router._resolve_turn_evidence(
        _DummyWS(),
        {"web_search": True},
        "busca na web onde é o encontro dev e me dá a previsão do tempo da cidade encontrada",
        "u1",
        "c1",
        intent_res=None,
        history=[],
        intent_routing=None,
        turn_ref={"conversation_id": "c1"},
        request_context=req_ctx,
    )

    assert attempted is True
    assert results == []
    # Fontes da etapa 1 preservadas integralmente
    assert web[0] is True
    assert len(web[2]) == 1
    assert web[2][0]["url"] == "https://evento.example"

    step_ids = {s["id"]: s for s in web[5]}
    assert step_ids["search-1"]["status"] == "completed"
    assert step_ids["tool-weather"]["status"] == "failed"

    assert any(f["type"] == "tool_failed" and f["family"] == "weather" for f in frames)
    assert len(req_ctx.get_memo("failed_tools")) == 1


@pytest.mark.asyncio
async def test_chained_search_unconfirmed_location_never_guesses(tool_db, monkeypatch):
    frames = []
    calls = []

    class _DummyWS:
        async def send_json(self, payload):
            frames.append(payload)

    async def _fake_search(*args, **kwargs):
        sources = [{"index": 1, "title": "FAQ", "url": "https://faq.example"}]
        results = [{"title": "FAQ", "snippet": "O evento ainda não teve endereço ou município anunciado."}]
        steps = [{"id": "search-1", "type": "search", "title": "Pesquisado na web", "detail": "evento", "status": "completed"}]
        return True, "onde será o evento", sources, results, {}, steps

    async def _fake_dispatch(*args, **kwargs):
        calls.append(args)
        return ToolResult(success=True, data={}, provider_id="open-meteo", family="weather")

    monkeypatch.setattr(chat_router, "_resolve_web_search", _fake_search)
    monkeypatch.setattr(disp_mod, "dispatch_tool", _fake_dispatch)

    req_ctx = RequestContext(user_id="u1", conversation_id="c1")
    web, results, attempted, _ = await chat_router._resolve_turn_evidence(
        _DummyWS(),
        {"web_search": True},
        "pesquise onde será o evento e me diga a previsão do tempo da cidade encontrada",
        "u1",
        "c1",
        intent_res=None,
        history=[],
        intent_routing=None,
        turn_ref={"conversation_id": "c1"},
        request_context=req_ctx,
    )

    assert calls == []
    assert results == []
    assert web[0] is True and len(web[2]) == 1
    assert any(f["type"] == "tool_failed" and f["error"] == "location_not_confirmed" for f in frames)
    assert req_ctx.get_memo("failed_tools")[0]["reason"] == "location_not_confirmed"
