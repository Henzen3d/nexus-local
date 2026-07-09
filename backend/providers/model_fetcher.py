import httpx
from typing import List, Dict, Any, Optional

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
    async def fetch_groq(api_key: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = await client.get("https://api.groq.com/openai/v1/models", headers=headers)
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            data = response.json()
            results = []
            for m in data.get("data", []):
                name = m.get("id")
                ctx = m.get("context_window")
                if name and ctx:
                    results.append({"model_name": name, "context_length": parse_context_length(ctx)})
            return results

    @staticmethod
    async def fetch_openrouter(api_key: str) -> List[Dict[str, Any]]:
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
            results = []
            for m in data.get("data", []):
                name = m.get("id")
                ctx = m.get("context_length")
                if name and ctx and name.endswith(":free"):
                    results.append({"model_name": name, "context_length": int(ctx)})
            return results

    @staticmethod
    async def fetch_gemini(api_key: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key}
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
                    results.append({"model_name": name, "context_length": int(ctx)})
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
                    results.append({"model_name": name, "context_length": parse_context_length(ctx)})
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
                    results.append({"model_name": name, "context_length": parse_context_length(ctx)})
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
                            results.append({"model_name": name, "context_length": 8192})
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
                                results.append({"model_name": name, "context_length": int(ctx) if ctx else 8192})
                        return results
                except Exception:
                    continue
            
            raise Exception(f"Nao foi possivel conectar ao Ollama em {base_url}. Verifique se o Ollama esta rodando localmente ou as credenciais.")
