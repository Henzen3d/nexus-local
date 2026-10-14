"""Testes da Fase 6 (Web Push) e Fase 7 (Hub/Histórico e Investigação Manual)."""
import asyncio
from datetime import datetime
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db, init_db
from backend.proactive import push, delivery, service
from backend.proactive.config import get_user_settings, upsert_user_settings
from backend.auth import create_access_token


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    asyncio.run(init_db())


@pytest.fixture
def test_client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    user_id = "user_push_test"
    async def _seed():
        db = await get_db()
        try:
            await db.execute(
                "INSERT OR IGNORE INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
                (user_id, user_id),
            )
            await db.commit()
        finally:
            await db.close()

    asyncio.run(_seed())
    token = create_access_token(user_id, user_id, "user")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_vapid_keys_lifecycle():
    db = await get_db()
    try:
        pub_b64, priv_pem, sub = await push.ensure_vapid_keys(db)
        assert len(pub_b64) > 20
        assert b"BEGIN PRIVATE KEY" in priv_pem
        assert sub.startswith("mailto:")

        # Segunda chamada deve retornar as mesmas chaves persistidas em meta
        pub2, priv2, sub2 = await push.ensure_vapid_keys(db)
        assert pub_b64 == pub2
        assert priv_pem == priv2
        assert sub == sub2
    finally:
        await db.close()


def test_vapid_public_key_endpoint(test_client, auth_headers):
    res = test_client.get("/api/push/vapid-public-key", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "publicKey" in data
    assert len(data["publicKey"]) > 20


def test_push_subscription_lifecycle(test_client, auth_headers):
    sub_payload = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/test-sub-123",
        "keys": {
            "p256dh": "test-p256dh-key",
            "auth": "test-auth-secret",
        },
        "user_agent": "Mozilla/5.0 Test",
    }
    # Subscribe
    res = test_client.post("/api/push/subscribe", json=sub_payload, headers=auth_headers)
    assert res.status_code == 200
    assert res.json().get("ok") is True

    # Unsubscribe
    del_res = test_client.request(
        "DELETE",
        "/api/push/subscribe",
        json={"endpoint": sub_payload["endpoint"]},
        headers=auth_headers,
    )
    assert del_res.status_code == 200
    assert del_res.json().get("removed") is True


def test_user_settings_push_and_persona(test_client, auth_headers):
    # GET settings iniciais
    res = test_client.get("/api/proactive/settings", headers=auth_headers)
    assert res.status_code == 200
    initial = res.json()
    assert "push_enabled" in initial
    assert "persona_style" in initial

    # PUT atualizando push_enabled e persona_style
    update_res = test_client.put(
        "/api/proactive/settings",
        json={
            "enabled": True,
            "push_enabled": True,
            "persona_style": "core",
        },
        headers=auth_headers,
    )
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated.get("push_enabled") is True
    assert updated.get("persona_style") == "core"


def test_quiet_hours_calculation():
    qh = {"start": "22:00", "end": "08:00"}
    assert push.is_in_quiet_hours(qh, datetime(2026, 10, 14, 23, 30)) is True
    assert push.is_in_quiet_hours(qh, datetime(2026, 10, 14, 3, 15)) is True
    assert push.is_in_quiet_hours(qh, datetime(2026, 10, 14, 14, 0)) is False

    qh_day = {"start": "12:00", "end": "14:00"}
    assert push.is_in_quiet_hours(qh_day, datetime(2026, 10, 14, 13, 0)) is True
    assert push.is_in_quiet_hours(qh_day, datetime(2026, 10, 14, 15, 0)) is False
    assert push.is_in_quiet_hours(None) is False


def test_proactive_history_endpoint(test_client, auth_headers):
    res = test_client.get("/api/proactive/history", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert "insights" in data
    assert isinstance(data["insights"], list)


def test_proactive_investigate_endpoint(test_client, auth_headers):
    payload = {
        "prompt": "Pesquisar novidades sobre inteligência artificial local",
        "category": "news",
    }
    res = test_client.post("/api/proactive/investigate", json=payload, headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert data.get("ok") is True
    assert "insight_id" in data
    assert "conversation_id" in data
