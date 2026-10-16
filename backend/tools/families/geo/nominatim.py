"""backend/tools/families/geo/nominatim.py — Provedor de geolocalização Nominatim/OpenStreetMap (Primário).
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)

# Throttle de 1 segundo para respeitar as diretrizes de uso do OpenStreetMap
_LAST_NOMINATIM_CALL = 0.0
_THROTTLE_LOCK = asyncio.Lock()


class NominatimProvider(ToolProvider):
    provider_id = "nominatim"
    family = "geo"
    base_url = "https://nominatim.openstreetmap.org"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        q = (params.get("query") or params.get("q") or params.get("address") or "").strip().lower()
        lat = params.get("lat")
        lon = params.get("lon")
        return self.make_deterministic_hash("geo:nominatim", {"q": q, "lat": lat, "lon": lon})

    async def execute(self, params: dict) -> ToolResult:
        global _LAST_NOMINATIM_CALL

        query = (params.get("query") or params.get("q") or params.get("address") or "").strip()
        lat = params.get("lat")
        lon = params.get("lon")

        # Aplica throttle de 1.0s
        async with _THROTTLE_LOCK:
            now = time.time()
            elapsed = now - _LAST_NOMINATIM_CALL
            if elapsed < 1.0:
                await asyncio.sleep(1.0 - elapsed)
            _LAST_NOMINATIM_CALL = time.time()

        headers = {
            "User-Agent": "NexusLocal-Geo/1.0 (https://github.com/Henzen3d/nexus-local)",
        }

        try:
            if lat is not None and lon is not None:
                # Reverse geocoding
                url = f"{self.base_url}/reverse"
                q_params = {"lat": str(lat), "lon": str(lon), "format": "json"}
                resp = await self._http_get(url, params=q_params, headers=headers, timeout=8.0)
                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"Nominatim Reverse HTTP {resp.status_code}",
                    )
                body = resp.json()
                normalized = {
                    "display_name": body.get("display_name"),
                    "lat": float(body.get("lat", lat)),
                    "lon": float(body.get("lon", lon)),
                    "type": body.get("type", "location"),
                    "address": body.get("address", {}),
                    "source": "Nominatim (OSM)",
                }
                return ToolResult(success=True, data=normalized, provider_id=self.provider_id, family=self.family)

            else:
                if not query:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error="Parâmetro 'query' (endereço ou cidade) é obrigatório",
                    )
                # Forward search
                url = f"{self.base_url}/search"
                q_params = {"q": query, "format": "json", "addressdetails": "1", "limit": "1"}
                resp = await self._http_get(url, params=q_params, headers=headers, timeout=8.0)
                if resp.status_code != 200:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"Nominatim Search HTTP {resp.status_code}",
                    )
                results = resp.json()
                if not results:
                    return ToolResult(
                        success=False,
                        data={},
                        provider_id=self.provider_id,
                        family=self.family,
                        error=f"Localização '{query}' não encontrada no Nominatim",
                    )
                top = results[0]
                normalized = {
                    "display_name": top.get("display_name"),
                    "lat": float(top.get("lat", 0.0)),
                    "lon": float(top.get("lon", 0.0)),
                    "type": top.get("type", "location"),
                    "importance": top.get("importance", 0.0),
                    "address": top.get("address", {}),
                    "source": "Nominatim (OSM)",
                }
                return ToolResult(success=True, data=normalized, provider_id=self.provider_id, family=self.family)

        except Exception as e:
            logger.error("[NominatimProvider] Erro ao consultar geolocalização: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
