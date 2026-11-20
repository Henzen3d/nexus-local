import httpx
import pytest
from fastapi import HTTPException

from backend import database
from backend.models import ModelToggle
from backend.routers.admin import (
    list_all_models,
    list_providers,
    sync_provider,
    toggle_all_provider_models,
)


@pytest.mark.asyncio
async def test_openrouter_sync_imports_mixed_chat_catalog_without_enabling_paid_models(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "openrouter-catalog.db")
    await database.init_db()
    user = {"id": "catalog-test", "role": "admin"}
    db = await database.get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, '', 'admin')",
            (user["id"], user["id"]),
        )
        await db.execute(
            "INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, 'openrouter', 'catalog-test-key')",
            (user["id"],),
        )
        await db.execute("UPDATE providers SET enabled = 1 WHERE id = 'openrouter'")
        await db.execute(
            "INSERT INTO free_model_registry (id, source, provider_name, model_id_raw) "
            "VALUES ('test-entry', 'manual', 'OpenRouter', 'test/vendor-chat')"
        )
        await db.commit()
    finally:
        await db.close()

    chat_endpoint = "/api/v1/chat/completions"
    free_price = {"prompt": "0", "completion": "0.0"}
    paid_price = {"prompt": "0.000000001", "completion": "0.000000002"}
    catalog = [
        {"id": "test/vendor-chat", "name": "Test: Vendor Chat", "pricing": paid_price, "context_length": 65536},
        {"id": "test/vendor-chat:free", "name": "Test: Vendor Chat (free)", "context_length": 32768},
        {
            "id": "test/preview-chat",
            "name": "Test: Preview Chat",
            "pricing": free_price,
            "top_provider": {"context_length": 131072},
            "architecture": {"input_modalities": ["text", "image"]},
            "endpoints": [chat_endpoint],
        },
        {"id": "openrouter/free", "context_length": 200000, "endpoints": [chat_endpoint]},
        {"id": "test/chat-with-fee", "pricing": {**free_price, "request": "0.1"}},
        {"id": "test/chat-without-pricing", "context_length": 16384},
        {"id": "test/vendor-chat:batch", "endpoints": ["/api/v1/batches"], "pricing": paid_price},
    ]
    response_status = 200

    def respond(request):
        assert str(request.url) == "https://openrouter.ai/api/v1/models"
        assert request.headers["Authorization"] == "Bearer catalog-test-key"
        return httpx.Response(response_status, json={"data": catalog})

    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs))

    async def openrouter_listing():
        providers = await list_providers(current_user=user)
        return {m["id"]: m for p in providers if p["id"] == "openrouter" for m in p["models"]}

    result = await sync_provider("openrouter", current_user=user)
    assert result["ok"] is True
    assert result["updated"] == 6

    models = await openrouter_listing()
    expected_paid = ("test/vendor-chat", "test/chat-with-fee", "test/chat-without-pricing")
    for model_id in expected_paid:
        model = models[f"openrouter/{model_id}"]
        assert model["enabled"] is False
        assert model["confirmed_free"] is False
    assert "openrouter/test/vendor-chat:batch" not in models
    assert models["openrouter/test/vendor-chat"]["display_name"] == "Test: Vendor Chat"
    preview = models["openrouter/test/preview-chat"]
    assert preview["enabled"] is True
    assert preview["confirmed_free"] is True
    assert preview["context_length"] == 131072
    assert preview["supports_vision"] is True

    chat_models = {m["id"] for m in await list_all_models(current_user=user) if m["provider_id"] == "openrouter"}
    assert chat_models == {"openrouter/test/vendor-chat:free", "openrouter/test/preview-chat", "openrouter/openrouter/free"}
    await toggle_all_provider_models("openrouter", ModelToggle(enabled=True), current_user=user)
    assert not (await openrouter_listing())["openrouter/test/vendor-chat"]["enabled"]

    # A resync is idempotent. It also withdraws free opt-ins when the preview becomes paid.
    assert (await sync_provider("openrouter", current_user=user))["updated"] == 0
    catalog[2]["pricing"] = paid_price
    assert (await sync_provider("openrouter", current_user=user))["updated"] == 1
    preview = (await openrouter_listing())["openrouter/test/preview-chat"]
    assert preview["enabled"] is False
    assert preview["confirmed_free"] is False

    response_status = 503
    with pytest.raises(HTTPException) as exc:
        await sync_provider("openrouter", current_user=user)
    assert exc.value.status_code == 502
    assert (await openrouter_listing())["openrouter/test/vendor-chat:free"]["enabled"] is True
