"""Guards: extrator não insiste em modelo 404; DuckDuckGo corta em 8s."""

from __future__ import annotations

import asyncio
import os
import sys
import time
import types
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-runtime-guards")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_missing_model_error_is_recognized():
    from backend.memory import is_missing_model_error

    err = RuntimeError(
        'Provider error 404: {"error":{"message":"The model `qwen/qwen3-32b` does not exist",'
        '"code":"model_not_found"}}'
    )
    assert is_missing_model_error(err)
    assert not is_missing_model_error(RuntimeError("timeout talking to provider"))


async def test_dead_model_is_remembered_until_cleared():
    import tempfile
    from backend import database as dbmod
    from backend.memory import (
        clear_dead_extractor_models,
        extractor_model_is_dead,
        mark_extractor_model_dead,
    )

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    dbmod.DB_PATH = Path(path)
    await dbmod.init_db()
    db = await dbmod.get_db()
    try:
        assert not await extractor_model_is_dead(db, "qwen/qwen3-32b")
        await mark_extractor_model_dead(db, "qwen/qwen3-32b")
        assert await extractor_model_is_dead(db, "qwen/qwen3-32b")
        assert not await extractor_model_is_dead(db, "outro-modelo")
        await clear_dead_extractor_models(db)
        assert not await extractor_model_is_dead(db, "qwen/qwen3-32b")
    finally:
        await db.close()


async def test_duckduckgo_search_times_out():
    fake = types.ModuleType("ddgs")

    class DDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def text(self, *args, **kwargs):
            time.sleep(5)
            return [{"title": "tarde", "body": "demorou", "href": "https://example.com"}]

    fake.DDGS = DDGS
    sys.modules["ddgs"] = fake

    from backend.web_search.providers import DuckDuckGoProvider

    started = time.monotonic()
    result = await DuckDuckGoProvider().search("teste", max_results=1, timeout=0.3)
    elapsed = time.monotonic() - started
    assert result == [], result
    assert elapsed < 2.0, elapsed


def main():
    tests = [
        test_missing_model_error_is_recognized,
        test_dead_model_is_remembered_until_cleared,
        test_duckduckgo_search_times_out,
    ]
    failed = 0
    for test in tests:
        try:
            if asyncio.iscoroutinefunction(test):
                run(test())
            else:
                test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
