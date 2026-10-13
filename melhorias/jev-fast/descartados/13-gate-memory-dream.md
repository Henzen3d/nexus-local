# Plano: Gate Determinístico do Extrator de Memória e Dream

**Status:** 🆕 Novo  
**Tempo Estimado:** 2h  
**Risco:** Médio (pode perder fatos sutis)

---

## 📋 Resumo

Oportunidade identificada pela análise Claude: implementar gate determinístico para extração de memória e consolidação Dream, reduzindo chamadas LLM desnecessárias em 60-80%.

---

## 🔍 Problema Identificado

```
Cenário atual:
┌────────────────────────────────────────────────────────┐
│ Após CADA resposta do LLM:                             │
│                                                        │
│ 1. Dream extrator roda (consome quota do provedor)    │
│    - Processa TUDO: saudações, confirmações, etc.      │
│    - Gasta cota do provedor free                       │
│    - Aumenta chance de 429 no próximo turno            │
│                                                        │
│ 2. Dream consolidator roda periodicamente              │
│    - Mandar memória para LLM mesmo sem mudança         │
│    - Consome quota adicional                           │
│                                                        │
│ Impacto:                                               │
│ - 40% das mensagens geram extração desnecessária       │
│ - Quota do provedor free esgota mais rápido            │
│ - Custo aumentado sem benefício                        │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. Gate Determinístico para Extração

```python
# backend/memory/extraction_gate.py (NOVO)
import re
from typing import Optional
from dataclasses import dataclass

@dataclass
class ExtractionSignal:
    """Sinais que indicam possibilidade de fato novo."""
    has_first_person: bool = False
    has_personal_pronoun: bool = False
    has_date_number: bool = False
    has_proper_name: bool = False
    has_new_topic: bool = False
    confidence: float = 0.0

# Padrões para detecção de sinais
_FIRST_PERSON_PATTERNS = re.compile(
    r'\b((?:eu|meu|minha|nós|nosso|nossa)|I|my|we|our)\b',
    re.IGNORECASE
)

 personal_pronouns = {'eu', 'meu', 'minha', 'nos', 'nossa', 'i', 'my', 'we', 'our'}
 dates_pattern = re.compile(r'\b(\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}|hoje|ontem|amanhã|semana|mês|ano)\b', re.I)
 numbers_pattern = re.compile(r'\b(\\d+\\s+(anos?|metros?|quilos?|reais?|anos?))\b', re.I)
 names_pattern = re.compile(r'\b([A-Z][a-z]+\\s+[A-Z][a-z]+)\b')  # Nomes próprios

def analyze_extraction_signals(message: str) -> ExtractionSignal:
    """
    Analisa mensagem e retorna sinais de possível fato novo.
    
    Retorna confidence 0.0-1.0 baseado nos sinais detectados.
    """
    signal = ExtractionSignal()
    
    # First person detection
    if _FIRST_PERSON_PATTERNS.search(message):
        signal.has_first_person = True
        signal.confidence += 0.3
    
    # Personal pronouns
    words = message.lower().split()
    if any(w.strip('.,!?;:') in personal_pronouns for w in words):
        signal.has_personal_pronoun = True
        signal.confidence += 0.2
    
    # Dates
    if dates_pattern.search(message):
        signal.has_date_number = True
        signal.confidence += 0.2
    
    # Numbers with units
    if numbers_pattern.search(message):
        signal.has_date_number = True
        signal.confidence += 0.1
    
    # Proper names (capitalized words in pairs)
    if names_pattern.search(message):
        signal.has_proper_name = True
        signal.confidence += 0.2
    
    # New topic detection (simplified: long message with new entities)
    if len(message) > 100 and signal.confidence > 0.3:
        signal.has_new_topic = True
        signal.confidence += 0.1
    
    return signal

def should_extract_memory(
    message: str,
    conversation_turns: int,
    last_extraction_turn: int,
) -> tuple[bool, ExtractionSignal]:
    """
    Decide se deve extrair memória da mensagem.
    
    Args:
        message: Mensagem do usuário
        conversation_turns: Total de turnos na conversa
        last_extraction_turn: Último turno que teve extração
    
    Returns:
        (should_extract, signal)
    """
    signal = analyze_extraction_signals(message)
    
    # Debounce: não extrair a cada turno
    turns_since_last = conversation_turns - last_extraction_turn
    if turns_since_last < 3:
        return False, signal
    
    # Threshold de confiança
    if signal.confidence < 0.4:
        return False, signal
    
    # Requer pelo menos 2 sinais
    signs_count = sum([
        signal.has_first_person,
        signal.has_personal_pronoun,
        signal.has_date_number,
        signal.has_proper_name,
    ])
    
    if signs_count < 2:
        return False, signal
    
    return True, signal
```

### 2. Gate para Dream Consolidator

```python
# backend/memory/dream_gate.py (NOVO)
from typing import List, Dict

async def should_run_dream(
    user_id: str,
    facts_created_since_last: int,
    total_facts: int,
) -> tuple[bool, str]:
    """
    Decide se deve rodar o Dream consolidator.
    
    Args:
        user_id: ID do usuário
        facts_created_since_last: Fatos criados desde último Dream
        total_facts: Total de fatos no banco
    
    Returns:
        (should_run, reason)
    """
    # Threshold mínimo de fatos novos
    if facts_created_since_last < 3:
        return False, f"apenas {facts_created_since_last} fatos novos (min: 3)"
    
    # Threshold relativo (5% do total)
    threshold_relative = max(5, total_facts * 0.05)
    if facts_created_since_last < threshold_relative:
        return False, f"{facts_created_since_last} fatos novos < {threshold_relative} (5% do total)"
    
    # Limite superior (evitar processar muitos de uma vez)
    if facts_created_since_last > 20:
        return True, f"batch grande: {facts_created_since_last} fatos"
    
    return True, f"{facts_created_since_last} fatos novos"
```

### 3. Deduplication Determinística

```python
# backend/memory/dedup.py (NOVO)
import hashlib
from typing import List, Dict

def compute_fact_key(fact: Dict) -> str:
    """
    Gera key determinística para fato (sem LLM).
    
    Normaliza texto e gera hash para comparação rápida.
    """
    # Normaliza
    text = fact.get("fact", "").lower().strip()
    text = re.sub(r'\s+', ' ', text)  # Remove espaços extras
    text = re.sub(r'[^\w\s]', '', text)  # Remove pontuação
    
    # Gera hash
    return hashlib.sha256(text.encode()).hexdigest()[:16]

async def deduplicate_facts(
    new_facts: List[Dict],
    existing_facts: List[Dict],
) -> Dict[str, List[str]]:
    """
    Deduplica fatos novos contra existentes via hash.
    
    Returns:
        Dict com grupos de fatos duplicados
    """
    # Computa keys para fatos existentes
    existing_keys = {}
    for fact in existing_facts:
        key = compute_fact_key(fact)
        if key not in existing_keys:
            existing_keys[key] = []
        existing_keys[key].append(fact["id"])
    
    # Agrupa novos fatos por key
    new_groups = {}
    for fact in new_facts:
        key = compute_fact_key(fact)
        if key not in new_groups:
            new_groups[key] = []
        new_groups[key].append(fact)
    
    # Encontra duplicatas
    duplicates = {}
    for key, new_items in new_groups.items():
        if key in existing_keys and len(new_items) > 1:
            duplicates[key] = {
                "existing_ids": existing_keys[key],
                "new_ids": [f["id"] for f in new_items],
            }
    
    return duplicates
```

### 4. Clustering Simples (sem LLM)

```python
# backend/memory/clustering.py (NOVO)
import numpy as np
from typing import List, Dict

def cluster_facts_by_similarity(
    facts: List[Dict],
    embeddings: List[np.ndarray],
    threshold: float = 0.85,
) -> List[List[int]]:
    """
    Agrupa fatos por similaridade de embedding (cosseno > threshold).
    
    Apenas clusters ambíguos (múltiplos fatos semelhantes) vão para o LLM.
    Fatos únicos são mantidos separados.
    """
    if len(facts) < 2:
        return [[i] for i in range(len(facts))]
    
    # Calcula matriz de similaridade
    embeddings_array = np.array(embeddings)
    similarities = embeddings_array @ embeddings_array.T
    
    # Agrupa por threshold
    clusters = []
    visited = set()
    
    for i in range(len(facts)):
        if i in visited:
            continue
        
        cluster = [i]
        visited.add(i)
        
        for j in range(i + 1, len(facts)):
            if j in visited:
                continue
            
            if similarities[i][j] >= threshold:
                cluster.append(j)
                visited.add(j)
        
        clusters.append(cluster)
    
    return clusters
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/memory/extraction_gate.py    # Gate determinístico para extração
backend/memory/dream_gate.py         # Gate para Dream consolidator
backend/memory/dedup.py              # Deduplicação por hash
backend/memory/clustering.py         # Clustering por similaridade
```

### Arquivos a Modificar
```
backend/memory_dream.py              # Integrar gates
backend/memory.py                    # Usar new extraction logic
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Chamadas de extração | 100% das msgs | ~20-40% | **-60 a -80%** |
| Quota consumida (dream) | Alta | Reduzida | **-50%** |
| Fatos perdidos | 0% | <2% (shadow mode) | Aceitável |
| Latência extração | 500ms (LLM) | 5ms (regex) | **-99%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_extraction_gate.py
import pytest
from backend.memory.extraction_gate import should_extract_memory, analyze_extraction_signals

@pytest.mark.asyncio
async def test_greeting_no_extraction():
    """Saudações não devem disparar extração."""
    signal = analyze_extraction_signals("Oi, tudo bem?")
    assert signal.confidence < 0.4
    
    should_extract, _ = should_extract_memory("Oi, tudo bem?", 5, 0)
    assert should_extract == False

@pytest.mark.asyncio
async def test_personal_fact_extraction():
    """Fatos pessoais devem disparar extração."""
    signal = analyze_extraction_signals(
        "Eu moro em Blumenau desde 2010 e tenho 46 anos"
    )
    assert signal.confidence >= 0.4
    assert signal.has_first_person == True
    assert signal.has_date_number == True
    
    should_extract, _ = should_extract_memory(
        "Eu moro em Blumenau desde 2010",
        conversation_turns=10,
        last_extraction_turn=5
    )
    assert should_extract == True

@pytest.mark.asyncio
async def test_debounce_works():
    """Debounce deve evitar extração em turnos consecutivos."""
    should_extract, _ = should_extract_memory(
        "Eu gosto de café",
        conversation_turns=5,
        last_extraction_turn=4  # Só 1 turno desde última
    )
    assert should_extract == False  # Debounce ativo

@pytest.mark.asyncio
async def test_dream_gate_threshold():
    """Dream deve rodar apenas com facts suficientes."""
    from backend.memory.dream_gate import should_run_dream
    
    # Poucos facts
    should_run, reason = await should_run_dream("user1", 2, 50)
    assert should_run == False
    
    # Facts suficientes
    should_run, reason = await should_run_dream("user1", 10, 50)
    assert should_run == True
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Implementar Extraction Gate
  - [ ] Criar `extraction_gate.py`
  - [ ] Implementar `analyze_extraction_signals()`
  - [ ] Implementar `should_extract_memory()`
  - [ ] Testar com mensagens variadas

- [ ] **Step 2:** Implementar Dream Gate
  - [ ] Criar `dream_gate.py`
  - [ ] Implementar `should_run_dream()`
  - [ ] Testar thresholds

- [ ] **Step 3:** Implementar Deduplication
  - [ ] Criar `dedup.py`
  - [ ] Implementar `compute_fact_key()`
  - [ ] Implementar `deduplicate_facts()`
  - [ ] Testar com fatos duplicados

- [ ] **Step 4:** Implementar Clustering
  - [ ] Criar `clustering.py`
  - [ ] Implementar `cluster_facts_by_similarity()`
  - [ ] Testar com embeddings

- [ ] **Step 5:** Integrar com Dream
  - [ ] Atualizar `memory_dream.py`
  - [ ] Aplicar gates antes de processar
  - [ ] Agrupar fatos ambíguos

- [ ] **Step 6:** Shadow Mode
  - [ ] Habilitar modo shadow (logar decisões sem aplicar)
  - [ ] Rodar por 1 semana
  - [ ] Comparar com extração anterior
  - [ ] Calibrar thresholds

- [ ] **Step 7:** Deploy
  - [ ] Backup do banco
  - [ ] Deploy em staging
  - [ ] Monitorar por 48h
  - [ ] Comparar qualidade dos fatos

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Perder fatos sutis | Média | Médio | Shadow mode + calibração |
| Falso positivo (extração desnecessária) | Baixa | Baixo | Thresholds conservadores |
| Falso negativo (não extrair quando deveria) | Baixa | Alto | Manter fallback para LLM |
| Deduplication falha | Baixa | Baixo | Hash colisão é rara |
| Performance do clustering | Média | Baixo | Limitar tamanho do cluster |

---

## 📈 Monitoramento

```python
# Adicionar métricas
EXTRACTION_GATE_triggered = Counter(
    'extraction_gate_triggered_total',
    'Vezes que gate permitiu extração'
)

EXTRACTION_GATE_filtered = Counter(
    'extraction_gate_filtered_total',
    'Vezes que gate filtrou extração'
)

DREAM_GATE_triggered = Counter(
    'dream_gate_triggered_total',
    'Vezes que dream gate permitiu execução'
)

DREAM_GATE_filtered = Counter(
    'dream_gate_filtered_total',
    'Vezes que dream gate filtrou execução'
)

FACTS_EXTRACTION_RATE = Histogram(
    'facts_extraction_rate',
    'Taxa de extração por mensagem'
)
```

---

## ⚠️ Considerações Importantes

1. **Shadow Mode:** Implementar em modo shadow primeiro (logar decisões sem aplicar)
   - Comparar com extração anterior por 1 semana
   - Calibrar thresholds baseado em falsos negativos

2. **Fallback para LLM:** Se gate detectar algo ambíguo, ainda chamar LLM
   - Não perder fatos importantes por eficiência

3. **Confiança Gradual:** Aumentar thresholds gradualmente
   - Começar com threshold alto (conservador)
   - Reduzir conforme validação

4. **Feedback Loop:** Permitir correção manual de fatos perdidos
   - Usuário pode marcar "estoque esqueceu este fato"
   - Usar para calibrar thresholds

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #4*  
*Responsável: Hermes Agent*
