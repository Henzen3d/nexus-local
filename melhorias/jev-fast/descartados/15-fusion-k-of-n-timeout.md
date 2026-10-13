# Plano: Fusion K-of-N + Timeout + Convergência

**Status:** 🆕 Novo (alternativa otimizada ao documento 14)  
**Tempo Estimado:** 1.5h  
**Risco:** Médio

---

## 📋 Resumo

Oportunidade identificada: em vez de esperar todos os N modelos responderem antes de chamar o juiz, iniciar o juiz quando K de N responderem (ex: 2 de 3) ou após timeout. Se as respostas convergem, pular o juiz.

---

## 🔍 Problema Identificado

```
Fusion atual (N+1 chamadas):
┌────────────────────────────────────────────────────────┐
│ Request entra no Fusion                                │
│                                                        │
│ Fase 1: N modelos geram respostas (sequencial ou async)│
│   ├─ Modelo A (ultra-550b): 3s                         │
│   ├─ Modelo B (super-120b): 2s                         │
│   └─ Modelo C (nano-omni):  8s ← free tier, lento      │
│                                                        │
│ Fase 2: Juiz avalia todas (sempre)                     │
│   └─ Juiz (modelo grande): 3s                          │
│                                                        │
│ TOTAL: 8s (espera o mais lento) + 3s (juiz) = 11s     │
│                                                        │
│ Problemas:                                             │
│ • Custa N+1 chamadas LLM                               │
│ • Espera provedor mais lento (cauda longa em free)     │
│ • Juiz roda SEMPRE, mesmo quando respostas concordam   │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. K-of-N com Timeout

```python
# backend/fusion/k_of_n.py (NOVO)
import asyncio
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
import time

@dataclass
class FusionConfig:
    """Configuração do Fusion com novos parâmetros."""
    num_models: int = 3
    k_required: int = 2  # Mínimo de respostas para iniciar juiz
    judge_timeout_s: float = 5.0  # Timeout para juiz
    model_timeout_s: float = 10.0  # Timeout por modelo
    convergence_threshold: float = 0.9  # Similaridade para pular juiz

@dataclass
class ModelResponse:
    """Resposta de um modelo."""
    model_id: str
    response: str
    latency_ms: float
    success: bool
    error: Optional[str] = None

@dataclass
class FusionResult:
    """Resultado final do Fusion."""
    response: str
    source: str  # "quorum", "judge", "timeout", "single"
    models_used: int
    judge_used: bool
    latency_ms: float
    confidence: float

async def fusion_k_of_n(
    prompt: str,
    models: List[Dict],
    config: FusionConfig,
    judge_fn: Callable,
) -> FusionResult:
    """
    Fusion otimizado com K-of-N e timeout.
    
    Algoritmo:
    1. Iniciar todos os modelos em paralelo
    2. Quando K modelos responderem:
       a. Verificar convergência
       b. Se convergiram → retornar sem juiz
       c. Se não → iniciar juiz
    3. Se timeout → usar melhores respostas disponíveis
    """
    start_time = time.time()
    
    # Fase 1: Executar modelos em paralelo com timeout
    tasks = [
        asyncio.wait_for(
            _call_model(model, prompt),
            timeout=config.model_timeout_s
        )
        for model in models
    ]
    
    # Aguarda até K respostas ou timeout
    done, pending = await asyncio.wait(
        tasks,
        timeout=config.model_timeout_s,
        return_when=asyncio.FIRST_COMPLETED
    )
    
    # Cancela tarefas pendentes
    for task in pending:
        task.cancel()
    
    # Coleta respostas completadas
    responses = []
    for task in done:
        try:
            result = task.result()
            if result.success:
                responses.append(result)
        except Exception as e:
            logger.warning(f"Model task failed: {e}")
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    # Caso 1: Menos que K respostas
    if len(responses) < config.k_required:
        return FusionResult(
            response=responses[0].response if responses else "Erro: sem respostas",
            source="timeout",
            models_used=len(responses),
            judge_used=False,
            latency_ms=elapsed_ms,
            confidence=0.5,
        )
    
    # Caso 2: Verificar convergência
    if await _check_convergence(responses, config.convergence_threshold):
        # Respostas convergiram → usar melhor sem juiz
        best = max(responses, key=lambda r: r.latency_ms)  # Mais rápida
        return FusionResult(
            response=best.response,
            source="quorum",
            models_used=len(responses),
            judge_used=False,
            latency_ms=elapsed_ms,
            confidence=0.95,
        )
    
    # Caso 3: Iniciar juiz com K respostas
    judge_future = asyncio.create_task(
        asyncio.wait_for(
            judge_fn(prompt, [r.response for r in responses]),
            timeout=config.judge_timeout_s
        )
    )
    
    # Aguarda juiz ou mais respostas
    done, pending = await asyncio.wait(
        [judge_future] + [t for t in tasks if not t.done()],
        timeout=config.judge_timeout_s,
        return_when=asyncio.FIRST_COMPLETED
    )
    
    for task in pending:
        task.cancel()
    
    # Retorna resultado do juiz ou melhor resposta disponível
    if not judge_future.done():
        return FusionResult(
            response=responses[0].response,
            source="judge_timeout",
            models_used=len(responses),
            judge_used=True,
            latency_ms=elapsed_ms + config.judge_timeout_s * 1000,
            confidence=0.7,
        )
    
    try:
        judge_result = judge_future.result()
        return FusionResult(
            response=judge_result["selected_response"],
            source="judge",
            models_used=len(responses),
            judge_used=True,
            latency_ms=(time.time() - start_time) * 1000,
            confidence=judge_result.get("confidence", 0.8),
        )
    except Exception as e:
        logger.error(f"Judge failed: {e}")
        return FusionResult(
            response=responses[0].response,
            source="judge_error",
            models_used=len(responses),
            judge_used=True,
            latency_ms=(time.time() - start_time) * 1000,
            confidence=0.5,
        )


async def _call_model(model: Dict, prompt: str) -> ModelResponse:
    """Chama um modelo e retorna resposta."""
    start = time.time()
    try:
        # Implementação existente de chamada ao modelo
        response = await call_model_via_provider(model["provider_id"], model["model_id"], prompt)
        return ModelResponse(
            model_id=model["model_id"],
            response=response,
            latency_ms=(time.time() - start) * 1000,
            success=True,
        )
    except Exception as e:
        return ModelResponse(
            model_id=model["model_id"],
            response="",
            latency_ms=(time.time() - start) * 1000,
            success=False,
            error=str(e),
        )


async def _check_convergence(
    responses: List[ModelResponse],
    threshold: float,
) -> bool:
    """
    Verifica se respostas convergem (são similares).
    
    Para respostas curtas (<100 chars): comparação exata
    Para respostas longas: similaridade por embedding
    """
    if len(responses) < 2:
        return True
    
    # Normaliza responses
    normalized = []
    for r in responses:
        text = r.response.strip().lower()
        text = ' '.join(text.split())  # Remove espaços extras
        normalized.append(text)
    
    # Verifica pairwise
    for i in range(len(normalized)):
        for j in range(i + 1, len(normalized)):
            if len(normalized[i]) < 100 and len(normalized[j]) < 100:
                # Respostas curtas: comparação exata
                if normalized[i] != normalized[j]:
                    return False
            else:
                # Respostas longas: similaridade por embedding
                sim = await _text_similarity(normalized[i], normalized[j])
                if sim < threshold:
                    return False
    
    return True


async def _text_similarity(a: str, b: str) -> float:
    """Calcula similaridade entre textos (placeholder para embedding)."""
    # Implementação simples com difflib
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio()
```

### 2. Integração com Fusion Config

```python
# backend/routers/fusion.py (modificado)
from ..fusion.k_of_n import fusion_k_of_n, FusionConfig

@router.post("/api/fusion/run")
async def run_fusion(request: dict):
    """
    Endpoint otimizado de Fusion com K-of-N.
    """
    # Configurações
    config = FusionConfig(
        num_models=request.get("num_models", 3),
        k_required=request.get("k_required", 2),
        judge_timeout_s=request.get("judge_timeout", 5.0),
        model_timeout_s=request.get("model_timeout", 10.0),
        convergence_threshold=request.get("convergence_threshold", 0.9),
    )
    
    # Executa Fusion
    result = await fusion_k_of_n(
        prompt=request["prompt"],
        models=request["models"],
        config=config,
        judge_fn=judge_response,  # Função existente
    )
    
    return {
        "response": result.response,
        "source": result.source,
        "models_used": result.models_used,
        "judge_used": result.judge_used,
        "latency_ms": result.latency_ms,
        "confidence": result.confidence,
    }


@router.get("/api/fusion/config")
async def get_fusion_config():
    """Retorna configuração atual do Fusion."""
    return {
        "k_required": 2,
        "judge_timeout_s": 5.0,
        "model_timeout_s": 10.0,
        "convergence_threshold": 0.9,
    }


@router.put("/api/fusion/config")
async def update_fusion_config(request: dict):
    """Atualiza configuração do Fusion."""
    # Persistir config no banco
    pass
```

### 3. Gate: Não Ativar Fusion para Triviais

```python
# backend/fusion/gate.py (NOVO)

def should_use_fusion(prompt: str, intent: str) -> bool:
    """
    Decide se deve usar Fusion baseado no prompt e intent.
    
    Não usa Fusion para:
    - Prompts triviais (saudações, agradecimentos)
    - Tarefas do executor determinístico
    - Requests com low complexity
    """
    # Check trivial
    if len(prompt) < 20 and prompt.lower() in TRIVIAL_PATTERNS:
        return False
    
    # Check intent
    if intent in ["TRIVIAL_QUICK", "DETERMINISTIC"]:
        return False
    
    # Check complexity (se disponível)
    # ... lógica existente ...
    
    return True
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/fusion/k_of_n.py           # Implementação K-of-N
backend/fusion/gate.py             # Gate para não usar Fusion em triviais
```

### Arquivos a Modificar
```
backend/routers/fusion.py          # Integrar novo algoritmo
backend/orchestration/build_context.py  # Passar config
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Latência Fusion (convergência) | N+1 modelos + juiz | K modelos | **-50%** |
| Latência Fusion (timeout) | N+1 modelos + juiz | K modelos + partial | **-30%** |
| Chamadas LLM (fusões simples) | N+1 | K | **-33%** |
| Chamadas LLM (fusões complexas) | N+1 | K+1 (juiz) | **-25%** |
| Custos (free tier) | Alto (cauda longa) | Reduzido | **-40%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_fusion_k_of_n.py
import pytest
import asyncio
from backend.fusion.k_of_n import fusion_k_of_n, FusionConfig, _check_convergence

@pytest.mark.asyncio
async def test_quorum_without_judge():
    """Se 2 de 3 convergirem, não deve usar juiz."""
    models = [
        {"provider_id": "test", "model_id": "m1", "name": "Model 1"},
        {"provider_id": "test", "model_id": "m2", "name": "Model 2"},
        {"provider_id": "test", "model_id": "m3", "name": "Model 3"},
    ]
    
    # Mock: M1 e M2 respondem com mesma resposta, M3 demora
    config = FusionConfig(k_required=2, model_timeout_s=1.0)
    
    result = await fusion_k_of_n(
        prompt="Teste",
        models=models,
        config=config,
        judge_fn=lambda p, r: {"selected_response": r[0]},
    )
    
    assert result.source == "quorum"
    assert result.judge_used == False
    assert result.models_used == 2

@pytest.mark.asyncio
async def test_convergence_short_responses():
    """Respostas curtas idênticas devem convergir."""
    responses = [
        type('obj', (object,), {'response': 'A resposta é 42'})(),
        type('obj', (object,), {'response': 'A resposta é 42'})(),
    ]
    
    assert await _check_convergence(responses, 0.9) == True

@pytest.mark.asyncio
async def test_convergence_different_responses():
    """Respostas diferentes não devem convergir."""
    responses = [
        type('obj', (object,), {'response': 'A resposta é 42'})(),
        type('obj', (object,), {'response': 'A resposta é 100'})(),
    ]
    
    assert await _check_convergence(responses, 0.9) == False

@pytest.mark.asyncio
async def test_timeout_fallback():
    """Deve fallback para respostas disponíveis em timeout."""
    models = [
        {"provider_id": "test", "model_id": "m1", "name": "Model 1"},
        {"provider_id": "test", "model_id": "m2", "name": "Model 2 (lento)"},
    ]
    
    config = FusionConfig(k_required=2, model_timeout_s=0.1)
    
    result = await fusion_k_of_n(
        prompt="Teste",
        models=models,
        config=config,
        judge_fn=lambda p, r: {"selected_response": r[0]},
    )
    
    assert result.source == "timeout"
    assert result.models_used >= 1
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Criar estrutura K-of-N
  - [ ] Criar `k_of_n.py`
  - [ ] Implementar `fusion_k_of_n()`
  - [ ] Implementar `_check_convergence()`
  - [ ] Testar com mocks

- [ ] **Step 2:** Integrar com router
  - [ ] Atualizar `backend/routers/fusion.py`
  - [ ] Adicionar endpoints de config
  - [ ] Manter compatibilidade retroativa

- [ ] **Step 3:** Adicionar gate
  - [ ] Criar `gate.py`
  - [ ] Integrar com smart_router
  - [ ] Testar com prompts triviais

- [ ] **Step 4:** Testes
  - [ ] Testar quorum com convergência
  - [ ] Testar timeout fallback
  - [ ] Testar integração completa

- [ ] **Step 5:** Deploy
  - [ ] Backup
  - [ ] Deploy staging
  - [ ] Ajustar thresholds conforme necessário
  - [ ] Monitorar por 48h

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Falso quorum (respostas parecidas mas erradas) | Baixa | Médio | Threshold configurável (0.8-0.95) |
| Perder resposta melhor (retardatário) | Média | Baixo | Logging + métricas de qualidade |
| Timeout muito curto | Média | Baixo | Default conservador (10s) |
| Break changes na API | Baixa | Alto | Parâmetro opcional, fallback |

---

## 📈 Monitoramento

```python
# Adicionar métricas
FUSION_K_OF_N_QUORUM_HIT = Counter(
    'fusion_k_of_n_quorum_hit_total',
    'Quorum atingido (pulou juiz)'
)

FUSION_K_OF_N_JUDGE_USED = Counter(
    'fusion_k_of_n_judge_used_total',
    'Juiz utilizado apesar de K-of-N'
)

FUSION_K_OF_N_TIMEOUT = Counter(
    'fusion_k_of_n_timeout_total',
    'Timeout atingido (fallback)'
)

FUSION_LATENCY_BY_SOURCE = Histogram(
    'fusion_latency_by_source_seconds',
    'Latência do Fusion por fonte (quorum/judge/timeout)'
)
```

---

## ⚠️ Considerações Importantes

1. **Configuração via Admin:**
   - `k_required`: 2-3 (padrão: 2)
   - `judge_timeout_s`: 3-10s (padrão: 5s)
   - `model_timeout_s`: 5-15s (padrão: 10s)
   - `convergence_threshold`: 0.8-0.95 (padrão: 0.9)

2. **Fallback Seguro:**
   - Se nenhum modelo responder → usar modelo default
   - Se juiz falhar → usar melhor resposta disponível
   - Sempre logar decisões para debugging

3. **Compatibilidade:**
   - Manter API existente funcionando
   - Novo algoritmo como opção (`?mode=k_of_n`)
   - Rollback fácil via feature flag

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #5 (atualizada)*  
*Versão: 2.0 (K-of-N + timeout + convergência)*  
*Responsável: Hermes Agent*
