"""
backend/ranking/token_bucket.py
Anti-429 Preventivo com Token Bucket em Memória (JEV Fast).

Evita penalidades de timeout (1-2s) e failovers desnecessários ao bloquear proativamente
chamadas a provedores conhecidos por limites estritos de RPM/RPD antes que ocorra HTTP 429.
Inclui histerese para proteger a afinidade do Sticky Routing (KV-cache).
"""

from __future__ import annotations

import time
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any

from backend.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class RateLimitConfig:
    provider_id: str
    rpm: int = 60           # Requests por minuto
    burst_size: int = 5     # Tamanho máximo de rajada permitida


# Configurações padrão conhecidas para provedores com free tier limitado
DEFAULT_PROVIDER_LIMITS: Dict[str, RateLimitConfig] = {
    "orcarouter": RateLimitConfig(provider_id="orcarouter", rpm=12, burst_size=3),
    "bynara": RateLimitConfig(provider_id="bynara", rpm=10, burst_size=3),
    "groq": RateLimitConfig(provider_id="groq", rpm=30, burst_size=5),
    "freetheai": RateLimitConfig(provider_id="freetheai", rpm=15, burst_size=3),
    "llm7": RateLimitConfig(provider_id="llm7", rpm=15, burst_size=3),
    "agnes": RateLimitConfig(provider_id="agnes", rpm=20, burst_size=4),
}


class TokenBucket:
    """Bucket com recarga contínua em memória e controle de histerese."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens: float = float(config.burst_size)
        self.last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()
        self._throttled: bool = False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        refill_rate = self.config.rpm / 60.0  # tokens por segundo
        self.tokens = min(float(self.config.burst_size), self.tokens + (elapsed * refill_rate))
        self.last_refill = now

    def can_acquire(self, tokens: int = 1, is_sticky: bool = False) -> bool:
        """Verificação sem lock para rotas rápidas (<0.001ms)."""
        self._refill()
        min_required = 0.5 if is_sticky else 1.0
        if self._throttled:
            recovery_threshold = 0.8 if is_sticky else 1.0
            return self.tokens >= recovery_threshold
        return self.tokens >= min_required

    async def acquire(self, tokens: int = 1, is_sticky: bool = False) -> Tuple[bool, float]:
        """Tenta consumir tokens atomicamente com histerese para sticky routing.
        
        Returns:
            (allowed, wait_time_seconds)
        """
        async with self._lock:
            self._refill()
            refill_rate = self.config.rpm / 60.0

            # Histerese: Se já entrou em estado throttled, exige recuperação antes de desarmar
            if self._throttled:
                recovery_threshold = 0.8 if is_sticky else 1.0
                if self.tokens < recovery_threshold:
                    deficit = recovery_threshold - self.tokens
                    wait_time = deficit / refill_rate if refill_rate > 0 else 5.0
                    return False, wait_time
                self._throttled = False

            # Limiar de disparo com histerese favorável ao Sticky Routing
            min_required = 0.5 if is_sticky else 1.0
            if self.tokens >= min_required:
                self.tokens -= tokens
                if self.tokens < 0.0:
                    self._throttled = True
                return True, 0.0

            self._throttled = True
            deficit = min_required - self.tokens
            wait_time = deficit / refill_rate if refill_rate > 0 else 5.0
            return False, wait_time

    async def on_rate_limit(self) -> None:
        """Aplica penalidade imediata ao receber HTTP 429 real da API."""
        async with self._lock:
            self.tokens = 0.0
            self._throttled = True
            self.last_refill = time.monotonic()


class TokenBucketManager:
    """Gerenciador singleton de Token Buckets para o Smart Router e Failover."""

    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        for prov_id, cfg in DEFAULT_PROVIDER_LIMITS.items():
            self._buckets[prov_id] = TokenBucket(cfg)

    def is_provider_available(self, provider_id: str, is_sticky: bool = False) -> bool:
        """Checagem instantânea em RAM se o provedor tem quota disponível no minuto."""
        bucket = self._buckets.get(provider_id.lower())
        if not bucket:
            return True  # Provedores sem limite estrito cadastrado
        return bucket.can_acquire(1, is_sticky=is_sticky)

    async def consume_token(self, provider_id: str, is_sticky: bool = False) -> bool:
        """Consome 1 token de forma atômica antes do despacho ao provedor."""
        bucket = self._buckets.get(provider_id.lower())
        if not bucket:
            return True
        allowed, _ = await bucket.acquire(1, is_sticky=is_sticky)
        if not allowed:
            logger.warning(
                "JEV Anti-429: Provedor '%s' próximo do limite de RPM (sticky=%s). Roteamento preventivo acionado.",
                provider_id,
                is_sticky,
            )
        return allowed

    async def on_rate_limit(self, provider_id: str) -> None:
        """Notifica o bucket que o provedor retornou HTTP 429 para penalização em RAM."""
        bucket = self._buckets.get(provider_id.lower())
        if bucket:
            await bucket.on_rate_limit()

    def get_status(self) -> Dict[str, Any]:
        """Retorna o estado dos buckets para auditoria ou admin."""
        res = {}
        for pid, b in self._buckets.items():
            b._refill()
            res[pid] = {
                "tokens": round(b.tokens, 2),
                "burst_size": b.config.burst_size,
                "rpm": b.config.rpm,
                "throttled": b._throttled,
            }
        return res

    def reset(self) -> None:
        """Restaura todos os buckets para capacidade total (útil para isolamento de testes)."""
        for b in self._buckets.values():
            b.tokens = float(b.config.burst_size)
            b.last_refill = time.monotonic()
            b._throttled = False


# Singleton global
token_bucket_manager = TokenBucketManager()
