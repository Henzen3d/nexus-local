"""Rate limiter em memória (janela deslizante) para endpoints sensíveis.

Projetado para o cenário do NexusLocal: processo único (uvicorn sem workers),
poucos usuários, exposto publicamente via Cloudflare Tunnel. Não precisa de
Redis — um dicionário protegido por lock de asyncio basta e evita dependências.

Uso típico::

    limiter = SlidingWindowLimiter(max_hits=10, window_seconds=15 * 60)
    retry_after = await limiter.hit(f"login:{ip}")
    if retry_after:
        raise HTTPException(429, headers={"Retry-After": str(retry_after)})
"""

from __future__ import annotations

import asyncio
import time
from collections import deque


class SlidingWindowLimiter:
    def __init__(self, max_hits: int, window_seconds: float, max_keys: int = 10_000):
        self.max_hits = int(max_hits)
        self.window = float(window_seconds)
        self.max_keys = int(max_keys)
        self._hits: dict[str, deque[float]] = {}
        self._lock = asyncio.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        q = self._hits.get(key)
        if q is None:
            q = deque()
            self._hits[key] = q
        cutoff = now - self.window
        while q and q[0] <= cutoff:
            q.popleft()
        return q

    async def hit(self, key: str) -> int:
        """Registra uma tentativa. Retorna 0 se permitido ou os segundos até liberar."""
        now = time.monotonic()
        async with self._lock:
            q = self._prune(key, now)
            if len(q) >= self.max_hits:
                return max(1, int(q[0] + self.window - now) + 1)
            q.append(now)
            # Evita crescimento ilimitado do dicionário sob scan de IPs.
            if len(self._hits) > self.max_keys:
                for stale in [k for k, dq in self._hits.items() if not dq or dq[-1] <= now - self.window]:
                    self._hits.pop(stale, None)
                if len(self._hits) > self.max_keys:
                    self._hits.clear()
            return 0

    async def reset(self, key: str) -> None:
        async with self._lock:
            self._hits.pop(key, None)


def client_ip(request) -> str:
    """IP do cliente considerando o proxy Nginx/Cloudflare.

    ``CF-Connecting-IP`` é definido pelo Cloudflare e ``X-Forwarded-For`` pelo
    Nginx (``proxy_set_header``). Como o backend só é alcançável pela rede
    Docker interna, confiar nesses headers é aceitável aqui.
    """
    headers = request.headers
    cf = headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"
