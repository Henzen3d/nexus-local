"""backend/tools/families/brasil/viacep.py — Provedor ViaCEP (Fallback para CEP).
"""
from __future__ import annotations

import re
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)


class ViaCEPProvider(ToolProvider):
    provider_id = "viacep"
    family = "brasil"
    base_url = "https://viacep.com.br/ws"
    fallback_order = 2
    requires_key = False

    def cache_key(self, params: dict) -> str:
        val = str(params.get("value") or params.get("cep") or "").strip()
        clean_val = re.sub(r"\D", "", val)
        return self.make_deterministic_hash("brasil:viacep", {"cep": clean_val})

    async def execute(self, params: dict) -> ToolResult:
        query_type = (params.get("type") or "").strip().lower()
        raw_val = str(params.get("value") or params.get("cep") or "").strip()

        # ViaCEP só atende consultas de CEP
        if query_type and query_type != "cep":
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="ViaCEP atende exclusivamente consultas de CEP",
            )

        clean_digits = re.sub(r"\D", "", raw_val)
        if len(clean_digits) != 8:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=f"CEP inválido: '{raw_val}'. Deve conter 8 dígitos.",
            )

        url = f"{self.base_url}/{clean_digits}/json/"
        try:
            resp = await self._http_get(url, timeout=8.0)
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"ViaCEP HTTP {resp.status_code}",
                )

            body = resp.json()
            if body.get("erro") is True:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"CEP '{clean_digits}' não encontrado no ViaCEP",
                )

            normalized = {
                "type": "cep",
                "cep": body.get("cep"),
                "street": body.get("logradouro"),
                "neighborhood": body.get("bairro"),
                "city": body.get("localidade"),
                "state": body.get("uf"),
                "ddd": body.get("ddd"),
                "ibge": body.get("ibge"),
                "source": "ViaCEP",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
            )

        except Exception as e:
            logger.error("[ViaCEPProvider] Erro ao consultar ViaCEP: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
