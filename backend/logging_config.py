"""
Configuração central de logging para o NexusLocal.

Fornece um logger nomeado ("nexuslocal") com formatador estruturado.
Todos os módulos de aplicação devem usar `get_logger(__name__)` em vez de
`print()` para emitir mensagens em runtime.

Uso:
    from backend.logging_config import get_logger
    logger = get_logger(__name__)

    logger.info("Mensagem informativa", extra={"conversation_id": conv_id})
    logger.error("Falha ao processar", exc_info=True)
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "nexuslocal"
_CONFIGURED = False
_DEFAULT_FMT = "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"

_SENSITIVE_LOG_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"\b(sk-(?:or-v1-|proj-)?[A-Za-z0-9_-]{12,})"),
    re.compile(r"\b(gsk_[A-Za-z0-9]{12,})"),
    re.compile(r"\b(AIza[0-9A-Za-z\-_]{20,})"),
    re.compile(r"((?:api_key|apikey|access_token|secret|password)\s*[=:]\s*)([^\s,;'\"]+)", re.IGNORECASE),
]


def redact_sensitive_text(text: str) -> str:
    """Mascara chaves de API, tokens Bearer e credenciais antes da emissão em logs."""
    if not text:
        return text
    out = str(text)
    out = _SENSITIVE_LOG_PATTERNS[0].sub(r"\1***REDACTED***", out)
    out = _SENSITIVE_LOG_PATTERNS[1].sub("***REDACTED***", out)
    out = _SENSITIVE_LOG_PATTERNS[2].sub("***REDACTED***", out)
    out = _SENSITIVE_LOG_PATTERNS[3].sub("***REDACTED***", out)
    out = _SENSITIVE_LOG_PATTERNS[4].sub(r"\1***REDACTED***", out)
    return out


class _SecretRedactionFilter(logging.Filter):
    """Redige credenciais ou segredos acidentais de record.msg e record.args."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered = record.getMessage()
            redacted = redact_sensitive_text(rendered)
            if redacted != rendered:
                record.msg = redacted
                record.args = None
        except Exception:
            if isinstance(record.msg, str):
                record.msg = redact_sensitive_text(record.msg)
        return True


class _ContextDefaults(logging.Filter):
    """Garante defaults de user_id, conversation_id e turn_id para formatos customizados."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "user_id"):
            record.user_id = "-"
        if not hasattr(record, "conversation_id"):
            record.conversation_id = "-"
        if not hasattr(record, "turn_id"):
            record.turn_id = "-"
        return True


class _ContextualFormatter(logging.Formatter):
    """Formatter padrão que compõe sufixos user/conv/turn na linha principal só quando presentes."""

    @staticmethod
    def _normalize_context_value(value: object) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text == "-":
            return None
        return text

    def formatMessage(self, record: logging.LogRecord) -> str:
        base = super().formatMessage(record)
        parts: list[str] = []
        user_id = self._normalize_context_value(getattr(record, "user_id", None))
        if user_id is not None:
            parts.append(f"user={user_id}")
        conversation_id = self._normalize_context_value(
            getattr(record, "conversation_id", None)
        )
        if conversation_id is not None:
            parts.append(f"conv={conversation_id}")
        turn_id = self._normalize_context_value(getattr(record, "turn_id", None))
        if turn_id is not None:
            parts.append(f"turn={turn_id}")
        if not parts:
            return base
        return f"{base} | {' | '.join(parts)}"


def _build_formatter(fmt: Optional[str]) -> logging.Formatter:
    if fmt is None:
        return _ContextualFormatter(_DEFAULT_FMT, datefmt=_DEFAULT_DATEFMT)
    return logging.Formatter(fmt, datefmt=_DEFAULT_DATEFMT)


def configure_logging(
    level: int = logging.INFO,
    stream=None,
    fmt: Optional[str] = None,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    Configura (idempotentemente) o logger raiz "nexuslocal".

    Deve ser chamado uma vez no startup da aplicação (main.py).
    Chamadas subsequentes são no-op se já configurado.

    Args:
        log_file: Caminho opcional para arquivo de log persistente.
                  Se informado, logs também são escritos no disco.
    """
    global _CONFIGURED

    root_logger = logging.getLogger(_LOGGER_NAME)

    if _CONFIGURED:
        return root_logger

    if stream is None:
        stream = sys.stderr

    formatter = _build_formatter(fmt)

    # Handler para stdout/stderr (docker logs)
    stream_handler = logging.StreamHandler(stream)
    stream_handler.addFilter(_ContextDefaults())
    stream_handler.addFilter(_SecretRedactionFilter())
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    # Handler para arquivo persistente (logs em disco)
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.addFilter(_ContextDefaults())
            file_handler.addFilter(_SecretRedactionFilter())
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"[LOG] Falha ao configurar arquivo de log: {e}", file=sys.stderr)

    root_logger.setLevel(level)
    root_logger.propagate = False

    _CONFIGURED = True
    return root_logger


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger filho do logger "nexuslocal".

    Uso:
        logger = get_logger(__name__)
    """
    if not _CONFIGURED:
        configure_logging()
    if name.startswith(_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
