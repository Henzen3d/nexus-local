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
import sys
from typing import Optional

_LOGGER_NAME = "nexuslocal"
_CONFIGURED = False


def configure_logging(
    level: int = logging.INFO,
    stream=None,
    fmt: Optional[str] = None,
) -> logging.Logger:
    """
    Configura (idempotentemente) o logger raiz "nexuslocal".

    Deve ser chamado uma vez no startup da aplicação (main.py).
    Chamadas subsequentes são no-op se já configurado.
    """
    global _CONFIGURED

    root_logger = logging.getLogger(_LOGGER_NAME)

    if _CONFIGURED:
        return root_logger

    if stream is None:
        stream = sys.stderr

    if fmt is None:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger.setLevel(level)
    root_logger.addHandler(handler)
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
