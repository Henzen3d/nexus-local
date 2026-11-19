"""test_smart_router_web_search.py — Testes da auto-ativação inteligente de busca web.

Valida:
1. Classificação automática de IntentKey.WEB_RESEARCH pelo Smart Router em perguntas factuais de atualidade.
2. Expansão das heurísticas de busca para plurais e eleições.
3. Migração incremental e padrão de heuristic_enabled=1 no banco de dados isolado.
4. Disparo automático no resolvedor de busca web do chat via auto_router.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
import pytest

from backend.ranking.smart_router import IntentKey, classify_intent
from backend.web_search.heuristics import should_search
from backend.routers.chat import _resolve_web_search


@pytest.fixture
def tmp_db():
    from backend import database as dbmod

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    old_db_path = dbmod.DB_PATH
    dbmod.DB_PATH = Path(path)

    import asyncio
    asyncio.run(dbmod.init_db())

    yield dbmod, path

    dbmod.DB_PATH = old_db_path
    try:
        os.remove(path)
    except Exception:
        pass


def test_classify_intent_factual_temporal_queries():
    """Perguntas factuais de atualidade ativam IntentKey.WEB_RESEARCH automaticamente sem toggle manual."""
    queries = [
        "Quem são os candidatos do segundo turno este ano?",
        "Quem é o atual presidente do Brasil?",
        "Qual a cotação do dólar hoje?",
        "Quais são as últimas notícias?",
        "Resultado do jogo de futebol de ontem",
        "Como estão as pesquisas eleitorais deste ano?",
    ]

    for q in queries:
        res = classify_intent(q, web_search=False)
        assert res.intent == IntentKey.WEB_RESEARCH, f"Falha na query: {q}"
        assert any(
            s.startswith("web_factual:") or s.startswith("web_heuristic:")
            for s in res.matched_signals
        ), f"Sinal não encontrado para: {q}"


def test_should_search_expanded_heuristics_plurals_and_elections():
    """Valida expansão de plurais ('quem são', 'quais são', 'como estão', 'resultado das')."""
    queries = [
        "Quem são os candidatos do segundo turno este ano?",
        "Quais são as notícias de hoje?",
        "Como estão as eleições este ano?",
        "Resultado das eleições deste ano",
    ]

    for q in queries:
        should, score = should_search(q, sensitivity="medium")
        assert should is True, f"should_search deveria ser True para: {q} (score={score})"
        assert score >= 0.4


@pytest.mark.asyncio
async def test_database_heuristic_enabled_default_and_migration(tmp_db):
    """Valida que novos bancos têm heuristic_enabled=1 e bancos antigos migram de 0 para 1."""
    dbmod, db_path = tmp_db

    # 1. Verifica que init_db criou com 1
    async with dbmod.aiosqlite.connect(dbmod.DB_PATH) as db:
        async with db.execute("SELECT heuristic_enabled FROM web_search_config WHERE id = 1") as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 1

        # 2. Simula banco antigo com heuristic_enabled = 0
        await db.execute("UPDATE web_search_config SET heuristic_enabled = 0 WHERE id = 1")
        await db.commit()

    # 3. Roda init_db() novamente para disparar a migração incremental
    await dbmod.init_db()

    # 4. Verifica que foi migrado com segurança para 1
    async with dbmod.aiosqlite.connect(dbmod.DB_PATH) as db:
        async with db.execute("SELECT heuristic_enabled FROM web_search_config WHERE id = 1") as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] == 1


@pytest.mark.asyncio
async def test_resolve_web_search_auto_router_trigger(monkeypatch):
    """Valida que quando intent_res é web_research, o resolvedor ativa auto_router mesmo sem web_search_requested."""
    db_mock = MagicMock()
    # Mock do get_web_search_config
    cur_cfg = AsyncMock()
    cur_cfg.fetchone = AsyncMock(return_value=(1, "duckduckgo", "", 5, 0, "medium"))

    class AsyncContextManagerMock:
        def __init__(self, return_val):
            self.return_val = return_val

        async def __aenter__(self):
            return self.return_val

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    db_mock.execute.return_value = AsyncContextManagerMock(cur_cfg)

    # Classificação de intenção simulando auto router
    intent_res = classify_intent("Quem são os candidatos do segundo turno este ano?", web_search=False)
    assert intent_res.intent == IntentKey.WEB_RESEARCH

    ws_mock = AsyncMock()
    ws_mock.send_json = AsyncMock()

    import backend.routers.chat as chat_module
    question = "Quem são os candidatos do segundo turno este ano?"
    snippet = {"url": "https://example.com/election", "title": "Resultados", "snippet": "Dados sintéticos"}
    execute = AsyncMock(return_value={"search_results": [snippet], "executed_queries": [question]})
    monkeypatch.setattr(chat_module, "execute_agentic_search", execute)

    used, query, sources, results, cfg, steps = await _resolve_web_search(
        ws=ws_mock,
        db=db_mock,
        req={"web_search": False},
        user_message=question,
        user_msg_id="msg-1",
        user_id="usr-1",
        conversation_id="conv-1",
        intent_res=intent_res,
        defer_telemetry=True,
    )

    assert used is True
    assert query == question
    assert sources[0]["url"] == snippet["url"]
    assert cfg["_telemetry"]["trigger_type"] == "auto_router"
    execute.assert_awaited_once()
    ws_mock.send_json.assert_any_call({"type": "search_start", "query": query})


# ── T2.1: Fast factual budget, deadline sharing, read timeout reuse, reader index fix ──

def test_select_search_budget_pt_en_es_and_exclusions():
    from backend.orchestration.pre_router import classify_heuristic_triage
    from backend.web_search.agent import select_search_budget

    # Fast factual eligible in PT, EN, ES
    fast_cases = [
        "Qual o clima em Curitiba amanhã em °C?",
        "What is the weather in Tokyo today in Fahrenheit?",
        "What is the forecast for Thursday in Porto?",
        "¿Cuál es el pronóstico del clima en Madrid hoy?",
        "Cotação do dólar hoje",
        "Current USD to EUR exchange rate",
        "Precio del bitcoin hoy",
    ]
    for q in fast_cases:
        routing = classify_heuristic_triage(q)
        b = select_search_budget(q, intent_routing=routing)
        assert b.mode == "fast_factual", f"Esperado fast_factual para: {q}"
        assert b.max_queries == 1
        assert b.max_results == 3
        assert b.max_main_reads == 1
        assert b.max_sub_articles == 0
        assert b.deadline_s == 4.0

    # Weather preserves locality, date, and unit without fabricating missing city
    r_weather = classify_heuristic_triage("Qual o clima em Curitiba amanhã em °C?")
    assert r_weather.search_queries
    assert "curitiba" in r_weather.search_queries[0].lower()
    assert "amanhã" in r_weather.search_queries[0].lower()
    assert "°c" in r_weather.search_queries[0].lower()

    # Ambiguous weather (no locality) -> does NOT infer a city & keeps standard budget
    r_ambig = classify_heuristic_triage("Como está o clima hoje?")
    assert select_search_budget("Como está o clima hoje?", intent_routing=r_ambig).mode == "standard"
    if r_ambig.search_queries:
        assert "são paulo" not in r_ambig.search_queries[0].lower()
        assert "curitiba" not in r_ambig.search_queries[0].lower()

    # Broad research, comparison, or target URL -> standard budget preserved
    standard_cases = [
        "Qual a previsão do tempo nesta semana?",
        "What will the weather be like next Tuesday?",
        "¿Cuál es el pronóstico del tiempo para esta semana?",
        "Compare Python vs Rust para servidores web de alta concorrência",
        "Faça uma pesquisa completa sobre baterias de estado sólido",
        "Veja as novidades no site example.com/blog sobre lançamentos",
        "Deep research on quantum error correction methods",
    ]
    for q in standard_cases:
        routing = classify_heuristic_triage(q)
        b = select_search_budget(q, intent_routing=routing)
        assert b.mode == "standard", f"Esperado standard para: {q}"
        assert b.max_main_reads == 2
        assert b.max_sub_articles == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["search", "reader"])
async def test_cancelling_agent_search_drains_running_children(monkeypatch, stage):
    import asyncio
    from backend.web_search import agent as agent_mod

    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def block():
        started.set()
        try:
            await asyncio.Future()
        finally:
            cleaned.set()

    async def search(*args, **kwargs):
        if stage == "search":
            await block()
        return [{"title": "Weather in Porto", "url": "https://example.com/porto", "snippet": "Weather"}]

    async def read(*args, **kwargs):
        if stage == "reader":
            await block()

    monkeypatch.setattr(agent_mod, "resolve_and_execute_search", search)
    monkeypatch.setattr(agent_mod, "deep_read_target", read)
    monkeypatch.setattr(agent_mod, "score_search_result", lambda *args, **kwargs: 10)
    parent = asyncio.create_task(agent_mod.execute_agentic_search(
        "Weather in Porto", None, {}, pre_planned_queries=["Weather in Porto"],
    ))
    await asyncio.wait_for(started.wait(), timeout=1)
    parent.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(parent, timeout=1)
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_execute_agentic_search_fast_budget_and_read_timeout_reuses_snippets(monkeypatch):
    import asyncio
    from backend.web_search import agent as agent_mod
    from backend.web_search.agent import SearchBudget, execute_agentic_search

    search_calls = []
    read_calls = []
    events = []

    async def fake_search(query, db, cfg, *, max_results_override=None, timeout=None):
        search_calls.append((query, max_results_override, timeout))
        return [
            {"title": "Clima Curitiba", "url": "https://clima.example.com/curitiba", "snippet": "22°C nublado em Curitiba"},
            {"title": "Previsao Curitiba", "url": "https://tempo.example.com/curitiba", "snippet": "Chuva leve à tarde"},
            {"title": "Local privado", "url": "http://127.0.0.1/secret", "snippet": "nao deve entrar"},
            {"title": "Quarto resultado", "url": "https://extra.example.com/curitiba", "snippet": "extra"},
            {"title": "Quinto resultado", "url": "https://quinto.example.com/curitiba", "snippet": "quinto"},
        ]

    read_cancelled = False

    async def slow_read(url, max_sub_articles=3, timeout=6.0):
        nonlocal read_cancelled
        read_calls.append((url, max_sub_articles, timeout))
        try:
            await asyncio.sleep(5.0)
            return {"url": url, "title": "Late", "text_sample": "late"}
        except asyncio.CancelledError:
            read_cancelled = True
            raise

    monkeypatch.setattr(agent_mod, "resolve_and_execute_search", fake_search)
    monkeypatch.setattr(agent_mod, "deep_read_target", slow_read)

    fast_short = SearchBudget(
        mode="fast_factual",
        max_queries=1,
        max_results=3,
        max_main_reads=1,
        max_sub_articles=0,
        deadline_s=0.25,
    )

    async def on_evt(evt):
        events.append(evt)

    res = await execute_agentic_search(
        "Qual o clima em Curitiba amanhã?",
        db=None,
        search_config={"enabled": True, "max_results": 5},
        on_event=on_evt,
        pre_planned_queries=["clima curitiba amanhã", "segunda query ignorada"],
        budget=fast_short,
    )

    # Only 1 query, max 3 public results, private URL filtered, at most 1 main read with 0 sub-articles
    assert len(search_calls) == 1
    assert search_calls[0][1] == 3
    assert len(res["search_results"]) == 3
    assert all("127.0.0.1" not in r["url"] for r in res["search_results"])
    assert len(read_calls) == 1
    assert read_calls[0][1] == 0
    # Slow read was cancelled cleanly, snippets preserved, and every step closed!
    assert read_cancelled is True
    assert res["scraped_pages"] == []
    assert res["metrics"]["mode"] == "fast_factual"
    assert res["metrics"]["queries_executed"] == 1
    assert res["metrics"]["results_returned"] == 3
    assert res["metrics"]["reads_started"] == 1
    assert res["metrics"]["reads_completed"] == 0
    assert res["metrics"]["read_timed_out"] is True
    assert res["metrics"]["timed_out"] is True

    started_ids = {e["id"] for e in events if e["type"] == "process_step_start"}
    ended_ids = {e["id"] for e in events if e["type"] == "process_step_end"}
    assert started_ids == ended_ids


@pytest.mark.asyncio
async def test_execute_agentic_search_no_useful_evidence(monkeypatch):
    from backend.web_search import agent as agent_mod
    from backend.web_search.agent import SearchBudget, execute_agentic_search

    async def empty_search(query, db, cfg, *, max_results_override=None, timeout=None):
        return []

    monkeypatch.setattr(agent_mod, "resolve_and_execute_search", empty_search)
    res = await execute_agentic_search(
        "Cotação do dólar hoje",
        db=None,
        search_config={"enabled": True, "max_results": 5},
        budget=SearchBudget.fast_factual(),
    )
    assert res["search_results"] == []
    assert res["scraped_pages"] == []
    assert res["metrics"]["results_returned"] == 0
    assert res["metrics"]["reads_started"] == 0
    assert res["metrics"]["reads_completed"] == 0


@pytest.mark.asyncio
async def test_deep_read_target_preserves_original_article_index_and_respects_zero_sub(monkeypatch):
    from backend.web_search import reader as reader_mod

    fetched_urls = []

    async def fake_fetch(url, timeout=6.0):
        fetched_urls.append(url)
        if url == "https://news.example.com/":
            return {
                "url": url,
                "title": "News",
                "text_sample": "Headlines",
                "articles": [
                    {"title": "Art 0", "url": "https://news.example.com/0", "date": "2026-10-01"},
                    {"title": "Art 1", "url": "https://news.example.com/1", "date": None},
                    {"title": "Art 2", "url": "https://news.example.com/2", "date": None},
                ],
            }
        if url.endswith("/1"):
            return {"url": url, "published_date": "2026-10-02", "text_sample": ""}
        if url.endswith("/2"):
            return {"url": url, "published_date": "2026-10-03", "text_sample": ""}
        return None

    monkeypatch.setattr(reader_mod, "fetch_page_content", fake_fetch)

    # max_sub_articles=0 -> only main page fetched
    page0 = await reader_mod.deep_read_target("https://news.example.com/", max_sub_articles=0, timeout=3.0)
    assert fetched_urls == ["https://news.example.com/"]
    assert page0["articles"][1]["date"] is None

    # max_sub_articles=3 -> dates assigned to exact original indices 1 and 2, NOT shifted to 0!
    fetched_urls.clear()
    page = await reader_mod.deep_read_target("https://news.example.com/", max_sub_articles=3, timeout=3.0)
    assert page["articles"][0]["date"] == "2026-10-01"
    assert page["articles"][1]["date"] == "2026-10-02"
    assert page["articles"][2]["date"] == "2026-10-03"
