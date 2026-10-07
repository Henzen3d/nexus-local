"""Texto falável e vozes Edge TTS em português."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
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
CHUNK_LIMIT = 3500

# Cache LRU em memória: hash(voice + text) -> bytes (máx 150 itens)
_AUDIO_CACHE: OrderedDict[str, bytes] = OrderedDict()
_MAX_CACHE_ITEMS = 150


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
    text = re.sub(r"^\s*>\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
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


def _cache_key(text: str, voice: str) -> str:
    return hashlib.sha256(f"{voice}:{text}".encode("utf-8")).hexdigest()


async def _synthesize_chunk(piece: str, voice: str) -> bytes:
    import edge_tts

    communicate = edge_tts.Communicate(piece, voice, rate="+10%")
    out = bytearray()
    async for event in communicate.stream():
        if event["type"] == "audio":
            data = event.get("data") or b""
            out.extend(data)
    return bytes(out)


async def synthesize(text: str, voice_id: str | None) -> bytes:
    spoken = prepare_speech(text)
    if not spoken:
        return b""
    voice = resolve_voice(voice_id)

    key = _cache_key(spoken, voice)
    if key in _AUDIO_CACHE:
        _AUDIO_CACHE.move_to_end(key)
        return _AUDIO_CACHE[key]

    chunks = chunk_for_speech(spoken, limit=CHUNK_LIMIT)
    if not chunks:
        return b""

    if len(chunks) == 1:
        audio_bytes = await _synthesize_chunk(chunks[0], voice)
    else:
        # Sintetiza múltiplos pedaços em paralelo acelerando a resposta
        pieces = await asyncio.gather(*[_synthesize_chunk(c, voice) for c in chunks])
        audio_bytes = b"".join(pieces)

    if audio_bytes:
        _AUDIO_CACHE[key] = audio_bytes
        if len(_AUDIO_CACHE) > _MAX_CACHE_ITEMS:
            _AUDIO_CACHE.popitem(last=False)

    return audio_bytes

