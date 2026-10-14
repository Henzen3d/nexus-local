import base64
import asyncio
import time
from collections import OrderedDict
from pathlib import Path
from backend.database import get_db, check_and_deactivate_model
from backend.providers.registry import get_provider, get_model_name
from backend.attachments.storage import get_absolute_path

class RelayError(Exception):
    pass

async def get_vision_relay_config(db):
    async with db.execute(
        "SELECT relay_provider_id, relay_model_id, relay_system_prompt, enabled, cache_descriptions FROM vision_relay_config WHERE id = 1"
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "relay_provider_id": row[0],
        "relay_model_id": row[1],
        "relay_system_prompt": row[2],
        "enabled": bool(row[3]),
        "cache_descriptions": bool(row[4])
    }

async def read_as_base64(relative_path: str) -> str:
    abs_path = get_absolute_path(relative_path)
    if not abs_path.exists():
        raise RelayError(f"Arquivo de imagem não encontrado no disco: {relative_path}")
    data = await asyncio.to_thread(abs_path.read_bytes)
    return base64.b64encode(data).decode("utf-8")

# JEV Fast: Cache L1 em RAM para descrições de imagens (0ms)
_VISION_L1_CACHE: OrderedDict[str, tuple[str, float]] = OrderedDict()
_VISION_L1_TTL = 3600.0  # 1 hora
_VISION_L1_MAX_ENTRIES = 512


async def get_cached_description(file_hash: str, db) -> str | None:
    key = file_hash
    now = time.monotonic()
    if key in _VISION_L1_CACHE:
        desc, ts = _VISION_L1_CACHE[key]
        if now - ts < _VISION_L1_TTL:
            _VISION_L1_CACHE.move_to_end(key)
            return desc
        del _VISION_L1_CACHE[key]

    async with db.execute(
        "SELECT description FROM vision_descriptions_cache WHERE file_hash = ?",
        (file_hash,)
    ) as cur:
        row = await cur.fetchone()
    if row and row[0]:
        _VISION_L1_CACHE[key] = (row[0], now)
        _VISION_L1_CACHE.move_to_end(key)
        while len(_VISION_L1_CACHE) > _VISION_L1_MAX_ENTRIES:
            _VISION_L1_CACHE.popitem(last=False)
        return row[0]
    return None


def invalidate_vision_l1_cache() -> None:
    """Invalida o cache em RAM de descrições de visão."""
    global _VISION_L1_CACHE
    _VISION_L1_CACHE.clear()


async def save_description_cache(file_hash: str, description: str, relay_model: str, db) -> None:
    key = file_hash
    _VISION_L1_CACHE[key] = (description, time.monotonic())
    _VISION_L1_CACHE.move_to_end(key)
    while len(_VISION_L1_CACHE) > _VISION_L1_MAX_ENTRIES:
        _VISION_L1_CACHE.popitem(last=False)
    await db.execute(
        """INSERT OR REPLACE INTO vision_descriptions_cache (file_hash, description, relay_model)
           VALUES (?, ?, ?)""",
        (file_hash, description, relay_model)
    )
    await db.commit()

async def describe_image_via_relay(
    image_rel_path: str | None,
    mime_type: str,
    file_hash: str,
    user_id: str,
    conversation_id: str | None = None,
    image_bytes: bytes | None = None,
) -> dict:
    db = await get_db()
    try:
        config = await get_vision_relay_config(db)
        if not config or not config["enabled"]:
            raise RelayError("Vision Relay desativado ou não configurado.")

        if not config["relay_provider_id"] or not config["relay_model_id"]:
            raise RelayError("Provedor ou modelo intérprete não configurado no Vision Relay.")

        # 1. Check cache
        if config["cache_descriptions"] and file_hash:
            cached = await get_cached_description(file_hash, db)
            if cached:
                return {"description": cached, "relay_model": config["relay_model_id"], "from_cache": True}

        # 2. Convert image to base64
        if image_bytes is not None:
            base64_data = base64.b64encode(image_bytes).decode("utf-8")
        elif image_rel_path:
            base64_data = await read_as_base64(image_rel_path)
        else:
            raise RelayError("Imagem ausente para o Vision Relay.")

        from backend.ranking.failover import resolve_model_with_failover
        resolved = await resolve_model_with_failover(config["relay_model_id"], db, user_id=user_id)
        final_model_id = resolved.model_id
        final_provider_id = resolved.provider_id

        # 3. Get provider instance
        provider = await get_provider(final_provider_id, db, user_id=user_id)
        model_name = await get_model_name(final_model_id, db)

        # Construct multimodal messages payload
        # Standard system prompt + user message with text + image base64
        messages = [
            {
                "role": "system",
                "content": config["relay_system_prompt"]
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Descreva esta imagem em detalhes objetivos, incluindo texto visível, objetos, pessoas, cores e contexto da cena."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_data}"}}
                ]
            }
        ]

        # 4. Stream chat to accumulate description
        chunks: list[str] = []
        try:
            async for chunk in provider.stream_chat(model=model_name, messages=messages, temperature=0.2):
                chunks.append(chunk)
        except Exception as e:
            error_msg = str(e)
            await check_and_deactivate_model(final_model_id, error_msg, db)
            raise RelayError(f"Erro ao chamar modelo intérprete '{final_model_id}': {error_msg}")

        description = "".join(chunks).strip()
        if not description:
            raise RelayError("O modelo intérprete retornou uma descrição vazia.")

        # 5. Save to cache
        if config["cache_descriptions"]:
            await save_description_cache(file_hash, description, final_model_id, db)

        return {"description": description, "relay_model": final_model_id, "from_cache": False}
    finally:
        await db.close()
