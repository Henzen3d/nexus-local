# Fase 2 — Batch Query Unificada para Context

**Status:** ✅ Pronto para Implementação  
**Tempo Estimado:** 1 hora  
**Risco:** Médio (mudança na estrutura de queries)

---

## 📋 Resumo

Unificar 5 queries SQL sequenciais em uma única query com CTE (Common Table Expression) para montar o contexto do usuário.

---

## 🔍 Problema Identificado

```
Request: "Me ajuda com um projeto de Python"
┌────────────────────────────────────────────────────────┐
│ build_context.py - build_memory_context():             │
│                                                        │
│ Query 1: Perfil do usuário (5ms)                      │
│   SELECT * FROM users WHERE id = ?                     │
│                                                        │
│ Query 2: Memórias relevantes (5ms)                     │
│   SELECT * FROM memories WHERE user_id = ?             │
│   ORDER BY relevance DESC LIMIT 30                     │
│                                                        │
│ Query 3: Summary global (5ms)                          │
│   SELECT * FROM memory_summaries                       │
│   WHERE user_id = ? AND type = 'global'                │
│                                                        │
│ Query 4: Projeto ativo (5ms)                           │
│   SELECT project_id FROM conversations WHERE id = ?    │
│                                                        │
│ Query 5: Contexto do modelo (5ms)                      │
│   SELECT context_length FROM models WHERE id = ?       │
│                                                        │
│ TOTAL: 25ms (5 round-trips de rede)                    │
└────────────────────────────────────────────────────────┘
```

**Impacto:** 5 round-trips de rede podem ser reduzidos para 1.

---

## ✅ Solução

### 1. Nova Query com CTE

```sql
-- backend/sql/batch_context.sql
WITH user_profile AS (
    SELECT 
        id, name, email, memory_enabled,
        ROW_NUMBER() OVER (ORDER BY id) as rn
    FROM users
    WHERE id = :user_id
),
user_memories AS (
    SELECT 
        content, importance, created_at,
        ROW_NUMBER() OVER (ORDER BY relevance DESC) as rn
    FROM memories
    WHERE user_id = :user_id
    AND is_active = 1
    LIMIT 30
),
global_summary AS (
    SELECT 
        content, updated_at,
        ROW_NUMBER() OVER (ORDER BY updated_at DESC) as rn
    FROM memory_summaries
    WHERE user_id = :user_id
    AND type = 'global'
    LIMIT 1
),
project_info AS (
    SELECT 
        project_id,
        ROW_NUMBER() OVER (ORDER BY updated_at DESC) as rn
    FROM conversations
    WHERE id = :conversation_id
    LIMIT 1
),
model_info AS (
    SELECT 
        context_length,
        ROW_NUMBER() OVER (ORDER BY id) as rn
    FROM models
    WHERE id = :model_id
    LIMIT 1
)
SELECT 
    -- User profile (col 1-4)
    up.id as user_id,
    up.name as user_name,
    up.email as user_email,
    up.memory_enabled as memory_enabled,
    -- User memories (col 5-7, max 30 rows)
    um.content as memory_content,
    um.importance as memory_importance,
    um.created_at as memory_created_at,
    -- Global summary (col 8-9)
    gs.content as global_summary_content,
    gs.updated_at as global_summary_updated_at,
    -- Project info (col 10)
    pi.project_id as active_project_id,
    -- Model info (col 11)
    mi.context_length as model_context_length
FROM user_profile up
LEFT JOIN user_memories um ON 1=1
LEFT JOIN global_summary gs ON 1=1
LEFT JOIN project_info pi ON 1=1
LEFT JOIN model_info mi ON 1=1
WHERE up.rn = 1
ORDER BY um.rn;
```

### 2. Implementação Python

```python
# backend/orchestration/batch_context.py (NOVO)
import aiosqlite
from pathlib import Path
from typing import Dict, Any, Optional, List

SQL_PATH = Path(__file__).parent.parent / "sql" / "batch_context.sql"


async def fetch_batch_context(
    db: aiosqlite.Connection,
    user_id: str,
    conversation_id: str,
    model_id: str,
) -> Dict[str, Any]:
    """
    Busca todo o contexto em uma única query com CTE.
    
    Returns:
        Dict com:
        - user_profile: dict com id, name, email, memory_enabled
        - memories: list of dicts com content, importance, created_at
        - global_summary: dict com content, updated_at ou None
        - project_id: str or None
        - model_context_length: int
    """
    sql = SQL_PATH.read_text()
    
    params = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "model_id": model_id,
    }
    
    async with db.execute(sql, params) as cur:
        rows = await cur.fetchall()
    
    if not rows:
        return {
            "user_profile": None,
            "memories": [],
            "global_summary": None,
            "project_id": None,
            "model_context_length": 8192,
        }
    
    # Processa resultados
    user_profile = None
    memories = []
    global_summary = None
    project_id = None
    model_context_length = 8192
    
    for row in rows:
        # User profile (primeira linha)
        if user_profile is None:
            user_profile = {
                "id": row[0],
                "name": row[1],
                "email": row[2],
                "memory_enabled": bool(row[3]),
            }
        
        # Memories (linhas 2-31)
        if row[4] is not None:
            memories.append({
                "content": row[4],
                "importance": row[5],
                "created_at": row[6],
            })
        
        # Global summary (última linha, se existir)
        if row[7] is not None and global_summary is None:
            global_summary = {
                "content": row[7],
                "updated_at": row[8],
            }
        
        # Project ID (última linha, se existir)
        if row[9] is not None and project_id is None:
            project_id = row[9]
        
        # Model context length (última linha, se existir)
        if row[10] is not None and model_context_length == 8192:
            model_context_length = int(row[10])
    
    return {
        "user_profile": user_profile,
        "memories": memories[:30],  # Garante limite
        "global_summary": global_summary,
        "project_id": project_id,
        "model_context_length": model_context_length,
    }
```

### 3. Integração com build_context.py

```python
# backend/orchestration/build_context.py (modificado)
from .batch_context import fetch_batch_context

async def build_memory_context(
    user: dict | None,
    conversation_id: str,
    user_message: str,
    use_memory: bool,
    provider_id: str,
    model_id: str,
) -> tuple[str, str]:
    """Versão otimizada com batch query."""
    
    if not user or "id" not in user or not use_memory:
        return "", "nomem"
    
    user_id = user["id"]
    
    try:
        # ── NOVO: Busca batch em 1 query ─────────────────────
        context_data = await fetch_batch_context(
            db, user_id, conversation_id, model_id
        )
        
        profile = context_data["user_profile"]
        mem_rows = context_data["memories"]
        global_sum = context_data["global_summary"]
        project_id = context_data["project_id"]
        ctx_window = context_data["model_context_length"]
        
        # ... resto da lógica permanece igual ...
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Queries SQL | 5 | 1 | **-80%** |
| Round-trips de rede | 5 | 1 | **-80%** |
| Latência (estimada) | 25ms | 8ms | **-68%** |
| Complexidade do código | Alta | Média | Reduzida |

---

## 🧪 Testes Requeridos

```python
# tests/test_batch_context.py
import pytest
import aiosqlite
from backend.orchestration.batch_context import fetch_batch_context

@pytest.mark.asyncio
async def test_fetch_batch_context_returns_all_data():
    """Deve retornar perfil, memórias, summary e projeto."""
    db = await aiosqlite.connect(":memory:")
    # ... setup de tabelas com dados ...
    
    result = await fetch_batch_context(
        db,
        user_id="user1",
        conversation_id="conv1",
        model_id="model1",
    )
    
    assert result["user_profile"] is not None
    assert result["user_profile"]["id"] == "user1"
    assert len(result["memories"]) > 0
    assert result["global_summary"] is not None
    assert result["project_id"] is not None
    assert result["model_context_length"] == 128000

@pytest.mark.asyncio
async def test_fetch_batch_context_empty():
    """Deve retornar defaults quando não há dados."""
    db = await aiosqlite.connect(":memory:")
    # ... tabelas vazias ...
    
    result = await fetch_batch_context(
        db,
        user_id="unknown_user",
        conversation_id="unknown_conv",
        model_id="unknown_model",
    )
    
    assert result["user_profile"] is None
    assert result["memories"] == []
    assert result["global_summary"] is None
    assert result["project_id"] is None
    assert result["model_context_length"] == 8192  # Default

@pytest.mark.asyncio
async def test_fetch_batch_context_limits_memories():
    """Deve limitar memórias a 30."""
    db = await aiosqlite.connect(":memory:")
    # ... insere 50 memórias ...
    
    result = await fetch_batch_context(db, ...)
    
    assert len(result["memories"]) <= 30
```

---

## ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Query CTE muito complexa | Baixa | Médio | Testes de performance com 10k linhas |
| SQLite não suporta CTE | Nula | N/A | SQLite 3.8.3+ suporta (versão atual é 3.45+) |
| Ordem das colunas confusa | Média | Baixo | Usar named tuples ou dataclasses para parsing |
| Performance pior que múltiplas queries | Baixa | Médio | Benchmark contra abordagem atual |

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/sql/batch_context.sql`
- [ ] Criar `backend/orchestration/batch_context.py`
- [ ] Modificar `build_memory_context()` para usar batch
- [ ] Adicionar testes em `test_batch_context.py`
- [ ] Rodar benchmark comparativo (antes/depois)
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(context): unify 5 queries into single CTE batch query`

---

## 🚀 Deploy

```bash
# 1. Backup do banco
sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"

# 2. Commit
git add backend/sql/batch_context.sql backend/orchestration/batch_context.py backend/orchestration/build_context.py
git commit -m "feat(context): unify 5 queries into single CTE batch query"

# 3. Deploy
git push origin main
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

---

## 📈 Benchmark (Pós-Implementação)

```python
# scripts/benchmark_batch_query.py
import asyncio
import time
import aiosqlite

async def benchmark():
    db = await aiosqlite.connect("backend/nexuslocal.db")
    
    # Mede query individual (5x)
    start = time.perf_counter()
    for _ in range(5):
        await db.execute("SELECT * FROM users WHERE id = ?", ("user1",))
        await db.execute("SELECT * FROM memories WHERE user_id = ?", ("user1",))
        # ... outras 3 queries
    individual_time = time.perf_counter() - start
    
    # Mede query batch (1x)
    start = time.perf_counter()
    for _ in range(5):
        await db.execute(SQL_BATCH, {"user_id": "user1"})
    batch_time = time.perf_counter() - start
    
    print(f"Individual: {individual_time*1000:.1f}ms")
    print(f"Batch: {batch_time*1000:.1f}ms")
    print(f"Economia: {(individual_time - batch_time) / individual_time * 100:.1f}%")

asyncio.run(benchmark())
```

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Aguardando implementação*
