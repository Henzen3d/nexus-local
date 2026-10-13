# Fase 1 — Cache de Contexto e Estado (Completo)

**Status:** ✅ Pronto para Implementação  
**Tempo Estimado:** 1h  
**Risco:** Baixo (cache read-only com fallback)

---

## 📋 Resumo

Cache em memória de **todos os dados estáveis** que não mudam entre requests:
1. **Modelos disponíveis** (documento anterior)
2. **System prompt base** (muda raramente)
3. **Configurações do sistema** (fusion, vision relay, etc)
4. **Templates de projeto** (estáveis por projeto)

TTL variável por tipo de dado (30s para modelos, 5min para contexto, 1h para templates).

---

## 🔍 Problema Identificado

```
Request: "Me ajuda com meu projeto Python"
┌────────────────────────────────────────────────────────┐
│ build_context.py - build_memory_context():             │
│                                                        │
│ Query 1: Perfil do usuário (5ms)                      │
│   SELECT * FROM users WHERE id = ?                     │
│                                                        │
│ Query 2: Memórias relevantes (5ms)                     │
│   SELECT * FROM memories WHERE user_id = ?             │
│                                                        │
│ Query 3: Summary global (5ms)                          │
│   SELECT * FROM memory_summaries WHERE ...             │
│                                                        │
│ Query 4: Projeto ativo (5ms)                           │
│   SELECT project_id FROM conversations WHERE id = ?    │
│                                                        │
│ Query 5: Contexto do modelo (5ms)                      │
│   SELECT context_length FROM models WHERE id = ?       │
│                                                        │
│ TOTAL: 25ms (5 round-trips)                           │
└────────────────────────────────────────────────────────┘
```

**Impacto:** Dados estáveis sendo recuperados do DB a cada request.

---

## ✅ Solução — Context Cache Unificado

```python
# backend/cache/context_cache.py (NOVO)
import time
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CacheType(str, Enum):
    MODELS = "models"           # 30s TTL
    SYSTEM_PROMPT = "system_prompt"  # 5min TTL
    USER_PROFILE = "user_profile"     # 5min TTL
    PROJECT_TEMPLATE = "project_template"  # 1h TTL
    FUSION_CONFIG = "fusion_config"   # 5min TTL
    VISION_RELAY_CONFIG = "vision_relay_config"  # 5min TTL


@dataclass
class CacheEntry:
    """Entrada no cache com timestamp."""
    data: Any
    created_at: float
    ttl_seconds: int
    
    @property
    def is_expired(self) -> bool:
        return time.time() - self.created_at > self.ttl_seconds
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at


class ContextCache:
    """
    Cache unificado de contexto e estado para evitar queries repetidas.
    
    Estrutura:
    {
        CacheType.MODELS: CacheEntry(...),
        CacheType.SYSTEM_PROMPT: CacheEntry(...),
        CacheType.USER_PROFILE:{user_id: CacheEntry(...)},
        CacheType.PROJECT_TEMPLATE: {project_id: CacheEntry(...)},
        ...
    }
    """
    
    # TTL por tipo (segundos)
    TTL = {
        CacheType.MODELS: 30,
        CacheType.SYSTEM_PROMPT: 300,  # 5 min
        CacheType.USER_PROFILE: 300,
        CacheType.PROJECT_TEMPLATE: 3600,  # 1h
        CacheType.FUSION_CONFIG: 300,
        CacheType.VISION_RELAY_CONFIG: 300,
    }
    
    def __init__(self):
        self._cache: Dict[CacheType, Any] = {}
        self._locks = {}  # Para concorrência
    
    def get(
        self,
        cache_type: CacheType,
        key: Optional[str] = None,
        db=None,
        loader=None,
    ) -> Optional[Any]:
        """
        Obtém dado do cache ou carrega do DB.
        
        Args:
            cache_type: Tipo do dado a cachejar
            key: Chave específica (user_id, project_id, etc)
            db: Conexão com o banco (para loading)
            loader: Função assíncrona para carregar do DB
        
        Returns:
            Dados cachejados ou None se não encontrado
        """
        cache_key = f"{cache_type.value}:{key}" if key else cache_type.value
        
        # Verifica cache
        entry = self._cache.get(cache_key)
        if entry and not entry.is_expired:
            logger.debug(f"Cache hit: {cache_key} ({entry.age_seconds:.1f}s old)")
            return entry.data
        
        # Cache miss ou expirado
        if loader and db:
            logger.info(f"Cache miss: {cache_key}, loading from DB")
            try:
                data = loader(db)
                if data is not None:
                    self.set(cache_type, key, data)
                    return data
            except Exception as e:
                logger.error(f"Failed to load {cache_key}: {e}")
        
        return None
    
    def set(
        self,
        cache_type: CacheType,
        key: Optional[str] = None,
        data: Any = None,
        ttl: Optional[int] = None,
    ) -> None:
        """Armazena dado no cache."""
        cache_key = f"{cache_type.value}:{key}" if key else cache_type.value
        ttl = ttl or self.TTL.get(cache_type, 300)
        
        self._cache[cache_key] = CacheEntry(
            data=data,
            created_at=time.time(),
            ttl_seconds=ttl,
        )
        logger.debug(f"Cache set: {cache_key} (TTL: {ttl}s)")
    
    def invalidate(self, cache_type: Optional[CacheType] = None, key: Optional[str] = None):
        """
        Invalida cache.
        
        Args:
            cache_type: Se especificado, invalida todo o tipo
            key: Se especificado, invalida apenas esta chave
        """
        if cache_type and not key:
            # Invalida todo o tipo
            prefix = f"{cache_type.value}:"
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]
            logger.info(f"Cache invalidated: all {cache_type.value}")
        elif cache_type and key:
            # Invalida chave específica
            cache_key = f"{cache_type.value}:{key}"
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.info(f"Cache invalidated: {cache_key}")
        else:
            # Invalida tudo
            self._cache.clear()
            logger.info("Cache fully invalidated")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do cache."""
        stats = {
            "total_entries": len(self._cache),
            "entries": []
        }
        
        for key, entry in self._cache.items():
            stats["entries"].append({
                "key": key,
                "type": entry.data.__class__.__name__,
                "age_seconds": round(entry.age_seconds, 1),
                "ttl_seconds": entry.ttl_seconds,
                "is_expired": entry.is_expired,
            })
        
        return stats


# Singleton global
context_cache = ContextCache()
```

### 2. Wrappers para Tipos Específicos

```python
# backend/cache/context_cache_wrappers.py (NOVO)
import aiosqlite
from typing import Dict, Any, Optional
from .context_cache import context_cache, CacheType


async def get_cached_system_prompt(db: Optional[aiosqlite.Connection] = None) -> str:
    """
    Busca system prompt base com cache.
    
    O system prompt é estável (muda raramente), então cache de 5min é seguro.
    """
    def _load_from_db(db) -> str:
        from backend.orchestration.build_context import BASE_SYSTEM_PROMPT
        return BASE_SYSTEM_PROMPT
    
    result = context_cache.get(
        CacheType.SYSTEM_PROMPT,
        db=db,
        loader=lambda db: _load_from_db(db)
    )
    
    return result or _load_from_db(None)


async def get_cached_user_profile(
    db: aiosqlite.Connection,
    user_id: str
) -> Optional[Dict[str, Any]]:
    """
    Busca perfil do usuário com cache.
    
    Perfil muda raramente (a não ser que o usuário edite).
    """
    async def _load(db) -> Optional[Dict]:
        async with db.execute(
            "SELECT id, name, email, role, memory_enabled FROM users WHERE id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "id": row[0],
                    "name": row[1],
                    "email": row[2],
                    "role": row[3],
                    "memory_enabled": bool(row[4]),
                }
        return None
    
    result = context_cache.get(
        CacheType.USER_PROFILE,
        key=user_id,
        db=db,
        loader=_load
    )
    
    return result


async def get_cached_project_template(
    db: aiosqlite.Connection,
    project_id: str
) -> Optional[Dict[str, Any]]:
    """
    Busca template/configurações do projeto com cache.
    
    Templates são estáveis (mudam apenas quando usuário edita).
    """
    async def _load(db) -> Optional[Dict]:
        async with db.execute(
            """SELECT instructions, memory, files, chats
               FROM projects WHERE id = ? AND archived = 0""",
            (project_id,)
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "instructions": row[0],
                    "memory": row[1],
                    "files": row[2],
                    "chats": row[3],
                }
        return None
    
    result = context_cache.get(
        CacheType.PROJECT_TEMPLATE,
        key=project_id,
        db=db,
        loader=_load
    )
    
    return result


async def get_cached_fusion_config(db: aiosqlite.Connection) -> Dict[str, Any]:
    """Busca config do Fusion com cache."""
    async def _load(db) -> Dict:
        async with db.execute(
            """SELECT judge_provider_id, judge_model_id, judge_system_prompt, 
                      enabled, grounding_enabled
               FROM fusion_config WHERE id = 'default'"""
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "judge_provider_id": row[0],
                    "judge_model_id": row[1],
                    "judge_system_prompt": row[2],
                    "enabled": bool(row[3]),
                    "grounding_enabled": bool(row[4]),
                }
        return {}
    
    result = context_cache.get(
        CacheType.FUSION_CONFIG,
        db=db,
        loader=_load
    )
    
    return result or {}


async def get_cached_vision_relay_config(db: aiosqlite.Connection) -> Dict[str, Any]:
    """Busca config do Vision Relay com cache."""
    async def _load(db) -> Dict:
        async with db.execute(
            """SELECT relay_provider_id, relay_model_id, relay_system_prompt,
                      enabled, cache_descriptions
               FROM vision_relay_config WHERE id = 'default'"""
        ) as cur:
            row = await cur.fetchone()
            if row:
                return {
                    "relay_provider_id": row[0],
                    "relay_model_id": row[1],
                    "relay_system_prompt": row[2],
                    "enabled": bool(row[3]),
                    "cache_descriptions": bool(row[4]),
                }
        return {}
    
    result = context_cache.get(
        CacheType.VISION_RELAY_CONFIG,
        db=db,
        loader=_load
    )
    
    return result or {}
```

### 3. Integração com Build Context

```python
# backend/orchestration/build_context.py (modificado)
from backend.cache.context_cache import context_cache, CacheType
from backend.cache.context_cache_wrappers import (
    get_cached_system_prompt,
    get_cached_user_profile,
    get_cached_project_template,
)

async def build_memory_context(
    user: dict | None,
    conversation_id: str,
    user_message: str,
    use_memory: bool,
    provider_id: str,
    model_id: str,
) -> tuple[str, str]:
    """Versão otimizada com cache de contexto."""
    
    if not user or "id" not in user or not use_memory:
        return "", "nomem"
    
    user_id = user["id"]
    
    try:
        # ── NOVO: Busca perfil com cache ───────────────────────
        profile = await get_cached_user_profile(db, user_id)
        if not profile:
            # Fallback: busca sem cache
            from backend.database import get_user_profile
            profile = await get_user_profile(user_id)
        
        mem_enabled = bool(profile.get("memory_enabled", 1))
        mem_rows: list = []
        global_sum = None
        project_sum = None

        if mem_enabled:
            # ... código existente para memórias ...
```

### 4. Integração com Smart Router

```python
# backend/ranking/smart_router.py (modificado)
from backend.cache.context_cache import context_cache, CacheType

async def select_best_model(intent_result, policy, db, previous_model_id=None):
    """Versão otimizada com cache de contexto."""
    
    # Usa cache unificado em vez de queries individuais
    models_data = await get_cached_models(db)  # Do documento anterior
    system_prompt = await get_cached_system_prompt(db)
    fusion_config = await get_cached_fusion_config(db)
    
    # ... resto da lógica permanece igual ...
```

---

## 📊 Métricas Esperadas

| Tipo de Dado | TTL | Queries Evitadas | Economia |
|--------------|-----|------------------|----------|
| Modelos | 30s | 1-3 por request | ~20ms |
| System Prompt | 5min | 0 (já era constante) | 0ms |
| User Profile | 5min | 1 por request | ~5ms |
| Project Template | 1h | 1-2 por request | ~10ms |
| Fusion Config | 5min | 1 por request | ~5ms |
| Vision Relay Config | 5min | 1 por request | ~5ms |
| **Total potencial** | - | **5-8 queries** | **~45ms** |

---

## 🧪 Testes Requeridos

```python
# tests/test_context_cache.py
import pytest
import time
import aiosqlite
from backend.cache.context_cache import ContextCache, CacheType

@pytest.mark.asyncio
async def test_cache_hit():
    """Primeira chamada popula cache, segunda usa cache."""
    cache = ContextCache()
    
    # Popula cache
    cache.set(CacheType.SYSTEM_PROMPT, data="test prompt")
    
    # Segunda chamada deve usar cache
    entry = cache._cache.get("system_prompt")
    assert entry is not None
    assert entry.data == "test prompt"
    assert entry.age_seconds < 1  # Recém criado

@pytest.mark.asyncio
async def test_cache_expiry():
    """Cache deve expirar após TTL."""
    cache = ContextCache()
    
    # Set com TTL curto
    cache.set(CacheType.MODELS, data="models", ttl=1)
    
    # Aguarda expirar
    await asyncio.sleep(1.1)
    
    entry = cache._cache.get("models")
    assert entry.is_expired

@pytest.mark.asyncio
async def test_cache_invalidation():
    """Invalidação deve remover entrada."""
    cache = ContextCache()
    
    cache.set(CacheType.USER_PROFILE, key="user1", data={"name": "Test"})
    assert "user_profile:user1" in cache._cache
    
    cache.invalidate(CacheType.USER_PROFILE, key="user1")
    assert "user_profile:user1" not in cache._cache

@pytest.mark.asyncio
async def test_wrapper_cached_profile():
    """Wrapper deve cachejar perfil do usuário."""
    db = await aiosqlite.connect(":memory:")
    # ... setup de tabela users ...
    
    from backend.cache.context_cache_wrappers import get_cached_user_profile
    
    # Primeira chamada (populate)
    profile1 = await get_cached_user_profile(db, "user1")
    
    # Segunda chamada (cache)
    profile2 = await get_cached_user_profile(db, "user1")
    
    assert profile1 == profile2
```

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/cache/context_cache.py`
- [ ] Criar `backend/cache/context_cache_wrappers.py`
- [ ] Modificar `build_context.py` para usar cache de perfil
- [ ] Modificar `smart_router.py` para usar cache de config
- [ ] Adicionar testes em `test_context_cache.py`
- [ ] Rodar `pytest tests/test_context_cache.py`
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(cache): add unified context cache with variable TTL`

---

## ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Cache stale (perfil atualizado mas cache não) | Baixa | Baixo | TTL 5min + endpoint de invalidação |
| Memória vazando (muitos users/projects) | Média | Médio | Limpeza automática de entradas expiradas |
| Concorrência (dois requests carregando mesmo dado) | Baixa | Baixo | Lock por chave ou permite duplicação temporária |
| Falha no loader (DB indisponível) | Baixa | Alto | Fallback para query direta, log de erro |

---

## 🚀 Deploy

```bash
# 1. Backup do banco
sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"

# 2. Commit
git add backend/cache/context_cache.py backend/cache/context_cache_wrappers.py
git add backend/orchestration/build_context.py backend/ranking/smart_router.py
git commit -m "feat(cache): add unified context cache with variable TTL"

# 3. Deploy
git push origin main
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

---

## 📈 Monitoramento

Endpoint para verificar estado do cache:

```python
# backend/routers/admin.py
@router.get("/api/admin/cache/stats")
async def get_cache_stats():
    from backend.cache.context_cache import context_cache
    return context_cache.get_stats()
```

Resposta esperada:
```json
{
  "total_entries": 15,
  "entries": [
    {"key": "models", "type": "list", "age_seconds": 5.2, "ttl_seconds": 30, "is_expired": false},
    {"key": "system_prompt", "type": "str", "age_seconds": 120.5, "ttl_seconds": 300, "is_expired": false},
    {"key": "user_profile:user1", "type": "dict", "age_seconds": 30.1, "ttl_seconds": 300, "is_expired": false},
    ...
  ]
}
```

---

*Documento criado: 2026-10-13*  
*Atualizado: 2026-10-13 (completo com cache de contexto)*  
*Responsável: Hermes Agent*  
*Status: Pronto para implementação*
