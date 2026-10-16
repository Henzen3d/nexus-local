"""backend/tools/families/translation/mymemory.py — Provedor de tradução MyMemory (Fallback gratuito sem API key).
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class MyMemoryProvider(ToolProvider):
    provider_id = "mymemory"
    family = "translation"
    base_url = "https://api.mymemory.translated.net/get"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        text = (params.get("text") or params.get("q") or "").strip().lower()
        src = (params.get("source") or params.get("from") or "en").strip().lower()
        tgt = (params.get("target") or params.get("to") or "pt").strip().lower()
        return self.make_deterministic_hash("translation:mymemory", {"t": text, "s": src, "tgt": tgt})

    async def execute(self, params: dict) -> ToolResult:
        text = (params.get("text") or params.get("q") or "").strip()
        if not text:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Parâmetro 'text' é obrigatório para tradução",
            )

        src = (params.get("source") or params.get("from") or "en").strip().lower()
        if src == "auto":
            src = "en"
        tgt = (params.get("target") or params.get("to") or "pt").strip().lower()

        # MyMemory limite seguro por chamada
        if len(text) > 1000:
            text = text[:1000]

        langpair = f"{src}|{tgt}"
        query_params = {
            "q": text,
            "langpair": langpair,
        }

        try:
            resp = await self._http_get(self.base_url, params=query_params, timeout=8.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="MyMemory rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"MyMemory HTTP {resp.status_code}",
                )

            body = resp.json()
            res_data = body.get("responseData", {})
            translated = res_data.get("translatedText")
            if not translated:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="MyMemory não retornou texto traduzido",
                )

            normalized = {
                "original": text,
                "translated": translated,
                "source_lang": src,
                "target_lang": tgt,
                "match": res_data.get("match"),
                "source": "MyMemory",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[MyMemoryProvider] Erro ao traduzir: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
