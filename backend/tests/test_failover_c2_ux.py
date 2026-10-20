"""Testes para o item C2 do Golden Prompt v3.0:
UX de failover invisível, pré-commit buffer e metadados terminais.
"""
import asyncio
import aiosqlite
import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.orchestration.resolve_request import (
    build_final_model_metadata,
    stream_from_llm,
)


@pytest.fixture
async def temp_db(tmp_path):
    db_path = tmp_path / "test_c2.db"
    db = await aiosqlite.connect(str(db_path))
    await db.executescript(
        """
        CREATE TABLE models (
            id TEXT PRIMARY KEY,
            name TEXT,
            display_name TEXT,
            provider_id TEXT,
            reasoning_control TEXT,
            reasoning_levels TEXT,
            reasoning_default TEXT
        );
        INSERT INTO models (id, name, display_name, provider_id) VALUES
            ('prov_a/model-a', 'model_a', 'Model A', 'prov_a'),
            ('prov_b/model-b', 'model_b', 'Model B', 'prov_b');
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
        INSERT OR REPLACE INTO meta (key, value) VALUES ('failover_total_budget_sec', '30');
        CREATE TABLE IF NOT EXISTS model_usage_log (
            id TEXT PRIMARY KEY,
            model_id TEXT,
            provider_id TEXT,
            conversation_id TEXT,
            user_id TEXT,
            was_fallback INTEGER,
            fallback_from_model_id TEXT,
            fallback_reason TEXT,
            was_auto_routed INTEGER,
            route_intent TEXT,
            route_confidence REAL,
            route_latency_ms REAL,
            route_policy TEXT
        );
        """
    )
    await db.commit()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_build_final_model_metadata_extended_fields(temp_db):
    """Verifica que build_final_model_metadata retorna tanto os campos legados quanto os novos opcionais."""
    meta = await build_final_model_metadata(
        temp_db,
        requested_model_id="prov_a/model-a",
        resolved_model_id="prov_b/model-b",
        resolved_provider_id="prov_b",
        failover_tier="tier1_same_family",
        spliced=False,
        outcome="success",
        attempt_count=2,
    )
    # Campos legados intactos
    assert meta["was_fallback"] is True
    assert meta["final_model_id"] == "prov_b/model-b"
    assert meta["final_model_name"] == "Model B"
    assert meta["final_provider_id"] == "prov_b"
    # Novos campos C2
    assert meta["requested_model"] == "prov_a/model-a"
    assert meta["served_by"] == "prov_b/model-b"
    assert meta["failover_tier"] == "tier1_same_family"
    assert meta["spliced"] is False
    assert meta["outcome"] == "success"
    assert meta["attempt_count"] == 2


@pytest.mark.asyncio
async def test_precommit_buffer_discards_failed_candidate_tokens(temp_db, monkeypatch):
    """Candidato que falha antes do commit (menos de 24 chars) tem seus tokens integralmente descartados."""
    sent_messages = []

    class FakeWebSocket:
        async def send_json(self, payload):
            sent_messages.append(payload)

    class FailingStream:
        def __init__(self):
            self.step = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.step == 0:
                self.step += 1
                return "Err"
            raise RuntimeError("Provider crashed early")

        async def aclose(self):
            pass

    class SuccessStream:
        def __init__(self):
            self.tokens = ["Resposta ", "completa ", "e ", "saudável ", "do ", "modelo ", "reserva."]
            self.idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.idx < len(self.tokens):
                tok = self.tokens[self.idx]
                self.idx += 1
                return tok
            raise StopAsyncIteration

        async def aclose(self):
            pass

    class FakeProviderA:
        def stream_chat(self, *args, **kwargs):
            return FailingStream()

    class FakeProviderB:
        def stream_chat(self, *args, **kwargs):
            return SuccessStream()

    async def fake_get_provider(provider_id, db, user_id=None):
        if provider_id == "prov_a":
            return FakeProviderA()
        return FakeProviderB()

    async def fake_get_model_name(model_id, db):
        return model_id.split("/")[-1]

    from backend.orchestration import resolve_request

    # Configura resolução com failover para alternar de A para B
    attempt_counter = 0

    class ResolvedMock:
        def __init__(self, m_id, p_id, was_fb=False):
            self.model_id = m_id
            self.provider_id = p_id
            self.display_name = m_id
            self.was_failover = was_fb
            self.failover_reason = "error" if was_fb else None
            self.failover_tier = "tier1_same_family" if was_fb else None

    async def fake_resolve_model_with_failover(*args, **kwargs):
        nonlocal attempt_counter
        attempt_counter += 1
        if attempt_counter == 1:
            return ResolvedMock("prov_a/model-a", "prov_a", was_fb=False)
        return ResolvedMock("prov_b/model-b", "prov_b", was_fb=True)

    monkeypatch.setattr(resolve_request, "get_provider", fake_get_provider)
    monkeypatch.setattr(resolve_request, "get_model_name", fake_get_model_name)
    monkeypatch.setattr(resolve_request, "resolve_model_with_failover", fake_resolve_model_with_failover)
    monkeypatch.setattr(resolve_request, "mark_model_success", AsyncMock())
    monkeypatch.setattr(resolve_request, "record_request", AsyncMock())

    ws = FakeWebSocket()
    result = await stream_from_llm(
        ws=ws,
        db=temp_db,
        conversation_id="c1",
        user_id="u1",
        model_id="prov_a/model-a",
        provider_id="prov_a",
        history=[{"role": "user", "content": "Olá"}],
    )

    assert result is not None
    full_response, final_m, final_p = result[:3]
    failover_meta = getattr(result, "failover_meta", {})
    assert final_m == "prov_b/model-b"
    assert "Resposta completa" in full_response

    # Verifica que nenhum token 'Err' do candidato 1 chegou ao cliente!
    token_messages = [m for m in sent_messages if m.get("type") == "token"]
    all_sent_text = "".join(m["content"] for m in token_messages)
    assert "Err" not in all_sent_text
    assert "Resposta completa" in all_sent_text

    # Verifica que não foi emitido nenhum failover_notice (failover invisível no sucesso)
    notice_messages = [m for m in sent_messages if m.get("type") == "failover_notice"]
    assert len(notice_messages) == 0

    # Metadados de failover conferem
    assert failover_meta["requested_model"] == "prov_a/model-a"
    assert failover_meta["served_by"] == "prov_b/model-b"
    assert failover_meta["attempt_count"] == 2


@pytest.mark.asyncio
async def test_precommit_forces_commit_on_short_completion(temp_db, monkeypatch):
    """Resposta curta válida (ex: 'Sim.' < 24 chars) deve sofrer force commit e ser enviada."""
    sent_messages = []

    class FakeWebSocket:
        async def send_json(self, payload):
            sent_messages.append(payload)

    class ShortStream:
        def __init__(self):
            self.tokens = ["Sim", "."]
            self.idx = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.idx < len(self.tokens):
                tok = self.tokens[self.idx]
                self.idx += 1
                return tok
            raise StopAsyncIteration

        async def aclose(self):
            pass

    class FakeProvider:
        def stream_chat(self, *args, **kwargs):
            return ShortStream()

    from backend.orchestration import resolve_request

    monkeypatch.setattr(resolve_request, "get_provider", AsyncMock(return_value=FakeProvider()))
    monkeypatch.setattr(resolve_request, "get_model_name", AsyncMock(return_value="model_a"))
    monkeypatch.setattr(resolve_request, "mark_model_success", AsyncMock())
    monkeypatch.setattr(resolve_request, "record_request", AsyncMock())

    class ResolvedMock:
        model_id = "prov_a/model-a"
        provider_id = "prov_a"
        display_name = "Model A"
        was_failover = False
        failover_reason = None

    monkeypatch.setattr(resolve_request, "resolve_model_with_failover", AsyncMock(return_value=ResolvedMock()))

    ws = FakeWebSocket()
    result = await stream_from_llm(
        ws=ws,
        db=temp_db,
        conversation_id="c1",
        user_id="u1",
        model_id="prov_a/model-a",
        provider_id="prov_a",
        history=[{"role": "user", "content": "Ok?"}],
    )

    assert result is not None
    full_response, final_m, final_p = result[:3]
    failover_meta = getattr(result, "failover_meta", {})
    assert full_response == "Sim."

    token_messages = [m for m in sent_messages if m.get("type") == "token"]
    all_sent_text = "".join(m["content"] for m in token_messages)
    assert all_sent_text == "Sim."


@pytest.mark.asyncio
async def test_terminal_failure_emits_single_error(temp_db, monkeypatch):
    """Quando todos os modelos falham, um único evento terminal de erro é enviado e retorna None."""
    sent_messages = []

    class FakeWebSocket:
        async def send_json(self, payload):
            sent_messages.append(payload)

    class CrashingStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RuntimeError("Hard provider crash")

        async def aclose(self):
            pass

    class FakeProvider:
        def stream_chat(self, *args, **kwargs):
            return CrashingStream()

    from backend.orchestration import resolve_request

    monkeypatch.setattr(resolve_request, "get_provider", AsyncMock(return_value=FakeProvider()))
    monkeypatch.setattr(resolve_request, "get_model_name", AsyncMock(return_value="model_a"))
    monkeypatch.setattr(resolve_request, "mark_model_success", AsyncMock())
    monkeypatch.setattr(resolve_request, "record_request", AsyncMock())

    class ResolvedMock:
        def __init__(self, idx):
            self.model_id = f"prov_a/model-{idx}"
            self.provider_id = "prov_a"
            self.display_name = f"Model {idx}"
            self.was_failover = idx > 1
            self.failover_reason = "error" if idx > 1 else None

    attempt_counter = 0

    async def fake_resolve(*args, **kwargs):
        nonlocal attempt_counter
        attempt_counter += 1
        return ResolvedMock(attempt_counter)

    monkeypatch.setattr(resolve_request, "resolve_model_with_failover", fake_resolve)

    ws = FakeWebSocket()
    result = await stream_from_llm(
        ws=ws,
        db=temp_db,
        conversation_id="c1",
        user_id="u1",
        model_id="prov_a/model-1",
        provider_id="prov_a",
        history=[{"role": "user", "content": "Teste"}],
    )

    assert result is None
    error_messages = [m for m in sent_messages if m.get("type") == "error"]
    # Exatamente um erro terminal emitido
    assert len(error_messages) == 1
    # Nenhum token emitido
    token_messages = [m for m in sent_messages if m.get("type") == "token"]
    assert len(token_messages) == 0
