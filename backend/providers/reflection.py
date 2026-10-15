"""Adaptador Reflection AI / Beam.

A API exige ``reasoning_content`` não vazio em toda mensagem assistant
anterior. Sem isso, o turno seguinte devolve HTTP 400
``missing_required_parameter``. Tags ``<think>`` no content não bastam.
String vazia também não. Espaço único foi aceito em 2026-10-15 quando
não há raciocínio capturado. HTTP 502/503 é falha upstream documentada.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any, AsyncIterator, Optional

import httpx

from backend.logging_config import get_logger
from backend.orchestration.artifacts import strip_thinking_tags
from backend.providers.base import (
    OpenAICompatProvider,
    RateLimitError,
    _pooled_client,
)

logger = get_logger(__name__)

_THINK_TAGS = (
    "think|thinking|reasoning|analysis|reflection|"
    "assistant_thought|thought|redacted_reasoning|redacted_thinking"
)
_THINK_BLOCK = re.compile(
    rf"<({_THINK_TAGS})(?:\s+[^>]*)?>([\s\S]*?)</\1>",
    re.IGNORECASE,
)
# A API rejeita "" e aceita " ".
_MISSING_REASONING = " "
_TRANSIENT_STATUS = {429, 500, 502, 503, 504}
_MAX_TRANSIENT_RETRIES = 2
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")


class ProviderHTTPError(RuntimeError):
    """Erro HTTP classificado. HTTP 400 não é retentável."""

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        request_id: str | None = None,
        retryable: bool = False,
        code: str | None = None,
        failover_reason: str = "error",
        headers: Any = None,
    ):
        self.status_code = status_code
        self.request_id = request_id
        self.retryable = retryable
        self.code = code
        self.failover_reason = failover_reason
        self.headers = headers
        super().__init__(f"Provider error {status_code}: {message}")


class ProviderTimeoutError(ProviderHTTPError):
    """Tempo limite esgotado em chamada upstream (timeout)."""

    def __init__(
        self,
        message: str = "tempo limite esgotado (timeout)",
        *,
        request_id: str | None = None,
    ):
        super().__init__(
            504,
            message,
            request_id=request_id,
            retryable=True,
            code="timeout",
            failover_reason="timeout",
        )


class ProviderConnectionError(ProviderHTTPError):
    """Falha de rede ou desconexão prematura com o provedor."""

    def __init__(
        self,
        message: str = "falha de rede ou desconexão prematura",
        *,
        request_id: str | None = None,
    ):
        super().__init__(
            502,
            message,
            request_id=request_id,
            retryable=True,
            code="connection_error",
            failover_reason="connection",
        )


class IncompleteStreamError(ProviderHTTPError):
    def __init__(self, message: str = "stream incompleto: evento [DONE] ausente"):
        super().__init__(
            502,
            message,
            retryable=True,
            failover_reason="upstream",
        )


def extract_reasoning_text(content: str | None) -> str | None:
    if not isinstance(content, str) or not content:
        return None
    parts = [match.group(2) for match in _THINK_BLOCK.finditer(content)]
    if not parts:
        return None
    text = "".join(parts).strip()
    return text or None


def reflection_history_extra(content: str | None, provider_id: str | None) -> dict:
    """Campo interno para o próximo turno do Beam. Outros provedores: vazio."""
    if provider_id != "reflection":
        return {}
    reasoning = extract_reasoning_text(content)
    if not reasoning:
        return {}
    return {"_nexus_reasoning": reasoning}


def strip_provider_private_fields(messages: list[dict]) -> list[dict]:
    """Remove metadados do Nexus antes de serializar para qualquer provedor."""
    cleaned = []
    for msg in messages:
        cleaned.append({
            key: value
            for key, value in msg.items()
            if not str(key).startswith("_nexus")
        })
    return cleaned


def prepare_reflection_messages(messages: list[dict]) -> list[dict]:
    """Copia o histórico no formato que o Beam aceita.

    Não remove turnos. Promove o raciocínio já capturado para
    ``reasoning_content`` e tira as tags do ``content``.
    """
    prepared: list[dict] = []
    for msg in messages:
        item = {
            key: value
            for key, value in msg.items()
            if not str(key).startswith("_nexus")
        }
        if item.get("role") != "assistant":
            prepared.append(item)
            continue

        stashed = msg.get("_nexus_reasoning")
        content = item.get("content")
        extracted = extract_reasoning_text(content) if isinstance(content, str) else None
        if isinstance(content, str):
            item["content"] = strip_thinking_tags(content)

        existing = item.get("reasoning_content")
        if isinstance(stashed, str) and stashed.strip():
            reasoning = stashed
        elif isinstance(existing, str) and existing.strip():
            reasoning = existing
        elif extracted:
            reasoning = extracted
        else:
            reasoning = _MISSING_REASONING
        item["reasoning_content"] = reasoning
        prepared.append(item)
    return prepared


def _header(headers: Any, name: str) -> str | None:
    if not headers:
        return None
    for key, value in headers.items():
        if str(key).lower() == name and value is not None:
            return str(value)
    return None


def _sanitize(text: str, api_key: str | None = None) -> str:
    cleaned = _JWT_RE.sub("<jwt>", text or "")
    cleaned = re.sub(r"Bearer\s+\S+", "Bearer <redacted>", cleaned)
    if api_key and api_key in cleaned:
        cleaned = cleaned.replace(api_key, "<redacted>")
    return cleaned[:500]


def _failover_reason(status_code: int) -> str:
    if status_code == 400:
        return "invalid_request"
    if status_code in (401, 403):
        return "auth"
    if status_code == 429:
        return "rate_limit"
    if status_code >= 500:
        return "upstream"
    return "error"


def _backoff_seconds(attempt: int, headers: Any) -> float:
    retry_after = _header(headers, "retry-after")
    if retry_after and retry_after.replace(".", "", 1).isdigit():
        value = float(retry_after)
        return int(value) if value.is_integer() else value
    return 0.5 * (2 ** attempt)


class ReflectionProvider(OpenAICompatProvider):
    """Chat Completions da Reflection. Não altera os outros provedores."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        *,
        client_factory=None,
        sleep=None,
    ):
        super().__init__(api_key=api_key, base_url=base_url)
        self._client_factory = client_factory
        self._sleep = sleep
        self.last_reasoning_content = ""

    def _open_client(self):
        if self._client_factory:
            return self._client_factory()
        return _pooled_client(timeout=120.0)

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key and self.api_key.strip():
            headers["Authorization"] = f"Bearer {self.api_key.strip()}"
        return headers

    def _build_payload(
        self,
        model: str,
        messages: list[dict],
        *,
        temperature: float,
        max_tokens: int,
        stream: bool,
        tools: list | None,
        reasoning_effort: str | None,
        reasoning_control: str | None,
    ) -> dict:
        payload: dict[str, Any] = {
            "model": model,
            "messages": prepare_reflection_messages(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        if tools:
            payload["tools"] = tools
        if reasoning_effort and reasoning_control:
            from backend.reasoning.payload import build_effort_payload
            payload = build_effort_payload(
                control=reasoning_control,
                level=reasoning_effort,
                base_payload=payload,
            )
        return payload

    def _can_retry(self, payload: dict) -> bool:
        if payload.get("tools"):
            return False
        for msg in payload.get("messages") or []:
            if msg.get("tool_calls"):
                return False
        return True

    def _error_from_http(
        self,
        status_code: int,
        body: bytes,
        headers: Any,
    ) -> ProviderHTTPError:
        raw = body.decode(errors="replace") if body else ""
        message = raw
        code = None
        try:
            parsed = json.loads(raw) if raw else {}
            err = parsed.get("error") if isinstance(parsed, dict) else None
            if isinstance(err, dict):
                message = err.get("message") or message
                code = err.get("code")
        except json.JSONDecodeError:
            pass
        should_retry = _header(headers, "x-should-retry")
        retryable = status_code in _TRANSIENT_STATUS
        if should_retry is not None and should_retry.lower() == "false":
            retryable = False
        if status_code == 429:
            retry_after = _header(headers, "retry-after")
            seconds = int(retry_after) if retry_after and retry_after.isdigit() else None
            err = RateLimitError(retry_after=seconds, provider=self.base_url)
            err.failover_reason = "rate_limit"  # type: ignore[attr-defined]
            err.status_code = status_code  # type: ignore[attr-defined]
            err.retryable = retryable  # type: ignore[attr-defined]
            err.request_id = _header(headers, "x-request-id")  # type: ignore[attr-defined]
            return err  # type: ignore[return-value]
        return ProviderHTTPError(
            status_code,
            _sanitize(message, self.api_key),
            request_id=_header(headers, "x-request-id"),
            retryable=retryable,
            code=code,
            failover_reason=_failover_reason(status_code),
            headers=headers,
        )

    def _log_call(
        self,
        *,
        status_code: int,
        model: str,
        stream: bool,
        duration_s: float,
        request_id: str | None,
        message: str,
    ) -> None:
        logger.warning(
            "Reflection HTTP %s model=%s stream=%s request_id=%s duration_ms=%s msg=%s",
            status_code,
            model,
            stream,
            request_id or "-",
            int(duration_s * 1000),
            _sanitize(message, self.api_key),
        )

    async def _sleep_before_retry(self, attempt: int, headers: Any) -> None:
        delay = _backoff_seconds(attempt, headers)
        if self._sleep:
            await self._sleep(delay)
        else:
            await asyncio.sleep(delay)

    async def complete_chat(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        reasoning_effort: Optional[str] = None,
        reasoning_control: Optional[str] = None,
        tools: list | None = None,
    ) -> str:
        payload = self._build_payload(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False,
            tools=tools,
            reasoning_effort=reasoning_effort,
            reasoning_control=reasoning_control,
        )
        body, _headers = await self._post_with_retries(payload)
        return self._parse_completion(body)

    async def _post_with_retries(self, payload: dict) -> tuple[bytes, Any]:
        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None
        for attempt in range(_MAX_TRANSIENT_RETRIES + 1):
            started = time.perf_counter()
            try:
                async with self._open_client() as client:
                    response = await client.post(url, headers=self._headers(), json=payload)
                    body = await response.aread()
            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                duration = time.perf_counter() - started
                error = ProviderTimeoutError(str(exc))
                self._log_call(
                    status_code=504,
                    model=payload.get("model", ""),
                    stream=False,
                    duration_s=duration,
                    request_id=None,
                    message=str(error),
                )
                last_error = error
                if attempt >= _MAX_TRANSIENT_RETRIES or not self._can_retry(payload):
                    raise error
                await self._sleep_before_retry(attempt, {})
                continue
            except (httpx.NetworkError, ConnectionError) as exc:
                duration = time.perf_counter() - started
                error = ProviderConnectionError(str(exc))
                self._log_call(
                    status_code=502,
                    model=payload.get("model", ""),
                    stream=False,
                    duration_s=duration,
                    request_id=None,
                    message=str(error),
                )
                last_error = error
                if attempt >= _MAX_TRANSIENT_RETRIES or not self._can_retry(payload):
                    raise error
                await self._sleep_before_retry(attempt, {})
                continue

            duration = time.perf_counter() - started
            if response.status_code == 200:
                return body, response.headers
            error = self._error_from_http(response.status_code, body, response.headers)
            self._log_call(
                status_code=response.status_code,
                model=payload.get("model", ""),
                stream=False,
                duration_s=duration,
                request_id=getattr(error, "request_id", None),
                message=str(error),
            )
            last_error = error
            if (
                attempt >= _MAX_TRANSIENT_RETRIES
                or not getattr(error, "retryable", False)
                or not self._can_retry(payload)
            ):
                raise error
            await self._sleep_before_retry(attempt, response.headers)
        raise last_error or ProviderHTTPError(500, "falha sem detalhe", retryable=True)

    def _parse_completion(self, body: bytes) -> str:
        raw = body.decode(errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise ProviderHTTPError(
                200,
                "resposta JSON inválida",
                retryable=False,
                failover_reason="upstream",
            ) from exc
        choices = data.get("choices") if isinstance(data, dict) else None
        if not choices:
            raise ProviderHTTPError(
                200,
                "resposta sem choices",
                retryable=False,
                failover_reason="upstream",
            )
        message = (choices[0] or {}).get("message") or {}
        reasoning = message.get("reasoning_content") or ""
        self.last_reasoning_content = reasoning if isinstance(reasoning, str) else str(reasoning)
        content = message.get("content")
        if content is None:
            return ""
        return content if isinstance(content, str) else str(content)

    async def stream_chat(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        reasoning_effort: Optional[str] = None,
        reasoning_control: Optional[str] = None,
        tools: list | None = None,
    ) -> AsyncIterator[str]:
        payload = self._build_payload(
            model,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            tools=tools,
            reasoning_effort=reasoning_effort,
            reasoning_control=reasoning_control,
        )
        url = f"{self.base_url}/chat/completions"
        for attempt in range(_MAX_TRANSIENT_RETRIES + 1):
            started = time.perf_counter()
            yielded = False
            try:
                async with self._open_client() as client:
                    async with client.stream(
                        "POST",
                        url,
                        headers=self._headers(),
                        json=payload,
                    ) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            error = self._error_from_http(
                                response.status_code, body, response.headers
                            )
                            self._log_call(
                                status_code=response.status_code,
                                model=model,
                                stream=True,
                                duration_s=time.perf_counter() - started,
                                request_id=getattr(error, "request_id", None),
                                message=str(error),
                            )
                            raise error
                        async for token in self._iter_sse(response):
                            yielded = True
                            yield token
                return
            except (httpx.TimeoutException, asyncio.TimeoutError) as exc:
                if not yielded:
                    error = ProviderTimeoutError(str(exc))
                    self._log_call(
                        status_code=504,
                        model=model,
                        stream=True,
                        duration_s=time.perf_counter() - started,
                        request_id=None,
                        message=str(error),
                    )
                    if attempt >= _MAX_TRANSIENT_RETRIES or not self._can_retry(payload):
                        raise error
                    await self._sleep_before_retry(attempt, {})
                else:
                    raise ProviderTimeoutError(str(exc))
            except (httpx.NetworkError, ConnectionError) as exc:
                if not yielded:
                    error = ProviderConnectionError(str(exc))
                    self._log_call(
                        status_code=502,
                        model=model,
                        stream=True,
                        duration_s=time.perf_counter() - started,
                        request_id=None,
                        message=str(error),
                    )
                    if attempt >= _MAX_TRANSIENT_RETRIES or not self._can_retry(payload):
                        raise error
                    await self._sleep_before_retry(attempt, {})
                else:
                    raise ProviderConnectionError(str(exc))
            except IncompleteStreamError as exc:
                self._log_call(
                    status_code=exc.status_code,
                    model=model,
                    stream=True,
                    duration_s=time.perf_counter() - started,
                    request_id=exc.request_id,
                    message=str(exc),
                )
                if yielded or attempt >= _MAX_TRANSIENT_RETRIES or not self._can_retry(payload):
                    raise
                await self._sleep_before_retry(attempt, getattr(exc, "headers", None))
            except ProviderHTTPError as exc:
                if (
                    yielded
                    or not exc.retryable
                    or attempt >= _MAX_TRANSIENT_RETRIES
                    or not self._can_retry(payload)
                ):
                    raise
                await self._sleep_before_retry(attempt, getattr(exc, "headers", None))
            except RateLimitError:
                raise

    async def _iter_sse(self, response) -> AsyncIterator[str]:
        in_thinking = False
        saw_done = False
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                saw_done = True
                break
            try:
                chunk = json.loads(data)
            except json.JSONDecodeError:
                continue
            if not isinstance(chunk, dict):
                continue
            if chunk.get("error"):
                err = chunk["error"]
                message = err.get("message") if isinstance(err, dict) else str(err)
                raise ProviderHTTPError(
                    502,
                    _sanitize(str(message), self.api_key),
                    retryable=False,
                    code=err.get("code") if isinstance(err, dict) else None,
                    failover_reason="upstream",
                )
            choices = chunk.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning_content") or ""
            content = delta.get("content") or ""
            if not isinstance(reasoning, str):
                reasoning = ""
            if not isinstance(content, str):
                content = ""
            piece = ""
            if reasoning:
                if not in_thinking:
                    piece += "<think>"
                    in_thinking = True
                piece += reasoning
            if content:
                if in_thinking:
                    piece += "</think>"
                    in_thinking = False
                piece += content
            if piece:
                yield piece
        if in_thinking:
            yield "</think>"
        if not saw_done:
            raise IncompleteStreamError()
