"""
backend/routers/logs.py
Endpoint para consulta de logs da aplicação em tempo real.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
import os
from pathlib import Path
from datetime import datetime

from backend.auth import require_admin
from backend.logging_config import get_logger

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = get_logger(__name__)

LOG_FILE = "/app/logs/app.log"


@router.get("/tail")
async def get_log_tail(
    lines: int = 100,
    level: str = "ALL",
    current_user: dict = Depends(require_admin),
):
    """Retorna as últimas N linhas do log da aplicação."""
    if not os.path.exists(LOG_FILE):
        return {"lines": [], "total_lines": 0, "file_exists": False}

    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        # Filtra por nível se solicitado
        if level != "ALL":
            all_lines = [l for l in all_lines if f"[{level}]" in l]

        total = len(all_lines)
        tail = all_lines[-lines:] if lines > 0 else all_lines

        return {
            "lines": [l.rstrip('\n') for l in tail],
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
    """Retorna erros e warnings das últimas N horas."""
    from datetime import datetime, timedelta

    if not os.path.exists(LOG_FILE):
        return {"errors": [], "count": 0}

    try:
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')

        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()

        errors = []
        for line in reversed(all_lines):
            if line.strip().startswith(cutoff) or line > cutoff:
                if "[ERROR]" in line or "[WARNING]" in line:
                    errors.append(line.rstrip('\n'))
                    if len(errors) >= limit:
                        break

        return {"errors": errors, "count": len(errors)}
    except Exception as e:
        return {"errors": [], "count": 0, "error": str(e)}


@router.get("/stats")
async def get_log_stats(current_user: dict = Depends(require_admin)):
    """Retorna estatísticas de logs (contagens por nível)."""
    if not os.path.exists(LOG_FILE):
        return {"total": 0, "error": 0, "warning": 0, "info": 0, "debug": 0}

    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "total": len(content.split('\n')),
            "error": content.count("[ERROR]"),
            "warning": content.count("[WARNING]"),
            "info": content.count("[INFO]"),
            "debug": content.count("[DEBUG]"),
        }
    except Exception as e:
        return {"total": 0, "error": 0, "warning": 0, "info": 0, "debug": 0, "error_detail": str(e)}
