# Plano: Write-Behind Post-Processing + PRAGMAs

**Status:** 🆕 Novo  
**Tempo Estimado:** 1h  
**Risco:** Baixo/Médio

---

## 📋 Resumo

Oportunidade identificada: mover pós-processamento (salvar mensagem, detectar artefatos, gravar cache, atualizar quota) para fora do caminho crítico usando write-behind com batching. Aplicar PRAGMAs de performance no SQLite.

---

## 🔍 Problema Identificado

```
Pós-processamento atual (caminho crítico):
┌────────────────────────────────────────────────────────┐
│ Streaming termina                                      │
│    │                                                   │
│    ▼                                                   │
│ 1. Salvar mensagem (commit síncrono)    ~10ms          │
│ 2. Detectar artefatos (regex)           ~5ms           │
│ 3. Gravar cache (INSERT)                ~15ms          │
│ 4. Atualizar quota (UPDATE)             ~5ms           │
│    │                                                   │
│    ▼                                                   │
│ USAÁRIO VÊ resposta (delay acumulado)                   │
│                                                        │
│ TOTAL pós-stream: ~35ms (bloqueia conclusão)           │
└────────────────────────────────────────────────────────┘

Problemas:
• Cada operação tem seu próprio commit (fsync)
• Caminho crítico aumenta latency percebida
• WAL mode não está otimizado
```

---

## ✅ Solução Proposta

### 1. Write-Behind Queue

```python
# backend/cache/write_behind.py (NOVO)
import asyncio
import logging
from typing import List, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class WriteType(str, Enum):
    CRITICAL = "critical"      # Mensagem do usuário (sempre síncrono)
    DERIVED = "derived"        # Cache, quota, artefatos (pode ser async)

@dataclass
class WriteJob:
    """Trabalho de escrita na fila."""
    write_type: WriteType
    operation: str  # "save_message", "update_cache", "update_quota", etc.
    data: Dict[str, Any]
    callback: Callable = None
    created_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = asyncio.get_event_loop().time()

class WriteBehindQueue:
    """
    Fila de writes assíncronos com batching.
    
    Funcionamento:
    - Writes CRITICAL são executados imediatamente (síncrono)
    - Writes DERIVED são colocados na fila
    - Fila é processada em batches com COMMIT único
    - Timeout de flush: 100ms ou 10 jobs, o que ocorrer primeiro
    """
    
    def __init__(self, max_batch_size: int = 10, flush_interval_s: float = 0.1):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._max_batch_size = max_batch_size
        self._flush_interval_s = flush_interval_s
        self._processing = False
        self._stats = {
            "critical_written": 0,
            "queued": 0,
            "batched": 0,
            "flushes": 0,
        }
    
    async def enqueue(
        self,
        write_type: WriteType,
        operation: str,
        data: Dict[str, Any],
        callback: Callable = None,
    ):
        """
        Adiciona trabalho na fila.
        
        CRITICAL: executado imediatamente
        DERIVED: colocado na fila para batching
        """
        job = WriteJob(
            write_type=write_type,
            operation=operation,
            data=data,
            callback=callback,
        )
        
        if write_type == WriteType.CRITICAL:
            # Executa imediatamente (caminho crítico)
            await self._execute_job(job)
            self._stats["critical_written"] += 1
        else:
            # Coloca na fila
            await self._queue.put(job)
            self._stats["queued"] += 1
            
            # Trigger flush se necessário
            if not self._processing:
                asyncio.create_task(self._process_queue())
    
    async def _process_queue(self):
        """Processa a fila em batches."""
        self._processing = True
        
        try:
            while True:
                batch = await self._collect_batch()
                
                if batch:
                    await self._execute_batch(batch)
                    self._stats["batched"] += len(batch)
                    self._stats["flushes"] += 1
                
                # Check se deve continuar
                if self._queue.empty():
                    break
                
                # Aguarda próximo flush
                await asyncio.sleep(self._flush_interval_s)
        
        finally:
            self._processing = False
    
    async def _collect_batch(self) -> List[WriteJob]:
        """Coleta jobs até atingir limite ou timeout."""
        batch = []
        start_time = asyncio.get_event_loop().time()
        
        while len(batch) < self._max_batch_size:
            try:
                # Timeout de 100ms para coletar mais jobs
                job = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=0.1
                )
                batch.append(job)
            except asyncio.TimeoutError:
                break
        
        return batch
    
    async def _execute_batch(self, batch: List[WriteJob]):
        """
        Executa batch de jobs com COMMIT único.
        
        Usa transação SQLite para atomicidade.
        """
        if not batch:
            return
        
        logger.debug(f"Executing batch of {len(batch)} jobs")
        
        # Agrupa por tipo de operação
        by_type = {}
        for job in batch:
            if job.operation not in by_type:
                by_type[job.operation] = []
            by_type[job.operation].append(job)
        
        # Executa cada tipo
        for operation, jobs in by_type.items():
            try:
                if operation == "save_cache":
                    await self._save_cache_batch(jobs)
                elif operation == "update_quota":
                    await self._update_quota_batch(jobs)
                elif operation == "detect_artifacts":
                    await self._detect_artifacts_batch(jobs)
                # Adicionar outros tipos conforme necessário
                
                # Executa callbacks
                for job in jobs:
                    if job.callback:
                        await job.callback()
                        
            except Exception as e:
                logger.error(f"Batch operation {operation} failed: {e}")
    
    async def _save_cache_batch(self, jobs: List[WriteJob]):
        """Salva múltiplos cache entries em uma transação."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("BEGIN")
            try:
                for job in jobs:
                    data = job.data
                    await db.execute(
                        "INSERT OR REPLACE INTO cache_exact (id, hash, model_id, response, token_est) VALUES (?, ?, ?, ?, ?)",
                        (data["id"], data["hash"], data["model_id"], data["response"], data["token_est"])
                    )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    
    async def _update_quota_batch(self, jobs: List[WriteJob]):
        """Atualiza múltiplas quotas em uma transação."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("BEGIN")
            try:
                for job in jobs:
                    data = job.data
                    await db.execute(
                        "UPDATE model_quota_status SET requests_used = requests_used + ? WHERE model_id = ? AND date = ?",
                        (data["increment"], data["model_id"], data["date"])
                    )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
    
    async def _detect_artifacts_batch(self, jobs: List[WriteJob]):
        """Detecta artefatos em múltiplas respostas."""
        for job in jobs:
            # Detecção é CPU-bound, roda em thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._detect_artifacts, job.data)
    
    def _detect_artifacts(self, data: Dict):
        """Detecta artefatos na resposta (imagem, código, etc)."""
        # Regex pré-compiladas (ver PRAGMAs abaixo)
        # ... lógica existente ...
        pass
    
    async def get_stats(self) -> Dict:
        """Retorna estatísticas da fila."""
        return {
            **self._stats,
            "queue_size": self._queue.qsize(),
            "is_processing": self._processing,
        }
    
    async def flush_immediately(self):
        """Força flush imediato da fila (útil no shutdown)."""
        if not self._queue.empty():
            batch = []
            while not self._queue.empty():
                try:
                    job = self._queue.get_nowait()
                    batch.append(job)
                except asyncio.QueueEmpty:
                    break
            if batch:
                await self._execute_batch(batch)


# Singleton
write_behind_queue = WriteBehindQueue()
```

### 2. PRAGMAs de Performance

```python
# backend/database.py (modificado)

# PRAGMAs otimizados para write-behind
OPTIMIZED_PRAGMAS = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA temp_store = MEMORY;
PRAGMA mmap_size = 268435456;
PRAGMA page_size = 4096;
PRAGMA cache_size = -20000;
PRAGMA busy_timeout = 5000;
"""

async def apply_optimized_pragmas(db):
    """Aplica PRAGMAs de performance."""
    for pragma in OPTIMIZED_PRAGMAS.strip().split(';'):
        pragma = pragma.strip()
        if pragma:
            try:
                await db.execute(pragma)
                logger.debug(f"Applied pragma: {pragma}")
            except Exception as e:
                logger.warning(f"Failed to apply pragma {pragma}: {e}")

async def init_db():
    """Init DB com PRAGMAs otimizados."""
    # ... código existente ...
    
    async with aiosqlite.connect(DB_PATH) as db:
        await apply_optimized_pragmas(db)
        # ... resto do init ...
```

### 3. Pré-compilação de Regex

```python
# backend/artifacts/detector.py (modificado)

# Regex pré-compiladas (carregadas uma vez no startup)
import re

ARTIFACT_PATTERNS = {
    "image_url": re.compile(
        r'https?://[^\s<>\"\')\]]+\.(png|jpg|jpeg|gif|webp)(?:\?[^\s<>\"\')]*)?',
        re.IGNORECASE
    ),
    "code_block": re.compile(
        r'```[\w]*\n([\s\S]+?)```',
        re.MULTILINE
    ),
    "x_username": re.compile(
        r'@([A-Za-z0-9_]{1,15})',
        re.IGNORECASE
    ),
    "youtube_url": re.compile(
        r'https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[^\s<>\"\')\]]+',
        re.IGNORECASE
    ),
}

def detect_artifacts(text: str) -> Dict[str, List[str]]:
    """Detecta artefatos usando regex pré-compiladas."""
    artifacts = {}
    
    for artifact_type, pattern in ARTIFACT_PATTERNS.items():
        matches = pattern.findall(text)
        if matches:
            artifacts[artifact_type] = list(set(matches))  # Unique
    
    return artifacts
```

### 4. Integração com Chat Router

```python
# backend/routers/chat.py (modificado)
from ..cache.write_behind import write_behind_queue, WriteType

@router.post("/chat/completions")
async def chat_completions(request: ChatRequest):
    # ... processamento da request ...
    
    # Resposta gerada
    response_text = await generate_response(...)
    
    # Envia resposta para usuário PRIMEIRO
    yield f"data: {json.dumps({'response': response_text})}\n\n"
    
    # NOVO: Pós-processamento em write-behind
    await write_behind_queue.enqueue(
        write_type=WriteType.CRITICAL,  # Mensagem é crítica
        operation="save_message",
        data={
            "conversation_id": request.conversation_id,
            "role": "assistant",
            "content": response_text,
            "model_id": selected_model.id,
        },
    )
    
    # Cache, quota, artefatos podem esperar
    await write_behind_queue.enqueue(
        write_type=WriteType.DERIVED,
        operation="save_cache",
        data={
            "model_id": selected_model.id,
            "messages": request.messages + [{"role": "assistant", "content": response_text}],
            "response": response_text,
        },
    )
    
    await write_behind_queue.enqueue(
        write_type=WriteType.DERIVED,
        operation="update_quota",
        data={
            "model_id": selected_model.id,
            "increment": 1,
        },
    )
    
    await write_behind_queue.enqueue(
        write_type=WriteType.DERIVED,
        operation="detect_artifacts",
        data={
            "text": response_text,
            "conversation_id": request.conversation_id,
        },
    )
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/cache/write_behind.py        # Write-behind queue
```

### Arquivos a Modificar
```
backend/database.py                  # PRAGMAs otimizados
backend/artifacts/detector.py        # Regex pré-compiladas
backend/routers/chat.py              # Usar write-behind
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Latência pós-stream | ~35ms | ~5ms (critical only) | **-86%** |
| Commits SQLite por request | 4 | 1 (batched) | **-75%** |
| fsyncs por request | 4 | 1 (batched) | **-75%** |
| Throughput (requests/sec) | 28 | 35 | **+25%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_write_behind.py
import pytest
import asyncio
from backend.cache.write_behind import WriteBehindQueue, WriteType

@pytest.mark.asyncio
async def test_critical_write_immediate():
    """Writes critical devem executar imediatamente."""
    queue = WriteBehindQueue()
    executed = []
    
    async def mock_execute(data):
        executed.append(data)
    
    await queue.enqueue(
        WriteType.CRITICAL,
        "save_message",
        {"content": "test"},
        callback=mock_execute,
    )
    
    assert len(executed) == 1
    assert executed[0]["content"] == "test"

@pytest.mark.asyncio
async def test_derived_write_queued():
    """Writes derived devem ser enfileirados."""
    queue = WriteBehindQueue()
    
    # Enqueue derived write
    await queue.enqueue(
        WriteType.DERIVED,
        "save_cache",
        {"model_id": "test"},
    )
    
    # Deve estar na fila
    assert queue._queue.qsize() == 1
    
    # Flush
    await asyncio.sleep(0.2)  # Espera flush
    
    # Fila deve estar vazia
    assert queue._queue.qsize() == 0

@pytest.mark.asyncio
async def test_batch_commit():
    """Batch deve usar COMMIT único."""
    queue = WriteBehindQueue(max_batch_size=5)
    
    # Enqueue multiple derived writes
    for i in range(5):
        await queue.enqueue(
            WriteType.DERIVED,
            "save_cache",
            {"index": i},
        )
    
    # Espera processar
    await asyncio.sleep(0.3)
    
    stats = await queue.get_stats()
    assert stats["batched"] == 5
    assert stats["flushes"] >= 1
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Criar Write-Behind Queue
  - [ ] Criar `write_behind.py`
  - [ ] Implementar classe principal
  - [ ] Implementar batch processing
  - [ ] Testar unitariamente

- [ ] **Step 2:** Aplicar PRAGMAs
  - [ ] Adicionar PRAGMAs no `init_db()`
  - [ ] Testar performance do SQLite
  - [ ] Verificar WAL mode

- [ ] **Step 3:** Pré-compilar Regex
  - [ ] Mover regex para constants
  - [ ] Carregar no startup
  - [ ] Testar performance

- [ ] **Step 4:** Integrar com Chat
  - [ ] Separar critical vs derived writes
  - [ ] Enviar resposta primeiro
  - [ ] Post-process em background

- [ ] **Step 5:** Testes
  - [ ] Testar write-behind
  - [ ] Testar batching
  - [ ] Testar flush no shutdown

- [ ] **Step 6:** Deploy
  - [ ] Backup do banco
  - [ ] Deploy staging
  - [ ] Monitorar latência pós-stream
  - [ ] Verificar integridade dos dados

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Perder dados se crash | Média | Médio | Critical writes são síncronos |
| Fila acumulando | Baixa | Baixo | Flush periódico + limite de tamanho |
| ORM conflict com batching | Baixa | Baixo | Transações claras |
| Debugging mais difícil | Média | Baixo | Logs detalhados de cada job |

---

## 📈 Monitoramento

```python
# Adicionar métricas
WRITE_BEHIND_QUEUED = Counter(
    'write_behind_queued_total',
    'Jobs enfileirados'
)

WRITE_BEHIND_BATCHED = Counter(
    'write_behind_batched_total',
    'Jobs processados em batch'
)

WRITE_BEHIND_FLUSHES = Counter(
    'write_behind_flushes_total',
    'Flashes executados'
)

WRITE_BEHIND_QUEUE_DEPTH = Gauge(
    'write_behind_queue_depth',
    'Profundidade atual da fila'
)

WRITE_BEHIND_LATENCY_MS = Histogram(
    'write_behind_latency_ms',
    'Latência dos writes (critical vs derived)'
)
```

---

## ⚠️ Considerações Importantes

1. **Dados Críticos vs Derivados:**
   - **Críticos:** Mensagem do usuário, resposta do assistant
   - **Derivados:** Cache, quota, artefatos, logs
   - Só derivados vão para write-behind

2. **Flush no Shutdown:**
   - Garantir que fila seja flushada antes de fechar
   - Usar signal handlers para graceful shutdown

3. **Timeout de Fila:**
   - Se fila muito cheia, forçar flush
   - Alertar se jobs ficam muito tempo na fila

4. **Transações:**
   - Cada batch deve ser atômico
   - Rollback em caso de erro

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #7*  
*Responsável: Hermes Agent*
