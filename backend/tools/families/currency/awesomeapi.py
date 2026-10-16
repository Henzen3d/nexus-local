"""backend/tools/families/currency/awesomeapi.py — Provedor de câmbio AwesomeAPI (Primário).
"""
from __future__ import annotations

from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class AwesomeAPIProvider(ToolProvider):
    provider_id = "awesomeapi"
    family = "currency"
    base_url = "https://economia.awesomeapi.com.br/json"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        from_curr = (params.get("from") or params.get("from_currency") or "USD").strip().upper()
        to_curr = (params.get("to") or params.get("to_currency") or "BRL").strip().upper()
        return self.make_deterministic_hash("currency:awesome", {"from": from_curr, "to": to_curr})

    async def execute(self, params: dict) -> ToolResult:
        from_curr = (params.get("from") or params.get("from_currency") or "USD").strip().upper()
        to_curr = (params.get("to") or params.get("to_currency") or "BRL").strip().upper()

        pair = f"{from_curr}-{to_curr}"
        url = f"{self.base_url}/last/{pair}"

        try:
            resp = await self._http_get(url, timeout=8.0)
            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="AwesomeAPI rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"AwesomeAPI HTTP {resp.status_code}: par {pair} não encontrado",
                )

            body = resp.json()
            key = f"{from_curr}{to_curr}"
            item = body.get(key)
            if not item:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Dados de câmbio não encontrados para {pair}",
                )

            rate = float(item.get("bid") or item.get("ask") or 0.0)
            normalized = {
                "from": from_curr,
                "to": to_curr,
                "name": item.get("name"),
                "rate": rate,
                "bid": float(item.get("bid") or 0.0),
                "ask": float(item.get("ask") or 0.0),
                "high": float(item.get("high") or 0.0),
                "low": float(item.get("low") or 0.0),
                "variation": float(item.get("varBid") or 0.0),
                "pct_change": float(item.get("pctChange") or 0.0),
                "timestamp": item.get("create_date"),
                "source": "AwesomeAPI",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[AwesomeAPIProvider] Erro ao consultar cotação: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
