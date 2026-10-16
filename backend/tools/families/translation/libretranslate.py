"""backend/tools/families/translation/libretranslate.py — Provedor de tradução LibreTranslate (Primário).
"""
from __future__ import annotations

import os
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class LibreTranslateProvider(ToolProvider):
    provider_id = "libretranslate"
    family = "translation"
    base_url = "https://libretranslate.com"
    fallback_order = 1
    requires_key = False
    env_key_name = "LIBRETRANSLATE_API_KEY"

    def cache_key(self, params: dict) -> str:
        text = (params.get("text") or params.get("q") or "").strip().lower()
        src = (params.get("source") or params.get("from") or "auto").strip().lower()
        tgt = (params.get("target") or params.get("to") or "pt").strip().lower()
        return self.make_deterministic_hash("translation:libre", {"t": text, "s": src, "tgt": tgt})

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

        src = (params.get("source") or params.get("from") or "auto").strip().lower()
        tgt = (params.get("target") or params.get("to") or "pt").strip().lower()

        # Limita tamanho para evitar abusos
        if len(text) > 3000:
            text = text[:3000]

        payload = {
            "q": text,
            "source": src,
            "target": tgt,
            "format": "text",
        }
        api_key = self.get_api_key()
        if api_key:
            payload["api_key"] = api_key

        url = f"{self.base_url}/translate"
        try:
            resp = await self._http_post(url, json_data=payload, timeout=9.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="LibreTranslate rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"LibreTranslate HTTP {resp.status_code}: {resp.text[:200]}",
                )

            body = resp.json()
            translated = body.get("translatedText")
            if not translated:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="LibreTranslate retornou resposta vazia",
                )

            normalized = {
                "original": text,
                "translated": translated,
                "source_lang": src,
                "target_lang": tgt,
                "source": "LibreTranslate",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[LibreTranslateProvider] Erro ao traduzir: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
