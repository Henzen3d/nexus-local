"""Família: cadastro fechado, chave só do próprio usuário, varinha exige login."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-family-access-secret")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _fresh_db():
    from backend import database as dbmod

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    dbmod.DB_PATH = Path(path)
    await dbmod.init_db()
    return dbmod


async def test_register_is_closed():
    await _fresh_db()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.auth import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    client = TestClient(app)
    res = client.post("/api/auth/register", json={"username": "estranho", "password": "segredo123"})
    assert res.status_code == 403, res.status_code


async def test_stranger_cannot_use_global_or_admin_key():
    dbmod = await _fresh_db()
    db = await dbmod.get_db()
    try:
        admin_id = str(uuid.uuid4())
        family_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'admin', 'x', 'admin')",
            (admin_id,),
        )
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'vera', 'x', 'user')",
            (family_id,),
        )
        await db.execute(
            "UPDATE providers SET api_key = 'global-secret', enabled = 1 WHERE id = 'groq'"
        )
        await db.execute(
            "INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, 'groq', 'admin-secret')",
            (admin_id,),
        )
        await db.commit()

        from backend.providers.registry import get_provider

        try:
            await get_provider("groq", db, user_id=family_id)
            raised = False
        except ValueError:
            raised = True
        assert raised, "usuário sem chave própria não pode herdar chave global nem a do admin"

        provider = await get_provider("groq", db, user_id=admin_id)
        assert provider.api_key == "admin-secret"
    finally:
        await db.close()


async def test_enhancer_config_requires_login():
    await _fresh_db()
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.enhancer import router as enhancer_router

    app = FastAPI()
    app.include_router(enhancer_router)
    client = TestClient(app)
    res = client.get("/api/enhancer/config")
    assert res.status_code in (401, 403), res.status_code


async def test_web_search_hides_api_key():
    dbmod = await _fresh_db()
    db = await dbmod.get_db()
    try:
        await db.execute(
            "UPDATE web_search_config SET api_key = 'brave-secret-key' WHERE id = 1"
        )
        user_id = str(uuid.uuid4())
        from backend.auth import hash_password

        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'vera', ?, 'user')",
            (user_id, hash_password("segredo123")),
        )
        await db.commit()
    finally:
        await db.close()

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.auth import router as auth_router
    from backend.routers.web_search import router as web_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(web_router)
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "vera", "password": "segredo123"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    res = client.get("/api/web-search/config", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert "brave-secret-key" not in str(body)
    assert body.get("api_key_set") is True


async def test_admin_creates_family_user():
    dbmod = await _fresh_db()
    db = await dbmod.get_db()
    try:
        from backend.auth import hash_password

        admin_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'osmar', ?, 'admin')",
            (admin_id, hash_password("admin-pass")),
        )
        await db.commit()
    finally:
        await db.close()

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.auth import router as auth_router
    from backend.routers.admin import router as admin_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(admin_router)
    client = TestClient(app)
    login = client.post("/api/auth/login", json={"username": "osmar", "password": "admin-pass"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    res = client.post(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"username": "vera", "password": "vera-pass", "email": "vera@example.com"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["user"]["role"] == "user"

    login_vera = client.post("/api/auth/login", json={"username": "vera", "password": "vera-pass"})
    assert login_vera.status_code == 200, login_vera.text


async def test_claim_copies_global_key_once():
    dbmod = await _fresh_db()
    db = await dbmod.get_db()
    try:
        admin_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'osmar', 'x', 'admin')",
            (admin_id,),
        )
        await db.execute(
            "UPDATE providers SET api_key = 'global-secret' WHERE id = 'groq'"
        )
        await db.execute(
            "INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, 'openai', 'ja-pessoal')",
            (admin_id,),
        )
        await db.execute("UPDATE providers SET api_key = 'global-openai' WHERE id = 'openai'")
        await db.commit()
        await dbmod.claim_global_provider_keys(db)
        async with db.execute(
            "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = 'groq'",
            (admin_id,),
        ) as cur:
            row = await cur.fetchone()
        assert row and row[0] == "global-secret"
        async with db.execute(
            "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = 'openai'",
            (admin_id,),
        ) as cur:
            kept = await cur.fetchone()
        assert kept and kept[0] == "ja-pessoal"
        await db.execute(
            "UPDATE user_api_keys SET api_key = 'trocada' WHERE user_id = ? AND provider_id = 'groq'",
            (admin_id,),
        )
        await db.commit()
        await dbmod.claim_global_provider_keys(db)
        async with db.execute(
            "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = 'groq'",
            (admin_id,),
        ) as cur:
            again = await cur.fetchone()
        assert again and again[0] == "trocada"
    finally:
        await db.close()


def main():
    tests = [
        test_register_is_closed,
        test_stranger_cannot_use_global_or_admin_key,
        test_enhancer_config_requires_login,
        test_web_search_hides_api_key,
        test_admin_creates_family_user,
        test_claim_copies_global_key_once,
    ]
    failed = 0
    for test in tests:
        try:
            run(test())
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
