# Plano: Fusion com Quorum e Juiz Condicional

**Status:** 🆕 Novo (baseado em análise parcial)  
**Tempo Estimado:** 1.5h  
**Risco:** Médio

---

## 📋 Resumo

Oportunidade identificada pela análise Claude (incompleta no prompt original): implementar quorum para decisões do Fusion e juíz condicional baseado em confiança.

---

## 🔍 Problema Identificado

```
Cenário atual (suposição baseado em arquitetura Fusion):
┌────────────────────────────────────────────────────────┐
│ Pipeline Fusion tradicional:                           │
│                                                        │
│ 1. Múltiplos modelos geram respostas                   │
│ 2. Response A (ultra-550b): "X"                        │
│ 3. Response B (super-120b): "Y"                        │
│ 4. Response C (laguna-m): "Z"                          │
│                                                        │
│ 5. Juiz (modelo grande) avalia todas                   │
│ 6. Seleciona a melhor                                  │
│                                                        │
│ Problemas:                                             │
│ • Juiz roda SEMPRE, mesmo quando respostas concordam   │
│ • Custo alto (modelo grande para julgamento)           │
│ • Latência adicionada (mais uma chamada LLM)           │
│ • Desnecessário para tarefas simples                   │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. Sistema de Quorum Simples

```python
# backend/fusion/quorum.py (NOVO)
from typing import List, Dict, Optional
from dataclasses import dataclass
import difflib

@dataclass
class QuorumResult:
    """Resultado da verificação de quorum."""
    has_quorum: bool
    consensus_response: Optional[str] = None
    agreement_score: float = 0.0
    disagree_responses: List[str] = None
    
    def __post_init__(self):
        if self.disagree_responses is None:
            self.disagree_responses = []

def check_quorum(
    responses: List[str],
    threshold: float = 0.8,
    min_agreement: int = 2,
) -> QuorumResult:
    """
    Verifica se há quorum entre respostas (concordância).
    
    Args:
        responses: Lista de respostas dos modelos
        threshold: Similaridade mínima para considerar concordância (0-1)
        min_agreement: Mínimo de respostas concordando
    
    Returns:
        QuorumResult com decisão e score
    """
    if len(responses) < 2:
        return QuorumResult(
            has_quorum=False,
            consensus_response=responses[0] if responses else None,
            agreement_score=1.0,
        )
    
    # Calcula similaridade pairwise
    agreements = []
    disagree_pairs = []
    
    for i in range(len(responses)):
        for j in range(i + 1, len(responses)):
            sim = _text_similarity(responses[i], responses[j])
            if sim >= threshold:
                agreements.append((i, j, sim))
            else:
                disagree_pairs.append((i, j, sim))
    
    # Verifica quorum (maoria concordando)
    if len(agreements) >= min_agreement:
        # Encontrar resposta mais concordante
        scores = {}
        for i, j, sim in agreements:
            scores[i] = scores.get(i, 0) + sim
            scores[j] = scores.get(j, 0) + sim
        
        if scores:
            best_idx = max(scores, key=scores.get)
            return QuorumResult(
                has_quorum=True,
                consensus_response=responses[best_idx],
                agreement_score=scores[best_idx] / max(1, len(responses) - 1),
            )
    
    # Sem quorum
    return QuorumResult(
        has_quorum=False,
        disagree_responses=responses,
    )

def _text_similarity(a: str, b: str) -> float:
    """Calcula similaridade entre dois textos (0-1)."""
    # Normaliza
    a_norm = ' '.join(a.lower().split())
    b_norm = ' '.join(b.lower().split())
    
    # SequenceMatcher
    matcher = difflib.SequenceMatcher(None, a_norm, b_norm)
    return matcher.ratio()
```

### 2. Juiz Condicional

```python
# backend/fusion/conditional_judge.py (NOVO)
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

async def should_use_judge(
    quorum_result,
    task_complexity: str,
    model_confidence: float,
) -> bool:
    """
    Decide se deve usar o juiz (modelo de avaliação).
    
    Args:
        quorum_result: Resultado do quorum
        task_complexity: Complexidade da tarefa (simple/medium/complex)
        model_confidence: Confidence média dos modelos
    
    Returns:
        True se deve usar juiz, False para usar quorum diretamente
    """
    # Caso 1: Quorum atingido - não precisa de juiz
    if quorum_result.has_quorum:
        logger.info(f"Quorum atingido (score={quorum_result.agreement_score:.2f}), pulando juiz")
        return False
    
    # Caso 2: Tarefa simples - não precisa de juiz
    if task_complexity == "simple":
        logger.info("Tarefa simples, pulando juiz")
        return False
    
    # Caso 3: Alta confiança nos modelos - pode pular juiz
    if model_confidence > 0.9:
        logger.info(f"Alta confiança ({model_confidence:.2f}), pulando juiz")
        return False
    
    # Caso 4: Discrepância alta - precisa de juiz
    if quorum_result.agreement_score < 0.5:
        logger.info("Discrepância alta, usando juiz")
        return True
    
    # Default: usar juiz para segurança
    return True
```

### 3. Integração com Fusion Pipeline

```python
# backend/fusion/pipeline.py (modificado)
from .quorum import check_quorum, QuorumResult
from .conditional_judge import should_use_judge

async def fusion_pipeline(
    prompt: str,
    model_responses: List[Dict],
    complexity: str = "medium",
) -> Dict:
    """
    Pipeline Fusion otimizado com quorum e juiz condicional.
    
    Args:
        prompt: Prompt original
        model_responses: Respostas dos modelos base ([{model, response, confidence}])
        complexity: Complexidade da tarefa
    
    Returns:
        Resposta final + metadados
    """
    responses = [r["response"] for r in model_responses]
    confidences = [r.get("confidence", 0.5) for r in model_responses]
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.5
    
    # Passo 1: Verificar quorum
    logger.info("Verificando quorum...")
    quorum_result = check_quorum(responses)
    
    # Passo 2: Decidir se precisa de juiz
    use_judge = await should_use_judge(
        quorum_result=quorum_result,
        task_complexity=complexity,
        model_confidence=avg_confidence,
    )
    
    # Passo 3: Executar pipeline
    if quorum_result.has_quorum and not use_judge:
        # Quorum atingido - usar resposta consenso
        logger.info("Quorum atingido, usando resposta consenso")
        return {
            "response": quorum_result.consensus_response,
            "source": "quorum",
            "confidence": quorum_result.agreement_score,
            "judge_used": False,
            "models_involved": len(model_responses),
        }
    
    elif use_judge:
        # Juiz necessário - avaliar respostas
        logger.info("Usando juiz para avaliação...")
        judge_response = await _call_judge(model_responses)
        
        return {
            "response": judge_response["selected_response"],
            "source": "judge",
            "confidence": judge_response.get("confidence", 0.5),
            "judge_used": True,
            "models_involved": len(model_responses),
        }
    
    else:
        # Sem quorum, sem juiz - escolher melhor modelo
        logger.info("Sem quorum, selecionando melhor modelo")
        best_model = max(model_responses, key=lambda x: x.get("confidence", 0))
        
        return {
            "response": best_model["response"],
            "source": "best_model",
            "confidence": best_model.get("confidence", 0.5),
            "judge_used": False,
            "models_involved": len(model_responses),
        }


async def _call_judge(model_responses: List[Dict]) -> Dict:
    """Chama modelo juiz para avaliação (custoso)."""
    # Implementação existente do judge
    pass
```

### 4. Configuração via Admin

```python
# backend/routers/fusion.py (modificado)
from .quorum import check_quorum
from .conditional_judge import should_use_judge

@router.post("/api/fusion/quorum-check")
async def check_quorum_endpoint(request: dict):
    """
    Endpoint para verificar quorum (useful para debugging).
    """
    responses = request.get("responses", [])
    threshold = request.get("threshold", 0.8)
    min_agreement = request.get("min_agreement", 2)
    
    quorum_result = check_quorum(responses, threshold, min_agreement)
    
    return {
        "has_quorum": quorum_result.has_quorum,
        "consensus_response": quorum_result.consensus_response,
        "agreement_score": quorum_result.agreement_score,
        "disagree_count": len(responses) - sum(1 for _ in quorum_result.agreements) if hasattr(quorum_result, 'agreements') else 0,
    }

@router.post("/api/fusion/judge-decision")
async def judge_decision_endpoint(request: dict):
    """
    Endpoint para simular decisão do juiz condicional.
    """
    quorum_result = request.get("quorum_result", {})
    task_complexity = request.get("task_complexity", "medium")
    model_confidence = request.get("model_confidence", 0.5)
    
    should_use = await should_use_judge(quorum_result, task_complexity, model_confidence)
    
    return {
        "should_use_judge": should_use,
        "reason": _get_reason(should_use, quorum_result, task_complexity, model_confidence),
    }
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/fusion/quorum.py              # Verificação de quorum
backend/fusion/conditional_judge.py   # Juiz condicional
backend/fusion/pipeline.py            # Pipeline integrado
```

### Arquivos a Modificar
```
backend/routers/fusion.py             # Endpoints de debug
backend/providers/registry.py         # Configurações do Fusion
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Chamadas ao juiz | 100% | 30-50% | **-50 a -70%** |
| Latência Fusion (quorum) | 2-5s | 50ms | **-99%** |
| Latência Fusion (juiz) | 2-5s | 2-5s | 0% (quando necessário) |
| Custo Fusion | Alto | Reduzido | **-40 a -60%** |
| Qualidade resposta | 100% | 98-99% | **-1% (aceitável)** |

---

## 🧪 Testes Requeridos

```python
# tests/test_fusion_quorum.py
import pytest
from backend.fusion.quorum import check_quorum, _text_similarity
from backend.fusion.conditional_judge import should_use_judge

@pytest.mark.asyncio
async def test_quorum_high_agreement():
    """Quorum deve ser atingido com respostas similares."""
    responses = [
        "A resposta é 42",
        "A resposta correta é 42",
        "42 é a resposta",
    ]
    
    result = check_quorum(responses, threshold=0.7)
    assert result.has_quorum == True
    assert result.consensus_response is not None
    assert result.agreement_score >= 0.7

@pytest.mark.asyncio
async def test_quorum_no_agreement():
    """Não deve haver quorum com respostas divergentes."""
    responses = [
        "A resposta é 42",
        "A resposta é 100",
        "Não sei a resposta",
    ]
    
    result = check_quorum(responses, threshold=0.8)
    assert result.has_quorum == False

@pytest.mark.asyncio
async def test_text_similarity():
    """Similaridade de texto deve funcionar."""
    sim = _text_similarity("Olá mundo", "Olá mundo")
    assert sim > 0.9
    
    sim = _text_similarity("Olá mundo", "Oi planeta")
    assert sim > 0.5
    
    sim = _text_similarity("Olá mundo", "Resposta diferente")
    assert sim < 0.3

@pytest.mark.asyncio
async def test_conditional_judge_simple_task():
    """Juiz não deve ser usado para tarefas simples."""
    quorum = type('obj', (object,), {'has_quorum': False})()
    
    should_use = await should_use_judge(quorum, "simple", 0.8)
    assert should_use == False

@pytest.mark.asyncio
async def test_conditional_judge_high_confidence():
    """Juiz não deve ser usado com alta confiança."""
    quorum = type('obj', (object,), {'has_quorum': False, 'agreement_score': 0.6})()
    
    should_use = await should_use_judge(quorum, "complex", 0.95)
    assert should_use == False

@pytest.mark.asyncio
async def test_conditional_judge_disagreement():
    """Juiz deve ser usado com baixa concordância."""
    quorum = type('obj', (object,), {'has_quorum': False, 'agreement_score': 0.3})()
    
    should_use = await should_use_judge(quorum, "complex", 0.5)
    assert should_use == True
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Implementar Quorum
  - [ ] Criar `quorum.py`
  - [ ] Implementar `check_quorum()`
  - [ ] Implementar `_text_similarity()`
  - [ ] Testar com casos variados

- [ ] **Step 2:** Implementar Juiz Condicional
  - [ ] Criar `conditional_judge.py`
  - [ ] Implementar `should_use_judge()`
  - [ ] Testar lógica de decisão

- [ ] **Step 3:** Integrar com Pipeline
  - [ ] Criar `pipeline.py`
  - [ ] Integrar quorum + juiz condicional
  - [ ] Manter compatibilidade com pipeline existente

- [ ] **Step 4:** Adicionar Endpoints
  - [ ] Endpoint `/api/fusion/quorum-check`
  - [ ] Endpoint `/api/fusion/judge-decision`
  - [ ] Documentar para debugging

- [ ] **Step 5:** Testes
  - [ ] Testar quorum com diversas entradas
  - [ ] Testar decisão do juiz
  - [ ] Testar integração completa

- [ ] **Step 6:** Deploy
  - [ ] Backup do banco
  - [ ] Deploy em staging
  - [ ] Monitorar taxa de quorum vs juiz
  - [ ] Ajustar thresholds se necessário

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Falso quorum (respostas parecidas mas erradas) | Baixa | Médio | Threshold conservador (0.8) |
| Juiz desnecessário ainda chamado | Média | Baixo | Logs detalhados para debug |
| Performance piora (cálculo de similaridade) | Baixa | Baixo | Otimizar com caching |
| Break changes na API existente | Baixa | Alto | Manter interface compatível |

---

## 📈 Monitoramento

```python
# Adicionar métricas
FUSION_QUORUM_HIT = Counter(
    'fusion_quorum_hit_total',
    'Quorum atingido (pulou juiz)'
)

FUSION_JUDGE_USED = Counter(
    'fusion_judge_used_total',
    'Juiz utilizado'
)

FUSION_JUDGE_SKIPPED = Counter(
    'fusion_judge_skipped_total',
    'Juiz pulado (quorum/confiança)'
)

FUSION_AVG_AGREEMENT = Histogram(
    'fusion_avg_agreement_score',
    'Score médio de acordo entre modelos'
)

FUSION_LATENCY_BREAKDOWN = Histogram(
    'fusion_latency_seconds',
    'Latência do Fusion (quorum vs judge)'
)
```

---

## ⚠️ Considerações Importantes

1. **Thresholds Ajustáveis:** Permitir ajuste via admin interface
   - `quorum_threshold`: 0.7-0.9 (padrão: 0.8)
   - `min_agreement`: 2-3 (padrão: 2)
   - `confidence_threshold`: 0.8-0.95 (padrão: 0.9)

2. **Fallback Seguro:** Se quorum falhar, sempre usar juiz para tarefas complexas
   - Não arriscar qualidade por velocidade

3. **Log Detalhado:** Registrar decisões para análise posterior
   - Por que quorum falhou?
   - Por que juiz foi necessário?
   - Qual a dispersão das respostas?

4. **A/B Testing:** Permitir testar diferentes configurações
   - Rolling deployment com flags
   - Comparar qualidade vs velocidade

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #5 (incompleta, ampliada)*  
*Responsável: Hermes Agent*
