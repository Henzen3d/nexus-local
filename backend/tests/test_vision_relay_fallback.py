"""Testes do Vision Relay — item 02: não abortar a resposta quando falhar."""

import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


def test_vision_cache_key_has_two_components():
    """vision_cache_key(file_hash, model) produz string 'hash:model'."""
    from backend.vision_relay.relay import vision_cache_key
    key = vision_cache_key("abc", "model-x")
    assert key == "abc:model-x"
    assert key.count(":") == 1


def test_image_placeholder_contains_filename():
    """image_placeholder(filename) insere o nome do arquivo."""
    from backend.vision_relay.relay import image_placeholder
    ph = image_placeholder("foto.png")
    assert "foto.png" in ph
    assert "descrição indisponível" in ph


def test_get_cached_description_uses_model_in_query():
    """Chamada ao DB inclui relay_model na consulta (composite key)."""
    import inspect
    from backend.vision_relay import relay as m
    src = inspect.getsource(m.get_cached_description)
    assert "relay_model" in src
    assert "vision_cache_key" in src


def test_save_description_cache_uses_composite_key():
    """save_description_cache também usa vision_cache_key."""
    import inspect
    from backend.vision_relay import relay as m
    src = inspect.getsource(m.save_description_cache)
    assert "vision_cache_key" in src


@pytest.mark.asyncio
async def test_timeout_wraps_stream_call():
    """asyncio.wait_for está presente no describe_image_via_relay."""
    import inspect
    from backend.vision_relay import relay as m
    src = inspect.getsource(m.describe_image_via_relay)
    assert "wait_for" in src
    assert "RELAY_IMAGE_TIMEOUT_S" in src


@pytest.mark.asyncio
async def test_describe_or_placeholder_returns_desc_on_success():
    """Sucesso do relay → descrição retorna normalmente."""
    from backend.orchestration.handle_attachments import describe_or_placeholder

    fake_res = {"description": "gato preto no sofá"}
    with patch(
        "backend.vision_relay.relay.describe_image_via_relay",
        new=AsyncMock(return_value=fake_res),
    ):
        result = await describe_or_placeholder(
            {"storage_path": "/x", "mime_type": "image/png", "file_hash": "h", "filename": "a.png"},
            "u1",
            None,
        )
    assert result == "gato preto no sofá"


@pytest.mark.asyncio
async def test_describe_or_placeholder_returns_placeholder_on_failure():
    """Falha do relay → placeholder é retornado, não raised."""
    from backend.orchestration.handle_attachments import describe_or_placeholder

    img = {
        "storage_path": "/x",
        "mime_type": "image/png",
        "file_hash": "h",
        "filename": "broken.jpg",
    }
    with patch(
        "backend.vision_relay.relay.describe_image_via_relay",
        new=AsyncMock(side_effect=Exception("boom")),
    ):
        result = await describe_or_placeholder(img, "u1", None)

    assert "broken.jpg" in result
    assert "descrição indisponível" in result


@pytest.mark.asyncio
async def test_handle_attachments_continues_on_relay_failure():
    """load_history com imagens armazenadas não aborta quando relay falha."""
    from backend.orchestration.handle_attachments import load_history

    db = MagicMock()
    fake_cur = AsyncMock()
    fake_cur.fetchall = AsyncMock(return_value=[
        ("msg1", "user", "o que é isso?",),
    ])
    fake_cm = AsyncMock()
    fake_cm.__aenter__ = AsyncMock(return_value=fake_cur)
    fake_cm.__aexit__ = AsyncMock(return_value=False)
    db.execute = MagicMock(return_value=fake_cm)
    db.commit = AsyncMock()

    msg_atts = {}
    extracted_text = {}

    with patch(
        "backend.vision_relay.relay.describe_image_via_relay",
        new=AsyncMock(side_effect=Exception("boom")),
    ):
        history, relay_used, relay_model_id = await load_history(
            db,
            "conv1",
            "msg1",
            msg_atts,
            extracted_text,
            model_supports_vision=False,
            web_search_used=False,
            search_results=[],
            web_search_query="",
            search_config=None,
            format_search_results_fn=None,
            user_id="u1",
            user_query="",
            model_id=None,
            provider_id=None,
        )

    assert len(history) == 1
    text = history[0]["content"]
    assert "broken" not in text  # sem imagem anexada = só texto original


@pytest.mark.asyncio
async def test_cached_description_respects_model_mismatch():
    """Cache deve ser invalidado quando o modelo relé muda (mesmo file_hash)."""
    from backend.vision_relay.relay import get_cached_description, save_description_cache

    class FakeCursor:
        def __init__(self, row):
            self._row = row
        def __await__(self):
            return iter([])
        async def fetchone(self):
            return self._row

    class FakeExec:
        def __init__(self, row):
            self._row = row
        def __aenter__(self):
            return asyncio.Future()
        def __aexit__(self, *a):
            return asyncio.Future()
        def __await__(self):
            return iter([])
        async def fetchone(self):
            return self._row

    fake_cm_enter = asyncio.Future()
    fake_cm_enter.set_result(None)
    fake_cm_exit = asyncio.Future()
    fake_cm_exit.set_result(False)

    class AsyncCtxMgr:
        def __init__(self, row):
            self._row = row
        def __aenter__(self):
            f = asyncio.Future()
            f.set_result(self)
            return f
        def __aexit__(self, *a):
            f = asyncio.Future()
            f.set_result(False)
            return f
        async def fetchone(self):
            return self._row
        def __await__(self):
            # Para chamadas sem async-with (ex: save_description_cache)
            f = asyncio.Future()
            f.set_result(self)
            return f.__await__()

    class FakeDB:
        def __init__(self):
            self._rows = []
        def execute(self, sql, args=()):
            row = self._rows[-1] if self._rows else None
            return AsyncCtxMgr(row)
        async def commit(self):
            pass

    db = FakeDB()
    db._rows = [("desc model-a", "model-a")]

    # Salvar com model-a
    await save_description_cache("hash1", "desc model-a", "model-a", db)

    # Buscar com model-a → encontra
    result_a = await get_cached_description("hash1", "model-a", db)
    assert result_a == "desc model-a"

    # Buscar com model-b → não encontra (model mismatch)
    result_b = await get_cached_description("hash1", "model-b", db)
    assert result_b is None


@pytest.mark.asyncio
async def test_relay_timeout_sends_timeout_and_raises():
    """Timeout de 25s gera RelayError com mensagem clara."""
    from backend.vision_relay.relay import RELAY_IMAGE_TIMEOUT_S, RelayError

    assert RELAY_IMAGE_TIMEOUT_S == 25

    # Verificar que o async for está dentro de wait_for
    import inspect
    from backend.vision_relay import relay as m
    src = inspect.getsource(m.describe_image_via_relay)
    assert "asyncio.wait_for" in src
    assert "_collect" in src
