"""
backend/routers/logs.py
Endpoint para consulta de logs da aplicação em tempo real.
Suporta agregação de eventos por cabeçalho, parsing de timestamp e
isolamento seguro de tracebacks multilinhas.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any, List, Optional
import os
import re
from pathlib import Path
from datetime import datetime, timedelta

from backend.auth import require_admin
from backend.logging_config import get_logger

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = get_logger(__name__)

# Caminho padrão ou configurado via variável de ambiente
LOG_FILE = os.getenv("NEXUS_LOG_FILE") or os.getenv("LOG_FILE") or "/app/logs/app.log"


def get_configured_log_file() -> Path:
    """Retorna o caminho atual do arquivo de log, consultando env vars ativas."""
    override = os.getenv("NEXUS_LOG_FILE") or os.getenv("LOG_FILE")
    return Path(override if override else LOG_FILE)


_LOG_HEADER_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[,\.]\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+\[(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\]"
)


def parse_log_timestamp(ts_str: str) -> Optional[datetime]:
    """Parseia timestamp de linha de log com fuso consistente."""
    try:
        # Se contiver T ou offset de fuso horário
        if "T" in ts_str or "+" in ts_str or ("-" in ts_str[10:]):
            iso_candidate = ts_str.replace(",", ".")
            dt = datetime.fromisoformat(iso_candidate)
            if dt.tzinfo is not None:
                # Normaliza para horário local ingênuo, consistente com o logger
                dt = dt.astimezone().replace(tzinfo=None)
            return dt

        clean = ts_str.split(",")[0].split(".")[0].strip()
        return datetime.strptime(clean, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


@router.get("/tail")
async def get_log_tail(
    lines: int = 100,
    level: str = "ALL",
    current_user: dict = Depends(require_admin),
):
    """Retorna as últimas N linhas do log da aplicação."""
    log_path = get_configured_log_file()
    if not log_path.exists():
        return {"lines": [], "total_lines": 0, "file_exists": False}

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        total = len(all_lines)

        if level != "ALL":
            lvl_upper = level.upper()
            target_levels = (
                ("ERROR", "CRITICAL", "FATAL") if lvl_upper in ("ERROR", "CRITICAL", "FATAL")
                else ("WARNING", "WARN") if lvl_upper in ("WARNING", "WARN")
                else (lvl_upper,)
            )
            filtered_lines: List[str] = []
            include_current = False
            for line in all_lines:
                m = _LOG_HEADER_RE.match(line)
                if m:
                    ev_lvl = m.group(2).upper()
                    include_current = (ev_lvl in target_levels)
                if include_current:
                    filtered_lines.append(line)
            tail = filtered_lines[-lines:] if lines > 0 else filtered_lines
        else:
            tail = all_lines[-lines:] if lines > 0 else all_lines

        return {
            "lines": [l.rstrip('\r\n') for l in tail],
            "total_lines": total,
            "file_exists": True,
            "last_updated": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao ler logs: {e}")


@router.get("/errors")
async def get_recent_errors(
    hours: int = 24,
    limit: int = 50,
    current_user: dict = Depends(require_admin),
):
    """Retorna erros e warnings das últimas N horas com parsing real de timestamp."""
    log_path = get_configured_log_file()
    if not log_path.exists():
        return {"errors": [], "count": 0}

    try:
        now = datetime.now()
        cutoff = now - timedelta(hours=hours)

        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        # Agrupa linhas em eventos estruturados
        events = []
        current_event = None
        for line in all_lines:
            m = _LOG_HEADER_RE.match(line)
            if m:
                ts = parse_log_timestamp(m.group(1))
                lvl = m.group(2).upper()
                current_event = {
                    "timestamp": ts,
                    "level": lvl,
                    "lines": [line.rstrip("\r\n")],
                }
                events.append(current_event)
            elif current_event is not None:
                # Linha de continuação / traceback multilinha
                current_event["lines"].append(line.rstrip("\r\n"))

        errors = []
        # Percorre eventos em ordem reversa (mais recentes primeiro)
        for ev in reversed(events):
            if ev["level"] in ("ERROR", "CRITICAL", "FATAL", "WARNING", "WARN"):
                ev_ts = ev["timestamp"]
                if ev_ts is not None and ev_ts < cutoff:
                    # Evento fora da janela de corte
                    continue
                event_repr = "\n".join(ev["lines"]).strip()
                errors.append(event_repr)
                if len(errors) >= limit:
                    break

        return {"errors": errors, "count": len(errors)}
    except Exception as e:
        return {"errors": [], "count": 0, "error": str(e)}


@router.get("/stats")
async def get_log_stats(current_user: dict = Depends(require_admin)):
    """Retorna estatísticas de logs (contagens por nível baseadas em cabeçalhos de eventos)."""
    log_path = get_configured_log_file()
    if not log_path.exists():
        return {
            "total": 0,
            "total_events": 0,
            "total_lines": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
            "debug": 0,
        }

    try:
        with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        error_count = 0
        warning_count = 0
        info_count = 0
        debug_count = 0

        for line in all_lines:
            m = _LOG_HEADER_RE.match(line)
            if not m:
                continue
            lvl = m.group(2).upper()
            if lvl in ("ERROR", "CRITICAL", "FATAL"):
                error_count += 1
            elif lvl in ("WARNING", "WARN"):
                warning_count += 1
            elif lvl == "INFO":
                info_count += 1
            elif lvl == "DEBUG":
                debug_count += 1

        total_events = error_count + warning_count + info_count + debug_count

        return {
            "total": total_events,
            "total_events": total_events,
            "total_lines": total_lines,
            "error": error_count,
            "warning": warning_count,
            "info": info_count,
            "debug": debug_count,
        }
    except Exception as e:
        return {
            "total": 0,
            "total_events": 0,
            "total_lines": 0,
            "error": 0,
            "warning": 0,
            "info": 0,
            "debug": 0,
            "error_detail": str(e),
        }
