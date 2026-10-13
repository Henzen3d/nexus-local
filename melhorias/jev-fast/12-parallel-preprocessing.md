# Plano: Paralelização das Fases de Pré-Processamento

**Status:** 🆕 Novo  
**Tempo Estimado:** 1.5h  
**Risco:** Médio (dependências entre fases)

---

## 📋 Resumo

Oportunidade identificada pela análise Claude: paralelizar fases independentes do pré-processamento (Router, Build Context, History) usando asyncio.gather.

---

## 🔍 Problema Identificado

```
Pipeline atual (sequencial):
┌────────────────────────────────────────────────────────┐
│ Request Received                                       │
│    │                                                   │
│    ▼                                                   │
│ ┌──────────────┐  35ms  ┌──────────────────────────┐  │
│ │ Smart Router │───────▶│ Classify + Select Model  │  │
│ └──────────────┘        └──────────────────────────┘  │
│    │                                                   │
│    ▼                                                   │
│ ┌──────────────┐  25ms  ┌──────────────────────────┐  │
│ │Build Context │───────▶│ Memórias + Projeto       │  │
│ └──────────────┘        └──────────────────────────┘  │
│    │                                                   │
│    ▼                                                   │
│ ┌──────────────┐  10ms  ┌──────────────────────────┐  │
│ │ Load History │───────▶│ Mensagens + Anexos       │  │
│ └──────────────┘        └──────────────────────────┘  │
│    │                                                   │
│    ▼                                                   │
│ TOTAL: ~70ms (sequencial)                               │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. Mapeamento de Dependências

```
FASE 1: Smart Router (inicial)
  ├─ NÃO depende de nada
  ├─ Retorna: model_id, intent, complexity
  └─ SAÍDA usada por: FASE 2 (modelo selecionado)

FASE 2: Build Context (parcialmente paralelizável)
  ├─ Depende de: model_id (da FASE 1)
  ├─ Sub-fases independentes:
  │   ├─ Query memórias (5ms)
  │   ├─ Query projeto (5ms)
  │   ├─ Query configurações (5ms)
  │   └─ Load history (5ms) ← PODE parallelizar com memórias!
  └─ SAÍDA: context_dict

FASE 3: Cache Check
  ├─ Depende de: model_id (da FASE 1)
  ├─ Depende de: context (da FASE 2)
  └─ SAÍDA: cache_hit or None
```

### 2. Implementação do Paralelismo

```python
# backend/orchestration/pipeline.py (NOVO)
import asyncio
from typing import Dict, Any, Tuple

async def run_parallel_phases(
    request_ctx: RequestContext,
) -> Dict[str, Any]:
    """
    Executa fases independentes em paralelo.
    
    Estrutura:
    - Fase 1 (Router)执行 primeiro (obrigatório)
    - Após router, executa em paralelo:
      - Build Context (memórias + histórico)
      - Cache Check (se aplicável)
    """
    
    # FASE 1: Router (obrigatório, sequencial)
    logger.info("Fase 1: Smart Router")
    router_result = await smart_router.classify_and_select(
        prompt=request_ctx.messages,
        user_id=request_ctx.user_id,
    )
    request_ctx.model_id = router_result.model_id
    request_ctx.intent = router_result.intent
    
    # FASE 2 & 3: Paralelo
    logger.info("Fases 2-3: Paralelizando...")
    
    # Tasks independentes
    tasks = [
        build_context_parallel(request_ctx, router_result),
        check_cache_parallel(request_ctx, router_result),
    ]
    
    # Executa em paralelo
    context_result, cache_result = await asyncio.gather(*tasks)
    
    return {
        "router": router_result,
        "context": context_result,
        "cache": cache_result,
    }


async def build_context_parallel(
    request_ctx: RequestContext,
    router_result: RouterResult,
) -> Dict[str, Any]:
    """Build context com sub-tasks paralelas."""
    
    # Sub-tasks independentes
    tasks = [
        get_user_memories(request_ctx.user_id),
        get_project_info(request_ctx.project_id),
        get_system_config(),
        load_history(request_ctx.conversation_id),
    ]
    
    # Executa em paralelo
    memories, project, config, history = await asyncio.gather(*tasks)
    
    # Monta contexto
    return {
        "memories": memories,
        "project": project,
        "config": config,
        "history": history,
        "fingerprint": compute_fingerprint(memories, project),
    }


async def check_cache_parallel(
    request_ctx: RequestContext,
    router_result: RouterResult,
) -> Optional[CacheHit]:
    """Check cache de forma independente."""
    
    # Só check se não for follow-up (gate)
    if not await should_use_semantic_cache(request_ctx):
        return None
    
    return await cache_manager.get(
        model_id=router_result.model_id,
        messages=request_ctx.messages,
        context_fingerprint=None,  # Será preenchido depois
        request_ctx=request_ctx,
    )
```

### 3. Conexões SQLite Separadas

```python
# backend/database.py (modificado)

# Pool de conexões de leitura para parallelismo
_READ_CONNECTIONS = {}
_MAX_READ_CONNECTIONS = 5

async def get_read_connection() -> aiosqlite.Connection:
    """
    Obtém conexão de leitura do pool.
    SQLite WAL mode permite múltiplas leituras concorrentes.
    """
    loop = asyncio.get_event_loop()
    thread_id = threading.get_ident()
    
    if thread_id not in _READ_CONNECTIONS:
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute("PRAGMA query_only = ON")  # Só leitura
        _READ_CONNECTIONS[thread_id] = conn
    
    return _READ_CONNECTIONS[thread_id]


async def close_read_connections():
    """Fecha todas as conexões de leitura (shutdown)."""
    for conn in _READ_CONNECTIONS.values():
        await conn.close()
    _READ_CONNECTIONS.clear()
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/orchestration/pipeline.py     # Pipeline paralelizado
backend/database.py                   # Pool de conexões (modificações)
```

### Arquivos a Modificar
```
backend/routers/chat.py               # Usar novo pipeline
backend/orchestration/build_context.py # Adaptar para paralelo
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Latência fases 2+3 | 35ms (seq) | 25ms (par) | **-29%** |
| Latência total pipeline | 70ms | 60ms | **-14%** |
| Throughput (requests/sec) | 14 | 17 | **+21%** |
| Conexões SQLite simultâneas | 1 | 4 | Aumento controlado |

**Nota:** O ganho é moderado porque as fases têm dependências. O maior ganho vem da paralelização das sub-tasks dentro do Build Context.

---

## 🧪 Testes Requeridos

```python
# tests/test_parallel_pipeline.py
import pytest
import asyncio

@pytest.mark.asyncio
async def test_parallel_phases_execute_concurrently():
    """Fases devem executar em paralelo."""
    ctx = RequestContext(...)
    
    start = time.time()
    result = await run_parallel_phases(ctx)
    elapsed = time.time() - start
    
    # Deve ser mais rápido que sequencial
    assert elapsed < 0.04  # < 40ms
    
    # Todas as fases devem completar
    assert "router" in result
    assert "context" in result
    assert "cache" in result

@pytest.mark.asyncio
async def test_dependency_order_maintained():
    """Dependências devem ser respeitadas."""
    ctx = RequestContext(...)
    
    # Router deve rodar antes de Context
    router_called = False
    context_called = False
    
    async def mock_router(*args, **kwargs):
        nonlocal router_called
        router_called = True
        return RouterResult(model_id="test")
    
    async def mock_context(*args, **kwargs):
        nonlocal context_called
        context_called = True
        assert router_called  # Router deve ter chamado primeiro
        return {}
    
    # Setup mocks...
    await run_parallel_phases(ctx)

@pytest.mark.asyncio
async def test_read_connections_pool():
    """Pool de conexões deve funcionar."""
    conn1 = await get_read_connection()
    conn2 = await get_read_connection()
    
    # Mesmo thread deve ter mesma conexão
    assert conn1 is conn2
    
    # Threads diferentes devem ter conexões diferentes
    connections = set()
    
    def get_conn():
        conn = asyncio.get_event_loop().run_until_complete(
            get_read_connection()
        )
        connections.add(conn)
    
    threads = [threading.Thread(target=get_conn) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Deve ter no máximo 5 conexões (limite do pool)
    assert len(connections) <= 5
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Mapear dependências
  - [ ] Documentar quais fases podem paralelizar
  - [ ] Identificar pontos de sincronização
  - [ ] Definir timeout para tasks

- [ ] **Step 2:** Implementar pool de conexões
  - [ ] Criar `get_read_connection()`
  - [ ] Implementar `_READ_CONNECTIONS` dict
  - [ ] Adicionar `PRAGMA query_only = ON`
  - [ ] Implementar `close_read_connections()`

- [ ] **Step 3:** Implementar pipeline paralelizado
  - [ ] Criar `run_parallel_phases()`
  - [ ] Implementar `build_context_parallel()`
  - [ ] Implementar `check_cache_parallel()`
  - [ ] Adicionar handling de erros por task

- [ ] **Step 4:** Integrar com chat router
  - [ ] Atualizar endpoint `/chat/completions`
  - [ ] Passar RequestContext
  - [ ] Tratar resultados paralelos

- [ ] **Step 5:** Testes
  - [ ] Testar paralelismo
  - [ ] Testar ordenação de dependências
  - [ ] Testar pool de conexões
  - [ ] Benchmark de performance

- [ ] **Step 6:** Deploy
  - [ ] Backup do banco
  - [ ] Deploy em staging
  - [ ] Monitorar conexões SQLite
  - [ ] Ajustar pool size se necessário

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Race condition no SQLite | Baixa | Médio | Pool de conexões + query_only |
| Memory leak (conexões não fechadas) | Média | Médio | Try/finally + close em shutdown |
| Ordenação incorreta de dependências | Baixa | Alto | Testes de ordenação obrigatórios |
| Timeout em tasks lentas | Média | Baixo | asyncio.wait_for com timeout |
| Aumento de carga no DB | Média | Médio | Limitar pool a 5 conexões |

---

## 📈 Monitoramento

```python
# Adicionar métricas
PARALLEL_PHASES_EXECUTED = Counter(
    'parallel_phases_executed_total',
    'Total de execuções paralelas'
)

PARALLEL_PHASES_TIMINGS = Histogram(
    'parallel_phases_timing_seconds',
    'Tempo de cada fase paralela'
)

SQLITE_READ_CONNECTIONS_ACTIVE = Gauge(
    'sqlite_read_connections_active',
    'Conexões de leitura ativas'
)

SQLITE_READ_CONNECTIONS_MAX = Gauge(
    'sqlite_read_connections_max',
    'Maximo de conexões de leitura'
)
```

---

## ⚠️ Considerações Importantes

1. **SQLite WAL Mode:** O banco deve estar em WAL mode para permitir leituras concorrentes
   ```sql
   PRAGMA journal_mode=WAL;
   ```

2. **query_only:** Todas as conexões de leitura devem ter `PRAGMA query_only = ON`
   para evitar escrita acidental

3. **Timeout:** Tasks paralelas devem ter timeout para evitar hanging
   ```python
   await asyncio.wait_for(task, timeout=5.0)
   ```

4. **Error Handling:** Erros em uma task não devem quebrar outras
   ```python
   results = await asyncio.gather(*tasks, return_exceptions=True)
   ```

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #3*  
*Responsável: Hermes Agent*
