"""backend/tools/sync_public_apis.py — Sincronizador automático com o repositório public-apis/public-apis.
"""
from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import aiosqlite
import httpx

from backend.logging_config import get_logger

logger = get_logger(__name__)

PUBLIC_APIS_RAW_URL = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"

RELEVANCE_KEYWORDS = {
    "high": [
        "weather", "climate", "forecast", "currency", "exchange", "forex", "finance", "stock",
        "geocoding", "geocode", "maps", "location", "news", "headlines", "translate",
        "translation", "wikipedia", "encyclopedia", "code", "compiler", "diagram", "chart",
        "cep", "cnpj", "brasil",
    ],
    "medium": [
        "book", "library", "author", "isbn", "animal", "dog", "cat", "fact", "trivia",
        "quote", "advice", "joke", "calendar", "holiday", "math", "calculator", "dictionary",
        "search", "email", "security", "ip", "dns",
    ],
    "low": [
        "anime", "manga", "game", "gaming", "pokemon", "beer", "cocktail", "food", "recipe",
        "music", "spotify", "video", "movie", "film", "comic", "meme",
    ],
}


def classify_relevance(api_name: str, description: str, category: str) -> str:
    """Classifica a relevância de uma API pública para o ecossistema NexusLocal."""
    text = f"{api_name} {description} {category}".lower()

    for kw in RELEVANCE_KEYWORDS["high"]:
        if re.search(rf"\b{re.escape(kw)}\b", text):
            return "high"

    for kw in RELEVANCE_KEYWORDS["medium"]:
        if re.search(rf"\b{re.escape(kw)}\b", text):
            return "medium"

    for kw in RELEVANCE_KEYWORDS["low"]:
        if re.search(rf"\b{re.escape(kw)}\b", text):
            return "low"

    return "unknown"


def parse_public_apis_readme(content: str) -> list[dict]:
    """Parseia as tabelas markdown do README.md do public-apis/public-apis."""
    apis: list[dict] = []
    current_category = "General"

    lines = content.splitlines()
    for line in lines:
        line_s = line.strip()
        # Detecta seções de categoria: ### Animals, ### Weather, etc.
        if line_s.startswith("### "):
            current_category = line_s[4:].strip()
            continue

        # Linhas de tabela markdown: | API | Description | Auth | HTTPS | CORS |
        if line_s.startswith("|") and line_s.endswith("|"):
            parts = [p.strip() for p in line_s.split("|")[1:-1]]
            if len(parts) >= 5:
                # Ignora cabeçalhos
                if parts[0].lower() in ("api", "---", ":---", "---:"):
                    continue
                if set(parts[0]) <= {"-", ":"}:
                    continue

                raw_api = parts[0]
                # Extrai nome e URL do formato markdown [Nome](URL)
                link_match = re.search(r"\[([^\]]+)\]\(([^)]+)\)", raw_api)
                if link_match:
                    api_name = link_match.group(1).strip()
                    url = link_match.group(2).strip()
                else:
                    api_name = raw_api.strip()
                    url = parts[4] if parts[4].startswith("http") else ""

                desc = parts[1] if len(parts) > 1 else ""
                auth = parts[2] if len(parts) > 2 else ""
                if auth == "`No`" or auth.lower() == "no":
                    auth = ""
                elif "`apiKey`" in auth or "apikey" in auth.lower():
                    auth = "apiKey"
                elif "`OAuth`" in auth or "oauth" in auth.lower():
                    auth = "OAuth"

                https_val = 1 if (len(parts) > 3 and "yes" in parts[3].lower()) else 0
                cors_val = parts[4].replace("`", "").strip() if len(parts) > 4 else "unknown"

                if api_name and url:
                    api_id = hashlib.sha256(f"{api_name}:{url}".encode("utf-8")).hexdigest()[:16]
                    rel = classify_relevance(api_name, desc, current_category)

                    apis.append({
                        "id": api_id,
                        "api_name": api_name,
                        "description": desc,
                        "auth": auth,
                        "https": https_val,
                        "cors": cors_val,
                        "category": current_category,
                        "url": url,
                        "relevance": rel,
                    })

    return apis


async def sync_public_apis(db: aiosqlite.Connection) -> dict:
    """Faz fetch do repositório público, parseia e atualiza a tabela public_apis_registry."""
    logger.info("[PublicApisSync] Iniciando sincronização com %s...", PUBLIC_APIS_RAW_URL)

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.get(PUBLIC_APIS_RAW_URL)
            if resp.status_code != 200:
                logger.error("[PublicApisSync] Falha ao baixar README: HTTP %d", resp.status_code)
                return {"error": f"HTTP {resp.status_code}", "synced": 0}

            content = resp.text

        parsed_apis = parse_public_apis_readme(content)
        if not parsed_apis:
            logger.warning("[PublicApisSync] Nenhuma API extraída do README")
            return {"synced": 0, "total": 0}

        # Busca URLs existentes em tool_providers para marcar como 'integrated'
        async with db.execute("SELECT base_url FROM tool_providers") as cur:
            p_rows = await cur.fetchall()
            integrated_urls = [r[0].lower() for r in p_rows]

        total_inserted = 0
        high_rel = 0
        medium_rel = 0
        low_rel = 0

        for api in parsed_apis:
            # Verifica se já está integrada
            is_integrated = 1 if any(p_url in api["url"].lower() or api["url"].lower() in p_url for p_url in integrated_urls) else 0

            if api["relevance"] == "high":
                high_rel += 1
            elif api["relevance"] == "medium":
                medium_rel += 1
            elif api["relevance"] == "low":
                low_rel += 1

            await db.execute(
                """
                INSERT INTO public_apis_registry
                (id, api_name, description, auth, https, cors, category, url, relevance, integrated, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    description = excluded.description,
                    auth = excluded.auth,
                    https = excluded.https,
                    cors = excluded.cors,
                    category = excluded.category,
                    relevance = excluded.relevance,
                    integrated = excluded.integrated
                """,
                (
                    api["id"],
                    api["api_name"],
                    api["description"],
                    api["auth"],
                    api["https"],
                    api["cors"],
                    api["category"],
                    api["url"],
                    api["relevance"],
                    is_integrated,
                )
            )
            total_inserted += 1

        # Atualiza timestamp em meta
        now_iso = datetime.now(timezone.utc).isoformat()
        await db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('public_apis_last_sync', ?)", (now_iso,))
        await db.commit()

        logger.info(
            "[PublicApisSync] Sincronização concluída: %d APIs registradas (Alta: %d, Média: %d, Baixa: %d)",
            total_inserted, high_rel, medium_rel, low_rel
        )

        return {
            "success": True,
            "last_synced": now_iso,
            "total_apis": total_inserted,
            "high_relevance": high_rel,
            "medium_relevance": medium_rel,
            "low_relevance": low_rel,
        }

    except Exception as e:
        logger.error("[PublicApisSync] Erro durante sincronização: %s", e)
        return {"success": False, "error": str(e)}
