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
async def test_resolve_web_search_auto_router_trigger():
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

    # Mock da busca executada para não chamar rede real
    import backend.routers.chat as chat_module
    orig_resolve_and_execute = chat_module.resolve_and_execute_search
    chat_module.resolve_and_execute_search = AsyncMock(return_value=([], []))

    try:
        req = {"web_search": False}
        used, query, sources, results, cfg, steps = await _resolve_web_search(
            ws=ws_mock,
            db=db_mock,
            req=req,
            user_message="Quem são os candidatos do segundo turno este ano?",
            user_msg_id="msg-1",
            user_id="usr-1",
            conversation_id="conv-1",
            intent_res=intent_res,
        )

        assert used is True
        assert query == "Quem são os candidatos do segundo turno este ano?"
        ws_mock.send_json.assert_any_call({"type": "search_start", "query": query})
    finally:
        chat_module.resolve_and_execute_search = orig_resolve_and_execute
