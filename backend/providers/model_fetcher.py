from decimal import Decimal, InvalidOperation

import httpx
from typing import List, Dict, Any, Optional

def vision_from_architecture(architecture) -> bool:
    """OpenRouter: architecture.input_modalities. Sem o campo, False."""
    if not isinstance(architecture, dict):
        return False
    mods = architecture.get("input_modalities")
    if not mods:
        return False
    if isinstance(mods, str):
        mods = [mods]
    return any(str(m).lower() == "image" for m in mods)


def _openrouter_model_is_free(model_id: str, pricing: Any) -> bool:
    if model_id.endswith(":free") or model_id == "openrouter/free":
        return True
    if not isinstance(pricing, dict) or not {"prompt", "completion"} <= pricing.keys():
        return False
    try:
        return all(Decimal(str(price)).is_zero() for price in pricing.values())
    except InvalidOperation:
        return False


def parse_context_length(ctx) -> int:
    if not ctx:
        return 8192
    if isinstance(ctx, dict):
        val = ctx.get("tokens") or ctx.get("value")
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                pass
        return 8192
    try:
        return int(ctx)
    except (ValueError, TypeError):
        return 8192

class ModelFetcher:
    @staticmethod
    async def fetch_groq(api_key: str, *, stats_out: dict | None = None) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.get("https://api.groq.com/openai/v1/models", headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            raw_list = data.get("data", [])
            results = []
            excluded_inactive = 0
            excluded_non_chat = 0
            excluded_missing_ctx = 0
            non_chat_prefixes = ("whisper", "canopylabs/orpheus", "meta-llama/llama-prompt-guard")
            for m in raw_list:
                name = m.get("id")
                active = m.get("active", True)
                if not active:
                    excluded_inactive += 1
                    continue
                if name and any(name.startswith(p) for p in non_chat_prefixes):
                    excluded_non_chat += 1
                    continue
                ctx = m.get("context_window")
                if name and ctx:
                    results.append({"model_name": name, "context_length": parse_context_length(ctx), "supports_vision": False})
                else:
                    excluded_missing_ctx += 1
            if stats_out is not None:
                stats_out.update({
                    "remote_total": len(raw_list),
                    "chat_eligible_count": len(results),
                    "excluded_inactive": excluded_inactive,
                    "excluded_non_chat": excluded_non_chat,
                    "excluded_missing_ctx": excluded_missing_ctx,
                })
            return results

    @staticmethod
    async def fetch_openrouter(api_key: str, *, stats_out: dict | None = None) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://nexuslocal.app",
                "X-Title": "NexusLocal"
            }
            response = await client.get("https://openrouter.ai/api/v1/models", headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            raw_list = data.get("data", [])
            results = []
            excluded_non_chat = 0
            free_count = 0
            paid_count = 0
            for m in raw_list:
                name = m.get("id")
                if not name:
                    continue
                endpoints = m.get("endpoints")
                if endpoints is not None and "/api/v1/chat/completions" not in endpoints:
                    excluded_non_chat += 1
                    continue
                top_provider = m.get("top_provider") or {}
                context = m.get("context_length") or top_provider.get("context_length")
                context_length = parse_context_length(context)
                confirmed_free = _openrouter_model_is_free(name, m.get("pricing"))
                if confirmed_free:
                    free_count += 1
                else:
                    paid_count += 1
                results.append({
                    "model_name": name,
                    "display_name": m.get("name"),
                    "context_length": context_length if context_length > 0 else 8192,
                    "supports_vision": vision_from_architecture(m.get("architecture")),
                    "confirmed_free": confirmed_free,
                })
            if stats_out is not None:
                stats_out.update({
                    "remote_total": len(raw_list),
                    "chat_eligible_count": len(results),
                    "excluded_non_chat": excluded_non_chat,
                    "free_count": free_count,
                    "paid_count": paid_count,
                })
            if not results:
                raise ValueError("O OpenRouter retornou um catálogo de chat vazio.")
            return results

    @staticmethod
    async def fetch_gemini(api_key: str) -> List[Dict[str, Any]]:
        headers = {}
        params = {"key": api_key}
        if api_key.startswith("AQ."):
            headers["x-goog-api-key"] = api_key
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers=headers,
                params=params
            )
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            results = []
            for m in data.get("models", []):
                if "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                name = m.get("name", "").replace("models/", "")
                ctx = m.get("inputTokenLimit")
                if name and ctx:
                    results.append({"model_name": name, "context_length": int(ctx), "supports_vision": False})
            return results

    @staticmethod
    async def fetch_cerebras(api_key: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.get("https://api.cerebras.ai/v1/models", headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            results = []
            for m in data.get("data", []):
                name = m.get("id")
                ctx = m.get("context_length")
                if name:
                    results.append({"model_name": name, "context_length": parse_context_length(ctx), "supports_vision": False})
            return results

    @staticmethod
    async def fetch_sambanova(api_key: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.get("https://api.sambanova.ai/v1/models", headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            results = []
            for m in data.get("data", []):
                name = m.get("id")
                ctx = m.get("context_length")
                if name:
                    results.append({"model_name": name, "context_length": parse_context_length(ctx)})
            return results
 
    @staticmethod
    async def fetch_cloudflare(account_id: str, api_key: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/models/search"
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            results = []
            for m in data.get("result", []):
                name = m.get("name")
                if not name:
                    continue
                ctx = 8192
                for prop in m.get("properties", []):
                    if prop.get("property_id") == "max_total_tokens":
                        try:
                            ctx = int(prop.get("value", 8192))
                        except ValueError:
                            pass
                        break
                results.append({"model_name": name, "context_length": ctx})
            return results
 
    @staticmethod
    async def fetch_generic(base_url: str, api_key: str) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        if "openrouter" in base_url:
            headers["HTTP-Referer"] = "https://nexuslocal.app"
            headers["X-Title"] = "NexusLocal"
        async with httpx.AsyncClient(timeout=15.0) as client:
            url = f"{base_url.rstrip('/')}/models"
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            results = []
            for m in data.get("data", []):
                name = m.get("id")
                ctx = m.get("context_length") or m.get("context_window")
                if name:
                    results.append({"model_name": name, "context_length": parse_context_length(ctx), "supports_vision": False})
            return results

    @staticmethod
    async def fetch_ollama(base_url: str, api_key: str = None) -> List[Dict[str, Any]]:
        url_clean = base_url.rstrip('/')
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            # 1. Try native Ollama /api/tags
            native_url = url_clean
            if native_url.endswith('/v1'):
                native_url = native_url[:-3].rstrip('/')
            
            try:
                response = await client.get(f"{native_url}/api/tags", headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    for m in data.get("models", []):
                        name = m.get("name")
                        if name:
                            # Ollama models don't expose context length via /api/tags easily.
                            # We default to 8192.
                            results.append({"model_name": name, "context_length": 8192, "supports_vision": False})
                    return results
            except Exception:
                pass
            
            # 2. Try OpenAI compatible endpoint at the given base_url
            for path in ["/models", "/v1/models"]:
                try:
                    if path == "/models":
                        url = f"{url_clean}/models"
                    else:
                        url = f"{native_url}/v1/models"
                    
                    response = await client.get(url, headers=headers)
                    if response.status_code == 200:
                        data = response.json()
                        results = []
                        for m in data.get("data", []):
                            name = m.get("id")
                            ctx = m.get("context_length") or m.get("context_window")
                            if name:
                                results.append({"model_name": name, "context_length": int(ctx) if ctx else 8192, "supports_vision": False})
                        return results
                except Exception:
                    continue
            
            raise Exception(f"Nao foi possivel conectar ao Ollama em {base_url}. Verifique se o Ollama esta rodando localmente ou as credenciais.")
