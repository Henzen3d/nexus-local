import asyncio
import json
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch, MagicMock

from backend.web_search.planner import plan_search_queries, clean_query_text
from backend.web_search.agent import score_search_result
from backend.database import get_db, init_db
from backend.routers.conversations import get_conversation
from backend.fusion.orchestrator import executar_fusion


def test_planner_query_expansion_conversational():
    """Verifica que o Query Planner remove rodeios conversacionais e foca em marcas/cidades."""
    prompt = "Como faço para criar uma empresa de sucesso como a Fix serviços de Blumenau?"
    queries = plan_search_queries(prompt)
    
    assert len(queries) >= 1
    # Verifica que termos chave como 'fix serviços' e 'Blumenau' estão presentes nas queries
    found_brand = any('"fix serviços"' in q.lower() or "fix" in q.lower() for q in queries)
    found_city = any("blumenau" in q.lower() for q in queries)
    assert found_brand, f"Marca Fix não encontrada nas queries geradas: {queries}"
    assert found_city, f"Cidade Blumenau não encontrada nas queries geradas: {queries}"

    cleaned = clean_query_text(prompt)
    assert "como faço para" not in cleaned.lower()
    assert "de sucesso" not in cleaned.lower()


def test_agent_relevance_scoring_discards_irrelevant_blogs():
    """Verifica que artigos genéricos sem relação com a marca/pergunta são descartados (score zero)."""
    user_query = "Como faço para criar uma empresa de sucesso como a Fix serviços de Blumenau?"
    
    # 1. Artigo genérico de SEO sobre abrir MEI/empresa (ex: egestor)
    irrelevant_result = {
        "title": "Como abrir uma empresa: Passo a passo completo para começar",
        "snippet": "Descubra como registrar o CNPJ, escolher o CNAE e abrir sua microempresa com segurança.",
        "url": "https://blog.egestor.com.br/como-abrir-uma-empresa/",
    }
    score_irrelevant = score_search_result(user_query, irrelevant_result)
    assert score_irrelevant == 0.0, f"Artigo genérico deveria ter score 0, teve {score_irrelevant}"

    # 2. Artigo ou site oficial da Fix Serviços em Blumenau
    relevant_result = {
        "title": "Fix Serviços Elétrica e Hidráulica em Blumenau",
        "snippet": "Serviços especializados em Blumenau/SC. Manutenção elétrica, hidráulica e reparos com garantia.",
        "url": "https://fixblu.com.br/servicos",
    }
    score_relevant = score_search_result(user_query, relevant_result)
    assert score_relevant > 20.0, f"Resultado relevante deveria ter score alto (>20), teve {score_relevant}"


@pytest.mark.asyncio
async def test_conversations_reconstructs_fusion_card_and_search_steps():
    """Garante que ao carregar a conversa (refresh de página), o FusionStatusCard e steps são reconstruídos."""
    await init_db()
    db = await get_db()
    conv_id = "test-conv-fusion-refresh"
    user_id = "user-test-fusion"
    user_msg_id = "msg-user-1"
    asst_msg_id = "msg-asst-1"

    try:
        await db.execute("INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (?, 'tester', 'hash')", (user_id,))
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'Conversa Fusion Teste')",
            (conv_id, user_id),
        )

        sources = [{"title": "Fix Blumenau", "url": "https://fixblu.com.br"}]
        steps = [{"id": "step-1", "title": "Pesquisando na web", "status": "completed"}]
        fusion_meta = {
            "statuses": [
                {
                    "model_id": "test/model-a",
                    "status": "done",
                    "response": "Resposta preliminar modelo A",
                    "confidence": "alta",
                },
                {
                    "model_id": "test/model-b",
                    "status": "done",
                    "response": "Resposta preliminar modelo B",
                    "confidence": "media",
                }
            ],
            "judge_model_id": "test/judge-1",
            "grounding": {"status": "done", "queries": ["query 1"], "found": True},
            "refined_prompt": "Pergunta refinada",
        }

        # Mensagem do usuário com metadados de busca
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, web_search_used, web_search_query, web_search_sources)
               VALUES (?, ?, 'user', 'Como funciona a Fix serviços?', 1, 'Fix serviços Blumenau', ?)""",
            (user_msg_id, conv_id, json.dumps(sources)),
        )

        # Mensagem do assistente com passos de processo e fusion_metadata
        await db.execute(
            """INSERT INTO messages (id, conversation_id, role, content, model_id, process_steps, fusion_metadata)
               VALUES (?, ?, 'assistant', 'Resposta consolidada pelo juiz', 'test/judge-1', ?, ?)""",
            (asst_msg_id, conv_id, json.dumps(steps), json.dumps(fusion_meta)),
        )
        await db.commit()
    finally:
        await db.close()

    # Chama o endpoint get_conversation
    detail = await get_conversation(conv_id, current_user={"id": user_id, "role": "user"})
    messages = detail["messages"]

    # Deve haver 3 mensagens na lista retornada:
    # 1. user
    # 2. fusion_status (virtual reconstruído a partir de fusion_metadata)
    # 3. assistant
    assert len(messages) == 3, f"Esperado 3 mensagens (user, fusion_status, assistant), obtido {len(messages)}"

    msg_roles = [m["role"] for m in messages]
    assert msg_roles == ["user", "fusion_status", "assistant"]

    fusion_msg = messages[1]
    assert fusion_msg["role"] == "fusion_status"
    assert len(fusion_msg["fusion_statuses"]) == 2
    assert fusion_msg["fusion_judge_model_id"] == "test/judge-1"
    assert fusion_msg["fusion_grounding"]["found"] is True
    assert fusion_msg["fusion_refined_prompt"] == "Pergunta refinada"

    asst_msg = messages[2]
    assert asst_msg["role"] == "assistant"
    assert asst_msg["content"] == "Resposta consolidada pelo juiz"
    assert asst_msg["web_search_used"] is True
    assert asst_msg["process_steps"] == steps
    assert asst_msg["web_search_sources"] == sources


@pytest.mark.asyncio
async def test_executar_fusion_persists_metadata_and_notifies_websocket():
    """Garante que executar_fusion salva fusion_metadata e steps, e emite stream_end completo."""
    await init_db()
    conv_id = "test-conv-exec-fusion"
    user_id = "user-test-fusion-exec"
    user_msg_id = "msg-user-exec-1"

    db = await get_db()
    try:
        await db.execute("INSERT OR IGNORE INTO users (id, username, password_hash) VALUES (?, 'tester2', 'hash')", (user_id,))
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'Conversa Fusion Teste 2')",
            (conv_id, user_id),
        )
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', 'Qual a capital do Brasil?')",
            (user_msg_id, conv_id),
        )
        await db.execute(
            "INSERT OR REPLACE INTO fusion_config (id, judge_provider_id, judge_model_id, enabled, grounding_enabled) "
            "VALUES (1, 'mock-provider', 'mock-judge', 1, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO fusion_models (id, provider_id, model_id, position) "
            "VALUES (1, 'mock-provider', 'mock-model', 0)"
        )
        await db.commit()
    finally:
        await db.close()

    mock_ws = AsyncMock()
    ws_sent_messages = []

    async def fake_send_json(payload):
        ws_sent_messages.append(payload)

    mock_ws.send_json = fake_send_json

    # Mock provider stream
    async def mock_stream_chat(*args, **kwargs):
        yield "Brasília é a capital."

    mock_provider = MagicMock()
    mock_provider.stream_chat = mock_stream_chat

    with patch("backend.fusion.orchestrator.get_provider", new=AsyncMock(return_value=mock_provider)), \
         patch("backend.fusion.orchestrator.get_model_name", new=AsyncMock(return_value="mock-model")), \
         patch("backend.ranking.failover.resolve_model_with_failover") as mock_failover:

        from backend.ranking.failover import ResolvedModel
        mock_failover.return_value = ResolvedModel(
            model_id="mock-model",
            provider_id="mock-provider",
            display_name="Mock Model",
            was_failover=False,
            original_model_id="mock-model"
        )

        test_steps = [{"id": "s1", "title": "Busca concluída"}]
        test_sources = [{"title": "Fonte 1", "url": "https://gov.br"}]

        await executar_fusion(
            prompt="Qual a capital do Brasil?",
            history=[{"role": "user", "content": "Qual a capital do Brasil?"}],
            websocket=mock_ws,
            conversation_id=conv_id,
            user_id=user_id,
            user_msg_id=user_msg_id,
            web_search_used=True,
            web_search_query="capital do Brasil",
            web_search_sources=test_sources,
            process_steps=test_steps,
        )

    # Verifica mensagens emitidas pelo WebSocket
    msg_types = [m.get("type") for m in ws_sent_messages]
    assert "fusion_start" in msg_types
    assert "fusion_status" in msg_types
    assert "stream_start" in msg_types
    assert "stream_end" in msg_types

    end_msg = next(m for m in ws_sent_messages if m.get("type") == "stream_end")
    assert end_msg["web_search_used"] is True
    assert end_msg["web_search_query"] == "capital do Brasil"
    assert end_msg["web_search_sources"] == test_sources
    assert end_msg["process_steps"] == test_steps

    # Verifica integridade no banco de dados SQLite temporário
    db = await get_db()
    try:
        async with db.execute(
            "SELECT role, content, fusion_metadata, process_steps FROM messages WHERE conversation_id = ? AND role = 'assistant'",
            (conv_id,),
        ) as cur:
            row = await cur.fetchone()
        assert row is not None, "Mensagem do assistente não foi persistida!"
        role, content, f_meta, p_steps = row
        assert "Brasília" in content
        assert f_meta is not None, "fusion_metadata não foi salvo na mensagem do assistente!"
        parsed_fmeta = json.loads(f_meta)
        assert "statuses" in parsed_fmeta
        assert len(parsed_fmeta["statuses"]) > 0

        assert p_steps is not None, "process_steps não foi salvo na mensagem do assistente!"
        parsed_steps = json.loads(p_steps)
        assert parsed_steps == test_steps
    finally:
        await db.close()
