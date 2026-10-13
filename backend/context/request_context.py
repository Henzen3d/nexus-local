"""
backend/context/request_context.py
Contexto de ciclo de vida de requisição com memoização de embeddings e profiling de latência.
Filosofia JEV (Just Execute Virtual): calcula uma única vez por requisição e reutiliza em RAM.
"""

from __future__ import annotations

import time
import uuid
import asyncio
from typing import Optional, Dict, Any

from backend.logging_config import get_logger

logger = get_logger(__name__)


class RequestContext:
    """
    Mantém o estado e os dados efêmeros de um único turno de conversa.
    Evita recalcular embeddings para a mesma consulta entre o Cache Semântico,
    RAG de Projetos e Busca Híbrida de Memória.
    """

    def __init__(
        self,
        request_id: Optional[str] = None,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ):
        self.request_id: str = request_id or str(uuid.uuid4())
        self.user_id: Optional[str] = user_id
        self.conversation_id: Optional[str] = conversation_id
        self.started_at: float = time.perf_counter()
        
        # Cache de embeddings em memória específico deste request: {texto_normalizado: blob_bytes}
        self._embedding_cache: Dict[str, bytes] = {}
        self._embedding_tasks: Dict[str, asyncio.Task[Optional[bytes]]] = {}
        self._embedding_lock = asyncio.Lock()
        self._memo: Dict[str, Any] = {}
        
        # Métricas de fases em milissegundos
        self.phase_latencies: Dict[str, float] = {}

    def set_memo(self, key: str, value: Any) -> None:
        self._memo[key] = value

    def get_memo(self, key: str, default: Any = None) -> Any:
        return self._memo.get(key, default)

    def set_embedding(self, text: str, blob: bytes) -> None:
        if text and blob:
            self._embedding_cache[text.strip()] = blob

    def record_phase(self, phase_name: str, start_time: float) -> float:
        """Registra a duração de uma fase em ms."""
        duration_ms = round((time.perf_counter() - start_time) * 1000, 3)
        self.phase_latencies[phase_name] = duration_ms
        return duration_ms

    async def get_embedding(self, text: str) -> Optional[bytes]:
        """
        Retorna o embedding do texto. Se já computado neste turno, retorna em 0.001ms.
        Caso contrário, computa assincronamente via FastEmbed e armazena em RAM.
        """
        if not text or not text.strip():
            return None

        norm_text = text.strip()
        if norm_text in self._embedding_cache:
            logger.debug(
                "JEV: Reutilizando embedding em RAM para request %s (0ms)",
                self.request_id,
            )
            return self._embedding_cache[norm_text]

        async with self._embedding_lock:
            cached = self._embedding_cache.get(norm_text)
            if cached is not None:
                return cached
            task = self._embedding_tasks.get(norm_text)
            if task is None:
                task = asyncio.create_task(self._compute_embedding(norm_text))
                self._embedding_tasks[norm_text] = task

        try:
            return await asyncio.shield(task)
        finally:
            if task.done():
                async with self._embedding_lock:
                    if self._embedding_tasks.get(norm_text) is task:
                        self._embedding_tasks.pop(norm_text, None)

    async def _compute_embedding(self, norm_text: str) -> Optional[bytes]:
        t0 = time.perf_counter()
        try:
            from backend.projects.embedder import embed_text_async
            blob = await embed_text_async(norm_text)
            if blob:
                self._embedding_cache[norm_text] = blob
                self.record_phase("fastembed_compute", t0)
            return blob
        except Exception as e:
            logger.warning(
                "Falha ao computar embedding no RequestContext: %s",
                e,
                exc_info=True,
            )
            return None
