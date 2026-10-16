"""backend/tests/test_tools_api.py — Testes das rotas REST de ferramentas e administração.
"""
from __future__ import annotations

import uuid
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import database as dbmod
from backend.auth import create_access_token
from backend.routers.tools import router as tools_router
from backend.tools.base import ToolResult
from backend.tools.registry import auto_register_default_providers


@pytest.fixture(scope="module")
def app_client():
    app = FastAPI()
    app.include_router(tools_router)
    return TestClient(app)


def _auth(user_id: str, role: str = "user") -> dict:
    token = create_access_token(user_id, user_id, role)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_tools_api_execute_and_diagram(app_client, monkeypatch):
    await dbmod.init_db()
    auto_register_default_providers()

    user_id = f"u-{uuid.uuid4()}"
    db = await dbmod.get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
            (user_id, user_id),
        )
        await db.commit()
    finally:
        await db.close()

    headers = _auth(user_id, role="user")

    # Mock dispatch_tool para não depender de APIs externas
    from backend.routers import tools as tools_mod

    async def fake_dispatch_tool(family, params, user_id, db):
        if family == "code_exec":
            return ToolResult(
                success=True,
                data={
                    "language": params.get("language"),
                    "stdout": "Hello Test\n",
                    "stderr": "",
                    "exit_code": 0,
                    "source": "MockPiston",
                },
                provider_id="piston",
                family="code_exec",
            )
        elif family == "diagrams":
            return ToolResult(
                success=True,
                data={
                    "diagram_type": params.get("type"),
                    "svg": "<svg>diagram</svg>",
                    "source": "MockKroki",
                },
                provider_id="kroki",
                family="diagrams",
            )
        return ToolResult(success=False, data={}, provider_id="unknown", family=family)

    monkeypatch.setattr(tools_mod, "dispatch_tool", fake_dispatch_tool)

    # 1. POST /api/tools/execute
    res_code = app_client.post(
        "/api/tools/execute",
        json={"language": "python", "code": "print('Hello Test')"},
        headers=headers,
    )
    assert res_code.status_code == 200
    data_code = res_code.json()
    assert data_code["success"] is True
    assert data_code["data"]["stdout"] == "Hello Test\n"

    # 2. POST /api/tools/diagram
    res_diag = app_client.post(
        "/api/tools/diagram",
        json={"type": "mermaid", "source_code": "graph TD; A-->B;"},
        headers=headers,
    )
    assert res_diag.status_code == 200
    data_diag = res_diag.json()
    assert data_diag["success"] is True
    assert "<svg>" in data_diag["data"]["svg"]


@pytest.mark.asyncio
async def test_admin_tools_endpoints_rbac(app_client):
    await dbmod.init_db()

    u_id = f"u-{uuid.uuid4()}"
    adm_id = f"admin-{uuid.uuid4()}"

    db = await dbmod.get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
            (u_id, u_id),
        )
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'admin')",
            (adm_id, adm_id),
        )
        await db.commit()
    finally:
        await db.close()

    user_headers = _auth(u_id, role="user")
    admin_headers = _auth(adm_id, role="admin")

    # 1. Usuário comum recebe 403 Forbidden
    res_forbidden = app_client.get("/api/admin/tools/status", headers=user_headers)
    assert res_forbidden.status_code == 403

    # 2. Admin recebe 200 OK com status e estatísticas
    res_status = app_client.get("/api/admin/tools/status", headers=admin_headers)
    assert res_status.status_code == 200
    data = res_status.json()
    assert "families" in data
    assert "global_stats" in data
    assert len(data["families"]) >= 10

    # 3. Toggle de provedor
    res_toggle = app_client.put(
        "/api/admin/tools/provider/open_meteo/toggle",
        json={"enabled": False},
        headers=admin_headers,
    )
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is False

    # Restaura provedor
    app_client.put(
        "/api/admin/tools/provider/open_meteo/toggle",
        json={"enabled": True},
        headers=admin_headers,
    )

    # 4. Leitura e atualização de configurações
    res_cfg = app_client.get("/api/admin/tools/config", headers=admin_headers)
    assert res_cfg.status_code == 200
    cfg = res_cfg.json()
    assert "global_enabled" in cfg
    assert "auto_detection" in cfg

    res_put_cfg = app_client.put(
        "/api/admin/tools/config",
        json={"rate_limit_per_user": 15},
        headers=admin_headers,
    )
    assert res_put_cfg.status_code == 200
    assert res_put_cfg.json()["success"] is True

    # 5. Catálogo de APIs públicas
    res_cat = app_client.get("/api/admin/tools/public-apis", headers=admin_headers)
    assert res_cat.status_code == 200
    cat_data = res_cat.json()
    assert "total" in cat_data
    assert "apis" in cat_data
