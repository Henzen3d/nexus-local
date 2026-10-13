"""
backend/metrics/task_benchmark.py
Sistema de Benchmarking e Instrumentação Não-Bloqueante (JEV Fast Plano 09).

Mede latências de fases (Fast-path, Intent Classification, RAG/Memory, LLM TTFB),
taxas de sucesso e estatísticas agregadas por tipo de tarefa sem bloquear o event loop.
"""

from __future__ import annotations

import time
import json
import asyncio
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional, List
from collections import deque

from backend.logging_config import get_logger

logger = get_logger(__name__)

BENCHMARK_LOG_DIR = Path(__file__).resolve().parent.parent / "storage" / "benchmark_logs"


@dataclass
class TaskBenchmark:
    """Métrica detalhada de uma tarefa executada."""
    timestamp: str
    task_type: str                         # "chat", "image_gen", "code_gen", etc.
    latency_ms: float
    model_id: str
    provider_id: str
    success: bool
    calls_made: int = 1
    tokens_input: int = 0
    tokens_output: int = 0
    cost_usd: float = 0.0
    errors: List[str] = field(default_factory=list)
    recovery_actions: List[str] = field(default_factory=list)
    phase_latencies: Dict[str, float] = field(default_factory=dict)


class TaskBenchmarkManager:
    """
    Coletor e agregador de métricas em memória com persistência 100% assíncrona.
    Garante que a resposta ao usuário nunca seja atrasada por I/O de disco.
    """

    def __init__(self, max_history: int = 1000):
        self._history: deque[TaskBenchmark] = deque(maxlen=max_history)
        self._lock = asyncio.Lock()
        self._log_dir = BENCHMARK_LOG_DIR
        self._log_dir_initialized = False

    def _ensure_dir(self) -> None:
        if not self._log_dir_initialized:
            try:
                self._log_dir.mkdir(parents=True, exist_ok=True)
                self._log_dir_initialized = True
            except Exception as e:
                logger.debug("Falha ao criar diretório de benchmark logs: %s", e)

    def _sync_write_log(self, bench_dict: dict) -> None:
        """Executado exclusivamente fora do event loop via asyncio.to_thread."""
        try:
            self._ensure_dir()
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            filepath = self._log_dir / f"bench_{bench_dict.get('task_type', 'task')}_{ts}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(bench_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("Benchmark non-blocking write error: %s", e)

    async def record_task_async(
        self,
        task_type: str,
        latency_ms: float,
        model_id: str,
        provider_id: str,
        success: bool = True,
        calls_made: int = 1,
        tokens_input: int = 0,
        tokens_output: int = 0,
        cost_usd: float = 0.0,
        errors: Optional[List[str]] = None,
        recovery_actions: Optional[List[str]] = None,
        phase_latencies: Optional[Dict[str, float]] = None,
        persist_to_disk: bool = False,
    ) -> TaskBenchmark:
        """Registra a conclusão de uma tarefa de forma não-bloqueante."""
        bench = TaskBenchmark(
            timestamp=datetime.utcnow().isoformat(),
            task_type=task_type,
            latency_ms=round(latency_ms, 3),
            model_id=model_id or "unknown",
            provider_id=provider_id or "unknown",
            success=success,
            calls_made=calls_made,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            cost_usd=round(cost_usd, 6),
            errors=errors or [],
            recovery_actions=recovery_actions or [],
            phase_latencies=phase_latencies or {},
        )

        async with self._lock:
            self._history.append(bench)

        if persist_to_disk:
            asyncio.create_task(asyncio.to_thread(self._sync_write_log, asdict(bench)))

        return bench

    def get_aggregated_stats(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas agregadas em tempo real calculadas em RAM (<1ms).
        """
        stats: Dict[str, Dict[str, Any]] = {}

        for item in self._history:
            ttype = item.task_type
            if task_type and ttype != task_type:
                continue

            if ttype not in stats:
                stats[ttype] = {
                    "total_requests": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "total_latency_ms": 0.0,
                    "total_tokens_input": 0,
                    "total_tokens_output": 0,
                    "phase_latencies_sum": {},
                    "phase_latencies_count": {},
                }

            s = stats[ttype]
            s["total_requests"] += 1
            if item.success:
                s["success_count"] += 1
            else:
                s["error_count"] += 1
            s["total_latency_ms"] += item.latency_ms
            s["total_tokens_input"] += item.tokens_input
            s["total_tokens_output"] += item.tokens_output

            for phase, val in item.phase_latencies.items():
                s["phase_latencies_sum"][phase] = s["phase_latencies_sum"].get(phase, 0.0) + val
                s["phase_latencies_count"][phase] = s["phase_latencies_count"].get(phase, 0) + 1

        # Formata médias
        result: Dict[str, Any] = {}
        for ttype, s in stats.items():
            reqs = s["total_requests"]
            avg_phases = {}
            for phase, total_val in s["phase_latencies_sum"].items():
                c = s["phase_latencies_count"].get(phase, 1)
                avg_phases[phase] = round(total_val / c, 2) if c > 0 else 0.0

            result[ttype] = {
                "count": reqs,
                "success_rate": round(s["success_count"] / reqs, 3) if reqs > 0 else 1.0,
                "error_rate": round(s["error_count"] / reqs, 3) if reqs > 0 else 0.0,
                "avg_latency_ms": round(s["total_latency_ms"] / reqs, 2) if reqs > 0 else 0.0,
                "avg_tokens_input": round(s["total_tokens_input"] / reqs, 1) if reqs > 0 else 0,
                "avg_tokens_output": round(s["total_tokens_output"] / reqs, 1) if reqs > 0 else 0,
                "avg_phase_latencies_ms": avg_phases,
            }

        return result


# Singleton global de benchmarking
task_benchmark_manager = TaskBenchmarkManager()
