"""Reflection / Beam: histórico, streaming e erros.

Causa comprovada na API (2026-10-15): turno 2 sem
messages[n].reasoning_content devolve HTTP 400
missing_required_parameter. Tags <think> no content não bastam.
String vazia também não. Espaço único é aceito quando não há
raciocínio capturado. HTTP 502 é falha upstream e pode ser retentado.
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.providers.base import OpenAICompatProvider
from backend.providers.reflection import (
    IncompleteStreamError,
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderTimeoutError,
    ReflectionProvider,
    prepare_reflection_messages,
    strip_provider_private_fields,
)


def test_assistant_think_tags_become_reasoning_content():
    history = [
        {"role": "user", "content": "Responda só: ok"},
        {"role": "assistant", "content": "<think>The user wants ok.</think>ok"},
        {"role": "user", "content": "Responda só: sim"},
    ]

    prepared = prepare_reflection_messages(history)

    assistant = prepared[1]
    assert assistant["content"] == "ok"
    assert assistant["reasoning_content"] == "The user wants ok."
    assert "<think>" not in assistant["content"]
    assert "_nexus_reasoning" not in assistant


def test_stashed_reasoning_wins_over_tags():
    prepared = prepare_reflection_messages([
        {
            "role": "assistant",
            "content": "<think>tag</think>ok",
            "_nexus_reasoning": "exato da API",
        }
    ])
    assert prepared[0]["reasoning_content"] == "exato da API"
    assert prepared[0]["content"] == "ok"


def test_missing_reasoning_uses_single_space():
    prepared = prepare_reflection_messages([
        {"role": "assistant", "content": "ok", "reasoning_content": ""},
    ])
    assert prepared[0]["reasoning_content"] == " "
    assert prepared[0]["content"] == "ok"


def test_non_assistant_messages_stay_untouched():
    prepared = prepare_reflection_messages([
        {"role": "system", "content": "seja breve"},
        {"role": "developer", "content": "formato json"},
        {"role": "user", "content": "oi"},
        {"role": "tool", "content": "resultado", "tool_call_id": "call_1"},
    ])
    assert all("reasoning_content" not in msg for msg in prepared)
    assert prepared[3]["tool_call_id"] == "call_1"
    assert len(prepared) == 4


def test_three_turns_keep_every_assistant_reasoning():
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "<think>r1</think>A"},
        {"role": "user", "content": "b"},
        {"role": "assistant", "content": "<think>r2</think>B"},
        {"role": "user", "content": "c"},
    ]
    prepared = prepare_reflection_messages(history)
    assistants = [m for m in prepared if m["role"] == "assistant"]
    assert [m["reasoning_content"] for m in assistants] == ["r1", "r2"]
    assert [m["content"] for m in assistants] == ["A", "B"]
    assert len(prepared) == 5


def test_history_extra_only_for_reflection():
    from backend.providers.reflection import reflection_history_extra

    extra = reflection_history_extra("<think>penso</think>ok", "reflection")
    assert extra == {"_nexus_reasoning": "penso"}
    assert reflection_history_extra("<think>penso</think>ok", "openrouter") == {}
    assert reflection_history_extra("sem tag", "reflection") == {}


def test_strip_private_fields_does_not_add_reasoning():
    cleaned = strip_provider_private_fields([
        {"role": "assistant", "content": "ok", "_nexus_reasoning": "segredo interno"},
    ])
    assert cleaned == [{"role": "assistant", "content": "ok"}]


class _CM:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, *args):
        return False


class FakeResponse:
    def __init__(self, status_code=200, body=b"", headers=None, lines=None, line_error=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._body = body if isinstance(body, bytes) else body.encode()
        self._lines = lines or []
        self._line_error = line_error

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line
        if self._line_error:
            raise self._line_error


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def stream(self, method, url, headers=None, json=None):
        self.calls.append({"stream": True, "url": url, "json": json, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return _CM(item)

    async def post(self, url, headers=None, json=None):
        self.calls.append({"stream": False, "url": url, "json": json, "headers": headers})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _provider(responses, sleep=None):
    client = FakeClient(responses)

    def factory():
        return _CM(client)

    provider = ReflectionProvider(
        api_key="test-key-not-real",
        base_url="https://api.reflection.ai/openai/v1",
        client_factory=factory,
        sleep=sleep or _no_sleep,
    )
    provider._client = client
    return provider


async def _no_sleep(_seconds):
    return None


def _sse(*chunks, done=True):
    lines = [f"data: {json.dumps(chunk)}" for chunk in chunks]
    if done:
        lines.append("data: [DONE]")
    return lines


async def _collect(provider, messages, **kwargs):
    parts = []
    async for token in provider.stream_chat("Beam-1.0-501B-A23B", messages, **kwargs):
        parts.append(token)
    return "".join(parts), provider._client.calls


@pytest.mark.asyncio
async def test_stream_wraps_reasoning_and_does_not_duplicate_it_in_content():
    provider = _provider([
        FakeResponse(lines=_sse(
            {"choices": [{"delta": {"reasoning_content": "penso"}}]},
            {"choices": [{"delta": {"content": "ok"}}]},
            {"choices": []},
        ))
    ])
    text, calls = await _collect(provider, [{"role": "user", "content": "oi"}])
    assert text == "<think>penso</think>ok"
    assert calls[0]["json"]["stream"] is True
    assert "Authorization" in calls[0]["headers"]
    assert "test-key-not-real" not in json.dumps({k: v for k, v in calls[0].items() if k != "headers"})


@pytest.mark.asyncio
async def test_stream_error_event_raises_without_retry():
    provider = _provider([
        FakeResponse(lines=_sse({"error": {"message": "upstream boom", "code": "bad_stream"}}, done=False)),
        FakeResponse(lines=_sse({"choices": [{"delta": {"content": "nao"}}]})),
    ])
    with pytest.raises(ProviderHTTPError) as exc:
        await _collect(provider, [{"role": "user", "content": "oi"}])
    assert exc.value.retryable is False or exc.value.status_code == 502
    assert len(provider._client.calls) == 1


@pytest.mark.asyncio
async def test_incomplete_stream_raises():
    provider = _provider([
        FakeResponse(lines=["data: " + json.dumps({"choices": [{"delta": {"content": "par"}}]})])
    ])
    with pytest.raises(IncompleteStreamError):
        await _collect(provider, [{"role": "user", "content": "oi"}])


@pytest.mark.asyncio
async def test_complete_chat_sends_stream_false_and_tolerates_null_content():
    body = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": None, "reasoning_content": "só pensei"}, "finish_reason": "length"}],
    })
    provider = _provider([FakeResponse(status_code=200, body=body)])
    text = await provider.complete_chat(
        "Beam-1.0-501B-A23B",
        [{"role": "user", "content": "oi"}],
    )
    assert text == ""
    assert provider._client.calls[0]["json"]["stream"] is False
    assert provider.last_reasoning_content == "só pensei"


@pytest.mark.asyncio
async def test_complete_chat_invalid_json_raises_provider_error():
    provider = _provider([FakeResponse(status_code=200, body=b"nao-json")])
    with pytest.raises(ProviderHTTPError):
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])


@pytest.mark.asyncio
async def test_http_400_is_not_retried():
    body = json.dumps({
        "error": {
            "code": "missing_required_parameter",
            "message": "Missing required parameter: 'messages[1].reasoning_content'",
        }
    })
    provider = _provider([
        FakeResponse(status_code=400, body=body, headers={"x-request-id": "req-400"}),
        FakeResponse(status_code=200, body=b"{}"),
    ])
    with pytest.raises(ProviderHTTPError) as exc:
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 400
    assert exc.value.retryable is False
    assert exc.value.request_id == "req-400"
    assert len(provider._client.calls) == 1


@pytest.mark.asyncio
async def test_http_502_retries_then_succeeds():
    slept = []

    async def record(seconds):
        slept.append(seconds)

    ok = json.dumps({"choices": [{"message": {"content": "sim", "reasoning_content": "r"}}]})
    provider = _provider([
        FakeResponse(status_code=502, body=b"bad gateway", headers={"x-request-id": "a"}),
        FakeResponse(status_code=200, body=ok, headers={"x-request-id": "b"}),
    ], sleep=record)
    text = await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert text == "sim"
    assert len(provider._client.calls) == 2
    assert slept == [0.5]


@pytest.mark.asyncio
async def test_http_502_honors_retry_after_and_stops_after_limit():
    slept = []

    async def record(seconds):
        slept.append(seconds)

    provider = _provider([
        FakeResponse(status_code=502, body=b"a", headers={"Retry-After": "3", "x-should-retry": "true"}),
        FakeResponse(status_code=503, body=b"b", headers={"x-should-retry": "true"}),
        FakeResponse(status_code=504, body=b"c"),
    ], sleep=record)
    with pytest.raises(ProviderHTTPError) as exc:
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 504
    assert exc.value.retryable is True
    assert len(provider._client.calls) == 3
    assert slept[0] == 3


@pytest.mark.asyncio
async def test_http_502_does_not_retry_when_should_retry_is_false():
    provider = _provider([
        FakeResponse(status_code=502, body=b"no", headers={"x-should-retry": "false"}),
        FakeResponse(status_code=200, body=b"{}"),
    ])
    with pytest.raises(ProviderHTTPError):
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert len(provider._client.calls) == 1


@pytest.mark.asyncio
async def test_http_502_with_tools_is_not_retried():
    provider = _provider([
        FakeResponse(status_code=502, body=b"no"),
        FakeResponse(status_code=200, body=b"{}"),
    ])
    with pytest.raises(ProviderHTTPError):
        await provider.complete_chat(
            "Beam-1.0-501B-A23B",
            [{"role": "user", "content": "oi"}],
            tools=[{"type": "function", "function": {"name": "ping"}}],
        )
    assert len(provider._client.calls) == 1


@pytest.mark.asyncio
async def test_openai_compat_does_not_send_private_reasoning_field():
    client = FakeClient([
        FakeResponse(lines=_sse({"choices": [{"delta": {"content": "ok"}}]}))
    ])

    provider = OpenAICompatProvider(api_key="other-key", base_url="https://example.test/v1")

    from contextlib import asynccontextmanager
    import backend.providers.base as base_mod

    @asynccontextmanager
    async def fake_pool(timeout=120.0):
        yield client

    original = base_mod._pooled_client
    base_mod._pooled_client = fake_pool
    try:
        parts = []
        async for token in provider.stream_chat(
            "outro-modelo",
            [{"role": "assistant", "content": "ok", "_nexus_reasoning": "nao enviar"}],
        ):
            parts.append(token)
    finally:
        base_mod._pooled_client = original

    sent = client.calls[0]["json"]["messages"][0]
    assert "_nexus_reasoning" not in sent
    assert "reasoning_content" not in sent
    assert sent["content"] == "ok"
    assert parts == ["ok"]


@pytest.mark.asyncio
async def test_multi_turn_consecutive_streaming():
    """Valida 3 turnos seguidos em streaming garantindo que cada turno assistant envia reasoning_content."""
    provider = _provider([
        # Turno 1
        FakeResponse(lines=_sse(
            {"choices": [{"delta": {"reasoning_content": "Pensei 1"}}]},
            {"choices": [{"delta": {"content": "Resposta 1"}}]},
        )),
        # Turno 2
        FakeResponse(lines=_sse(
            {"choices": [{"delta": {"reasoning_content": "Pensei 2"}}]},
            {"choices": [{"delta": {"content": "Resposta 2"}}]},
        )),
        # Turno 3
        FakeResponse(lines=_sse(
            {"choices": [{"delta": {"reasoning_content": "Pensei 3"}}]},
            {"choices": [{"delta": {"content": "Resposta 3"}}]},
        )),
    ])

    from backend.orchestration.handle_attachments import load_history
    from backend.providers.reflection import reflection_history_extra

    # Simula Turno 1
    t1_text, calls = await _collect(provider, [{"role": "user", "content": "Pergunta 1"}])
    assert t1_text == "<think>Pensei 1</think>Resposta 1"

    # Simula Turno 2
    extra1 = reflection_history_extra(t1_text, "reflection")
    history_turn2 = [
        {"role": "user", "content": "Pergunta 1"},
        {"role": "assistant", "content": "Resposta 1", **extra1},
        {"role": "user", "content": "Pergunta 2"},
    ]
    t2_text, calls = await _collect(provider, history_turn2)
    assert t2_text == "<think>Pensei 2</think>Resposta 2"
    # Valida payload do Turno 2 enviado para a API
    sent_msgs_t2 = calls[1]["json"]["messages"]
    assert sent_msgs_t2[1]["reasoning_content"] == "Pensei 1"
    assert sent_msgs_t2[1]["content"] == "Resposta 1"
    assert "<think>" not in sent_msgs_t2[1]["content"]

    # Simula Turno 3
    extra2 = reflection_history_extra(t2_text, "reflection")
    history_turn3 = [
        {"role": "user", "content": "Pergunta 1"},
        {"role": "assistant", "content": "Resposta 1", **extra1},
        {"role": "user", "content": "Pergunta 2"},
        {"role": "assistant", "content": "Resposta 2", **extra2},
        {"role": "user", "content": "Pergunta 3"},
    ]
    t3_text, calls = await _collect(provider, history_turn3)
    assert t3_text == "<think>Pensei 3</think>Resposta 3"
    # Valida payload do Turno 3 enviado para a API
    sent_msgs_t3 = calls[2]["json"]["messages"]
    assert sent_msgs_t3[1]["reasoning_content"] == "Pensei 1"
    assert sent_msgs_t3[3]["reasoning_content"] == "Pensei 2"
    assert sent_msgs_t3[3]["content"] == "Resposta 2"


@pytest.mark.asyncio
async def test_multi_turn_consecutive_non_streaming():
    """Valida 3 turnos seguidos em modo não-streaming."""
    provider = _provider([
        FakeResponse(status_code=200, body=json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "Resp 1", "reasoning_content": "P1"}}]
        })),
        FakeResponse(status_code=200, body=json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "Resp 2", "reasoning_content": "P2"}}]
        })),
        FakeResponse(status_code=200, body=json.dumps({
            "choices": [{"message": {"role": "assistant", "content": "Resp 3", "reasoning_content": "P3"}}]
        })),
    ])

    # Turno 1
    r1 = await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "Q1"}])
    assert r1 == "Resp 1"
    assert provider.last_reasoning_content == "P1"

    # Turno 2
    r2 = await provider.complete_chat("Beam-1.0-501B-A23B", [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "Resp 1", "_nexus_reasoning": provider.last_reasoning_content},
        {"role": "user", "content": "Q2"},
    ])
    assert r2 == "Resp 2"
    assert provider.last_reasoning_content == "P2"
    assert provider._client.calls[1]["json"]["messages"][1]["reasoning_content"] == "P1"

    # Turno 3
    r3 = await provider.complete_chat("Beam-1.0-501B-A23B", [
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "Resp 1", "_nexus_reasoning": "P1"},
        {"role": "user", "content": "Q2"},
        {"role": "assistant", "content": "Resp 2", "_nexus_reasoning": "P2"},
        {"role": "user", "content": "Q3"},
    ])
    assert r3 == "Resp 3"
    assert provider._client.calls[2]["json"]["messages"][3]["reasoning_content"] == "P2"


@pytest.mark.asyncio
async def test_timeout_retries_and_succeeds_non_streaming():
    slept = []
    async def record_sleep(s):
        slept.append(s)

    ok_body = json.dumps({"choices": [{"message": {"content": "ok", "reasoning_content": "r"}}]})
    provider = _provider([
        httpx.ReadTimeout("read timed out"),
        FakeResponse(status_code=200, body=ok_body),
    ], sleep=record_sleep)

    result = await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert result == "ok"
    assert len(provider._client.calls) == 2
    assert len(slept) == 1


@pytest.mark.asyncio
async def test_timeout_exceeds_retry_limit_raises_timeout_error():
    provider = _provider([
        httpx.ReadTimeout("timed out 1"),
        httpx.ReadTimeout("timed out 2"),
        httpx.ReadTimeout("timed out 3"),
    ])
    with pytest.raises(ProviderTimeoutError) as exc:
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 504
    assert exc.value.failover_reason == "timeout"
    assert exc.value.retryable is True
    assert len(provider._client.calls) == 3


@pytest.mark.asyncio
async def test_stream_timeout_before_tokens_retries():
    ok_response = FakeResponse(lines=_sse({"choices": [{"delta": {"content": "final"}}]}))
    provider = _provider([
        httpx.ConnectTimeout("connection timed out"),
        ok_response,
    ])
    text, calls = await _collect(provider, [{"role": "user", "content": "oi"}])
    assert text == "final"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_stream_timeout_after_tokens_raises_without_retry():
    # Quando o stream já começou a emitir tokens para o usuário, não pode repetir do zero
    interrupted_resp = FakeResponse(
        lines=["data: " + json.dumps({"choices": [{"delta": {"content": "inicio"}}]})],
        line_error=httpx.ReadTimeout("socket timed out mid-stream"),
    )
    provider = _provider([
        interrupted_resp,
        FakeResponse(lines=_sse({"choices": [{"delta": {"content": "repetido"}}]}))
    ])
    with pytest.raises(ProviderTimeoutError) as exc:
        await _collect(provider, [{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 504
    assert len(provider._client.calls) == 1


@pytest.mark.asyncio
async def test_network_disconnect_retries_and_succeeds():
    slept = []
    async def record_sleep(s):
        slept.append(s)

    ok_body = json.dumps({"choices": [{"message": {"content": "conectado", "reasoning_content": "r"}}]})
    provider = _provider([
        httpx.ConnectError("connection reset by peer"),
        FakeResponse(status_code=200, body=ok_body),
    ], sleep=record_sleep)

    result = await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert result == "conectado"
    assert len(provider._client.calls) == 2


@pytest.mark.asyncio
async def test_stream_502_honors_retry_after():
    slept = []
    async def record_sleep(s):
        slept.append(s)

    provider = _provider([
        FakeResponse(status_code=502, body=b"Bad Gateway", headers={"Retry-After": "4"}),
        FakeResponse(lines=_sse({"choices": [{"delta": {"content": "recuperado"}}]}))
    ], sleep=record_sleep)

    text, calls = await _collect(provider, [{"role": "user", "content": "oi"}])
    assert text == "recuperado"
    assert len(calls) == 2
    assert slept == [4]


@pytest.mark.asyncio
async def test_empty_choices_raises_upstream_error():
    provider = _provider([
        FakeResponse(status_code=200, body=json.dumps({"choices": []})),
    ])
    with pytest.raises(ProviderHTTPError) as exc:
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert exc.value.failover_reason == "upstream"
    assert exc.value.retryable is False


@pytest.mark.asyncio
async def test_auth_error_not_retryable():
    provider = _provider([
        FakeResponse(status_code=401, body=json.dumps({"error": {"message": "Invalid API Key"}})),
        FakeResponse(status_code=200, body=b"{}"),
    ])
    with pytest.raises(ProviderHTTPError) as exc:
        await provider.complete_chat("Beam-1.0-501B-A23B", [{"role": "user", "content": "oi"}])
    assert exc.value.status_code == 401
    assert exc.value.failover_reason == "auth"
    assert exc.value.retryable is False
    assert len(provider._client.calls) == 1

