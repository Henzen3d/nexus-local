import asyncio
import httpx
from backend.database import get_db

async def get_web_search_config(db):
    async with db.execute(
        "SELECT enabled, search_provider, api_key, max_results, heuristic_enabled, heuristic_sensitivity FROM web_search_config WHERE id = 1"
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    return {
        "enabled": bool(row[0]),
        "search_provider": row[1],
        "api_key": row[2],
        "max_results": row[3],
        "heuristic_enabled": bool(row[4]),
        "heuristic_sensitivity": row[5]
    }

class BraveSearchProvider:
    async def search(self, query: str, api_key: str, max_results: int = 5) -> list[dict]:
        if not api_key:
            print("[Brave Search] Warning: API Key missing")
            return []
        url = "https://api.search.brave.com/res/v1/web/search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key
        }
        params = {
            "q": query,
            "count": max_results
        }
        async with httpx.AsyncClient() as client:
            try:
                res = await client.get(url, headers=headers, params=params, timeout=8.0)
                if res.status_code == 200:
                    data = res.json()
                    results = []
                    web_results = data.get("web", {}).get("results", [])
                    for r in web_results[:max_results]:
                        results.append({
                            "title": r.get("title", ""),
                            "snippet": r.get("description", ""),
                            "url": r.get("url", "")
                        })
                    return results
                else:
                    print(f"[Brave Search] API responded with status {res.status_code}: {res.text}")
            except Exception as e:
                print(f"[Brave Search Error] {e}")
        return []

class DuckDuckGoProvider:
    async def search(self, query: str, max_results: int = 5) -> list[dict]:
        try:
            def sync_search():
                from ddgs import DDGS
                with DDGS() as ddgs:
                    # Using text method which is stable
                    res_list = list(ddgs.text(query, max_results=max_results))
                    return res_list
            
            loop = asyncio.get_event_loop()
            raw_results = await loop.run_in_executor(None, sync_search)
            results = []
            for r in raw_results:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", "")
                })
            return results
        except Exception as e:
            print(f"[DuckDuckGo Search Error] {e}")
        return []

async def resolve_and_execute_search(query: str, db, config: dict = None) -> list[dict]:
    if not config:
        config = await get_web_search_config(db)
    if not config or not config["enabled"]:
        return []

    provider_name = config["search_provider"]
    max_results = config["max_results"]
    api_key = config["api_key"]

    if provider_name == "brave":
        provider = BraveSearchProvider()
        return await provider.search(query, api_key=api_key, max_results=max_results)
    elif provider_name == "duckduckgo":
        provider = DuckDuckGoProvider()
        return await provider.search(query, max_results=max_results)
    else:
        # Fallback to DuckDuckGo if unknown provider
        provider = DuckDuckGoProvider()
        return await provider.search(query, max_results=max_results)
