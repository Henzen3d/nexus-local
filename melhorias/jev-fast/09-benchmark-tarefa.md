# Ponto 5 — Benchmark por Tarefa

**Status:** 🆕 Novo (não implementado)  
**Tempo Estimado:** 30 min  
**Risco:** Baixo (somente leitura/métrica)

---

## 📋 Resumo

Sistema de benchmarking que mede latência total, custo, quantidade de chamadas, taxa de sucesso e erros recuperados por tipo de tarefa. Decisões de otimização devem ser baseadas em dados, não suposições.

---

## 🔍 Problema Identificado

```
Problema atual:
┌────────────────────────────────────────────────────────┐
│ - Não sabemos qual operação é mais lenta               │
│ - Não medimos custo por tipo de request                │
│ - Não temos baseline para comparar otimizações         │
│ - Otimizações podem piorar performance em certos casos  │
│ - Não sabemos taxa de sucesso real                     │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução

### 1. Instrumentação de Métricas

```python
# backend/metrics/task_benchmark.py (NOVO)
import time
import json
import asyncio
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime

@dataclass
class TaskBenchmark:
    """Métrica de uma tarefa executada."""
    timestamp: str
    task_type: str  # "chat", "image_gen", "code_gen", "search", etc.
    latency_ms: float
    tokens_input: int
    tokens_output: int
    cost_usd: float
    calls_made: int
    success: bool
    errors: list
    recovery_actions: list
    model_id: str
    provider_id: str

class TaskBenchmarkManager:
    """
    Coleta e agrega métricas por tipo de tarefa.
    """
    
    def __init__(self, log_dir: str = "benchmark_logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)
        self._current_benchmarks: Dict[str, TaskBenchmark] = {}
    
    def start_benchmark(self, task_id: str, task_type: str):
        """Inicia medição de uma tarefa."""
        self._current_benchmarks[task_id] = {
            "start_time": time.perf_counter(),
            "task_type": task_type,
            "calls_made": 0,
            "errors": [],
            "recovery_actions": [],
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_usd": 0.0,
        }
    
    def record_call(self, task_id: str, model_id: str = None, provider_id: str = None):
        """Registra uma chamada ao modelo."""
        if task_id in self._current_benchmarks:
            self._current_benchmarks[task_id]["calls_made"] += 1
            if model_id:
                self._current_benchmarks[task_id]["model_id"] = model_id
            if provider_id:
                self._current_benchmarks[task_id]["provider_id"] = provider_id
    
    def record_tokens(self, task_id: str, input_tokens: int, output_tokens: int):
        """Registra tokens usados."""
        if task_id in self._current_benchmarks:
            bench = self._current_benchmarks[task_id]
            bench["tokens_input"] += input_tokens
            bench["tokens_output"] += output_tokens
    
    def record_cost(self, task_id: str, cost_usd: float):
        """Registra custo."""
        if task_id in self._current_benchmarks:
            self._current_benchmarks[task_id]["cost_usd"] += cost_usd
    
    def record_error(self, task_id: str, error: str, recovery: str = None):
        """Registra erro e ação de recuperação."""
        if task_id in self._current_benchmarks:
            bench = self._current_benchmarks[task_id]
            bench["errors"].append(error)
            if recovery:
                bench["recovery_actions"].append(recovery)
    
    def finish_benchmark(
        self,
        task_id: str,
        success: bool,
        model_id: str = None,
        provider_id: str = None,
    ) -> TaskBenchmark:
        """Finaliza medição e retorna resultado."""
        if task_id not in self._current_benchmarks:
            raise ValueError(f"Task {task_id} não encontrada")
        
        bench = self._current_benchmarks.pop(task_id)
        latency_ms = (time.perf_counter() - bench["start_time"]) * 1000
        
        result = TaskBenchmark(
            timestamp=datetime.now().isoformat(),
            task_type=bench["task_type"],
            latency_ms=latency_ms,
            tokens_input=bench["tokens_input"],
            tokens_output=bench["tokens_output"],
            cost_usd=bench["cost_usd"],
            calls_made=bench["calls_made"],
            success=success,
            errors=bench["errors"],
            recovery_actions=bench["recovery_actions"],
            model_id=model_id or bench.get("model_id", "unknown"),
            provider_id=provider_id or bench.get("provider_id", "unknown"),
        )
        
        # Salva log
        self._save_log(result)
        
        return result
    
    def _save_log(self, benchmark: TaskBenchmark):
        """Salva benchmark em arquivo JSON."""
        log_file = (
            self.log_dir / 
            f"benchmark_{benchmark.task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        with open(log_file, "w") as f:
            json.dump(asdict(benchmark), f, indent=2, default=str)
    
    def get_aggregated_stats(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Retorna estatísticas agregadas por tipo de tarefa.
        Lê dos logs recentes.
        """
        stats = {}
        
        for log_file in self.log_dir.glob("benchmark_*.json"):
            with open(log_file) as f:
                data = json.load(f)
            
            ttype = data.get("task_type", "unknown")
            
            if task_type and ttype != task_type:
                continue
            
            if ttype not in stats:
                stats[ttype] = {
                    "count": 0,
                    "total_latency_ms": 0,
                    "total_cost_usd": 0,
                    "total_calls": 0,
                    "success_count": 0,
                    "error_count": 0,
                    "recoveries": 0,
                }
            
            s = stats[ttype]
            s["count"] += 1
            s["total_latency_ms"] += data["latency_ms"]
            s["total_cost_usd"] += data["cost_usd"]
            s["total_calls"] += data["calls_made"]
            if data["success"]:
                s["success_count"] += 1
            else:
                s["error_count"] += 1
            s["recoveries"] += len(data.get("recovery_actions", []))
        
        # Calcula médias
        for ttype, s in stats.items():
            if s["count"] > 0:
                s["avg_latency_ms"] = s["total_latency_ms"] / s["count"]
                s["avg_cost_usd"] = s["total_cost_usd"] / s["count"]
                s["avg_calls"] = s["total_calls"] / s["count"]
                s["success_rate"] = s["success_count"] / s["count"]
        
        return stats
```

### 2. Integração com Chat Flow

```python
# backend/routers/chat.py (modificado)
from backend.metrics.task_benchmark import TaskBenchmarkManager

_benchmark = TaskBenchmarkManager()

async def _process_turn(...):
    import uuid
    task_id = str(uuid.uuid4())
    
    # ── NOVO: Inicia benchmark ──────────────────────────────
    _benchmark.start_benchmark(task_id, "chat")
    
    try:
        # ... código existente ...
        
        # Registra chamadas ao modelo
        _benchmark.record_call(task_id, model_id, provider_id)
        
        # ... mais código ...
        
        # Finaliza com sucesso
        result = _benchmark.finish_benchmark(task_id, success=True)
        
    except Exception as e:
        # Finaliza com erro
        result = _benchmark.finish_benchmark(
            task_id, 
            success=False,
            errors=[str(e)]
        )
        raise
```

### 3. Endpoint de Dashboard

```python
# backend/routers/admin.py (modificado)
from backend.metrics.task_benchmark import _benchmark

@router.get("/api/admin/benchmark/stats")
async def get_benchmark_stats(task_type: str = None):
    """Retorna estatísticas de benchmark por tipo de tarefa."""
    stats = _benchmark.get_aggregated_stats(task_type)
    return {"benchmark_stats": stats}

@router.get("/api/admin/benchmark/stats/chat")
async def get_chat_benchmark_stats():
    """Estatísticas específicas de chat."""
    stats = _benchmark.get_aggregated_stats("chat")
    return {"benchmark_stats": stats.get("chat", {})}
```

---

## 📊 Exemplo de Saída

```json
{
  "chat": {
    "count": 1547,
    "total_latency_ms": 234567,
    "total_cost_usd": 12.45,
    "total_calls": 1890,
    "success_count": 1498,
    "error_count": 49,
    "recoveries": 23,
    "avg_latency_ms": 151.6,
    "avg_cost_usd": 0.008,
    "avg_calls": 1.22,
    "success_rate": 0.969
  },
  "image_gen": {
    "count": 234,
    "avg_latency_ms": 4500.0,
    "avg_cost_usd": 0.045,
    "success_rate": 0.94
  }
}
```

---

## 🧪 Testes de Benchmark

```python
# tests/test_task_benchmark.py
import pytest
import time
from backend.metrics.task_benchmark import TaskBenchmarkManager

@pytest.mark.asyncio
async def test_benchmark_measurement():
    """Benchmark deve medir latência corretamente."""
    manager = TaskBenchmarkManager()
    task_id = "test_1"
    
    manager.start_benchmark(task_id, "chat")
    await asyncio.sleep(0.1)  # 100ms
    result = manager.finish_benchmark(task_id, success=True)
    
    assert result.latency_ms >= 100
    assert result.task_type == "chat"
    assert result.success is True

@pytest.mark.asyncio
async def test_benchmark_error_handling():
    """Benchmark deve registrar erros."""
    manager = TaskBenchmarkManager()
    task_id = "test_2"
    
    manager.start_benchmark(task_id, "chat")
    manager.record_error(task_id, "Rate limit exceeded", "retry")
    result = manager.finish_benchmark(task_id, success=False)
    
    assert result.success is False
    assert len(result.errors) == 1
    assert len(result.recovery_actions) == 1

@pytest.mark.asyncio
async def test_aggregated_stats():
    """Estatísticas agregadas devem calcular médias corretamente."""
    manager = TaskBenchmarkManager()
    
    # Simula 3 tasks
    for i in range(3):
        tid = f"task_{i}"
        manager.start_benchmark(tid, "chat")
        time.sleep(0.01)
        manager.finish_benchmark(tid, success=True)
    
    stats = manager.get_aggregated_stats("chat")
    
    assert stats["chat"]["count"] == 3
    assert stats["chat"]["success_rate"] == 1.0
    assert stats["chat"]["avg_latency_ms"] > 0
```

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/metrics/task_benchmark.py`
- [ ] Integrar com `chat.py`
- [ ] Adicionar endpoint admin
- [ ] Adicionar testes
- [ ] Rodar `pytest tests/test_task_benchmark.py`
- [ ] Verificar logs sendo gerados
- [ ] Commit: `feat(metrics): add task benchmarking system`

---

## 📈 Uso para Decisões de Otimização

```
Antes de implementar qualquer otimização:

1. Rodar baseline benchmark
   curl http://localhost:8000/api/admin/benchmark/stats

2. Implementar otimização

3. Rodar novo benchmark nas mesmas condições

4. Comparar:
   - Latência média caiu?
   - Taxa de sucesso melhorou?
   - Custo diminuiu?
   - Número de calls aumentou? (pode ser pior)

5. Só merge se: latency↓ OU success_rate↑ OU cost↓
```

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Pendente (novo)*
