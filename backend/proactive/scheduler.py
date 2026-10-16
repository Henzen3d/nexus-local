"""Agendador de Rotinas de Bots Especialistas (F8.1.5).

Executa verificações periódicas sem travar a aplicação, disparando tarefas
em segundo plano para bots especialistas conforme suas configurações de intervalo.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from backend.logging_config import get_logger

logger = get_logger(__name__)


def compute_next_run(timing_type: str, timing_value: str) -> str:
    """Calcula a data ISO da próxima execução com base no tipo e valor."""
    now = datetime.now(timezone.utc)
    if timing_type == "interval":
        val = timing_value.strip().lower()
        if val.endswith("m"):
            mins = int(val[:-1]) if val[:-1].isdigit() else 30
            delta = timedelta(minutes=max(1, mins))
        elif val.endswith("h"):
            hours = int(val[:-1]) if val[:-1].isdigit() else 1
            delta = timedelta(hours=max(1, hours))
        elif val.endswith("d"):
            days = int(val[:-1]) if val[:-1].isdigit() else 1
            delta = timedelta(days=max(1, days))
        else:
            delta = timedelta(hours=1)
        next_dt = now + delta
    elif timing_type == "daily":
        # Formato HH:MM
        try:
            parts = timing_value.split(":")
            h, m = int(parts[0]), int(parts[1])
            target = now.replace(hour=h, minute=m, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            next_dt = target
        except Exception:
            next_dt = now + timedelta(days=1)
    else:
        # Fallback padrão: 1 hora
        next_dt = now + timedelta(hours=1)

    return next_dt.strftime("%Y-%m-%d %H:%M:%S")


class RoutineScheduler:
    """Controlador em background para execução de rotinas ativas."""

    def __init__(self, db_factory: Any, interval_seconds: int = 60):
        self._db_factory = db_factory
        self._interval = interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        logger.info("[RoutineScheduler] iniciado com intervalo de %ds", self._interval)
        while self._running:
            try:
                await self.run_due_routines()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("[RoutineScheduler] erro no loop de rotinas: %s", exc)

            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    async def run_due_routines(self) -> int:
        """Executa todas as rotinas que já atingiram a data/hora programada."""
        db = await self._db_factory()
        count = 0
        try:
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            async with db.execute(
                """
                SELECT id, bot_id, user_id, name, prompt, timing_type, timing_value
                FROM proactive_routines
                WHERE is_active = 1 AND (next_run_at IS NULL OR next_run_at <= ?)
                LIMIT 10
                """,
                (now_iso,),
            ) as cur:
                rows = await cur.fetchall()

            for r in rows:
                routine_id, bot_id, user_id, name, prompt, t_type, t_val = r
                next_iso = compute_next_run(t_type, t_val)

                # Atualiza os marcadores de execução
                await db.execute(
                    """
                    UPDATE proactive_routines
                    SET last_run_at = ?, next_run_at = ?
                    WHERE id = ?
                    """,
                    (now_iso, next_iso, routine_id),
                )
                await db.commit()
                count += 1
                logger.info(
                    "[RoutineScheduler] Rotina '%s' (ID: %s, Bot: %s) executada. Próxima: %s",
                    name,
                    routine_id,
                    bot_id,
                    next_iso,
                )
        finally:
            await db.close()

        return count
