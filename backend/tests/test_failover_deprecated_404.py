import pytest
import aiosqlite
from backend.database import (
    extract_suggested_model,
    classify_model_error,
    check_and_deactivate_model,
    init_db,
    get_db,
)


def test_extract_suggested_model_gemini_payload():
    payload = (
        'This model models/gemini-2.5-pro is no longer available to new users. '
        'Please update your code to use models/gemini-3.1-pro-preview.'
    )
    suggested = extract_suggested_model(payload)
    assert suggested == "models/gemini-3.1-pro-preview"


def test_extract_suggested_model_gemini_native_json():
    payload = (
        '[Gemini Native] API error 404: {"error": {"code": 404, '
        '"message": "This model models/gemini-2.5-pro is no longer available to new users. '
        'Please update your code to use models/gemini-3.1-pro-preview.", "status": "NOT_FOUND"}}'
    )
    suggested = extract_suggested_model(payload)
    assert suggested == "models/gemini-3.1-pro-preview"


def test_classify_model_error_gemini_deprecated():
    payload = (
        '[Gemini Native] API error 404: {"error": {"code": 404, '
        '"message": "This model models/gemini-2.5-pro is no longer available to new users. '
        'Please update your code to use models/gemini-3.1-pro-preview.", "status": "NOT_FOUND"}}'
    )
    res = classify_model_error(payload)
    assert res["is_deactivation"] is True
    assert res["reason"] == "model_deprecated"
    assert res["suggested_model"] == "models/gemini-3.1-pro-preview"
    assert "model_deprecated" in res["status_message"]
    assert "models/gemini-3.1-pro-preview" in res["status_message"]


def test_classify_model_error_not_found():
    payload = "Error 404: model not found in catalog"
    res = classify_model_error(payload)
    assert res["is_deactivation"] is True
    assert res["reason"] == "model_not_found"
    assert res["suggested_model"] is None


def test_classify_model_error_billing():
    payload = "Provider error: insufficient_quota for current billing cycle"
    res = classify_model_error(payload)
    assert res["is_deactivation"] is True
    assert res["reason"] == "billing_error"


@pytest.mark.asyncio
async def test_check_and_deactivate_model_gemini_deprecated():
    await init_db()
    db = await get_db()
    try:
        # Inserir provider e modelo
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled) VALUES ('gemini', 'Google Gemini', 'https://api.google.com', 1)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled, confirmed_free) "
            "VALUES ('gemini/gemini-2.5-pro', 'gemini', 'models/gemini-2.5-pro', 'Gemini 2.5 Pro', 1, 1)"
        )
        await db.commit()

        payload = (
            '[Gemini Native] API error 404: {"error": {"code": 404, '
            '"message": "This model models/gemini-2.5-pro is no longer available to new users. '
            'Please update your code to use models/gemini-3.1-pro-preview.", "status": "NOT_FOUND"}}'
        )

        deactivated = await check_and_deactivate_model("gemini/gemini-2.5-pro", payload, db=db)
        assert deactivated is True

        # Verificar se modelo foi desativado
        async with db.execute("SELECT enabled, confirmed_free FROM models WHERE id = 'gemini/gemini-2.5-pro'") as cur:
            row = await cur.fetchone()
            assert row == (0, 0)

        # Verificar se model_quota_status registrou a mensagem com status_message
        async with db.execute("SELECT status, last_error_message FROM model_quota_status WHERE model_id = 'gemini/gemini-2.5-pro'") as cur:
            status_row = await cur.fetchone()
            assert status_row is not None
            assert status_row[0] == "exhausted"
            assert "model_deprecated" in status_row[1]
            assert "models/gemini-3.1-pro-preview" in status_row[1]
    finally:
        await db.close()
