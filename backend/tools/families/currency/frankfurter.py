"""backend/tools/families/currency/frankfurter.py — Provedor de câmbio Frankfurter (Fallback baseado em dados do ECB).
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class FrankfurterProvider(ToolProvider):
    provider_id = "frankfurter"
    family = "currency"
    base_url = "https://api.frankfurter.app"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        from_curr = (params.get("from") or params.get("from_currency") or "USD").strip().upper()
        to_curr = (params.get("to") or params.get("to_currency") or "BRL").strip().upper()
        return self.make_deterministic_hash("currency:frankfurter", {"from": from_curr, "to": to_curr})

    async def execute(self, params: dict) -> ToolResult:
        from_curr = (params.get("from") or params.get("from_currency") or "USD").strip().upper()
        to_curr = (params.get("to") or params.get("to_currency") or "BRL").strip().upper()

        url = f"{self.base_url}/latest"
        query_params = {"from": from_curr, "to": to_curr}

        try:
            resp = await self._http_get(url, params=query_params, timeout=8.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Frankfurter rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Frankfurter HTTP {resp.status_code}",
                )

            body = resp.json()
            rates = body.get("rates", {})
            rate = rates.get(to_curr)
            if rate is None:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Câmbio {to_curr} não disponível na Frankfurter",
                )

            normalized = {
                "from": from_curr,
                "to": to_curr,
                "name": f"{from_curr} para {to_curr}",
                "rate": float(rate),
                "bid": float(rate),
                "ask": float(rate),
                "timestamp": body.get("date"),
                "source": "Frankfurter (ECB)",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[FrankfurterProvider] Erro ao consultar Frankfurter: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
