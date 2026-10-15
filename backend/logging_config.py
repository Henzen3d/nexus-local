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
from pathlib import Path
from typing import Optional

_LOGGER_NAME = "nexuslocal"
_CONFIGURED = False


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

    if fmt is None:
        fmt = "%(asctime)s [%(levelname)s] %(name)s [%(filename)s:%(lineno)d]: %(message)s"
        # Inclui user_id e conversation_id nos logs quando disponíveis
        extra_fmt = " | user=%(user_id)s | conv=%(conversation_id)s"
    else:
        extra_fmt = ""

    # Handler para stdout/stderr (docker logs)
    stream_handler = logging.StreamHandler(stream)
    stream_handler.setFormatter(logging.Formatter(fmt + extra_fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    root_logger.addHandler(stream_handler)

    # Handler para arquivo persistente (logs em disco)
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.setFormatter(logging.Formatter(
                fmt + extra_fmt,
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
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
