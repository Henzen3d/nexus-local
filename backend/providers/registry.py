from .base import OpenAICompatProvider, GeminiProvider, CloudflareProvider, RateLimitError
import aiosqlite


async def get_provider(provider_id: str, db: aiosqlite.Connection, user_id: str = None):
    async with db.execute(
        "SELECT base_url, api_key, enabled, is_free FROM providers WHERE id = ?",
        (provider_id,),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise ValueError(f"Provider '{provider_id}' not found.")
    base_url, global_key, enabled, is_free = row
    if not enabled:
        raise ValueError(f"Provider '{provider_id}' is disabled.")
        
    api_key = None
    if user_id:
        async with db.execute(
            "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = ?",
            (user_id, provider_id),
        ) as key_cur:
            key_row = await key_cur.fetchone()
            if key_row:
                api_key = key_row[0]
                
    if not api_key:
        api_key = global_key
        
    if not api_key and provider_id != "ollama":
        raise ValueError(f"Provedor '{provider_id}' necessita de Chave de API pessoal configurada.")

    if provider_id == "ollama":
        clean_url = base_url.rstrip("/")
        if not clean_url.endswith("/v1"):
            base_url = f"{clean_url}/v1"
        return OpenAICompatProvider(api_key=api_key or "", base_url=base_url)

    if provider_id == "gemini":
        return GeminiProvider(api_key=api_key or "", base_url=base_url)
    if provider_id == "cloudflare":
        return CloudflareProvider(api_key=api_key or "", base_url=base_url)
    return OpenAICompatProvider(api_key=api_key or "", base_url=base_url)


async def get_model_name(model_id: str, db: aiosqlite.Connection) -> str:
    async with db.execute(
        "SELECT name FROM models WHERE id = ?", (model_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise ValueError(f"Model '{model_id}' not found.")
    return row[0]
