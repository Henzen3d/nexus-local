# Plano: Gate do Cache Semântico + Índice em RAM

**Status:** 🆕 Novo  
**Tempo Estimado:** 2h  
**Risco:** Médio (mudança de schema)

---

## 📋 Resumo

Oportunidade identificada pela análise Claude: implementar gate inteligente para cache semântico e carregar índice em RAM para evitar scan completo a cada request.

---

## 🔍 Problema Identificado

```
Request: "Continue" ou "e o segundo ponto?"
┌────────────────────────────────────────────────────────┐
│ Situação:                                              │
│ • Follow-up sem contexto próprio                       │
│ • Cache semântico escaneia TODAS as linhas             │
│ • user_id não está na tabela cache_semantic            │
│ • Resposta pode vazar entre usuários da família        │
│                                                        │
│ Benchmarks atuais:                                     │
│ • 132 entries em cache_semantic                        │
│ • Scan linha a linha: ~113ms                           │
│ • Custo: embedding (100ms) + cosine (13ms)             │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. Gate Determinístico (Antes do Cache Semântico)

```python
# backend/cache/manager.py (modificado)

async def should_use_semantic_cache(
    ctx: RequestContext,
) -> bool:
    """
    Decide se deve usar cache semântico baseado em sinais.
    
    Sinais que DESATIVAM o cache semântico:
    - Histórico não vazio (follow-up)
    - Anexo presente
    - Web search ativo
    - Projeto ativo
    """
    has_history = len(ctx.messages) > 1
    has_attachment = ctx.has_attachment
    has_web_search = ctx.web_search_active
    has_project = ctx.project_id is not None
    
    if any([has_history, has_attachment, has_web_search, has_project]):
        logger.debug("Semantic cache GATED: follow-up/attachment/project")
        return False
    
    return True
```

### 2. Índice em RAM com Matrizes

```python
# backend/cache/semantic_index.py (NOVO)
import numpy as np
from typing import Dict, List, Tuple

class SemanticIndex:
    """
    Índice de embeddings em RAM para busca rápida por cosseno.
    
    Estrutura:
    - Matriz float32 [n_entries x embedding_dim]
    - Lista de IDs correspondentes
    - Lista de responses correspondentes
    - Atualizado em cada INSERT (não em cada READ)
    """
    
    def __init__(self):
        self._matriz: Optional[np.ndarray] = None
        self._ids: List[str] = []
        self._responses: List[str] = []
        self._user_ids: Dict[str, str] = {}  # entry_id -> user_id
        self._lock = asyncio.Lock()
    
    async def rebuild(self, db: aiosqlite.Connection):
        """Reconstrói índice a partir do DB (chamar após INSERT/DELETE)."""
        async with db.execute("""
            SELECT id, embedding, response, user_id 
            FROM cache_semantic 
            ORDER BY id
        """) as cur:
            rows = await cur.fetchall()
        
        if not rows:
            self._matriz = None
            self._ids.clear()
            self._responses.clear()
            return
        
        # Constrói matriz
        embeddings = []
        self._ids = []
        self._responses = []
        self._user_ids = {}
        
        for row in rows:
            entry_id, emb_blob, response, user_id = row
            vec = _blob_to_embedding(emb_blob)
            embeddings.append(vec)
            self._ids.append(entry_id)
            self._responses.append(response)
            self._user_ids[entry_id] = user_id
        
        self._matriz = np.array(embeddings, dtype=np.float32)
        logger.info(f"Semantic index rebuilt: {len(rows)} entries")
    
    async def search(
        self, 
        query_vec: np.ndarray, 
        threshold: float,
        user_id: str
    ) -> Optional[Tuple[str, str, float]]:
        """
        Busca similaridade por cosseno usando matriz.
        
        Returns:
            (entry_id, response, similarity) or None
        """
        if self._matriz is None or len(self._matriz) == 0:
            return None
        
        # Matmul vetorizado: O(n) em vez de O(n*d) Python loop
        similarities = self._matriz @ query_vec.T
        similarities = similarities.flatten()
        
        # Filtra por threshold e user_id
        best_idx = -1
        best_sim = 0.0
        
        for i, sim in enumerate(similarities):
            if sim > best_sim and sim >= threshold:
                # Verifica user_id
                entry_id = self._ids[i]
                if self._user_ids.get(entry_id) == user_id:
                    best_idx = i
                    best_sim = sim
        
        if best_idx == -1:
            return None
        
        return (
            self._ids[best_idx],
            self._responses[best_idx],
            float(best_sim)
        )
```

### 3. Escopo por user_id no Schema

```sql
-- migration: add user_id to cache_semantic
ALTER TABLE cache_semantic ADD COLUMN user_id TEXT;

-- Criar índice para queries futuras
CREATE INDEX idx_cache_semantic_user ON cache_semantic(user_id, created_at);
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/cache/semantic_index.py    # Classe SemanticIndex
```

### Arquivos a Modificar
```
backend/cache/manager.py           # Integrar gate + índice
backend/routers/memory.py          # Passar user_id no cache
backend/database.py                # Migration user_id
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Latência cache semântico (follow-up) | 113ms | 0ms (gate) | **-100%** |
| Latência cache semântico (primeira req) | 113ms | ~5ms (matriz) | **-95%** |
| Vazamento entre usuários | Possível | Impossível | **Fix** |
| Memória RAM adicional | - | ~10MB (132 entries) | **Baixo** |

---

## 🧪 Testes Requeridos

```python
# tests/test_semantic_gate.py
import pytest
import numpy as np

@pytest.mark.asyncio
async def test_gate_blocks_followup():
    """Cache semântico deve ser ignorado em follow-ups."""
    ctx = RequestContext(
        messages=[{"role": "user", "content": "Oi"}, {"role": "user", "content": "Continue"}],
        has_attachment=False,
        web_search_active=False,
        project_id=None,
    )
    assert await should_use_semantic_cache(ctx) == False

@pytest.mark.asyncio
async def test_gate_allows_first_request():
    """Cache semântico deve funcionar em primeira request."""
    ctx = RequestContext(
        messages=[{"role": "user", "content": "Quanto é 2+2?"}],
        has_attachment=False,
        web_search_active=False,
        project_id=None,
    )
    assert await should_use_semantic_cache(ctx) == True

@pytest.mark.asyncio
async def test_index_finds_best_match():
    """Índice deve encontrar similaridade correta."""
    index = SemanticIndex()
    # Setup...
    result = await index.search(query_vec, threshold=0.9, user_id="user1")
    assert result is not None
    assert result[2] >= 0.9

@pytest.mark.asyncio
async def test_index_filters_by_user():
    """Índice deve filtrar por user_id."""
    # Setup com dois usuários
    result = await index.search(query_vec, threshold=0.9, user_id="user2")
    assert result is None  # User2 não tem matches
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Migration do schema
  - [ ] Adicionar coluna `user_id` em `cache_semantic`
  - [ ] Criar índice
  - [ ] Populat user_id nos dados existentes (usuário padrão)
  - [ ] Backup do banco antes

- [ ] **Step 2:** Gate logic
  - [ ] Criar `should_use_semantic_cache()`
  - [ ] Testar com follow-ups, attachments, projects
  - [ ] Integrar com `CacheManager.get()`

- [ ] **Step 3:** Índice em RAM
  - [ ] Criar classe `SemanticIndex`
  - [ ] Implementar `rebuild()` e `search()`
  - [ ] Testar performance vs scan atual

- [ ] **Step 4:** Integração
  - [ ] Carregar índice no startup
  - [ ] Invalidar índice após INSERT/DELETE
  - [ ] Passar user_id em todas as chamadas

- [ ] **Step 5:** Testes
  - [ ] Rodar suite existente
  - [ ] Adicionar testes de gate
  - [ ] Benchmark de performance

- [ ] **Step 6:** Deploy
  - [ ] Backup do banco
  - [ ] Migrar schema
  - [ ] Deploy em staging
  - [ ] Monitorar por 24h

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Índicia desincronizado | Média | Baixo | Rebuild em cada INSERT/DELETE |
| user_id null em registros antigos | Alta | Baixo | Fallback para scan completo |
| Memória RAM excessiva | Baixa | Baixo | Limite de entries no índice (~10k) |
| Quebra de API existente | Baixa | Alto | Manter compatibilidade retroativa |

---

## 📈 Monitoramento

```python
# Adicionar métricas
SEMANTIC_CACHE_GATED = Counter(
    'semantic_cache_gated_total',
    'Vezes que cache semântico foi ignorado por gate'
)

SEMANTIC_CACHE_INDEX_HIT = Counter(
    'semantic_cache_index_hit_total',
    'Hits no índice em RAM'
)

SEMANTIC_CACHE_INDEX_MISS = Counter(
    'semantic_cache_index_miss_total',
    'Misses no índice (fallback para DB)'
)
```

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #1*  
*Responsável: Hermes Agent*
