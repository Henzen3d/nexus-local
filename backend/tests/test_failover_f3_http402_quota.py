import pytest
from datetime import datetime, timezone
import aiosqlite

from backend.database import init_db, get_db, classify_model_error, check_and_deactivate_model
from backend.ranking.quota import is_quota_exhausted_error, mark_model_exhausted, get_quota_status
from backend.ranking.failover import resolve_model_with_failover, _get_next_best_ranked_model


LONGCAT_402_PAYLOAD = (
    'Provider error 402: {"error":{"code":"too_many_requests",'
    '"message":"AppId:**jt51 Usage limit reached.","type":"rate_limit_error"}}'
)


def test_is_quota_exhausted_error_longcat():
    assert is_quota_exhausted_error(LONGCAT_402_PAYLOAD) is True


def test_classify_model_error_longcat_is_quota_not_permanent_deactivation():
    res = classify_model_error(LONGCAT_402_PAYLOAD)
    assert res["is_deactivation"] is False
    assert res["reason"] == "quota_exhausted"


@pytest.mark.asyncio
async def test_longcat_402_applies_long_quota_cooldown():
    """Valida que o erro 402 Usage limit reached aplica cooldown de no mínimo 1 hora."""
    await init_db()
    db = await get_db()
    try:
        model_id = "longcat/LongCat-2.5-Preview"
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('longcat', 'LongCat', 'https://api.longcat.chat', 1, 1)")
        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{model_id}', 'longcat', 'LongCat-2.5', 'LongCat 2.5 Preview', 1)")
        await db.commit()

        # Invocamos mark_model_exhausted com o payload 402
        t_before = datetime.now(timezone.utc)
        await mark_model_exhausted(model_id, db, error_msg=LONGCAT_402_PAYLOAD)

        quota = await get_quota_status(model_id, db)
        assert quota["status"] == "exhausted"
        assert quota["last_error_message"] == LONGCAT_402_PAYLOAD
        assert quota["estimated_reset_at"] is not None

        # O reset_at deve ser de pelo menos 1 hora (3600 segundos) a partir de t_before
        reset_dt = datetime.fromisoformat(quota["estimated_reset_at"])
        delta_seconds = (reset_dt - t_before).total_seconds()
        assert delta_seconds >= 3590  # margem para tempo de execução
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_longcat_402_removes_model_from_tier2_failover():
    """Confirma que o modelo em cooldown 402 é retirado do Tier 2 e aciona failover."""
    await init_db()
    db = await get_db()
    try:
        model_longcat = "longcat/LongCat-2.5-Preview"
        model_alternative = "groq/llama-3.3-70b"

        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('longcat', 'LongCat', 'https://api.longcat.chat', 1, 1)")
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('groq', 'Groq', 'https://api.groq', 1, 1)")

        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{model_longcat}', 'longcat', 'LongCat-2.5', 'LongCat 2.5 Preview', 1)")
        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{model_alternative}', 'groq', 'llama-3.3', 'Llama 3.3 70B', 1)")

        # Longcat tem score maior no ranking geral que o alternativo
        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{model_longcat}', 99)")
        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{model_alternative}', 90)")
        await db.commit()

        # check_and_deactivate_model com payload 402 aplica cooldown de quota sem desativar o modelo permanentemente
        deactivated = await check_and_deactivate_model(model_longcat, LONGCAT_402_PAYLOAD, db=db)
        assert deactivated is False

        # Modelo continua enabled=1
        async with db.execute(f"SELECT enabled FROM models WHERE id = '{model_longcat}'") as cur:
            row = await cur.fetchone()
            assert row[0] == 1

        # Mas quota está exhausted
        quota = await get_quota_status(model_longcat, db)
        assert quota["status"] == "exhausted"

        # Tier 2 NÃO deve selecionar o LongCat enquanto estiver em cooldown de quota
        next_best = await _get_next_best_ranked_model(db, exclude_model_ids=[], exclude_family_ids=[])
        assert next_best is not None
        assert next_best[0] == model_alternative

        # Requisitar o modelo esgotado deve fazer failover
        resolved = await resolve_model_with_failover(model_longcat, db)
        assert resolved.was_failover is True
        assert resolved.model_id == model_alternative
    finally:
        await db.close()
