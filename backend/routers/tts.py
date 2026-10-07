"""Leitura das respostas com Edge TTS. A escolha de voz fica na conta."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.database import get_db
from backend import tts as ttsmod

router = APIRouter(prefix="/api/tts", tags=["tts"])


def _voice_key(user_id: str) -> str:
    return f"tts_voice:{user_id}"


def _auto_key(user_id: str) -> str:
    return f"tts_auto:{user_id}"


async def _meta_get(db, key: str) -> str | None:
    async with db.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None


async def _meta_set(db, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


class SpeakIn(BaseModel):
    text: str
    voice: str | None = None


class SettingsIn(BaseModel):
    voice: str | None = None
    auto: bool | None = None


def _voices():
    return [
        {"id": key, "name": ttsmod.VOICE_LABELS[key], "edge": ttsmod.VOICES[key]}
        for key in ttsmod.VOICES
    ]


async def _load(user_id: str) -> dict:
    db = await get_db()
    try:
        voice = await _meta_get(db, _voice_key(user_id)) or ttsmod.DEFAULT_VOICE
        if voice not in ttsmod.VOICES:
            voice = ttsmod.DEFAULT_VOICE
        auto = (await _meta_get(db, _auto_key(user_id))) == "1"
        return {"voice": voice, "auto": auto, "voices": _voices()}
    finally:
        await db.close()


@router.get("/settings")
async def get_settings(user: dict = Depends(get_current_user)):
    return await _load(user["id"])


@router.put("/settings")
async def put_settings(body: SettingsIn, user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        if body.voice is not None:
            voice = body.voice.strip().lower()
            if voice not in ttsmod.VOICES:
                raise HTTPException(status_code=400, detail="Voz não disponível.")
            await _meta_set(db, _voice_key(user["id"]), voice)
        if body.auto is not None:
            await _meta_set(db, _auto_key(user["id"]), "1" if body.auto else "0")
        await db.commit()
    finally:
        await db.close()
    return await _load(user["id"])


@router.post("")
async def speak(body: SpeakIn, user: dict = Depends(get_current_user)):
    if not ttsmod.prepare_speech(body.text):
        raise HTTPException(status_code=400, detail="Nada para ler.")
    voice = body.voice
    if not voice:
        saved = await _load(user["id"])
        voice = saved["voice"]
    try:
        audio = await ttsmod.synthesize(body.text, voice)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Não foi possível gerar o áudio.") from exc
    if not audio:
        raise HTTPException(status_code=400, detail="Nada para ler.")
    return Response(content=audio, media_type="audio/mpeg")
