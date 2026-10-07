"""Texto falável e vozes Edge TTS em português."""

from __future__ import annotations

import re

VOICES = {
    "antonio": "pt-BR-AntonioNeural",
    "francisca": "pt-BR-FranciscaNeural",
    "thalita": "pt-BR-ThalitaNeural",
}

VOICE_LABELS = {
    "antonio": "Antonio",
    "francisca": "Francisca",
    "thalita": "Thalita",
}

DEFAULT_VOICE = "antonio"
MAX_SPEECH_CHARS = 20000
CHUNK_LIMIT = 1500


def resolve_voice(voice_id: str | None) -> str:
    key = (voice_id or "").strip().lower()
    return VOICES.get(key, VOICES[DEFAULT_VOICE])


def prepare_speech(raw: str) -> str:
    text = raw or ""
    text = re.sub(r"```[\s\S]*?```", " ", text)
    text = re.sub(r"`[^`]+`", " ", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_]{1,3}", "", text)
    text = re.sub(r"^\s*[-*]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_SPEECH_CHARS]


def chunk_for_speech(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    if not text:
        return []
    chunks: list[str] = []
    rest = text
    while rest:
        if len(rest) <= limit:
            chunks.append(rest)
            break
        window = rest[:limit]
        cut = window.rfind(". ")
        if cut >= limit // 3:
            cut += 2
        else:
            cut = window.rfind(" ")
            cut = cut + 1 if cut > 0 else limit
        chunks.append(rest[:cut])
        rest = rest[cut:]
    return chunks


async def synthesize(text: str, voice_id: str | None) -> bytes:
    import edge_tts

    spoken = prepare_speech(text)
    if not spoken:
        return b""
    voice = resolve_voice(voice_id)
    out = bytearray()
    for piece in chunk_for_speech(spoken):
        communicate = edge_tts.Communicate(piece, voice)
        async for event in communicate.stream():
            if event["type"] == "audio":
                data = event.get("data") or b""
                out.extend(data)
    return bytes(out)
