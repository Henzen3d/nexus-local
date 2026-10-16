"""Testes do Agendador de Rotinas (F8.1.5)."""
from datetime import datetime, timezone
import pytest
from backend.database import get_db, init_db
from backend.proactive.scheduler import RoutineScheduler, compute_next_run


def test_compute_next_run():
    # Minutos
    next_m = compute_next_run("interval", "15m")
    assert next_m > datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Horas
    next_h = compute_next_run("interval", "2h")
    assert next_h > datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Dias
    next_d = compute_next_run("interval", "3d")
    assert next_d > datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    # Daily HH:MM
    next_daily = compute_next_run("daily", "23:59")
    assert len(next_daily) == 19


@pytest.mark.asyncio
async def test_routine_scheduler_execution():
    await init_db()
    db = await get_db()
    try:
        # Cria usuário e bot para teste
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash) VALUES ('usr_sch_1', 'sched_user', 'hash')"
        )
        await db.execute(
            """
            INSERT OR IGNORE INTO proactive_bots (id, user_id, name, system_instructions)
            VALUES ('bot_sch_1', 'usr_sch_1', 'Bot Agendado', 'Instruções de teste')
            """
        )
        # Cria rotina vencida (com next_run_at no passado)
        await db.execute(
            """
            INSERT INTO proactive_routines (id, bot_id, user_id, name, prompt, timing_type, timing_value, next_run_at, is_active)
            VALUES ('rt_1', 'bot_sch_1', 'usr_sch_1', 'Rotina Vencida', 'Checar novidades', 'interval', '30m', '2020-01-01 00:00:00', 1)
            """
        )
        await db.commit()
    finally:
        await db.close()

    scheduler = RoutineScheduler(get_db, interval_seconds=10)
    executed = await scheduler.run_due_routines()
    assert executed >= 1

    # Checa se next_run_at foi avançado para o futuro
    db = await get_db()
    try:
        async with db.execute("SELECT next_run_at, last_run_at FROM proactive_routines WHERE id = 'rt_1'") as cur:
            row = await cur.fetchone()
            assert row is not None
            assert row[0] > datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            assert row[1] is not None
    finally:
        await db.close()
