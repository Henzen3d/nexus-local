import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.database import DB_PATH, init_db
from backend.orchestration.handle_attachments import (
    load_history,
    trim_history_to_budget,
)
from backend.orchestration.resolve_request import stream_from_llm


@pytest.fixture
async def setup_resilience_db():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) VALUES ('prov_test', 'Test Provider', 'http://test', 1, 1)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_fail', 'fail_model', 'Model Fail', 'prov_test', 1, 8192)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_fallback', 'fallback_model', 'Model Fallback', 'prov_test', 1, 8192)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_families (id, display_name) VALUES ('resilience_fam', 'Resilience Family')"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_family_members (family_id, model_id, fallback_order) VALUES ('resilience_fam', 'model_fail', 1)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_family_members (family_id, model_id, fallback_order) VALUES ('resilience_fam', 'model_fallback', 2)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user1', 'prov_test', 'sk-test-key')"
        )
        await db.commit()
    yield DB_PATH


@pytest.mark.asyncio
async def test_load_history_skips_empty_assistant_messages(setup_resilience_db):
    """Garante que mensagens vazias do assistente no histórico não sejam injetadas para quebrar o contexto."""
    async with aiosqlite.connect(DB_PATH) as db:
        conv_id = "test_empty_skip_conv"
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, model_id, provider_id) VALUES (?, 'user1', 'Test', 'model_fail', 'prov_test')",
            (conv_id,),
        )
        # Turno 1: Usuário + Assistente ok
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m1', ?, 'user', 'Bom dia')", (conv_id,))
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m2', ?, 'assistant', 'Olá! Como posso ajudar?')", (conv_id,))
        # Turno 2: Pergunta + Assistente falhou (salvo vazio '')
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m3', ?, 'user', 'Estou testando o NexusLocal')", (conv_id,))
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m4', ?, 'assistant', '')", (conv_id,))
        # Turno 3: Nova pergunta
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m5', ?, 'user', 'oi')", (conv_id,))
        await db.commit()

        history, _, _ = await load_history(
            db=db,
            conversation_id=conv_id,
            user_msg_id="m5",
            attachments_by_msg={},
            extracted_text_by_id={},
            model_supports_vision=False,
            web_search_used=False,
            search_results=[],
            web_search_query="",
            search_config=None,
            format_search_results_fn=None,
            user_id="user1",
            user_query="oi",
        )

        roles_and_contents = [(m["role"], m["content"]) for m in history]
        # A mensagem 'm4' vazia do assistente DEVE ter sido descartada
        assert ("assistant", "") not in roles_and_contents
        # As perguntas 'Bom dia' e 'Estou testando o NexusLocal' foram preservadas
        contents = [m["content"] for m in history]
        assert "Bom dia" in contents
        assert "Olá! Como posso ajudar?" in contents
        assert "Estou testando o NexusLocal" in contents
        assert "oi" in contents


def test_trim_history_preserves_minimum_recent_messages():
    """Garante que orçamentos apertados não descartem 100% do histórico recente."""
    history = [
        {"role": "user", "content": "Primeira mensagem antiga"},
        {"role": "assistant", "content": "Primeira resposta antiga"},
        {"role": "user", "content": "Mensagem recente"},
    ]
    # Com reserved_tokens alto, available ficaria 0 sem o piso mínimo
    kept, removed = trim_history_to_budget(history, budget_tokens=2000, reserved_tokens=3000)
    assert len(kept) >= 1
    assert kept[-1]["content"] == "Mensagem recente"


@pytest.mark.asyncio
async def test_stream_from_llm_cascades_on_empty_model_response(setup_resilience_db):
    """Garante que modelo que retorne 0 tokens (vazio) acione o failover para o próximo em vez de fingir sucesso."""
    mock_ws = AsyncMock()

    class EmptyProvider:
        async def stream_chat(self, **kwargs):
            # Não emite nenhum token (yield nada)
            if False:
                yield "never"

    class GoodFallbackProvider:
        async def stream_chat(self, **kwargs):
            yield "Resposta válida do modelo reserva."

    async with aiosqlite.connect(DB_PATH) as db:
        async def mock_get_provider(pid, database, user_id=None):
            return EmptyProvider()

        call_count = 0
        def provider_factory(current_mid):
            nonlocal call_count
            call_count += 1
            if current_mid == "model_fail":
                return EmptyProvider()
            return GoodFallbackProvider()

        with patch("backend.orchestration.resolve_request.get_provider") as mock_gp:
            async def side_effect(pid, database, user_id=None):
                return EmptyProvider()

            # Força o primeiro modelo a retornar EmptyProvider e o segundo GoodFallbackProvider
            mock_gp.side_effect = lambda pid, d, user_id=None: (
                EmptyProvider() if call_count == 0 else GoodFallbackProvider()
            )

            async def patched_get_provider(pid, database, user_id=None):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return EmptyProvider()
                return GoodFallbackProvider()

            mock_gp.side_effect = patched_get_provider

            res = await stream_from_llm(
                ws=mock_ws,
                db=db,
                conversation_id="conv-empty-failover",
                user_id="user1",
                model_id="model_fail",
                provider_id="prov_test",
                history=[{"role": "user", "content": "teste"}],
            )

            assert res is not None
            full_response, resolved_mid, resolved_pid = res
            assert "Resposta válida do modelo reserva" in full_response
            assert resolved_mid == "model_fallback"


@pytest.mark.asyncio
async def test_load_history_strips_thinking_and_reflection_tags(setup_resilience_db):
    """Garante que tags <think> e <reflection> do assistente em turnos anteriores sejam removidas do histórico."""
    async with aiosqlite.connect(DB_PATH) as db:
        conv_id = "test_strip_thinking_conv"
        await db.execute(
            "INSERT INTO conversations (id, user_id, title, model_id, provider_id) VALUES (?, 'user1', 'Test', 'model_fail', 'prov_test')",
            (conv_id,),
        )
        # Turno 1 com tags de reflexão e pensamento do Beam / DeepSeek
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m_strip_1', ?, 'user', 'Pergunta 1')", (conv_id,))
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES ('m_strip_2', ?, 'assistant', '<reflection>pensando sobre a velocidade...</reflection>\n<think>mais pensamentos</think>\n\nResposta limpa 1')",
            (conv_id,),
        )
        # Turno 2
        await db.execute("INSERT INTO messages (id, conversation_id, role, content) VALUES ('m_strip_3', ?, 'user', 'Pergunta 2')", (conv_id,))
        await db.commit()

        history, _, _ = await load_history(
            db=db,
            conversation_id=conv_id,
            user_msg_id="m_strip_3",
            attachments_by_msg={},
            extracted_text_by_id={},
            model_supports_vision=False,
            web_search_used=False,
            search_results=[],
            web_search_query="",
            search_config=None,
            format_search_results_fn=None,
            user_id="user1",
            user_query="Pergunta 2",
        )

        assistant_msgs = [m for m in history if m["role"] == "assistant"]
        assert len(assistant_msgs) == 1
        assert "<reflection>" not in assistant_msgs[0]["content"]
        assert "<think>" not in assistant_msgs[0]["content"]
        assert assistant_msgs[0]["content"] == "Resposta limpa 1"


@pytest.mark.asyncio
async def test_stream_from_llm_sends_error_when_all_failovers_exhausted(setup_resilience_db):
    """Garante que, se todos os modelos elegíveis falharem (vazio ou erro), um erro explícito é emitido ao WebSocket."""
    mock_ws = AsyncMock()

    class AlwaysEmptyProvider:
        async def stream_chat(self, **kwargs):
            if False:
                yield "never"

    async with aiosqlite.connect(DB_PATH) as db:
        with patch("backend.orchestration.resolve_request.get_provider") as mock_gp:
            mock_gp.return_value = AlwaysEmptyProvider()

            res = await stream_from_llm(
                ws=mock_ws,
                db=db,
                conversation_id="conv-all-empty",
                user_id="user1",
                model_id="model_fail",
                provider_id="prov_test",
                history=[{"role": "user", "content": "teste"}],
            )

            assert res is None
            # Verifica que ws.send_json recebeu ao menos um evento de erro
            calls = [call.args[0] for call in mock_ws.send_json.call_args_list if call.args]
            error_events = [c for c in calls if c.get("type") == "error"]
            assert len(error_events) >= 1
            assert "erro" in error_events[-1]["message"].lower() or "resposta" in error_events[-1]["message"].lower()

