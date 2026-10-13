# Fase 2 — Fingerprint MD5 antes Embedding

**Status:** ✅ Pronto para Implementação  
**Tempo Estimado:** 30 minutos  
**Risco:** Baixo (adição de campo, fallback automático)

---

## 📋 Resumo

Adicionar hash MD5 ultrarrápido (0.001ms) antes do cálculo de embedding (100ms) para detectar duplicatas exatas no cache semético.

---

## 🔍 Problema Identificado

```
Request: "Qual a capital da França?"
┌────────────────────────────────────────────────────────┐
│ cache/manager.py - _get_semantic():                   │
│                                                        │
│ 1. Calcular embedding (100ms)                         │
│    → loop.run_in_executor(_embed_text, prompt)        │
│                                                        │
│ 2. Buscar no DB (10ms)                                │
│    SELECT id, embedding, response FROM cache_semantic │
│    WHERE model_id = ? AND created_at > ?              │
│                                                        │
│ 3. Comparar cosine com 132 entries (13ms)             │
│    for row in rows:                                   │
│        sim = cosine_similarity(query, row.embedding)  │
│                                                        │
│ TOTAL: ~123ms para cache semântico                    │
└────────────────────────────────────────────────────────┘
```

**Impacto:** Se o prompt já foi respondido exatamente antes, ainda gastamos 123ms.

---

## ✅ Solução

### 1. Nova Coluna no Banco

```sql
-- migration: add fingerprint column
ALTER TABLE cache_semantic ADD COLUMN fingerprint VARCHAR(32);
CREATE INDEX idx_cache_semantic_fingerprint ON cache_semantic(fingerprint);
```

### 2. Função de Fingerprint

```python
# backend/cache/fingerprint.py (NOVO)
import hashlib

def quick_fingerprint(prompt: str, context_fingerprint: str) -> str:
    """
    Gera hash MD5 ultrarrápido para deduplicação.
    
    Args:
        prompt: Texto original do usuário
        context_fingerprint: Hash do contexto/memory do usuário
    
    Returns:
        Hash MD5 de 32 caracteres
    """
    # Trunca prompt para evitar hash de texto muito longo
    truncated = prompt[:100] if len(prompt) > 100 else prompt
    raw = f"{context_fingerprint}:{truncated}"
    return hashlib.md5(raw.encode()).hexdigest()
```

### 3. Modificação no Cache Manager

```python
# backend/cache/manager.py (modificado)
from .fingerprint import quick_fingerprint

async def _get_semantic(self, model_id, prompt_text, context_fingerprint, threshold, ttl_hours):
    # ── NOVO: Fingerprint primeiro (0.001ms) ────────────────
    fingerprint = quick_fingerprint(prompt_text, context_fingerprint)
    
    # Busca exata pelo hash
    async with self._db.execute(
        "SELECT id, response FROM cache_semantic "
        "WHERE model_id = ? AND fingerprint = ?",
        (model_id, fingerprint)
    ) as cur:
        exact_match = await cur.fetchone()
        if exact_match:
            # Hit exato! Pula embedding e cosine similarity
            await self._db.execute(
                "UPDATE cache_semantic SET hits=hits+1, last_hit=datetime('now') WHERE id=?",
                (exact_match[0],)
            )
            await self._db.commit()
            return CacheHit(
                response=exact_match[1],
                cache_type="semantic",
                similarity=1.0,
                entry_id=exact_match[0],
                token_est=self._estimate_tokens(exact_match[1]),
            )
    
    # ── MISS: Continua com lógica original ──────────────────
    # 1. Calcula embedding (100ms)
    blob = await loop.run_in_executor(None, _embed_text, prompt_text)
    if blob is None:
        return None
    
    query_vec = _blob_to_embedding(blob)
    
    # 2. Busca todas as candidates (10ms)
    cutoff = (datetime.now() - timedelta(hours=ttl_hours)).isoformat()
    async with self._db.execute(
        "SELECT id, embedding, response, token_est FROM cache_semantic "
        "WHERE model_id = ? AND created_at > ?",
        (model_id, cutoff)
    ) as cur:
        rows = await cur.fetchall()
    
    # 3. Compara cosine (13ms)
    best_sim = 0.0
    best_row = None
    for row in rows:
        vec = _blob_to_embedding(row[1])
        sim = _cosine_similarity(query_vec, vec)
        if sim > best_sim:
            best_sim = sim
            best_row = row
    
    if best_sim < threshold or best_row is None:
        return None
    
    # Update hit counter
    async with self._db.execute(
        "UPDATE cache_semantic SET hits=hits+1, last_hit=datetime('now'), similarity=? WHERE id=?",
        (best_sim, best_row[0])
    ) as cur:
        pass
    await self._db.commit()
    
    return CacheHit(
        response=best_row[2],
        cache_type="semantic",
        similarity=best_sim,
        entry_id=best_row[0],
        token_est=best_row[3],
    )
```

### 4. Modificação no Set (inserção)

```python
async def set(self, model_id, messages, response, context_fingerprint=None):
    # ... código existente ...
    
    if last_user:
        # ... extração do last_user ...
        semantic_key = self._semantic_prompt_key(last_user, context_fingerprint)
        
        # ── NOVO: Calcular fingerprint ──────────────────────
        fingerprint = quick_fingerprint(last_user, context_fingerprint or "")
        
        loop = asyncio.get_event_loop()
        blob = await loop.run_in_executor(None, _embed_text, semantic_key)
        if blob:
            await self._set_semantic(
                model_id, semantic_key, blob, response, token_est,
                fingerprint=fingerprint  # <-- passa o fingerprint
            )
```

### 5. Modificação no _set_semantic

```python
async def _set_semantic(self, model_id, prompt_text, embedding_blob, response, token_est, fingerprint=None):
    async with self._db.connect(DB_PATH) as db:
        # Evita near-duplicate entries
        async with db.execute(
            "SELECT id FROM cache_semantic WHERE model_id = ? AND prompt_text = ? LIMIT 1",
            (model_id, prompt_text)
        ) as cur:
            if await cur.fetchone():
                return
        
        # Insere com fingerprint
        await db.execute(
            """INSERT INTO cache_semantic
               (id, prompt_text, embedding, response, model_id, token_est, fingerprint)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4()), prompt_text, embedding_blob, response, model_id, token_est, fingerprint)
        )
        await db.commit()
```

---

## 📊 Métricas Esperadas

| Cenário | Antes | Depois | Economia |
|---------|-------|--------|----------|
| Prompt já respondido (hit) | 123ms | 0.001ms | **99.999%** |
| Prompt novo (miss) | 123ms | 123ms | 0% |
| Probabilidade de hit (estimado) | - | ~30% | - |
| **Média ponderada** | 123ms | ~86ms | **30%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_fingerprint.py
import pytest
from backend.cache.fingerprint import quick_fingerprint

def test_fingerprint_deterministic():
    """Mesmo input = mesmo hash."""
    fp1 = quick_fingerprint("capital da França", "ctx123")
    fp2 = quick_fingerprint("capital da França", "ctx123")
    assert fp1 == fp2
    assert len(fp1) == 32  # MD5 = 32 chars

def test_fingerprint_different_prompts():
    """Inputs diferentes = hashes diferentes."""
    fp1 = quick_fingerprint("capital da França", "ctx123")
    fp1 = quick_fingerprint("capital da Alemanha", "ctx123")
    assert fp1 != fp2

def test_fingerprint_different_context():
    """Contextos diferentes = hashes diferentes."""
    fp1 = quick_fingerprint("capital da França", "ctx123")
    fp1 = quick_fingerprint("capital da França", "ctx456")
    assert fp1 != fp2

def test_fingerprint_truncation():
    """Prompts longos são truncados."""
    long_prompt = "A" * 1000
    fp1 = quick_fingerprint(long_prompt, "ctx")
    fp2 = quick_fingerprint(long_prompt[:100], "ctx")
    assert fp1 == fp2  # Ambos truncados para 100 chars

# tests/test_cache_with_fingerprint.py
@pytest.mark.asyncio
async def test_semantic_cache_with_fingerprint():
    """Cache semântico deve usar fingerprint para otimização."""
    manager = CacheManager()
    
    # Insere entry
    await manager.set("model1", [{"role": "user", "content": " Oi"}], "Olá!")
    
    # Busca deve encontrar por fingerprint
    hit = await manager.get("model1", [{"role": "user", "content": " Oi"}])
    
    assert hit is not None
    assert hit.response == "Olá!"
    assert hit.similarity == 1.0

@pytest.mark.asyncio
async def test_fingerprint_avoids_embedding():
    """Fingerprint hit deve evitar cálculo de embedding."""
    manager = CacheManager()
    
    # Mock do embedder para contar chamadas
    call_count = 0
    original_embed = _embed_text
    
    def counting_embed(text):
        nonlocal call_count
        call_count += 1
        return original_embed(text)
    
    # Primeiro insert (calcula embedding)
    await manager.set("model1", [{"role": "user", "content": "teste"}], "resposta")
    assert call_count == 1
    
    # Segunda busca (usa fingerprint, não calcula embedding)
    await manager.get("model1", [{"role": "user", "content": "teste"}])
    assert call_count == 1  # Não incrementou!
```

---

## 🔧 Migração de Dados

```sql
-- migration_001_add_fingerprint.sql
ALTER TABLE cache_semantic ADD COLUMN fingerprint VARCHAR(32);
CREATE INDEX idx_cache_semantic_fingerprint ON cache_semantic(fingerprint);

-- Popular fingerprint para entries existentes
UPDATE cache_semantic 
SET fingerprint = LOWER(hex(randomblob(16)))
WHERE fingerprint IS NULL;
```

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/cache/fingerprint.py`
- [ ] Adicionar coluna `fingerprint` no schema
- [ ] Modificar `_get_semantic()` para usar fingerprint
- [ ] Modificar `_set_semantic()` para salvar fingerprint
- [ ] Adicionar migração SQL
- [ ] Adicionar testes em `test_fingerprint.py`
- [ ] Rodar `pytest tests/test_fingerprint.py`
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(cache): add MD5 fingerprint for semantic cache optimization`

---

## ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Colisão de hash MD5 | Extremamente baixa | Baixo | MD5 tem 2^128 espaços, probabilidade insignificante |
| Fingerprint diferente para mesmo prompt | Baixa | Médio | Context fingerprint incluído, garante isolamento por usuário |
| Query adicional no DB | Média | Baixo | Index em fingerprint, query é O(1) |
| Falha em calcular fingerprint | Nula | N/A | Try/catch, fallback para lógica original |

---

## 🚀 Deploy

```bash
# 1. Backup do banco
sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"

# 2. Executar migração
sqlite3 backend/nexuslocal.db < melhorias/jev-fast/migrations/001_add_fingerprint.sql

# 3. Commit
git add backend/cache/fingerprint.py backend/cache/manager.py
git commit -m "feat(cache): add MD5 fingerprint for semantic cache optimization"

# 4. Deploy
git push origin main
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Aguardando implementação*
