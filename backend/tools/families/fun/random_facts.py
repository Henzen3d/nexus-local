"""backend/tools/families/fun/random_facts.py — Provedor de curiosidades e diversão (Fatos aleatórios, conselhos, pets).
"""
from __future__ import annotations

import random
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class RandomFactsProvider(ToolProvider):
    provider_id = "random_facts"
    family = "fun"
    base_url = "https://uselessfacts.jsph.pl"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        # Retorna string vazia ou chave única para garantir que TTL=0 não retenha cache
        return ""

    @property
    def ttl_seconds(self) -> int:
        return 0  # Sem cache

    async def execute(self, params: dict) -> ToolResult:
        sub_type = (params.get("type") or "fact").strip().lower()

        try:
            if sub_type in ("dog", "cachorro", "cao"):
                url = "https://dog.ceo/api/breeds/image/random"
                resp = await self._http_get(url, timeout=7.0)
                if resp.status_code == 200:
                    b = resp.json()
                    return ToolResult(
                        success=True,
                        data={
                            "type": "dog",
                            "image_url": b.get("message"),
                            "source": "Dog CEO API",
                        },
                        provider_id=self.provider_id,
                        family=self.family,
                    )

            elif sub_type in ("cat", "gato"):
                url = "https://api.thecatapi.com/v1/images/search"
                resp = await self._http_get(url, timeout=7.0)
                if resp.status_code == 200:
                    b = resp.json()
                    img_url = b[0].get("url") if b else None
                    return ToolResult(
                        success=True,
                        data={
                            "type": "cat",
                            "image_url": img_url,
                            "source": "TheCatAPI",
                        },
                        provider_id=self.provider_id,
                        family=self.family,
                    )

            elif sub_type in ("advice", "conselho"):
                url = "https://api.adviceslip.com/advice"
                resp = await self._http_get(url, timeout=7.0)
                if resp.status_code == 200:
                    b = resp.json()
                    slip = b.get("slip", {})
                    return ToolResult(
                        success=True,
                        data={
                            "type": "advice",
                            "advice": slip.get("advice"),
                            "id": slip.get("id"),
                            "source": "Advice Slip API",
                        },
                        provider_id=self.provider_id,
                        family=self.family,
                    )

            # Default: fact
            url = "https://uselessfacts.jsph.pl/api/v2/facts/random"
            resp = await self._http_get(url, timeout=7.0)
            if resp.status_code == 200:
                b = resp.json()
                return ToolResult(
                    success=True,
                    data={
                        "type": "fact",
                        "fact": b.get("text"),
                        "source": "Useless Facts API",
                    },
                    provider_id=self.provider_id,
                    family=self.family,
                )

            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=f"Falha ao obter dados aleatórios de '{sub_type}'",
            )

        except Exception as e:
            logger.error("[RandomFactsProvider] Erro: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
