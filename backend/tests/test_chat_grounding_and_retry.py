from unittest.mock import AsyncMock

import pytest

from backend import database
from backend.orchestration.persist_turn import ConversationAccessError
from backend.ranking.failover import FallbackRequirements, resolve_model_with_failover
from backend.ranking.smart_router import load_routing_catalog
from backend.routers import chat
from backend.tools.base import ToolResult


@pytest.fixture
async def chat_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "chat.sqlite")
    await database.init_db()
    db = await database.get_db()
    try:
        await db.execute("INSERT INTO users(id, username, password_hash) VALUES ('chat-test', 'chat-test', '')")
        await db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('tool_auto_detection', 'true')")
        await db.commit()
        yield db
    finally:
        await db.close()


@pytest.fixture
def chat_pipeline(monkeypatch):
    monkeypatch.setattr("backend.orchestration.pre_router.run_pre_router_triage", AsyncMock(return_value=None))
    monkeypatch.setattr(chat, "build_memory_context", AsyncMock(return_value=("", "")))
    monkeypatch.setattr(chat, "resolve_project_context", AsyncMock(return_value=(None, "Prompt de teste")))
    monkeypatch.setattr(chat, "run_post_turn_indexing", AsyncMock())
    monkeypatch.setattr("backend.metrics.task_benchmark_manager.record_task_async", AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question,tool_success,explicit_web,expected_search",
    [
        ("Qual a previsão do tempo em Blumenau?", True, False, None),
        ("Qual a previsão do tempo em Blumenau?", False, False, "Qual a previsão do tempo em Blumenau?"),
        ("Qual a previsão do tempo em Blumenau?", True, True, "Qual a previsão do tempo em Blumenau?"),
        ("Qual a previsão para Blumenau e há algum alerta oficial?", True, False, "há algum alerta oficial Blumenau"),
        ("Qual a previsão para Blumenau e há algum alerta oficial?", False, False,
         "Qual a previsão para Blumenau e há algum alerta oficial?"),
    ],
)
async def test_turn_grounding_uses_tools_and_web_for_their_parts(
    chat_db, monkeypatch, question, tool_success, explicit_web, expected_search,
):
    monkeypatch.setattr(chat, "get_web_search_config", AsyncMock(return_value={"enabled": True}))
    monkeypatch.setattr("backend.tools.dispatcher.is_tools_globally_enabled", AsyncMock(return_value=True))
    dispatch = AsyncMock(return_value=ToolResult(
        success=tool_success, family="weather", provider_id="test-weather",
        data={"forecast": "chuva à tarde"} if tool_success else {},
    ))
    monkeypatch.setattr("backend.tools.dispatcher.dispatch_tool", dispatch)
    web = AsyncMock(return_value={
        "search_results": [{"url": "https://example.org/alertas", "title": "Aviso oficial", "snippet": "Aviso de chuva"}],
    })
    monkeypatch.setattr(chat, "execute_agentic_search", web)

    web_evidence, tools, attempted, answered = await chat._resolve_turn_evidence(
        AsyncMock(), {"web_search": explicit_web}, question, "chat-test", "conversation",
        intent_res=None, history=[], intent_routing=None, turn_ref=None,
    )

    dispatch.assert_awaited_once()
    assert dispatch.call_args.args[1]["city"] == "Blumenau"
    assert attempted
    assert bool(tools) is tool_success
    assert answered == (expected_search is None)
    if expected_search is None:
        web.assert_not_awaited()
        assert not web_evidence[0]
    else:
        web.assert_awaited_once()
        assert web.call_args.args[0] == expected_search
        assert web_evidence[2][0]["url"] == "https://example.org/alertas"


@pytest.mark.asyncio
async def test_mixed_grounding_reaches_the_model_together(chat_db, chat_pipeline, monkeypatch):
    monkeypatch.setattr("backend.tools.dispatcher.is_tools_globally_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr("backend.tools.dispatcher.dispatch_tool", AsyncMock(return_value=ToolResult(
        success=True, family="weather", provider_id="test-weather", data={"forecast": "chuvoso à tarde"},
    )))
    monkeypatch.setattr(chat, "get_web_search_config", AsyncMock(return_value={"enabled": True}))
    monkeypatch.setattr(chat, "execute_agentic_search", AsyncMock(return_value={
        "search_results": [{"url": "https://example.org/alertas", "title": "Aviso oficial", "snippet": "Alerta de alagamento"}],
    }))
    stream = AsyncMock(return_value=None)
    monkeypatch.setattr(chat, "resolve_and_stream", stream)
    await chat._process_turn(
        AsyncMock(), chat_db, {"turn_id": "mixed-turn"}, {"id": "chat-test"}, None,
        "Qual a previsão para Blumenau e há algum alerta oficial?", "groq/openai/gpt-oss-20b",
        "groq", False, [], None, False, False, False,
    )
    history = stream.await_args.args[6]
    assert "chuvoso à tarde" in history[0]["content"]
    assert "Alerta de alagamento" in history[-1]["content"]
    assert "https://example.org/alertas" in history[-1]["content"]
    assert stream.await_args.kwargs["cache_response"] is False


@pytest.mark.asyncio
async def test_retry_reuses_conversation_message_and_bound_document(chat_db, chat_pipeline, tmp_path, monkeypatch):
    from backend.attachments import storage

    attachment_id = "att_" + "a" * 32
    monkeypatch.setattr(storage, "STORAGE_DIR", tmp_path)
    (tmp_path / "relatorio.pdf").write_bytes(b"%PDF-1.4")
    await chat_db.execute(
        """INSERT INTO attachments
           (id, filename, mime_type, file_type, storage_path, extracted_text, user_id, size_bytes, file_hash)
           VALUES (?, 'relatorio.pdf', 'application/pdf', 'document', 'relatorio.pdf',
                   'Receita do relatorio: 7829.', 'chat-test', 8, 'test-hash')""",
        (attachment_id,),
    )
    await chat_db.commit()

    monkeypatch.setattr(chat, "_resolve_web_search", AsyncMock(return_value=(False, "", [], [], None, [])))
    model_id = "groq/openai/gpt-oss-20b"
    stream = AsyncMock(side_effect=[None, ("A receita é 7829.", None, model_id, "groq")])
    monkeypatch.setattr(chat, "resolve_and_stream", stream)
    user = {"id": "chat-test"}
    request = {"request_id": "request-pdf", "reasoning_effort": "high"}
    text = "Quanto foi a receita no documento?"
    socket = AsyncMock()

    async def attempt(turn_id, conversation_id=None, message=text, actor=user):
        await chat._process_turn(
            socket, chat_db, {**request, "turn_id": turn_id}, actor, conversation_id, message,
            model_id, "groq", False, [attachment_id], None, False, False, False,
        )

    await attempt("attempt-one")
    # The client lost the first conversation_created frame and still starts from a blank composer.
    await attempt("attempt-two")
    created = [
        call.args[0]["conversation_id"] for call in socket.send_json.await_args_list
        if call.args[0]["type"] == "conversation_created"
    ]
    assert len(created) == 2 and created[0] == created[1]
    assert stream.await_count == 2
    assert all(call.kwargs["reasoning_effort"] == "high" for call in stream.await_args_list)
    assert all("Receita do relatorio: 7829." in call.args[6][-1]["content"] for call in stream.await_args_list)

    await attempt("attempt-after-success", created[0])
    assert stream.await_count == 2
    assert socket.send_json.await_args.args[0]["finish_reason"] == "already_completed"
    async with chat_db.execute(
        "SELECT m.role, a.id FROM messages m LEFT JOIN attachments a ON a.message_id = m.id WHERE m.conversation_id = ?",
        (created[0],),
    ) as cur:
        assert sorted(await cur.fetchall()) == [("assistant", None), ("user", attachment_id)]
    with pytest.raises(ConversationAccessError):
        await attempt("attempt-changed", created[0], message="Texto diferente")
    with pytest.raises(ConversationAccessError):
        await attempt("attempt-other-owner", created[0], actor={"id": "other-user"})


@pytest.mark.asyncio
async def test_failover_prefers_compatible_free_candidates_and_excludes_hidden_models(chat_db):
    await chat_db.execute("UPDATE models SET enabled = 0")
    await chat_db.executemany(
        "INSERT INTO providers(id, name, base_url, is_free, enabled) VALUES (?, ?, 'https://example.invalid', ?, 1)",
        [("free-test", "Free", 1), ("paid-test", "Paid", 0)],
    )
    await chat_db.execute("UPDATE providers SET enabled = 1 WHERE id = 'openrouter'")
    await chat_db.executemany(
        "INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('chat-test', ?, 'test-key')",
        [("free-test",), ("paid-test",), ("openrouter",)],
    )
    await chat_db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('free_registry_hide_unconfirmed', 'true')")
    models = [
        ("free-test/original", "free-test", "original", 16384, 1, 1, 62),
        ("free-test/reserve", "free-test", "reserve", 16384, 1, 1, 70),
        ("free-test/short", "free-test", "short", 4096, 1, 1, 98),
        ("free-test/text", "free-test", "text", 16384, 0, 1, 98),
        ("paid-test/reserve", "paid-test", "paid", 16384, 1, 0, 95),
        ("openrouter/test/hidden-paid", "openrouter", "hidden", 16384, 1, 0, 99),
    ]
    await chat_db.executemany(
        """INSERT INTO models(id, provider_id, name, context_length, supports_vision, confirmed_free, display_name, enabled)
           VALUES (?, ?, ?, ?, ?, ?, 'Candidate', 1)""",
        [row[:-1] for row in models],
    )
    await chat_db.executemany(
        "INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES (?, ?)",
        [(row[0], row[-1]) for row in models],
    )
    await chat_db.commit()

    catalog = await load_routing_catalog(chat_db, user_id="chat-test")
    assert "openrouter/test/hidden-paid" not in {model["id"] for model in catalog}
    requirements = FallbackRequirements("economical_free", min_context_length=8192, requires_vision=True)
    result = await resolve_model_with_failover(
        "free-test/original", chat_db, force_skip=True, user_id="chat-test", requirements=requirements,
    )
    assert result.model_id == "free-test/reserve"
    result = await resolve_model_with_failover(
        "free-test/original", chat_db, force_skip=True, user_id="chat-test", requirements=requirements,
        exclude_model_ids=["free-test/reserve"],
    )
    assert result.model_id == "paid-test/reserve"
