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

            amount = params.get("amount")
            if amount is not None:
                try:
                    amt = float(amount)
                    if amt > 0 and rate > 0:
                        # Se o par for USD-BRL e o valor estiver em reais (ou from=BRL), divide; se o valor for em USD, multiplica
                        if (from_curr != "BRL" and to_curr == "BRL" and amt >= 1000 and "dólar" not in str(params.get("raw_unit", "")).lower()) or from_curr == "BRL":
                            # Ex: R$ 132.000 -> US$ 26.073
                            converted = round(amt / rate, 2)
                            normalized["amount_brl"] = amt
                            normalized["converted_amount"] = converted
                            normalized["target_currency"] = from_curr if from_curr != "BRL" else to_curr
                            normalized["conversion_summary"] = (
                                f"R$ {amt:,.2f} equivale a aproximadamente {normalized['target_currency']} {converted:,.2f} "
                                f"(cotação: 1 {from_curr if from_curr != 'BRL' else to_curr} = R$ {rate:.4f})."
                            )
                        else:
                            # Ex: US$ 100 -> R$ 506
                            converted = round(amt * rate, 2)
                            normalized["amount_origin"] = amt
                            normalized["converted_amount_brl"] = converted
                            normalized["conversion_summary"] = (
                                f"{from_curr} {amt:,.2f} equivale a aproximadamente R$ {converted:,.2f} "
                                f"(cotação: 1 {from_curr} = R$ {rate:.4f})."
                            )
                except Exception:
                    pass

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
