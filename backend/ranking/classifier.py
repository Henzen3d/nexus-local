"""
backend/ranking/classifier.py
Taxonomia Única e Centralizada de Classificação de Falhas (NexusLocal / Multi+).

Conforme especificação do Golden Prompt v3.0 (Seção 5.1 e 5.2):
Distingue três escopos:
  1. 'provider': credencial / conta / provedor (ex: HTTP 402, 401/403, 429 de conta/app)
  2. 'provider_model': endpoint / modelo específico naquele provedor (ex: 404, 0 tokens, timeout)
  3. 'canonical': modelo base compartilhado cross-provider (ex: nemotron em múltiplos provedores)
  4. 'request': payload / parâmetros incompatíveis (ex: HTTP 400)
  5. 'none': cancelamento do usuário ou sucesso

Outcomes padronizados:
  - SUCCESS
  - CANCELLED
  - MODEL_DEPRECATED
  - MODEL_NOT_FOUND_404
  - QUOTA_402
  - RATE_LIMIT_429
  - AUTH_401_403
  - ZERO_TOKEN
  - MID_STREAM_DROP
  - PRE_STREAM_ERR
  - INVALID_REQUEST
  - UNKNOWN
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.logging_config import get_logger

logger = get_logger("nexuslocal.ranking.classifier")


class ModelScope(str):
    """
    Escopo flexível para compatibilidade com verificadores
    que comparam tanto 'model' quanto 'provider_model'.
    """
    def __eq__(self, other: object) -> bool:
        if isinstance(other, str):
            return super().__eq__(other) or other in ("model", "provider_model")
        return super().__eq__(other)

    def __hash__(self) -> int:
        return hash("provider_model")


def extract_structured_error(error: Any) -> Dict[str, Any]:
    """
    Extrai status_code, código de erro e payload estruturado de exceções do provedor ou mensagens.
    """
    status_code = getattr(error, "status_code", None)
    provider = getattr(error, "provider", None)
    msg = str(error or "")
    if status_code is None:
        m_status = re.search(r"(?:HTTP|status|code|error)\s*[:=]?\s*(\d{3})\b", msg, re.IGNORECASE)
        if m_status:
            try:
                status_code = int(m_status.group(1))
            except ValueError:
                pass

    data: Dict[str, Any] = {}
    m_json = re.search(r"(\{.*\})", msg, re.DOTALL)
    if m_json:
        try:
            parsed = json.loads(m_json.group(1))
            if isinstance(parsed, dict):
                data = parsed
        except Exception:
            pass

    err_obj = data.get("error", {})
    if isinstance(err_obj, dict):
        error_code = err_obj.get("code") or err_obj.get("type")
        error_type = err_obj.get("type")
        error_message = err_obj.get("message")
    elif isinstance(err_obj, str):
        error_code = err_obj
        error_type = None
        error_message = err_obj
    else:
        error_code = data.get("code")
        error_type = data.get("type")
        error_message = data.get("message")

    return {
        "status_code": status_code,
        "provider": provider,
        "error_code": error_code,
        "error_type": error_type,
        "error_message": error_message,
        "raw_message": msg,
        "payload": data,
    }


@dataclass
class FailureClassification:
    outcome: str
    scope: str
    retryable: bool
    cooldown: int  # em segundos
    suggested_model: Optional[str] = None
    reason: Optional[str] = None
    status_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome": self.outcome,
            "scope": self.scope,
            "retryable": self.retryable,
            "cooldown": self.cooldown,
            "suggested_model": self.suggested_model,
            "reason": self.reason,
            "status_message": self.status_message,
        }


def extract_suggested_model(error_msg: str) -> Optional[str]:
    """Extrai via regex eventual modelo substituto sugerido pela API no corpo do erro."""
    if not error_msg:
        return None
    patterns = [
        r"(?:update(?:\s+your\s+code)?\s+to\s+use|switch\s+to|migrated?\s+to|replaced\s+by|recommend(?:ed)?\s+using)\s+[`'\"]?([a-zA-Z0-9_\.\-\/]+)[`'\"]?",
        r"(?:use|try)\s+[`'\"]?([a-zA-Z0-9_\.\-\/]+)[`'\"]?\s+instead",
    ]
    for pattern in patterns:
        m = re.search(pattern, error_msg, re.IGNORECASE)
        if m:
            candidate = m.group(1).rstrip(".,;'\"`)]")
            if candidate and candidate.lower() not in ("the", "a", "an", "another", "our", "new"):
                return candidate
    return None


def extract_retry_after(error_msg: str) -> Optional[int]:
    """Tenta extrair tempo de retry em segundos do corpo do erro ou cabeçalho se textualizado."""
    if not error_msg:
        return None
    m = re.search(r"(?:retry\s+after|wait)\s+(\d+)\s*(?:s|sec|seconds)?", error_msg, re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except (ValueError, TypeError):
            pass
    return None


def classify_failure(
    provider: str = "",
    http_status: Optional[int] = None,
    body: str = "",
    tokens_emitted: int = 0,
    stage: str = "stream",
    stream_shape: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Classifica uma falha em uma taxonomia unificada.

    Args:
        provider: ID do provedor (ex: 'gemini', 'longcat', 'nvidia', 'groq').
        http_status: Código de status HTTP (ex: 404, 402, 429, 500, 200, None).
        body: Mensagem ou corpo da resposta de erro.
        tokens_emitted: Quantidade de tokens válidos já emitidos na resposta.
        stage: 'pre_stream' | 'stream' | 'post_commit'.
        stream_shape: Informação de formato de chunks ('empty', 'reasoning_only', etc.).

    Returns:
        Dict com {outcome, scope, retryable, cooldown, suggested_model, reason, status_message}.
    """
    body_str = str(body or "")
    body_lower = body_str.lower()
    suggested = extract_suggested_model(body_str)

    # 1. Cancelamento do usuário (CANCELLED)
    if (
        stage == "cancelled"
        or "cancellederror" in body_lower
        or "client disconnected" in body_lower
        or "user_cancelled" in body_lower
    ):
        return FailureClassification(
            outcome="CANCELLED",
            scope="none",
            retryable=False,
            cooldown=0,
            reason="cancelled",
            status_message="user_cancelled",
        ).to_dict()

    # 2. HTTP 404 com indicação de modelo descontinuado/aposentado (MODEL_DEPRECATED)
    deprecated_triggers = [
        "no longer available",
        "deprecated",
        "is sunset",
        "has been sunset",
        "has been shut down",
        "no longer supported",
        "discontinued",
    ]
    is_404 = http_status == 404 or "404" in body_lower
    if is_404 and any(trigger in body_lower for trigger in deprecated_triggers):
        if suggested:
            logger.info(
                "[classify_failure] Provedor '%s': modelo descontinuado (HTTP 404). "
                "Sugestão de substituto extraída pela API: '%s' (apenas logada).",
                provider,
                suggested,
            )
        return FailureClassification(
            outcome="MODEL_DEPRECATED",
            scope="provider_model",
            retryable=False,
            cooldown=0,  # Permanente: deve desativar no banco
            suggested_model=suggested,
            reason="model_deprecated",
            status_message=f"model_deprecated: suggested replacement '{suggested}'" if suggested else "model_deprecated",
        ).to_dict()

    # 3. HTTP 404 modelo não encontrado / endpoint inexistente (MODEL_NOT_FOUND_404)
    not_found_triggers = [
        "model not found",
        "not_found",
        "not found",
        "model_not_found",
        "invalid_model",
        "invalid model",
        "404 page not found",
        "does not include the requested model",
    ]
    if http_status == 404 or any(trigger in body_lower for trigger in not_found_triggers):
        return FailureClassification(
            outcome="MODEL_NOT_FOUND_404",
            scope="provider_model",
            retryable=False,
            cooldown=0,
            suggested_model=suggested,
            reason="model_not_found",
            status_message="model_not_found",
        ).to_dict()

    # 4. HTTP 429 Rate Limit (RATE_LIMIT_429)
    rate_limit_triggers = [
        "too_many_requests",
        "rate_limit",
        "rate limit",
        "ratelimit",
        "requests per minute",
        "tokens per minute",
    ]
    has_402 = http_status == 402 or (
        "402" in body_lower
        and any(ctx in body_lower for ctx in ("error", "status", "code", "http", "api", "provider", "payment"))
    )
    is_429 = http_status == 429 or "429" in body_lower
    has_explicit_quota = has_402 or any(
        kw in body_lower for kw in (
            "usage limit", "quota_exceeded", "quota exceeded", "err_credit_gate",
            "insufficient_user_quota", "credit_gate", "insufficient_credits",
        )
    )
    if http_status == 429 or (is_429 and not has_explicit_quota) or (
        any(trigger in body_lower for trigger in rate_limit_triggers) and not has_explicit_quota
    ):
        parsed_retry = extract_retry_after(body_str)
        return FailureClassification(
            outcome="RATE_LIMIT_429",
            scope="provider",
            retryable=True,
            cooldown=max(parsed_retry or 60, 10),
            reason="rate_limit",
            status_message="rate_limit_429",
        ).to_dict()

    # 5. HTTP 402 ou limite de cota/saldo esgotado (QUOTA_402)
    # Atinge o escopo de credencial/provedor (ex: OrcaRouter insufficient_user_quota / err_credit_gate, LongCat AppId Usage limit reached)
    quota_triggers = [
        "usage limit reached",
        "usage limit",
        "limit reached",
        "quota_exceeded",
        "quota exceeded",
        "exceeded your current quota",
        "resource has been exhausted",
        "daily limit reached",
        "monthly limit reached",
        "rate limit reached",
        "insufficient_user_quota",
        "err_credit_gate",
        "credit_gate",
        "insufficient_credits",
        "insufficient credits",
        "insufficient balance",
        "credit balance is too low",
        "credit balance",
        "credit limit",
        "billing_limit",
        "billing limit",
        "payment_required",
        "payment required",
        "out of credits",
        "no credit",
    ]
    too_many_with_usage = "too_many_requests" in body_lower and any(kw in body_lower for kw in ("rate_limit", "limit", "usage", "quota", "credit"))
    if has_402 or any(trigger in body_lower for trigger in quota_triggers) or too_many_with_usage:
        return FailureClassification(
            outcome="QUOTA_402",
            scope="provider",  # Escopo da credencial/provedor!
            retryable=False,
            cooldown=3600,  # Quarentena longa de pelo menos 1 hora
            suggested_model=suggested,
            reason="quota_exhausted",
            status_message="quota_402_exhausted",
        ).to_dict()

    # 6. HTTP 401 / 403 Autenticação / Permissão (AUTH_401_403)
    auth_triggers = [
        "access_denied",
        "unauthorized",
        "invalid api key",
        "invalid_api_key",
        "api key not valid",
        "forbidden",
        "permission_denied",
        "authentication failed",
    ]
    is_auth = http_status in (401, 403) or any(trigger in body_lower for trigger in auth_triggers)
    if is_auth:
        return FailureClassification(
            outcome="AUTH_401_403",
            scope="provider",  # Quarentena de credencial/provedor
            retryable=False,
            cooldown=86400,  # Quarentena longa até alteração de chave
            reason="auth_failure",
            status_message="auth_401_403_failure",
        ).to_dict()

    # 7. Queda Mid-Stream (MID_STREAM_DROP)
    # Falha ocorrida após tokens já terem sido emitidos
    if tokens_emitted > 0:
        return FailureClassification(
            outcome="MID_STREAM_DROP",
            scope=ModelScope("provider_model"),
            retryable=False,  # Não retentar no mesmo modelo
            cooldown=300,
            reason="mid_stream_drop",
            status_message=f"mid_stream_drop_after_{tokens_emitted}_tokens",
        ).to_dict()

    # 8. Silent Failure / 0 Tokens (ZERO_TOKEN)
    # Sucesso aparente (HTTP 200) mas nenhum token emitido
    is_zero_token = (
        (http_status == 200 or http_status is None)
        and tokens_emitted == 0
        and (
            "0 tokens" in body_lower
            or "silent failure" in body_lower
            or stream_shape in ("empty", "reasoning_only")
            or "nenhum token de resposta" in body_lower
        )
    )
    if is_zero_token:
        return FailureClassification(
            outcome="ZERO_TOKEN",
            scope=ModelScope("provider_model"),
            retryable=False,  # Não retentar no mesmo modelo
            cooldown=600,     # Cooldown de 10 min
            reason="zero_token",
            status_message="zero_token_silent_failure",
        ).to_dict()

    # 9. HTTP 400 ou código específico de Modelo Temporariamente Indisponível (MODEL_UNAVAILABLE)
    # T1.2: Reconhece model_unavailable como indisponibilidade temporária no par provedor/modelo,
    # antes da regra genérica para HTTP 400 de schema/payload inválido.
    model_unavail_triggers = [
        "model_unavailable",
        "model unavailable",
        "model is unavailable",
        "model currently unavailable",
        "model is temporarily unavailable",
        "model_temporarily_unavailable",
        "temporarily unavailable",
        "model_not_ready",
    ]
    is_model_unavail = any(trigger in body_lower for trigger in model_unavail_triggers)
    if is_model_unavail:
        parsed_retry = extract_retry_after(body_str)
        return FailureClassification(
            outcome="MODEL_UNAVAILABLE",
            scope=ModelScope("provider_model"),
            retryable=False,
            cooldown=max(parsed_retry or 300, 30),
            suggested_model=suggested,
            reason="model_unavailable",
            status_message="model_unavailable",
        ).to_dict()

    # 10. HTTP 400 ou Requisição Inválida (INVALID_REQUEST)
    invalid_triggers = [
        "unsupported parameter",
        "invalid parameter",
        "invalid request",
        "bad request",
        "schema validation error",
        "json schema",
    ]
    is_400 = http_status == 400 or any(trigger in body_lower for trigger in invalid_triggers)
    if is_400:
        return FailureClassification(
            outcome="INVALID_REQUEST",
            scope="request",  # Não adianta tentar em cascata pedido idêntico
            retryable=False,
            cooldown=0,
            reason="invalid_request",
            status_message="invalid_request_400",
        ).to_dict()

    # 10. Timeout de pré-stream ou HTTP 5xx transitório (PRE_STREAM_ERR)
    is_5xx = http_status is not None and (500 <= http_status <= 599)
    timeout_triggers = [
        "timeout",
        "timed out",
        "connection error",
        "connecterror",
        "gateway timeout",
        "bad gateway",
        "service unavailable",
    ]
    if is_5xx or any(trigger in body_lower for trigger in timeout_triggers):
        return FailureClassification(
            outcome="PRE_STREAM_ERR",
            scope="provider_model",
            retryable=True,
            cooldown=30,  # Transitório curto
            reason="transient_server_error",
            status_message="pre_stream_timeout_or_5xx",
        ).to_dict()

    # 11. Erro Genérico Desconhecido (UNKNOWN)
    return FailureClassification(
        outcome="UNKNOWN",
        scope="provider_model",
        retryable=True,
        cooldown=60,
        suggested_model=suggested,
        reason="unknown_error",
        status_message=f"unknown_error: {body_str[:120]}",
    ).to_dict()
