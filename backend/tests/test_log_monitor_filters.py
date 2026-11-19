"""
backend/tests/test_log_monitor_filters.py
Testes unitários para contadores e filtros do Monitor de Logs (T5.2).
Valida isolamento de tracebacks multilinhas, parsing real de timestamp,
fuso consistente e exclusão correta de eventos fora da janela de horas.
"""

import os
import tempfile
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from backend.routers.logs import (
    get_log_stats,
    get_recent_errors,
    get_log_tail,
    parse_log_timestamp,
    _LOG_HEADER_RE,
)

admin_user = {"id": "admin-1", "role": "admin"}


@pytest.fixture
def temp_log_file(monkeypatch):
    """Cria um arquivo de log temporário isolado para cada teste."""
    fd, path = tempfile.mkstemp(suffix=".log")
    os.close(fd)
    monkeypatch.setenv("NEXUS_LOG_FILE", path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_parse_log_timestamp_formats():
    # Formato padrão asctime
    dt1 = parse_log_timestamp("2026-11-19 14:30:15")
    assert dt1 == datetime(2026, 11, 19, 14, 30, 15)

    # Com milissegundos vírgula
    dt2 = parse_log_timestamp("2026-11-19 14:30:15,123")
    assert dt2 == datetime(2026, 11, 19, 14, 30, 15)

    # Com milissegundos ponto
    dt3 = parse_log_timestamp("2026-11-19 14:30:15.456")
    assert dt3 == datetime(2026, 11, 19, 14, 30, 15)

    # ISO com T
    dt4 = parse_log_timestamp("2026-11-19T14:30:15")
    assert dt4 == datetime(2026, 11, 19, 14, 30, 15)

    # Inválido
    assert parse_log_timestamp("invalid-date") is None


@pytest.mark.asyncio
async def test_log_stats_event_counting_with_multiline_traceback_and_blanks(temp_log_file):
    """
    T5.2: Valida que eventos são contados por cabeçalho,
    de modo que tracebacks multilinhas e linhas em branco não causem
    descompasso entre total_events e a soma dos níveis.
    """
    sample_content = (
        "2026-11-19 10:00:00 [INFO] nexuslocal.routers.chat: Início do turno | user=u1\n"
        "\n"
        "2026-11-19 10:00:01 [DEBUG] nexuslocal.ranking.smart_router: Candidatos avaliados\n"
        "2026-11-19 10:00:02 [DEBUG] nexuslocal.ranking.smart_router: Fit calculado\n"
        "2026-11-19 10:00:03 [WARNING] nexuslocal.ranking.sources: 429 rate limit temporário\n"
        "2026-11-19 10:00:04 [ERROR] nexuslocal.orchestration: Falha crítica na chamada\n"
        "Traceback (most recent call last):\n"
        '  File "resolve_request.py", line 1234, in stream\n'
        '    raise ProviderHTTPError(402, "insufficient_user_quota")\n'
        "ProviderHTTPError: [402] insufficient_user_quota\n"
        "\n"
        "2026-11-19 10:00:05 [CRITICAL] nexuslocal.database: Conexão esgotada\n"
    )
    with open(temp_log_file, "w", encoding="utf-8") as f:
        f.write(sample_content)

    stats = await get_log_stats(current_user=admin_user)

    # 1 INFO, 2 DEBUG, 1 WARNING, 2 ERROR (ERROR + CRITICAL) = 6 eventos no total
    assert stats["info"] == 1
    assert stats["debug"] == 2
    assert stats["warning"] == 1
    assert stats["error"] == 2  # ERROR + CRITICAL
    assert stats["total_events"] == 6
    assert stats["total"] == 6  # Consistente: soma dos níveis == total
    assert stats["error"] + stats["warning"] + stats["info"] + stats["debug"] == stats["total"]

    # total_lines conta linhas físicas brutas (incluindo tracebacks e vazias)
    assert stats["total_lines"] > 6


@pytest.mark.asyncio
async def test_get_recent_errors_filter_by_actual_timestamp_window(temp_log_file):
    """
    T5.2: Corrige o filtro de 'últimas N horas' para analisar o timestamp do evento.
    Eventos antigos (mesmo contendo traceback multilinha) devem ser descartados,
    evitando que a comparação lexicográfica antiga ('line > cutoff') vazasse eventos.
    """
    now = datetime.now()
    recent_ts = (now - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    ancient_ts = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")

    log_content = (
        f"{ancient_ts} [ERROR] nexuslocal.old: Erro ocorrido 5 dias atrás\n"
        "Traceback (most recent call last):\n"
        '  File "old_module.py", line 42, in run\n'
        "RuntimeError: ancient bug\n"
        f"{ancient_ts} [WARNING] nexuslocal.old: Warning ocorrido 5 dias atrás\n"
        f"{recent_ts} [ERROR] nexuslocal.recent: Erro recente dentro da janela\n"
        "Traceback (most recent call last):\n"
        '  File "new_module.py", line 10, in run\n'
        "ValueError: fresh error\n"
    )
    with open(temp_log_file, "w", encoding="utf-8") as f:
        f.write(log_content)

    # Consulta últimas 24 horas
    res = await get_recent_errors(hours=24, limit=50, current_user=admin_user)

    assert res["count"] == 1
    assert len(res["errors"]) == 1
    assert "Erro recente dentro da janela" in res["errors"][0]
    assert "fresh error" in res["errors"][0]

    # O erro antigo e seus tracebacks NÃO devem estar presentes
    assert "Erro ocorrido 5 dias atrás" not in res["errors"][0]
    assert "ancient bug" not in res["errors"][0]


@pytest.mark.asyncio
async def test_get_log_tail_with_filter_preserves_traceback(temp_log_file):
    """
    Valida que ao filtrar por nível no tail (ex: ERROR), o bloco completo
    com o traceback é preservado.
    """
    log_content = (
        "2026-11-19 12:00:00 [INFO] nexuslocal.app: Sistema pronto\n"
        "2026-11-19 12:00:01 [ERROR] nexuslocal.app: Falha inesperada\n"
        "Traceback (most recent call last):\n"
        "  File app.py, line 1\n"
        "Exception: boom\n"
        "2026-11-19 12:00:02 [INFO] nexuslocal.app: Mensagem pós erro\n"
    )
    with open(temp_log_file, "w", encoding="utf-8") as f:
        f.write(log_content)

    res = await get_log_tail(lines=100, level="ERROR", current_user=admin_user)
    lines = res["lines"]

    assert any("[ERROR]" in l for l in lines)
    assert any("Traceback (most recent call last):" in l for l in lines)
    assert any("Exception: boom" in l for l in lines)
    # Linhas de INFO devem ter sido filtradas
    assert not any("[INFO]" in l for l in lines)
