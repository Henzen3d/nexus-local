"""Testes do formatter contextual de logs (backend.logging_config)."""
from __future__ import annotations

from contextlib import contextmanager
import io
import logging
import os
import re
import sys
import tempfile
from typing import Iterator, Optional

import pytest

import backend.logging_config as lc

_LOG_LINE_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} "
    r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\] "
    r"nexuslocal\.\S+ \[[^:\]]+:\d+\]: .+"
)


@contextmanager
def _isolated_logging(
    *,
    stream=None,
    level: int = logging.INFO,
    fmt: Optional[str] = None,
    log_file: Optional[str] = None,
) -> Iterator[logging.Logger]:
    root = logging.getLogger("nexuslocal")
    previous_handlers = list(root.handlers)
    previous_level = root.level
    previous_propagate = root.propagate
    previous_configured = lc._CONFIGURED

    lc._CONFIGURED = False
    root.handlers.clear()
    try:
        lc.configure_logging(
            level=level,
            stream=stream,
            fmt=fmt,
            log_file=log_file,
        )
        yield root
    finally:
        created_handlers = list(root.handlers)
        root.handlers.clear()
        for handler in created_handlers:
            try:
                handler.flush()
            finally:
                handler.close()
        root.handlers.extend(previous_handlers)
        root.setLevel(previous_level)
        root.propagate = previous_propagate
        lc._CONFIGURED = previous_configured


def test_log_without_context_omits_suffix_and_preserves_structure():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.WARNING):
        logger = lc.get_logger("backend.providers.reflection")
        logger.warning(
            "Reflection HTTP 400 model=Beam stream=False request_id=req-1 duration_ms=12 msg=bad"
        )
    line = buf.getvalue().strip()

    assert _LOG_LINE_RE.match(line), f"Formato inesperado: {line!r}"
    assert "[WARNING]" in line
    assert "Reflection HTTP 400" in line
    assert "user=" not in line
    assert "conv=" not in line
    assert "user=-" not in line
    assert "conv=-" not in line
    assert " | " not in line
    assert "Logging error" not in line


def test_log_with_only_user_id():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.INFO):
        logger = lc.get_logger("backend.routers.chat")
        logger.info("Turno iniciado", extra={"user_id": "user-42"})
    line = buf.getvalue().strip()

    assert _LOG_LINE_RE.match(line), f"Formato inesperado: {line!r}"
    assert line.endswith("Turno iniciado | user=user-42")
    assert "conv=" not in line


def test_log_with_only_conversation_id():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.INFO):
        logger = lc.get_logger("backend.routers.chat")
        logger.info("Histórico carregado", extra={"conversation_id": "conv-99"})
    line = buf.getvalue().strip()

    assert _LOG_LINE_RE.match(line), f"Formato inesperado: {line!r}"
    assert line.endswith("Histórico carregado | conv=conv-99")
    assert "user=" not in line


def test_log_with_both_user_and_conversation_id():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.INFO):
        logger = lc.get_logger("backend.routers.chat")
        logger.info(
            "Mensagem enviada",
            extra={"user_id": "user-42", "conversation_id": "conv-99"},
        )
        logger.info("IDs numéricos", extra={"user_id": 0, "conversation_id": 7})
    lines = buf.getvalue().splitlines()

    assert len(lines) == 2
    assert _LOG_LINE_RE.match(lines[0])
    assert lines[0].endswith("Mensagem enviada | user=user-42 | conv=conv-99")
    assert lines[1].endswith("IDs numéricos | user=0 | conv=7")


@pytest.mark.parametrize("absent_value", [None, "", "   ", "\t\n", "-", " - "])
def test_absent_context_values_are_omitted_and_valid_sibling_preserved(absent_value):
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.INFO):
        logger = lc.get_logger("backend.memory")
        logger.info(
            "Ambos ausentes",
            extra={"user_id": absent_value, "conversation_id": absent_value},
        )
        logger.info(
            "Só user válido",
            extra={"user_id": "u-7", "conversation_id": absent_value},
        )
        logger.info(
            "Só conv válido",
            extra={"user_id": absent_value, "conversation_id": "c-8"},
        )
    lines = buf.getvalue().splitlines()

    assert len(lines) == 3
    assert lines[0].endswith("Ambos ausentes")
    assert "user=" not in lines[0]
    assert "conv=" not in lines[0]

    assert lines[1].endswith("Só user válido | user=u-7")
    assert "conv=" not in lines[1]

    assert lines[2].endswith("Só conv válido | conv=c-8")
    assert "user=" not in lines[2]


def test_traceback_keeps_context_suffix_on_main_line_only():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.ERROR):
        logger = lc.get_logger("backend.memory_dream")
        try:
            raise RuntimeError("falha simulada")
        except RuntimeError:
            logger.error(
                "Erro ao consolidar",
                exc_info=True,
                extra={"user_id": "u-123", "conversation_id": "c-456"},
            )
    lines = buf.getvalue().splitlines()

    assert len(lines) > 2
    first_line = lines[0]
    traceback_lines = lines[1:]

    assert _LOG_LINE_RE.match(first_line), f"Formato inesperado: {first_line!r}"
    assert "[ERROR]" in first_line
    assert first_line.endswith("Erro ao consolidar | user=u-123 | conv=c-456")
    assert traceback_lines[0].startswith("Traceback (most recent call last):")
    assert "RuntimeError: falha simulada" in traceback_lines[-1]
    for tb_line in traceback_lines:
        assert "user=" not in tb_line
        assert "conv=" not in tb_line


def test_traceback_without_context_has_no_suffix():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.ERROR):
        logger = lc.get_logger("backend.memory_dream")
        try:
            raise ValueError("sem contexto")
        except ValueError:
            logger.error("Falha isolada", exc_info=True)
    lines = buf.getvalue().splitlines()

    assert len(lines) > 2
    assert lines[0].endswith("Falha isolada")
    assert lines[1].startswith("Traceback (most recent call last):")
    assert "ValueError: sem contexto" in lines[-1]
    for line in lines:
        assert "user=" not in line
        assert "conv=" not in line


def test_stream_and_file_handlers_produce_identical_output(monkeypatch):
    fd, tmp_log_path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    stderr_buf = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stderr_buf)

    try:
        with _isolated_logging(stream=None, level=logging.INFO, log_file=tmp_log_path):
            logger = lc.get_logger("backend.routers.logs")
            logger.info("Sem contexto")
            logger.info("Apenas user", extra={"user_id": "u-1"})
            logger.info("Apenas conv", extra={"conversation_id": "c-2"})
            logger.warning(
                "Ambos presentes",
                extra={"user_id": "u-1", "conversation_id": "c-2"},
            )
            try:
                raise KeyError("chave-ausente")
            except KeyError:
                logger.error(
                    "Erro com stack",
                    exc_info=True,
                    extra={"user_id": "u-1"},
                )

        with open(tmp_log_path, "r", encoding="utf-8") as fh:
            file_text = fh.read()
    finally:
        if os.path.exists(tmp_log_path):
            os.unlink(tmp_log_path)

    stderr_text = stderr_buf.getvalue()
    assert stderr_text == file_text
    assert "user=-" not in file_text
    assert "conv=-" not in file_text
    assert "Sem contexto\n" in file_text
    assert "Apenas user | user=u-1\n" in file_text
    assert "Apenas conv | conv=c-2\n" in file_text
    assert "Ambos presentes | user=u-1 | conv=c-2\n" in file_text
    assert "Erro com stack | user=u-1\nTraceback (most recent call last):" in file_text


def test_custom_fmt_preserves_context_defaults_and_format():
    buf_with_placeholders = io.StringIO()
    with _isolated_logging(
        stream=buf_with_placeholders,
        level=logging.INFO,
        fmt="[%(levelname)s] %(message)s u=%(user_id)s c=%(conversation_id)s",
    ):
        logger = lc.get_logger("backend.custom")
        logger.info("sem extra")
        logger.info("com extra", extra={"user_id": "u-9", "conversation_id": "c-10"})

    lines = buf_with_placeholders.getvalue().splitlines()
    assert lines == [
        "[INFO] sem extra u=- c=-",
        "[INFO] com extra u=u-9 c=c-10",
    ]
    assert "Logging error" not in buf_with_placeholders.getvalue()

    buf_minimal = io.StringIO()
    with _isolated_logging(
        stream=buf_minimal,
        level=logging.INFO,
        fmt="[%(levelname)s] %(message)s",
    ):
        logger = lc.get_logger("backend.custom")
        logger.info("formato fixo", extra={"user_id": "u-9", "conversation_id": "c-10"})

    assert buf_minimal.getvalue().splitlines() == ["[INFO] formato fixo"]


def test_log_with_turn_id():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.INFO):
        logger = lc.get_logger("backend.orchestration.resolve_request")
        logger.info("Failover acionado", extra={"turn_id": "turn-abc-123"})
    line = buf.getvalue().strip()

    assert _LOG_LINE_RE.match(line)
    assert line.endswith("Failover acionado | turn=turn-abc-123")
    assert "user=" not in line
    assert "conv=" not in line


def test_log_with_user_conv_and_turn_id():
    buf = io.StringIO()
    with _isolated_logging(stream=buf, level=logging.INFO):
        logger = lc.get_logger("backend.routers.chat")
        logger.info(
            "Turno concluído",
            extra={"user_id": "u-1", "conversation_id": "c-2", "turn_id": "turn-3"},
        )
    line = buf.getvalue().strip()

    assert _LOG_LINE_RE.match(line)
    assert line.endswith("Turno concluído | user=u-1 | conv=c-2 | turn=turn-3")

