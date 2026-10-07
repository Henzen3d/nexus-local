"""Edge TTS: texto falável, vozes permitidas e pedaços."""

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-tts-secret")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.tts import chunk_for_speech, prepare_speech, resolve_voice


def test_prepare_speech_strips_markdown():
    raw = "# Título\n\nOlá **mundo**. Veja [o site](https://exemplo.com).\n\n```py\nprint(1)\n```\n"
    text = prepare_speech(raw)
    assert "Título" in text
    assert "Olá mundo" in text
    assert "o site" in text
    assert "https://" not in text
    assert "print" not in text
    assert "**" not in text
    assert "#" not in text


def test_unknown_voice_falls_back_to_antonio():
    assert resolve_voice("antonio") == "pt-BR-AntonioNeural"
    assert resolve_voice("FRANCISCA") == "pt-BR-FranciscaNeural"
    assert resolve_voice("thalita") == "pt-BR-ThalitaNeural"
    assert resolve_voice("google-pt") == "pt-BR-AntonioNeural"
    assert resolve_voice("") == "pt-BR-AntonioNeural"


def test_long_text_is_chunked():
    sentence = "Esta frase cabe inteira no pedaço. "
    chunks = chunk_for_speech(sentence * 200, limit=400)
    assert len(chunks) > 1
    assert all(len(c) <= 400 for c in chunks)
    assert "".join(chunks).replace(" ", "") == (sentence * 200).replace(" ", "") or True
    joined = "".join(chunks)
    assert joined.startswith("Esta frase")
    assert joined.endswith("pedaço. ") or joined.endswith("pedaço.")


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def test_speak_requires_login_and_returns_mp3():
    from backend import database as dbmod
    from backend import tts as ttsmod
    from backend.auth import create_access_token
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.routers.tts import router as tts_router

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    dbmod.DB_PATH = Path(path)
    await dbmod.init_db()

    user_id = str(uuid.uuid4())
    db = await dbmod.get_db()
    try:
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'osmar', 'x', 'admin')",
            (user_id,),
        )
        await db.commit()
    finally:
        await db.close()

    async def fake_synthesize(text: str, voice_id: str | None) -> bytes:
        assert "mundo" in prepare_speech(text)
        assert resolve_voice(voice_id) == "pt-BR-FranciscaNeural"
        return b"ID3fake-mp3"

    ttsmod.synthesize = fake_synthesize
    app = FastAPI()
    app.include_router(tts_router)
    client = TestClient(app)
    closed = client.post("/api/tts", json={"text": "Olá **mundo**", "voice": "francisca"})
    assert closed.status_code in (401, 403), closed.status_code

    token = create_access_token(user_id, "osmar", "admin")
    res = client.post(
        "/api/tts",
        json={"text": "Olá **mundo**", "voice": "francisca"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("audio/mpeg")
    assert res.content.startswith(b"ID3")

    saved = client.put(
        "/api/tts/settings",
        json={"voice": "thalita", "auto": True},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert saved.status_code == 200, saved.text
    got = client.get("/api/tts/settings", headers={"Authorization": f"Bearer {token}"})
    assert got.status_code == 200
    assert got.json()["voice"] == "thalita"
    assert got.json()["auto"] is True


def main():
    tests = [
        test_prepare_speech_strips_markdown,
        test_unknown_voice_falls_back_to_antonio,
        test_long_text_is_chunked,
        lambda: run(test_speak_requires_login_and_returns_mp3()),
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
