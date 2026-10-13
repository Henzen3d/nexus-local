# Plano: Anti-429 Preventivo com Token Bucket

**Status:** 🆕 Novo  
**Tempo Estimado:** 1.5h  
**Risco:** Baixo/Médio

---

## 📋 Resumo

Oportunidade identificada: prevenir 429s antes que aconteçam usando token bucket local baseado nos limites conhecidos de RPM/RPD por provedor. Manter tratamento reativo como rede de segurança.

---

## 🔍 Problema Identificado

```
Cenário atual (tratamento reativo):
┌────────────────────────────────────────────────────────┐
│ 1. Request é enviado                                    │
│ 2. Provedor retorna 429 (rate limit)                   │
│ 3. Failover tenta próximo provedor (1-2s)              │
│ 4. Se todos 429 → usuário espera                        │
│                                                        │
│ Custo do 429:                                          │
│ • Round-trip perdido: 200-500ms                        │
│ • Failover: +500ms-2s                                  │
│ • Tentativas: até 3x                                   │
│ • Experiência do usuário: lenta e frustrante            │
└────────────────────────────────────────────────────────┘

Exemplo real:
- OrcaRouter: 10 RPD (requests per minute) por key
- Bynara: 5 RPD por modelo
- Usuário faz 3 requests em 10 segundos → 429 no 3º
```

---

## ✅ Solução Proposta

### 1. Token Bucket por Provedor/Modelo

```python
# backend/ranking/token_bucket.py (NOVO)
import asyncio
import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class RateLimitConfig:
    """Configuração de rate limit para um provedor/modelo."""
    provider_id: str
    model_id: Optional[str] = None  # None = aplica a todos os modelos
    rpm: int = 60  # Requests per minute
    rpd: int = 1000  # Requests per day
    burst_size: int = 5  # Token bucket size (allow bursts)

class TokenBucket:
    """
    Token bucket para controle de rate limit preventivo.
    
    Funcionamento:
    - Cada provedor/modelo tem seu próprio bucket
    - Tokens são adicionados continuamente (rate)
    - Cada request consome 1 token
    - Se bucket vazio → rejeita request (before it hits API)
    """
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.tokens = config.burst_size  # Começa cheio
        self.last_refill = time.monotonic()
        self.daily_count = 0
        self.daily_reset = time.time() + 86400  # Reset dia seguinte
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> Tuple[bool, float]:
        """
        Tenta adquirir tokens.
        
        Returns:
            (allowed, wait_time_seconds)
        """
        async with self._lock:
            # Check daily limit
            if time.time() > self.daily_reset:
                self.daily_count = 0
                self.daily_reset = time.time() + 86400
            
            if self.daily_count + tokens > self.config.rpd:
                logger.warning(
                    f"Daily limit reached for {self.config.provider_id}"
                )
                return False, 86400  # Wait until tomorrow
            
            # Refill tokens
            now = time.monotonic()
            elapsed = now - self.last_refill
            refill_rate = self.config.rpm / 60.0  # Tokens per second
            new_tokens = elapsed * refill_rate
            self.tokens = min(
                self.config.burst_size,
                self.tokens + new_tokens
            )
            self.last_refill = now
            
            # Check if enough tokens
            if self.tokens < tokens:
                # Calculate wait time
                deficit = tokens - self.tokens
                wait_time = deficit / refill_rate
                logger.debug(
                    f"Rate limited: {self.config.provider_id} "
                    f"(tokens={self.tokens:.1f}, needed={tokens}, "
                    f"wait={wait_time:.2f}s)"
                )
                return False, wait_time
            
            # Consume tokens
            self.tokens -= tokens
            self.daily_count += tokens
            return True, 0
    
    async def get_status(self) -> Dict:
        """Retorna status atual do bucket."""
        async with self._lock:
            return {
                "provider_id": self.config.provider_id,
                "model_id": self.config.model_id,
                "tokens_available": self.tokens,
                "burst_size": self.config.burst_size,
                "daily_used": self.daily_count,
                "daily_limit": self.config.rpd,
                "rpm_limit": self.config.rpm,
            }


class RateLimitManager:
    """Gerencia buckets para todos os provedores/modelos."""
    
    def __init__(self):
        self._buckets: Dict[str, TokenBucket] = {}
        self._configs: Dict[str, RateLimitConfig] = {}
    
    def register_config(self, config: RateLimitConfig):
        """Registra configuração de rate limit."""
        key = self._make_key(config.provider_id, config.model_id)
        self._configs[key] = config
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(config)
    
    async def acquire(
        self, 
        provider_id: str, 
        model_id: Optional[str] = None
    ) -> Tuple[bool, float]:
        """
        Tenta adquirir token para provedor/modelo.
        
        Returns:
            (allowed, wait_time_seconds)
        """
        key = self._make_key(provider_id, model_id)
        
        # Procura bucket específico primeiro
        bucket = self._buckets.get(key)
        
        # Se não existe, procura bucket do provedor
        if bucket is None:
            provider_key = self._make_key(provider_id, None)
            bucket = self._buckets.get(provider_key)
        
        # Se ainda não existe, usa padrão
        if bucket is None:
            logger.warning(
                f"No rate limit config for {provider_id}/{model_id}, "
                f"allowing by default"
            )
            return True, 0
        
        return await bucket.acquire()
    
    async def on_429(self, provider_id: str, model_id: str):
        """
        Called when a 429 is received (reactive fallback).
        Penalizes the bucket temporarily.
        """
        key = self._make_key(provider_id, model_id)
        bucket = self._buckets.get(key)
        if bucket:
            # Reduz tokens disponíveis (penalidade)
            bucket.tokens = max(0, bucket.tokens - 3)
            logger.warning(
                f"429 received for {provider_id}/{model_id}, "
                f"penalizing bucket"
            )
    
    def _make_key(self, provider_id: str, model_id: Optional[str]) -> str:
        return f"{provider_id}:{model_id or 'all'}"
    
    async def get_all_status(self) -> Dict[str, Dict]:
        """Retorna status de todos os buckets."""
        status = {}
        for key, bucket in self._buckets.items():
            status[key] = await bucket.get_status()
        return status


# Singleton
rate_limit_manager = RateLimitManager()
```

### 2. Integração com Smart Router

```python
# backend/ranking/smart_router.py (modificado)
from .token_bucket import rate_limit_manager

async def select_best_model(intent_result, policy, db, previous_model_id=None):
    """Versão otimizada com rate limit preventivo."""
    
    # ... lógica existente ...
    
    # NOVO: Check rate limit antes de selecionar
    best_model = models_data[0]  # Modelo selecionado pela lógica existente
    
    allowed, wait_time = await rate_limit_manager.acquire(
        provider_id=best_model["provider_id"],
        model_id=best_model["id"],
    )
    
    if not allowed:
        logger.info(
            f"Rate limited: {best_model['id']} (wait {wait_time:.1f}s), "
            f"trying failover"
        )
        # Tenta próximo modelo disponível
        for model in models_data[1:]:
            allowed, wait_time = await rate_limit_manager.acquire(
                provider_id=model["provider_id"],
                model_id=model["id"],
            )
            if allowed:
                best_model = model
                break
        else:
            # Todos rate limitados
            raise RateLimitExceededError(
                f"All models rate limited. Try again in {wait_time:.0f}s"
            )
    
    return best_model
```

### 3. Configuração via Banco

```sql
-- Tabela de rate limits (nova)
CREATE TABLE IF NOT EXISTS rate_limit_configs (
    id TEXT PRIMARY KEY,
    provider_id TEXT NOT NULL,
    model_id TEXT,
    rpm INTEGER NOT NULL DEFAULT 60,
    rpd INTEGER NOT NULL DEFAULT 1000,
    burst_size INTEGER NOT NULL DEFAULT 5,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Inserts iniciais (valores comuns de free tier)
INSERT OR REPLACE INTO rate_limit_configs 
    (id, provider_id, model_id, rpm, rpd, burst_size) 
VALUES 
    ('orca-default', 'orcarouter', NULL, 10, 1000, 3),
    ('bynara-default', 'bynara', NULL, 5, 500, 2),
    ('gemini-default', 'gemini', NULL, 60, 1500, 10);
```

### 4. Endpoint de Debug

```python
# backend/routers/admin.py (modificado)
from ..ranking.token_bucket import rate_limit_manager

@router.get("/api/admin/rate-limits")
async def get_rate_limits():
    """Retorna status de todos os rate limits."""
    return await rate_limit_manager.get_all_status()

@router.post("/api/admin/rate-limits/{provider_id}/{model_id}/penalize")
async def penalize_rate_limit(provider_id: str, model_id: str):
    """
    Aplica penalidade manual (para testar ou after 429).
    """
    await rate_limit_manager.on_429(provider_id, model_id)
    return {"status": "ok"}
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/ranking/token_bucket.py      # Token bucket implementation
```

### Arquivos a Modificar
```
backend/ranking/smart_router.py      # Integrar check
backend/routers/admin.py             # Endpoint debug
backend/database.py                  # Migration tabela
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| 429s recebidos | 100% dos casos | ~10% (edge cases) | **-90%** |
| Latência percebida (429) | 1-3s | 0ms (previnido) | **-100%** |
| Failovers causados por 429 | Alto | Baixo | **-80%** |
| Requests rejeitados preventivamente | 0 | ~5-10% | Controle proativo |

---

## 🧪 Testes Requeridos

```python
# tests/test_token_bucket.py
import pytest
import asyncio
import time
from backend.ranking.token_bucket import TokenBucket, RateLimitConfig, RateLimitManager

@pytest.mark.asyncio
async def test_bucket_allows_burst():
    """Bucket deve允许 burst até burst_size."""
    config = RateLimitConfig(
        provider_id="test",
        rpm=60,
        rpd=1000,
        burst_size=5,
    )
    bucket = TokenBucket(config)
    
    # Deve allow 5 requests instantly
    for i in range(5):
        allowed, wait = await bucket.acquire()
        assert allowed == True
        assert wait == 0

@pytest.mark.asyncio
async def test_bucket_rejects_after_burst():
    """Bucket deve rejeitar após esgotar tokens."""
    config = RateLimitConfig(
        provider_id="test",
        rpm=60,
        rpd=1000,
        burst_size=3,
    )
    bucket = TokenBucket(config)
    
    # Consome todos os tokens
    for _ in range(3):
        await bucket.acquire()
    
    # Próximo deve ser rejeitado
    allowed, wait = await bucket.acquire()
    assert allowed == False
    assert wait > 0

@pytest.mark.asyncio
async def test_bucket_refills_over_time():
    """Tokens devem ser refeitos com o tempo."""
    config = RateLimitConfig(
        provider_id="test",
        rpm=60,  # 1 token per second
        rpd=1000,
        burst_size=1,
    )
    bucket = TokenBucket(config)
    
    # Consome token
    await bucket.acquire()
    
    # Aguarda refill
    await asyncio.sleep(1.1)
    
    # Deve ter token novamente
    allowed, wait = await bucket.acquire()
    assert allowed == True

@pytest.mark.asyncio
async def test_daily_limit():
    """Daily limit deve ser respeitado."""
    config = RateLimitConfig(
        provider_id="test",
        rpm=60,
        rpd=5,  # Low limit for test
        burst_size=5,
    )
    bucket = TokenBucket(config)
    
    # Consome todos os tokens diários
    for _ in range(5):
        await bucket.acquire()
    
    # Deve atingir daily limit
    allowed, wait = await bucket.acquire()
    assert allowed == False
    assert wait > 3600  # Wait until tomorrow

@pytest.mark.asyncio
async def test_manager_finds_provider_bucket():
    """Manager deve encontrar bucket correto."""
    manager = RateLimitManager()
    manager.register_config(RateLimitConfig(
        provider_id="test",
        rpm=60,
        rpd=1000,
        burst_size=5,
    ))
    
    # Deve encontrar bucket do provedor
    allowed, _ = await manager.acquire("test", "any-model")
    assert allowed == True
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Criar Token Bucket
  - [ ] Criar `token_bucket.py`
  - [ ] Implementar `TokenBucket` class
  - [ ] Implementar `RateLimitManager`
  - [ ] Testar unitariamente

- [ ] **Step 2:** Migrar schema
  - [ ] Adicionar tabela `rate_limit_configs`
  - [ ] Populat com configs padrão
  - [ ] Testar migration

- [ ] **Step 3:** Integrar com Smart Router
  - [ ] Adicionar check de rate limit
  - [ ] Implementar fallback para próximo modelo
  - [ ] Testar com mocks de 429

- [ ] **Step 4:** Adicionar endpoints
  - [ ] GET `/api/admin/rate-limits`
  - [ ] POST `/api/admin/rate-limits/{p}/{m}/penalize`
  - [ ] Documentar para debugging

- [ ] **Step 5:** Testes integrais
  - [ ] Testar com provedores reais
  - [ ] Testar cenários de 429
  - [ ] Benchmark de latência

- [ ] **Step 6:** Deploy
  - [ ] Backup do banco
  - [ ] Deploy staging
  - [ ] Monitorar 429s vs rejeições
  - [ ] Ajustar thresholds se necessário

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Limites errados (muito agressivo) | Média | Médio | Defaults conservadores + override |
| Limites mudam sem aviso | Alta | Baixo | Manual override + auto-adjust |
| Falso positivo (bloqueia request válido) | Baixa | Baixo | Keep reativo como fallback |
| Memória vazando (muitos buckets) | Baixa | Baixo | Limite de buckets + cleanup |

---

## 📈 Monitoramento

```python
# Adicionar métricas
RATE_LIMIT_REJECTIONS = Counter(
    'rate_limit_rejections_total',
    'Requests rejeitados preventivamente'
)

RATE_LIMIT_429S_CAUGHT = Counter(
    'rate_limit_429s_caught_total',
    '429s ainda capturados (fallback reativo)'
)

RATE_LIMIT_SUCCESSFUL_PREVENTIONS = Counter(
    'rate_limit_preventions_total',
    '429s prevenidos com sucesso'
)

RATE_LIMIT_WAIT_TIME = Histogram(
    'rate_limit_wait_time_seconds',
    'Tempo de espera cuando rate limited'
)
```

---

## ⚠️ Considerações Importantes

1. **Defaults Conservadores:**
   - Começar com limits 2x maiores que os conhecidos
   - Ajustar baseado em observação

2. **Override Manual:**
   - Permitir admin sobrescrever limits
   - Endpoint para "bypass" em emergência

3. **Integração com Failover Existente:**
   - Token bucket é CAMADA ADICIONAL, não substitui failover
   - Se bucket permitir mas API retornar 429 → failover reativo

4. **Logging Detalhado:**
   - Logar cada rejeição com provider/model/wait_time
   - Dashboard para visualizar padrões

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #6*  
*Responsável: Hermes Agent*
