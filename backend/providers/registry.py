from .base import OpenAICompatProvider, GeminiProvider, CloudflareProvider, RateLimitError
import os
import aiosqlite

# Placeholders guardados no DB / UI que NÃO são chaves reais
KEY_SENTINELS = frozenset({"", "free", "env", "from_env", "none", "null", "your-api-key"})


def is_key_sentinel(api_key: str | None) -> bool:
    return (api_key or "").strip().lower() in KEY_SENTINELS


def resolve_env_api_key(provider_id: str, api_key: str | None) -> str:
    """Resolve sentinelas e fallbacks de env (ex.: ZenMux com api_key='free')."""
    key = (api_key or "").strip()
    if provider_id == "zenmux" and is_key_sentinel(key):
        key = (os.getenv("ZENMUX_API_KEY") or "").strip()
    if is_key_sentinel(key):
        return ""
    return key


async def is_admin_key_shared_for_provider(db: aiosqlite.Connection, provider_id: str) -> bool:
    """
    Fonte da verdade: providers.share_admin_key (por provedor).
    O toggle global em Configurações apenas aplica bulk (liga/desliga todos).
    Fallback: se a coluna ainda não existir em DBs antigos mid-migration, usa meta.
    """
    try:
        async with db.execute(
            "SELECT share_admin_key FROM providers WHERE id = ?",
            (provider_id,),
        ) as cur:
            row = await cur.fetchone()
            if row is not None:
                return int(row[0] or 0) == 1
    except Exception:
        pass
    try:
        async with db.execute(
            "SELECT value FROM meta WHERE key = 'share_admin_keys'"
        ) as meta_cur:
            meta_row = await meta_cur.fetchone()
            return bool(meta_row and meta_row[0] == "true")
    except Exception:
        return False


async def get_provider(provider_id: str, db: aiosqlite.Connection, user_id: str = None):
    async with db.execute(
        "SELECT base_url, api_key, enabled, is_free FROM providers WHERE id = ?",
        (provider_id,),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        raise ValueError(f"Provider '{provider_id}' not found.")
    base_url, _global_key, enabled, _is_free = row
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

    # Família: cada conta usa só a própria chave. Sem herança da chave global
    # nem da chave de outro usuário. ZenMux no .env fica só para o admin.
    if is_key_sentinel(api_key) and provider_id == "zenmux" and user_id:
        async with db.execute(
            "SELECT role FROM users WHERE id = ?",
            (user_id,),
        ) as role_cur:
            role_row = await role_cur.fetchone()
        if role_row and role_row[0] == "admin":
            api_key = resolve_env_api_key(provider_id, api_key)
    elif not is_key_sentinel(api_key):
        api_key = (api_key or "").strip()
    else:
        api_key = ""
        
    if not api_key and provider_id != "ollama":
        raise ValueError(
            f"Provedor '{provider_id}' necessita de Chave de API válida. "
            f"Configure em Configurações → Provedores"
            + (" ou defina ZENMUX_API_KEY no .env." if provider_id == "zenmux" else ".")
        )

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
