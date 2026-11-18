"""Contratos WebSocket do chat entre Python (Pydantic) e TypeScript (T2.4)."""
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.orchestration.ws_protocol import (
    ConversationCreatedEvent,
    StreamClearEvent,
    StreamEndFailure,
    StreamEndSuccess,
    StreamStartEvent,
    StreamTokenEvent,
    build_stream_end_failure,
    build_stream_end_success,
    dump_ws_event,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "chat_ws_contract.json"


def _load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_canonical_fixtures_validate_against_python_models():
    data = _load_fixture()
    for entry in data["valid_frames"]:
        kind = entry["expect_kind"]
        payload = entry["payload"]
        name = entry["name"]

        if kind == "conversation_created":
            ev = ConversationCreatedEvent(**payload)
            assert dump_ws_event(ev)["conversation_id"] == payload["conversation_id"]
        elif kind == "stream_start":
            ev = StreamStartEvent(**payload)
            assert dump_ws_event(ev)["conversation_id"] == payload["conversation_id"]
        elif kind == "token":
            ev = StreamTokenEvent(**payload)
            assert dump_ws_event(ev)["content"] == payload["content"]
        elif kind == "stream_clear":
            ev = StreamClearEvent(**payload)
            assert dump_ws_event(ev)["type"] == "stream_clear"
        elif kind == "stream_end_success":
            if "legacy" in name:
                # Legacy frame without explicit outcome still validates when upgraded
                ev = StreamEndSuccess(**payload)
            else:
                ev = StreamEndSuccess(**payload)
            out = dump_ws_event(ev)
            assert out["type"] == "stream_end"
            assert out["outcome"] == "success"
            assert out["message_id"]
            assert out["conversation_id"]
        elif kind == "stream_end_failure":
            if "reason" not in payload:
                # Legacy rollout failure without reason
                ev = StreamEndFailure(reason=payload.get("finish_reason", "error"), **payload)
            else:
                ev = StreamEndFailure(**payload)
            out = dump_ws_event(ev)
            assert out["type"] == "stream_end"
            assert out["outcome"] in ("error", "empty", "timeout", "cancelled")
            assert "message_id" not in out


def test_incomplete_success_frame_rejected_by_pydantic():
    data = _load_fixture()
    incomplete = data["incomplete_success_frame"]
    with pytest.raises(ValidationError):
        StreamEndSuccess(**incomplete)


def test_build_stream_end_success_strips_internal_fields_and_sanitizes_latencies():
    payload = build_stream_end_success(
        message_id="msg-1",
        conversation_id="conv-1",
        turn_id="turn-99",
        cascade_history=[{"model_id": "secret/internal", "detail": "raw stack"}],
        raw_error="secret",
        phase_latencies={"llm_ttfb": 123.456, "bad_nan": float("nan"), "bad_inf": float("inf")},
    )
    assert payload["type"] == "stream_end"
    assert payload["outcome"] == "success"
    assert payload["turn_id"] == "turn-99"
    assert "cascade_history" not in payload
    assert "raw_error" not in payload
    assert payload["phase_latencies"] == {"llm_ttfb": 123.46}


def test_build_stream_end_failure_produces_stable_reason_and_compat_finish_reason():
    payload = build_stream_end_failure(
        reason="empty_response",
        outcome="empty",
        conversation_id="conv-1",
        turn_id="turn-7",
        message="A resposta do modelo foi vazia.",
    )
    assert payload["type"] == "stream_end"
    assert payload["outcome"] == "empty"
    assert payload["reason"] == "empty_response"
    assert payload["finish_reason"] == "empty"
    assert payload["turn_id"] == "turn-7"
    assert "message_id" not in payload
