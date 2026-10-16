"""backend/tools/base.py — Classe base abstrata e modelos para provedores de ferramentas.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union

import httpx

from backend.logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_TTL: dict[str, int] = {
    "weather": 900,         # 15 min
    "currency": 300,        # 5 min
    "brasil": 86400,        # 24 horas (padrão; CEP tem 7 dias via override)
    "knowledge": 86400,     # 24 horas
    "news": 1800,           # 30 min
    "translation": 2592000, # 30 dias
    "geo": 604800,          # 7 dias
    "fun": 0,               # sem cache
    "code_exec": 0,         # sem cache
    "diagrams": 3600,       # 1 hora
}


@dataclass
class ToolResult:
    """Resultado padronizado da execução de uma ferramenta externa."""
    success: bool
    data: Union[dict, list, str, Any]
    provider_id: str
    family: str
    cached: bool = False
    latency_ms: float = 0.0
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def provider(self) -> str:
        return self.provider_id

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provider"] = self.provider_id
        return d


class ToolProvider(ABC):
    """Classe base abstrata para todos os provedores de APIs públicas / Ferramentas."""
    provider_id: str
    family: str
    base_url: str
    timeout: float = 10.0
    requires_key: bool = False
    env_key_name: Optional[str] = None
    fallback_order: int = 1
    enabled: bool = True

    def __init__(self) -> None:
        pass

    @abstractmethod
    async def execute(self, params: dict) -> ToolResult:
        """Executa a chamada ao provedor externo com os parâmetros fornecidos."""
        raise NotImplementedError

    @abstractmethod
    def cache_key(self, params: dict) -> str:
        """Gera chave de cache determinística para os parâmetros."""
        raise NotImplementedError

    @property
    def ttl_seconds(self) -> int:
        """TTL padrão de cache para esta família."""
        return DEFAULT_TTL.get(self.family, 900)

    def get_api_key(self) -> Optional[str]:
        """Obtém a chave de API da variável de ambiente configurada."""
        if not self.env_key_name:
            return None
        return os.getenv(self.env_key_name)

    def is_configured(self) -> bool:
        """Verifica se o provedor está pronto para uso (tem chave se requer)."""
        if not self.enabled:
            return False
        if self.requires_key and not self.get_api_key():
            return False
        return True

    def make_deterministic_hash(self, key_prefix: str, params: dict) -> str:
        """Helper para gerar hash sha256 determinístico de parâmetros."""
        sorted_params = json.dumps(params, sort_keys=True, ensure_ascii=True)
        digest = hashlib.sha256(f"{key_prefix}:{sorted_params}".encode("utf-8")).hexdigest()
        return f"{self.family}:{self.provider_id}:{digest}"

    async def _http_get(
        self,
        url: str,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Helper HTTP GET assíncrono com tratamento de timeout e 429."""
        t_out = timeout or self.timeout
        req_headers = {"User-Agent": "NexusLocal-Tools/1.0"}
        if headers:
            req_headers.update(headers)

        async with httpx.AsyncClient(timeout=t_out, follow_redirects=True) as client:
            resp = await client.get(url, params=params, headers=req_headers)
            if resp.status_code == 429:
                logger.warning("[Tool:%s:%s] Rate limit (HTTP 429) em %s", self.family, self.provider_id, url)
            return resp

    async def _http_post(
        self,
        url: str,
        json_data: Any = None,
        data: Any = None,
        content: Any = None,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> httpx.Response:
        """Helper HTTP POST assíncrono com tratamento de timeout e 429."""
        t_out = timeout or self.timeout
        req_headers = {"User-Agent": "NexusLocal-Tools/1.0"}
        if headers:
            req_headers.update(headers)

        async with httpx.AsyncClient(timeout=t_out, follow_redirects=True) as client:
            resp = await client.post(url, json=json_data, data=data, content=content, params=params, headers=req_headers)
            if resp.status_code == 429:
                logger.warning("[Tool:%s:%s] Rate limit (HTTP 429) em %s", self.family, self.provider_id, url)
            return resp
