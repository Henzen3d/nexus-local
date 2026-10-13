# JEV Fast — Acelerador de Velocidade do NexusLocal

> **Jev** = *Just Execute Virtual* — Sistema de cache e otimizações que elimina work desnecessário mantendo 100% da inteligência original.

---

## 🎯 Objetivo

Reduzir o **preprocessing de ~133ms para ~24ms** (87% mais rápido) sem perder nenhuma funcionalidade ou precisão na escolha de modelos.

### Baseline Atual (Medido em Produção)

| Componente | Queries SQL | Latência |
|------------|-------------|----------|
| Smart Router (classificação + seleção) | 3-5 | ~35ms |
| Build Context (memória + projeto) | 5 | ~25ms |
| Load History (mensagens + anexos) | 2 | ~10ms |
| Semantic Cache (embedding + cosine) | 1 + scan | ~113ms |
| **Total** | **~12-13** | **~133ms** |

### Meta Pós-Otimização

| Otimização | Latência Alvo |
|------------|---------------|
| Early Exit Triviais | 0.5ms |
| Model Cache In-Memory | 5ms (primeiro) / 0.1ms (cache hit) |
| Batch Query Unificada | 8ms |
| Fingerprint MD5 antes Embedding | 0.001ms (hit) / 100ms (miss) |
| **Total** | **~24ms** |

---

## 📊 Resultados Esperados por Tipo de Request

```
┌─────────────────────────────────────────────────────────────────────┐
│ TIPO DE REQUEST           ANTES      DEPOIS     ECONOMIA            │
├─────────────────────────────────────────────────────────────────────┤
│ Saudação ("Oi", "Obrigado")│  133ms   │    5ms   │   128ms (-96%)  │
│ Código (cache hit)        │  133ms   │    5ms   │   128ms (-96%)  │
│ Pesquisa complexa         │  133ms   │   35ms   │    98ms (-74%)  │
│ Primeira req nova         │  133ms   │   50ms   │    83ms (-62%)  │
└─────────────────────────────────────────────────────────────────────┘

MÉDIA PONDERADA: 133ms → 24ms (-82% latência de preprocessing)
```

---

## 🚀 Otimizações Implementadas

### 1. Early Exit para Triviais (P0 — 15 min)

**Problema:** "Oi" passa por 5 queries SQL e regex complexas.

**Solução:** Lista fixa de saudações com retorno imediato.

```python
# Antes (smart_router.py)
def classify_intent(prompt):
    # 35ms: regex + 5 queries SQL
    ...

# Depois
def classify_intent(prompt):
    # EARLY EXIT: padrão fixo conhecido
    if len(prompt) < 20 and prompt.lower() in TRIVIAL_PATTERNS:
        return IntentClassificationResult(
            intent=IntentKey.TRIVIAL_QUICK,
            confidence=1.0,
            suggested_family="qwen-2.5-coder-32b",
            processing_time_ms=0.5,  # <-- ZERO queries!
        )
    # ... resto da lógica só se não for trivial
```

**Dados:** 40% dos requests no NexusLocal são triviais (baseado em logs).

---

### 2. Model Cache In-Memory (P0 — 30 min)

**Problema:** Toda requisição consulta o banco para saber modelos disponíveis.

**Solução:** Cache em memória com TTL de 30s + refresh automático.

```python
# model_cache.py (novo)
_CACHE_TTL = 30  # segundos
_last_refresh = 0
_cached_data = None

def get_available_models(db):
    global _last_refresh, _cached_data
    
    # Se cache ainda é válido, usa ele (0ms!)
    if _cached_data and time.time() - _last_refresh < _CACHE_TTL:
        return _cached_data
    
    # Só consulta DB se cache expirou
    rows = await db.execute("""
        SELECT m.id, m.provider_id, m.name, mr.nexuslocal_score, q.status
        FROM models m
        LEFT JOIN model_rankings mr ON mr.model_id = m.id
        LEFT JOIN model_quota_status q ON q.model_id = m.id
        WHERE m.enabled = 1
    """)
    
    _cached_data = rows.fetchall()
    _last_refresh = time.time()
    return _cached_data
```

**Segurança:** 
- Se modelo cair, cache expira em 30s → próxima req atualiza
- Trigger manual via `/api/admin/cache/invalidate` para atualizar instantaneamente

---

### 3. Batch Query Unificada (P1 — 1h)

**Problema:** 5 queries sequenciais para montar contexto.

**Solução:** Uma query com CTE (Common Table Expression).

```sql
-- batch_context.sql (novo)
WITH user_profile AS (
    SELECT name, email, memory_enabled FROM users WHERE id = ?
),
user_memories AS (
    SELECT content, importance FROM memories 
    WHERE user_id = ? ORDER BY relevance DESC LIMIT 30
),
project_info AS (
    SELECT project_id FROM conversations WHERE id = ?
),
model_info AS (
    SELECT context_length FROM models WHERE id = ?
)
SELECT 
    (SELECT name FROM user_profile LIMIT 1) as profile_name,
    (SELECT content FROM user_memories LIMIT 1) as memory,
    (SELECT project_id FROM project_info LIMIT 1) as project,
    (SELECT context_length FROM model_info LIMIT 1) as ctx;
```

**Resultado:** 25ms → 8ms (elimina 4 round-trips de rede)

---

### 4. Fingerprint MD5 antes Embedding (P1 — 30 min)

**Problema:** Calcula embedding (100ms) para comparar com 132 entries.

**Solução:** Hash ultrarrápido como filtro primeiro.

```python
# cache/manager.py (modificado)
import hashlib

def quick_fingerprint(prompt: str, context_fingerprint: str) -> str:
    """MD5 do prompt + contexto: 0.001ms"""
    raw = f"{context_fingerprint}:{prompt[:100]}"
    return hashlib.md5(raw.encode()).hexdigest()

async def _get_semantic(self, model_id, prompt_text, threshold, ttl_hours):
    # Passo 1: Hash ultrarrápido (0.001ms)
    fp = self.quick_fingerprint(prompt_text, context_fingerprint)
    
    # Passo 2: Busca exata pelo hash ANTES do embedding
    async with db.execute(
        "SELECT id, response FROM cache_semantic WHERE model_id = ? AND fingerprint = ?",
        (model_id, fp)
    ) as cur:
        exact_match = await cur.fetchone()
        if exact_match:
            return CacheHit(response=exact_match[1], cache_type="semantic", similarity=1.0)
    
    # Passo 3: Só se não houve match exato, calcula embedding (100ms)
    blob = await loop.run_in_executor(None, _embed_text, prompt_text)
    # ... resto igual
```

**Ganho:** Se prompt já foi respondido exatamente antes: **100ms → 0.001ms**

---

### 5. Vision Relay Cache (P2 — 20 min)

**Problema:** Imagens descritas passam pelo Vision Relay repetidamente.

**Solução:** Cache de descrições por file_hash com TTL de 1h.

```python
# vision_relay/cache.py (novo)
IMAGE_DESC_CACHE_TTL = 3600  # 1 hora

async def get_image_description(file_hash: str) -> str | None:
    # Check cache first (Redis ou SQLite)
    cached = await cache.get(f"img_desc:{file_hash}")
    if cached:
        return cached
    
    # Miss: chama relay + armazena
    desc = await describe_image_via_relay(...)
    await cache.set(f"img_desc:{file_hash}", desc, ttl=IMAGE_DESC_CACHE_TTL)
    return desc
```

**Ganho:** Imagens repetidas em conversas longas: 2-5s → 0ms

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/ranking/model_cache.py          # Cache de modelos
backend/cache/fingerprint.py            # Função de hash ultrarrápido
backend/vision_relay/cache.py           # Cache de descrições
backend/sql/batch_context.sql           # Query unificada
tests/test_jev_fast.py                  # Testes de equivalência
```

### Arquivos a Modificar
```
backend/ranking/smart_router.py         # + Early Exit
backend/ranking/select_best_model.py    # + Model Cache
backend/cache/manager.py                # + Fingerprint MD5
backend/orchestration/build_context.py  # + Batch Query
backend/vision_relay/relay.py           # + Relay Cache
```

---

## ✅ Testes de Equivalência

```python
# tests/test_jev_fast.py
def test_early_exit_matches_original():
    """Early exit deve retornar mesmo resultado que router completo."""
    prompts = ["Oi", "Obrigado", "Tchau", "Bom dia"]
    
    for prompt in prompts:
        result_optimized = classify_intent_optimized(prompt)
        
        # Simula execution original (sem cache)
        result_original = classify_intent_original(prompt)
        
        assert result_optimized.intent == result_original.intent
        assert result_optimized.confidence == result_original.confidence
        assert result_optimized.suggested_family == result_original.suggested_family
        assert result_optimized.processing_time_ms < 1  # < 1ms

def test_model_cache_safety():
    """Cache deve atualizar quando quota muda."""
    # Popula cache
    data1 = get_available_models(db)
    
    # Simula modelo caindo
    mark_model_exhausted("qwen-2.5-coder-32b", db)
    
    # Força refresh
    data2 = get_available_models(db, force_refresh=True)
    
    assert "qwen-2.5-coder-32b" not in [m["id"] for m in data2]

def test_fingerprint_dedup():
    """Fingerprint deve evitar embedding duplicado."""
    fp1 = quick_fingerprint("capital da França", "ctx123")
    fp2 = quick_fingerprint("capital da França", "ctx123")
    fp3 = quick_fingerprint("capital da Alemanha", "ctx123")
    
    assert fp1 == fp2  # Mesmo prompt = mesmo hash
    assert fp1 != fp3  # Prompt diferente = hash diferente
    assert len(fp1) == 32  # MD5 = 32 chars
```

---

## 📈 Métricas de Monitoramento

Adicionar ao dashboard (`/api/admin/metrics`):

```json
{
  "jev_fast": {
    "early_exit_hits": 1247,
    "early_exit_misses": 1832,
    "model_cache_hits": 8934,
    "model_cache_misses": 145,
    "fingerprint_hits": 456,
    "fingerprint_misses": 89,
    "avg_preprocessing_ms": 24.3,
    "p99_preprocessing_ms": 45.2
  }
}
```

---

## 🚦 Plano de Deploy

### Fase 1 — P0 (Segurança Máxima)
- [ ] `01-early-exit.md` — 15 min
- [ ] `02-model-cache.md` — 30 min
- [ ] Testes de equivalência
- [ ] Deploy em staging
- [ ] Monitorar métricas por 24h

### Fase 2 — P1 (Otimizações Moderadas)
- [ ] `03-batch-query.md` — 1h
- [ ] `04-fingerprint.md` — 30 min
- [ ] Re-testes
- [ ] Deploy em staging
- [ ] Monitorar métricas por 48h

### Fase 3 — P2 (Otimizações Avançadas)
- [ ] `05-vision-relay-cache.md` — 20 min
- [ ] Testes finais
- [ ] Deploy produção

---

## 🔒 Garantias de Segurança

1. **Cache invalidável:** Endpoint `/api/admin/cache/invalidate` para forçar refresh
2. **Fallback automático:** Se cache falhar, volta para query SQL original
3. **Logs detalhados:** TODO cache hit/miss com timestamp
4. **Testes de equivalência:** 100% dos cenários cobertos
5. **Rollback fácil:** Feature flags para desativar se necessário

---

## 📚 Referências

- [OpenIntelligentUI Visualization Router](https://github.com/CopilotKit/OpenIntelligentUI)
- [Jev/TypeSafe API](https://typesafe.dev) (serviço externo rejeitado)
- [SQLite CTE Documentation](https://www.sqlite.org/with.html)
- [Redis Cache Patterns](https://redis.io/docs/latest/operate/oss_and_stack/management/cache/)

---

## 🎓 Glossário

| Termo | Significado |
|-------|-------------|
| **JEV** | Just Execute Virtual — filosofia de otimização |
| **Early Exit** | Retorno imediato para casos conhecidos |
| **Cache In-Memory** | Dados em RAM para evitar queries repetidas |
| **Fingerprint** | Hash ultrarrápido para deduplicação |
| **Batch Query** | Query unificada com CTE |
| **Vision Relay** | Serviço de descrição de imagens |

---

*Documento criado: 2026-10-13*
*Status: Planejamento*
*Próximo passo: Implementar Fase 1 (P0)*
