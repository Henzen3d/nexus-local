"""Contratos Pydantic para eventos WebSocket do chat (T2.4 / T2.3).

Centraliza a serialização e validação dos frames de ciclo de vida do stream:
- ``ConversationCreatedEvent``
- ``StreamStartEvent``
- ``StreamTokenEvent``
- ``StreamClearEvent``
- ``StreamEndSuccess`` (exige ``message_id`` e ``conversation_id`` não vazios, ``outcome='success'``)
- ``StreamEndFailure`` (``outcome`` em {'error', 'empty', 'timeout', 'cancelled'} + ``reason`` estável)

Campos internos (``cascade_history``, detalhes crus de exceção, prompts, credenciais)
jamais devem ser serializados nestes envelopes.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


def parse_turn_id(value: Any) -> str | None:
    if isinstance(value, str):
        value = value.strip()
        if 0 < len(value) <= 128:
            return value
    return None


class TurnSocket:
    """Attach the same correlation to progress and lifecycle frames for one turn."""

    def __init__(self, socket: Any, turn_id: str, conversation_id: str | None):
        self._socket = socket
        self.turn_id = turn_id
        self.conversation_id = conversation_id

    async def send_json(self, event: dict[str, Any]) -> None:
        correlated = {**event, "turn_id": self.turn_id}
        if self.conversation_id is not None and "conversation_id" not in correlated:
            correlated["conversation_id"] = self.conversation_id
        await self._socket.send_json(correlated)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._socket, name)


class ConversationCreatedEvent(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    type: Literal["conversation_created"] = "conversation_created"
    conversation_id: str = Field(..., min_length=1)
    title: str = ""
    project_id: Optional[str] = None
    turn_id: Optional[str] = None


class StreamStartEvent(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    type: Literal["stream_start"] = "stream_start"
    conversation_id: str = Field(..., min_length=1)
    turn_id: Optional[str] = None
    from_cache: Optional[bool] = None
    cache_type: Optional[str] = None
    cache_similarity: Optional[float] = None


class StreamTokenEvent(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    type: Literal["token"] = "token"
    content: str
    turn_id: Optional[str] = None
    conversation_id: Optional[str] = None


class StreamClearEvent(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    type: Literal["stream_clear"] = "stream_clear"
    turn_id: Optional[str] = None
    conversation_id: Optional[str] = None


class StreamEndSuccess(BaseModel):
    """Frame terminal de sucesso: SEMPRE carrega ``message_id`` e ``conversation_id`` válidos."""

    model_config = ConfigDict(protected_namespaces=())

    type: Literal["stream_end"] = "stream_end"
    outcome: Literal["success"] = "success"
    message_id: str = Field(..., min_length=1)
    conversation_id: str = Field(..., min_length=1)
    turn_id: Optional[str] = None
    finish_reason: Optional[str] = None

    from_cache: Optional[bool] = None
    cache_type: Optional[str] = None
    cache_similarity: Optional[float] = None

    artifact_id: Optional[str] = None
    artifact_type: Optional[str] = None
    artifact_title: Optional[str] = None
    artifacts: Optional[list[dict[str, Any]]] = None

    relay_used: Optional[bool] = None
    relay_model: Optional[str] = None

    web_search_used: Optional[bool] = None
    web_search_query: Optional[str] = None
    web_search_sources: Optional[list[dict[str, Any]]] = None
    source_count: Optional[int] = None

    process_steps: Optional[list[dict[str, Any]]] = None
    process_duration_ms: Optional[float] = None

    was_fallback: Optional[bool] = None
    final_model_id: Optional[str] = None
    final_model_name: Optional[str] = None
    final_provider_id: Optional[str] = None
    requested_model: Optional[str] = None
    served_by: Optional[str] = None
    failover_tier: Optional[str] = None
    spliced: Optional[bool] = None
    attempt_count: Optional[int] = None

    phase_latencies: Optional[dict[str, float]] = None

    ui_blocks: Optional[dict[str, Any]] = None
    ui_errors: Optional[list[dict[str, Any]]] = None
    ui_dropped: Optional[int] = None


class StreamEndFailure(BaseModel):
    """Frame terminal de falha/vazio/timeout: nunca exige ``message_id`` e sempre destrava o compositor."""

    model_config = ConfigDict(protected_namespaces=())

    type: Literal["stream_end"] = "stream_end"
    outcome: Literal["error", "empty", "timeout", "cancelled"] = "error"
    reason: str = Field(..., min_length=1)
    conversation_id: Optional[str] = None
    turn_id: Optional[str] = None
    finish_reason: Optional[str] = None
    message: Optional[str] = None


def dump_ws_event(event: BaseModel) -> dict[str, Any]:
    """Serializa evento WS preservando campos definidos e omitindo opcionais não preenchidos."""
    return event.model_dump(exclude_none=True)


def build_stream_end_success(**kwargs: Any) -> dict[str, Any]:
    """Constrói e valida ``StreamEndSuccess`` preservando chaves legadas esperadas pelo frontend."""
    # Remove explicitamente chaves técnicas internas que nunca devem cruzar o wire
    for forbidden in ("cascade_history", "raw_error", "traceback", "api_key"):
        kwargs.pop(forbidden, None)
    # Normaliza phase_latencies para números finitos
    if "phase_latencies" in kwargs and isinstance(kwargs["phase_latencies"], dict):
        import math
        kwargs["phase_latencies"] = {
            str(k): round(float(v), 2)
            for k, v in kwargs["phase_latencies"].items()
            if isinstance(v, (int, float)) and math.isfinite(v)
        }
    model = StreamEndSuccess(**kwargs)
    return model.model_dump(exclude_none=True)


def build_stream_end_failure(
    *,
    reason: str,
    outcome: Literal["error", "empty", "timeout", "cancelled"] = "error",
    conversation_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    finish_reason: Optional[str] = None,
    message: Optional[str] = None,
) -> dict[str, Any]:
    """Constrói e valida ``StreamEndFailure`` com ``finish_reason`` para compatibilidade de rollout."""
    model = StreamEndFailure(
        outcome=outcome,
        reason=reason,
        conversation_id=conversation_id,
        turn_id=turn_id,
        finish_reason=finish_reason or outcome,
        message=message,
    )
    return model.model_dump(exclude_none=True)
