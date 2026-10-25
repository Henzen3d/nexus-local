import pytest
import aiosqlite
import json
from unittest.mock import AsyncMock, MagicMock, patch

from backend.orchestration.resolve_request import (
    build_cascade_error_summary,
    send_and_persist_error,
)


def test_build_cascade_error_summary():
    cascade_history = [
        {"attempt": 1, "model_id": "orcarouter/deepseek/deepseek-v4.1-flash-1017", "provider_id": "orcarouter", "detail": "Cota/crédito esgotado (402)"},
        {"attempt": 2, "model_id": "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free", "provider_id": "openrouter", "detail": "Modelo finalizou sem gerar nenhum token de resposta."},
        {"attempt": 3, "model_id": "llm7/DeepSeek-V4-Flash-0731", "provider_id": "llm7", "detail": "Erro do provedor: Model unavailable 400"},
        {"attempt": 4, "model_id": "gemini/gemini-3.8-flash", "provider_id": "gemini", "detail": "Tempo limite de resposta excedido (15s)"},
    ]
    summary = build_cascade_error_summary(cascade_history, "Tempo limite de resposta esgotado após tentativas de failover.")
    assert "Tempo limite de resposta esgotado após tentativas de failover." in summary
    assert "Tentei 4 modelos alternativos sem sucesso" in summary


@pytest.mark.asyncio
async def test_send_and_persist_error(tmp_path):
    db_path = tmp_path / "test_error_persistence.db"
    db = await aiosqlite.connect(str(db_path))
    await db.executescript(
        """
        CREATE TABLE conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            user_id TEXT,
            model_id TEXT,
            provider_id TEXT,
            created_at TEXT,
            updated_at TEXT
        );
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            role TEXT,
            content TEXT,
            created_at TEXT,
            model_id TEXT,
            provider TEXT,
            relay_used INTEGER DEFAULT 0,
            relay_model TEXT,
            kind TEXT DEFAULT 'normal'
        );
        INSERT INTO conversations (id, title, user_id) VALUES ('conv-123', 'Café', 'user-1');
        """
    )
    await db.commit()

    sent_ws = []
    class FakeWs:
        async def send_json(self, payload):
            sent_ws.append(payload)

    cascade = [
        {"attempt": 1, "model_id": "model-a", "provider_id": "prov-a", "detail": "402 Out of credits"},
        {"attempt": 2, "model_id": "model-b", "provider_id": "prov-b", "detail": "Timeout 15s"},
    ]
    await send_and_persist_error(
        FakeWs(),
        db,
        "conv-123",
        "Tempo limite de resposta esgotado.",
        cascade,
        "model-b",
        "prov-b",
    )

    # 1. Checa envio WebSocket: primeiro stream_clear (limpa rascunho residual),
    # depois o frame de erro.
    assert len(sent_ws) == 2
    assert sent_ws[0]["type"] == "stream_clear"
    msg = sent_ws[1]
    assert msg["type"] == "error"
    assert "Tempo limite de resposta esgotado." in msg["message"]
    assert "Tentei 2 modelos alternativos" in msg["message"]
    assert msg.get("retry_suggested") is True
    assert msg.get("attempts") == 2

    # 2. Checa persistência no SQLite com kind='error'
    async with db.execute("SELECT role, content, kind, model_id FROM messages WHERE conversation_id = 'conv-123'") as cur:
        row = await cur.fetchone()
        assert row is not None
        role, content, kind, model_id = row
        assert role == "assistant"
        assert kind == "error"
        assert "Tempo limite de resposta esgotado." in content
        assert "Tentei 2 modelos alternativos" in content
        assert model_id == "model-b"

    await db.close()


@pytest.mark.asyncio
async def test_gemini_thinking_extraction():
    from backend.providers.base import GeminiProvider

    chunk1 = {"candidates": [{"content": {"parts": [{"text": "Vou calcular a cafeina extraída...", "thought": True}]}}]}
    chunk2 = {"candidates": [{"content": {"parts": [{"text": " Um expresso de 36g costuma conter..."}]}}]}
    sse_lines = [
        f"data: {json.dumps(chunk1)}",
        f"data: {json.dumps(chunk2)}",
    ]

    class FakeResponse:
        status_code = 200
        async def aiter_lines(self):
            for line in sse_lines:
                yield line
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    class FakeClient:
        def stream(self, method, url, **kwargs):
            return FakeResponse()
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    with patch("backend.providers.base._pooled_client", return_value=FakeClient()):
        p = GeminiProvider("AIzaSyFakeKey", "https://generativelanguage.googleapis.com")
        received_tokens = []
        async for token in p.stream_chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "café"}]):
            received_tokens.append(token)

    full_text = "".join(received_tokens)
    assert "<think>" in full_text
    assert "Vou calcular a cafeina extraída..." in full_text
    assert "</think>" in full_text
    assert "Um expresso de 36g costuma conter..." in full_text
