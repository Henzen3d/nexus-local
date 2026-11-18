import asyncio
import httpx
from backend.database import get_db

from backend.logging_config import get_logger
logger = get_logger(__name__)

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
    async def search(self, query: str, api_key: str, max_results: int = 5, timeout: float = 8.0) -> list[dict]:
        if not api_key:
            logger.warning("[Brave Search] Warning: API Key missing")
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
                res = await client.get(url, headers=headers, params=params, timeout=max(0.5, float(timeout)))
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
                    logger.info("[Brave Search] API responded with status %s", res.status_code)
            except Exception as e:
                logger.error("[Brave Search Error]", exc_info=e)
        return []

class DuckDuckGoProvider:
    async def search(self, query: str, max_results: int = 5, timeout: float = 8.0) -> list[dict]:
        try:
            def sync_search():
                from ddgs import DDGS

                with DDGS() as ddgs:
                    # Using text method which is stable
                    res_list = list(ddgs.text(query, max_results=max_results))
                    return res_list

            loop = asyncio.get_running_loop()
            raw_results = await asyncio.wait_for(
                loop.run_in_executor(None, sync_search),
                timeout=timeout,
            )
            results = []
            for r in raw_results:
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "url": r.get("href", "")
                })
            return results
        except asyncio.TimeoutError:
            logger.warning("[DuckDuckGo Search] Timeout após %.1fs", timeout)
            return []
        except Exception as e:
            err_msg = str(e).lower()
            if "no results" in err_msg:
                logger.info("[DuckDuckGo Search] Nenhum resultado encontrado")
                return []
            if "ratelimit" in err_msg or "rate limit" in err_msg or "202" in err_msg:
                logger.warning("[DuckDuckGo Search] Rate limit atingido pelo DuckDuckGo")
                return []
            logger.error("[DuckDuckGo Search Error] %s", type(e).__name__)
        return []

async def resolve_and_execute_search(
    query: str,
    db,
    config: dict = None,
    *,
    max_results_override: int | None = None,
    timeout: float | None = None,
) -> list[dict]:
    if not config:
        config = await get_web_search_config(db)
    if not config or not config["enabled"]:
        return []

    provider_name = config["search_provider"]
    max_results = int(config["max_results"] or 5)
    if max_results_override is not None:
        max_results = max(1, min(max_results, int(max_results_override)))
    api_key = config["api_key"]
    eff_timeout = max(0.5, float(timeout)) if timeout is not None else 8.0

    if provider_name == "brave":
        provider = BraveSearchProvider()
        return await provider.search(query, api_key=api_key, max_results=max_results, timeout=eff_timeout)
    elif provider_name == "duckduckgo":
        provider = DuckDuckGoProvider()
        return await provider.search(query, max_results=max_results, timeout=eff_timeout)
    else:
        # Fallback to DuckDuckGo if unknown provider
        provider = DuckDuckGoProvider()
        return await provider.search(query, max_results=max_results, timeout=eff_timeout)
