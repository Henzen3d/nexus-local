import pytest
import uuid
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.routers.account import router as account_router
from backend.routers.admin import router as admin_router
from backend.auth import create_access_token
from backend.database import get_db, init_db

@pytest.mark.asyncio
async def test_get_my_account():
    await init_db()
    db = await get_db()
    try:
        user_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'tester_toggle', 'x', 'user')",
            (user_id,)
        )
        await db.commit()

        token = create_access_token(user_id, "tester_toggle", "user")

        app = FastAPI()
        app.include_router(account_router)
        client = TestClient(app)

        res = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert data["id"] == user_id
        assert data["username"] == "tester_toggle"
        assert data["role"] == "user"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_roles_osmar_and_admin():
    await init_db()
    db = await get_db()
    try:
        id_osmar = str(uuid.uuid4())
        id_admin = str(uuid.uuid4())
        await db.execute("INSERT OR REPLACE INTO users (id, username, password_hash, role) VALUES (?, 'osmar', 'x', 'user')", (id_osmar,))
        await db.execute("INSERT OR REPLACE INTO users (id, username, password_hash, role) VALUES (?, 'admin', 'x', 'user')", (id_admin,))
        await db.commit()

        # Executa o init_db para rodar a migração de garantia de roles
        await init_db()

        async with db.execute("SELECT role FROM users WHERE id = ?", (id_osmar,)) as cur:
            row_osmar = await cur.fetchone()
            assert row_osmar[0] == "admin"

        async with db.execute("SELECT role FROM users WHERE id = ?", (id_admin,)) as cur:
            row_admin = await cur.fetchone()
            assert row_admin[0] == "user"
    finally:
        await db.close()

@pytest.mark.asyncio
async def test_regular_user_can_toggle_provider_and_models():
    await init_db()
    db = await get_db()
    try:
        user1_id = str(uuid.uuid4())
        user2_id = str(uuid.uuid4())
        await db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, 'user1', 'x', 'user')", (user1_id,))
        await db.execute("INSERT INTO users (id, username, password_hash, role) VALUES (?, 'user2', 'x', 'user')", (user2_id,))

        prov_id = f"prov_test_{uuid.uuid4().hex[:6]}"
        model1_id = f"{prov_id}/model1"
        model2_id = f"{prov_id}/model2"

        await db.execute(
            "INSERT INTO providers (id, name, base_url, enabled, is_free) VALUES (?, 'Test Prov', 'http://test', 1, 1)",
            (prov_id,)
        )
        await db.execute(
            "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES (?, 'm1', 'Model 1', ?, 1)",
            (model1_id, prov_id)
        )
        await db.execute(
            "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES (?, 'm2', 'Model 2', ?, 1)",
            (model2_id, prov_id)
        )
        await db.commit()

        token_user1 = create_access_token(user1_id, "user1", "user")
        token_user2 = create_access_token(user2_id, "user2", "user")

        app = FastAPI()
        app.include_router(admin_router)
        client = TestClient(app)

        # 1. Usuário comum consegue desativar model1
        res = client.patch(
            f"/api/admin/models/{model1_id}",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {token_user1}"}
        )
        assert res.status_code == 200, res.text

        # 2. Usuário 1 lista provedores: model1 está desativado, model2 está ativo
        res_prov_u1 = client.get("/api/admin/providers", headers={"Authorization": f"Bearer {token_user1}"})
        assert res_prov_u1.status_code == 200
        provs_u1 = [p for p in res_prov_u1.json() if p["id"] == prov_id]
        assert len(provs_u1) == 1
        m_map_u1 = {m["id"]: m["enabled"] for m in provs_u1[0]["models"]}
        assert m_map_u1[model1_id] is False
        assert m_map_u1[model2_id] is True

        # 3. Usuário 2 não foi afetado pela desativação do Usuário 1!
        res_prov_u2 = client.get("/api/admin/providers", headers={"Authorization": f"Bearer {token_user2}"})
        assert res_prov_u2.status_code == 200
        provs_u2 = [p for p in res_prov_u2.json() if p["id"] == prov_id]
        m_map_u2 = {m["id"]: m["enabled"] for m in provs_u2[0]["models"]}
        assert m_map_u2[model1_id] is True
        assert m_map_u2[model2_id] is True

        # 4. Usuário 1 desativa o provedor inteiro
        res_toggle_prov = client.patch(
            f"/api/admin/providers/{prov_id}",
            json={"enabled": False},
            headers={"Authorization": f"Bearer {token_user1}"}
        )
        assert res_toggle_prov.status_code == 200

        # Para Usuário 1, provedor está desativado
        res_prov_u1_after = client.get("/api/admin/providers", headers={"Authorization": f"Bearer {token_user1}"})
        p_u1 = [p for p in res_prov_u1_after.json() if p["id"] == prov_id][0]
        assert p_u1["enabled"] is False

        # Para Usuário 2, provedor continua ativado
        res_prov_u2_after = client.get("/api/admin/providers", headers={"Authorization": f"Bearer {token_user2}"})
        p_u2 = [p for p in res_prov_u2_after.json() if p["id"] == prov_id][0]
        assert p_u2["enabled"] is True

        # 5. Tentativa de usuário comum alterar base_url ou context_length deve retornar 403
        res_forbidden_url = client.patch(
            f"/api/admin/providers/{prov_id}",
            json={"base_url": "http://malicious"},
            headers={"Authorization": f"Bearer {token_user1}"}
        )
        assert res_forbidden_url.status_code == 403

        res_forbidden_ctx = client.patch(
            f"/api/admin/models/{model1_id}",
            json={"context_length": 999999},
            headers={"Authorization": f"Bearer {token_user1}"}
        )
        assert res_forbidden_ctx.status_code == 403
    finally:
        await db.close()
