# Fase 3 — Vision Relay Cache

**Status:** ✅ Pronto para Implementação  
**Tempo Estimado:** 20 minutos  
**Risco:** Baixo (cache read-only)

---

## 📋 Resumo

Cache de descrições de imagens geradas pelo Vision Relay para evitar chamadas HTTP repetidas.

---

## 🔍 Problema Identificado

```
Conversa com 5 imagens aninhadas:
┌────────────────────────────────────────────────────────┐
│ Request 1: "O que tem na imagem 1?"                   │
│   → Vision Relay chama LLM (2-5s)                     │
│   → Resposta: "É um gato preto..."                    │
│                                                        │
│ Request 2: "E a imagem 2?"                            │
│   → Vision Relay chama LLM (2-5s)                     │
│   → Resposta: "É um cachorro..."                      │
│                                                        │
│ Request 3: "Você pode comparar as duas?"              │
│   → Reprocessa imagem 1 (2-5s)  ← DESNECESSÁRIO!      │
│   → Reprocessa imagem 2 (2-5s)  ← DESNECESSÁRIO!      │
│   → Compara textos (50ms)                              │
│                                                        │
│ TOTAL: 10-20s desperdiçados em reprocessamento         │
└────────────────────────────────────────────────────────┘
```

**Impacto:** Conversas longas com muitas imagens podem levar 30-60s a mais do que o necessário.

---

## ✅ Solução

### 1. Módulo de Cache

```python
# backend/vision_relay/cache.py (NOVO)
import asyncio
import hashlib
import time
from typing import Optional, Dict, Any
from pathlib import Path
import aiosqlite

CACHE_TTL = 3600  # 1 hora
CACHE_DIR = Path(__file__).parent.parent / "storage" / "vision_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache em memória para acesso ultrarrápido
_memory_cache: Dict[str, Dict[str, Any]] = {}
_last_cleanup = 0.0


def _hash_image(mime_type: str, file_hash: str) -> str:
    """Gera key única para a imagem."""
    return hashlib.sha256(f"{mime_type}:{file_hash}".encode()).hexdigest()[:16]


async def get_cached_description(
    mime_type: str,
    file_hash: str,
) -> Optional[str]:
    """
    Busca descrição cacheada da imagem.
    
    Returns:
        Descrição cacheada ou None se não encontrado.
    """
    key = _hash_image(mime_type, file_hash)
    
    # Verifica cache em memória primeiro (0ms)
    if key in _memory_cache:
        entry = _memory_cache[key]
        if time.time() - entry["created_at"] < CACHE_TTL:
            return entry["description"]
        else:
            del _memory_cache[key]
    
    # Verifica cache persistente (SQLite)
    cache_path = CACHE_DIR / "descriptions.db"
    try:
        async with aiosqlite.connect(cache_path) as db:
            async with db.execute(
                "SELECT description FROM image_descriptions WHERE key = ? AND expires_at > datetime('now')",
                (key,)
            ) as cur:
                row = await cur.fetchone()
                if row:
                    # Repopula memória
                    _memory_cache[key] = {
                        "description": row[0],
                        "created_at": time.time(),
                    }
                    return row[0]
    except Exception:
        pass
    
    return None


async def set_cached_description(
    mime_type: str,
    file_hash: str,
    description: str,
) -> None:
    """Armazena descrição no cache."""
    key = _hash_image(mime_type, file_hash)
    
    # Atualiza memória
    _memory_cache[key] = {
        "description": description,
        "created_at": time.time(),
    }
    
    # Atualiza persistência ( SQLite)
    cache_path = CACHE_DIR / "descriptions.db"
    try:
        async with aiosqlite.connect(cache_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS image_descriptions (
                    key TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    mime_type TEXT,
                    file_hash TEXT,
                    created_at REAL,
                    expires_at TEXT
                )
            """)
            await db.execute("""
                INSERT OR REPLACE INTO image_descriptions
                (key, description, mime_type, file_hash, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, datetime(?, '+1 hour'))
            """, (
                key, description, mime_type, file_hash,
                time.time(), time.strftime("%Y-%m-%d %H:%M:%S")
            ))
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save vision cache: {e}")


async def cleanup_expired_cache() -> int:
    """Remove entradas expiradas do cache em memória."""
    global _last_cleanup
    now = time.time()
    
    # Limpa a cada 10 minutos
    if now - _last_cleanup < 600:
        return 0
    
    _last_cleanup = now
    
    expired_keys = [
        k for k, v in _memory_cache.items()
        if now - v["created_at"] > CACHE_TTL
    ]
    
    for key in expired_keys:
        del _memory_cache[key]
    
    return len(expired_keys)
```

### 2. Integração com relay.py

```python
# backend/vision_relay/relay.py (modificado)
from .cache import get_cached_description, set_cached_description

async def describe_image_via_relay(
    storage_path: str,
    mime_type: str,
    file_hash: str,
    user_id: str,
    conversation_id: str | None = None,
    image_bytes: bytes | None = None,
) -> dict:
    """Versão otimizada com cache."""
    
    # ── NOVO: Tenta cache primeiro (0ms) ───────────────────
    cached = await get_cached_description(mime_type, file_hash)
    if cached:
        logger.debug(f"Vision cache hit for {file_hash[:8]}")
        return {
            "description": cached,
            "relay_model": "cached",
            "cached": True,
        }
    
    # ── MISS: Chama Vision Relay normalmente (2-5s) ────────
    # ... código existente ...
    
    result = await _call_relay_api(...)
    
    # ── NOVO: Armazena no cache ────────────────────────────
    if result.get("description"):
        await set_cached_description(mime_type, file_hash, result["description"])
    
    return result
```

---

## 📊 Métricas Esperadas

| Cenário | Antes | Depois | Economia |
|---------|-------|--------|----------|
| Primeira imagem | 2-5s | 2-5s | 0% |
| Imagem repetida (cache hit) | 2-5s | 0ms | **100%** |
| Conversa com 5 imagens (repetidas) | 10-25s | 2-5s | **80-90%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_vision_cache.py
import pytest
import asyncio
import time
from backend.vision_relay.cache import (
    get_cached_description,
    set_cached_description,
    cleanup_expired_cache,
)

@pytest.mark.asyncio
async def test_cache_set_and_get():
    """Deve armazenar e recuperar descrição do cache."""
    mime_type = "image/png"
    file_hash = "abc123"
    description = "Um gato preto sentado"
    
    # Armazena
    await set_cached_description(mime_type, file_hash, description)
    
    # Recupera
    cached = await get_cached_description(mime_type, file_hash)
    
    assert cached == description

@pytest.mark.asyncio
async def test_cache_miss():
    """Deve retornar None para imagem não cacheada."""
    cached = await get_cached_description("image/jpeg", "nonexistent")
    assert cached is None

@pytest.mark.asyncio
async def test_cache_different_images():
    """Imagens diferentes devem ter caches diferentes."""
    await set_cached_description("image/png", "hash1", "Descrição 1")
    await set_cached_description("image/png", "hash2", "Descrição 2")
    
    desc1 = await get_cached_description("image/png", "hash1")
    desc2 = await get_cached_description("image/png", "hash2")
    
    assert desc1 == "Descrição 1"
    assert desc2 == "Descrição 2"
    assert desc1 != desc2

@pytest.mark.asyncio
async def test_cleanup_expired():
    """Deve remover entradas expiradas."""
    # Mock do tempo para simular expiração
    import backend.vision_relay.cache as cache_module
    cache_module._memory_cache["test"] = {
        "description": "test",
        "created_at": time.time() - 3700,  # 1h1min atrás
    }
    
    cleaned = await cleanup_expired_cache()
    
    assert cleaned == 1
    assert "test" not in cache_module._memory_cache
```

---

## 📝 Checklist de Implementação

- [ ] Criar `backend/vision_relay/cache.py`
- [ ] Modificar `describe_image_via_relay()` para usar cache
- [ ] Adicionar testes em `test_vision_cache.py`
- [ ] Rodar `pytest tests/test_vision_cache.py`
- [ ] Verificar que todos os testes passam
- [ ] Commit: `feat(vision): add relay description cache with 1h TTL`

---

## ⚠️ Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Cache staleness (imagem atualizada) | Baixa | Baixo | TTL 1h, usuário pode forçar refresh |
| Espaço em disco (muitas imagens) | Média | Baixo | Cleanup automático a cada 10min |
| Concorrência (dois requests mesma imagem) | Baixa | Baixo | Lock ou apenas deixa calcular duas vezes |
| Falha no SQLite do cache | Baixa | Baixo | Apenas memória, perde cache mas funciona |

---

## 🚀 Deploy

```bash
# 1. Backup do banco
sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"

# 2. Commit
git add backend/vision_relay/cache.py backend/vision_relay/relay.py tests/test_vision_cache.py
git commit -m "feat(vision): add relay description cache with 1h TTL"

# 3. Deploy
git push origin main
docker compose build --no-cache backend
docker compose up -d --force-recreate backend
```

---

*Documento criado: 2026-10-13*
*Responsável: Hermes Agent*
*Status: Aguardando implementação*
