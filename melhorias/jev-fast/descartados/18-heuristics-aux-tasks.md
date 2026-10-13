# Plano: Heurísticas para Tarefas Auxiliares (Título e Busca Web)

**Status:** 🆕 Novo  
**Tempo Estimado:** 45 min  
**Risco:** Baixo

---

## 📋 Resumo

Oportunidade identificada: substituir LLM por heurísticas em tarefas auxiliares como geração de título de conversa e decisão de busca na web. Adicionar cache de resultados de busca.

---

## 🔍 Problema Identificado

```
Cenário atual (suposição a confirmar):
┌────────────────────────────────────────────────────────┐
│ 1. Título da conversa gerado por LLM                  │
│    • 1 chamada LLM por chat criado                     │
│    • Custo: ~500ms + tokens                            │
│    • Resultado: "Conversa sobre Python" (genérico)     │
│                                                        │
│ 2. Decisão de busca web por LLM                        │
│    • 1 chamada LLM para decidir "buscar ou não?"       │
│    • Se buscar: +1 chamada LLM + ddgs (1-2s)          │
│    • Buscas repetidas não são cacheadas                │
│                                                        │
│ TOTAL desperdiçado:                                    │
│ • 1-2 chamadas LLM por interação inicial              │
│ • 1-2s em buscas repetidas                             │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. Título por Heurística

```python
# backend/conversations/title_generator.py (NOVO)
import re
from typing import Optional

class TitleGenerator:
    """
    Gera títulos de conversa usando heurísticas (sem LLM).
    
    Estratégía:
    1. Extrair primeira frase do primeiro prompt
    2. Limpar e truncar para ~50 caracteres
    3. Refinar com LLM apenas se heurística falhar
    """
    
    # Padrões para extração
    QUESTION_PATTERNS = [
        re.compile(r'^[?？]\s*(.+)', re.MULTILINE),  # Começa com ?
        re.compile(r'^(como|o que|qual|quando|onde|por que|quem)\s', re.I),  # Palavras interrogativas
    ]
    
    STATEMENT_PATTERNS = [
        re.compile(r'^(vou|quiero|want|need|preciso)\s', re.I),  # Declarações de intenção
    ]
    
    @classmethod
    def generate_title(cls, messages: list, use_llm_fallback: bool = True) -> str:
        """
        Gera título a partir das mensagens.
        
        Args:
            messages: Lista de mensagens da conversa
            use_llm_fallback: Se True, usa LLM se heurística falhar
        
        Returns:
            Título gerado (max 50 chars)
        """
        if not messages:
            return "Nova conversa"
        
        # Pega primeira mensagem do usuário
        first_user_msg = None
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Multimodal: extrai texto
                    content = " ".join(
                        p.get("text", "") 
                        for p in content 
                        if isinstance(p, dict) and p.get("type") == "text"
                    )
                first_user_msg = content.strip()
                break
        
        if not first_user_msg:
            return "Nova conversa"
        
        # Tenta extrair pergunta
        title = cls._extract_question(first_user_msg)
        
        # Se não encontrou pergunta, usa primeira frase
        if not title or len(title) < 3:
            title = cls._extract_first_sentence(first_user_msg)
        
        # Limpa e truncar
        title = cls._clean_title(title)
        
        # Fallback para LLM se título muito genérico
        if len(title) < 5 and use_llm_fallback:
            title = cls._llm_generate_title(messages)
        
        return title or "Nova conversa"
    
    @classmethod
    def _extract_question(cls, text: str) -> Optional[str]:
        """Extrai pergunta do texto."""
        for pattern in cls.QUESTION_PATTERNS:
            match = pattern.match(text)
            if match:
                return match.group(1).strip()
        return None
    
    @classmethod
    def _extract_first_sentence(cls, text: str) -> str:
        """Extrai primeira frase do texto."""
        # Divide por terminadores de frase
        sentences = re.split(r'[.!?。]+', text)
        if sentences:
            return sentences[0].strip()
        return text[:50]
    
    @classmethod
    def _clean_title(cls, title: str) -> str:
        """Limpa e truncar título."""
        # Remove caracteres especiais
        title = re.sub(r'[^\w\sÀ-Üà-öõ-ÿ\'-]', ' ', title)
        # Normaliza espaços
        title = ' '.join(title.split())
        # Truncan
        if len(title) > 50:
            title = title[:47] + "..."
        return title.strip()
    
    @classmethod
    def _llm_generate_title(cls, messages: list) -> str:
        """
        Fallback: usa LLM para gerar título.
        """
        # Implementação existente (chama LLM)
        # ...
        return "Conversa"
```

### 2. Decisão de Busca Web por Heurística

```python
# backend/web_search/decision.py (NOVO)
import re
from typing import Optional

class WebSearchDecision:
    """
    Decide se deve buscar na web usando heurísticas (sem LLM).
    """
    
    # Palavras-chave que indicam necessidade de busca
    SEARCH_TRIGGERS = [
        r'\b(hoje|atual|atualmente|último|ultima|recente|novo|nova)\b',  # Temporal
        r'\b(preço|valor|custo|quanto custa|qual valor)\b',  # Preço
        r'\b(últimas notícias|notícias de hoje|breaking news)\b',  # Notícias
        r'\b(http|https|www\.)\b',  # URLs
        r'\b(\d{4})\b',  # Anos recentes
        r'\b(new|latest|recent|update)\b',  # Inglês
    ]
    
    # Padrões que NÃO precisam de busca
    NO_SEARCH_PATTERNS = [
        r'^\s*$',  # Vazio
        r'\b(oi|olá|ola|hello|hi)\b',  # Saudações
        r'\b(obrigado|obrigada|thanks|thank you)\b',  # Agradecimento
        r'\b(tchau|adeus|bye)\b',  # Despedida
        r'\b(sim|não|nao|yes|no)\b',  # Sim/não
    ]
    
    @classmethod
    def should_search(cls, prompt: str, conversation_history: list = None) -> bool:
        """
        Decide se deve buscar na web.
        
        Returns:
            True se deve buscar, False caso contrário
        """
        if not prompt or len(prompt.strip()) < 3:
            return False
        
        prompt_lower = prompt.lower()
        
        # Check NO_SEARCH patterns primeiro
        for pattern in cls.NO_SEARCH_PATTERNS:
            if re.search(pattern, prompt_lower):
                return False
        
        # Check SEARCH triggers
        trigger_count = 0
        for pattern in cls.SEARCH_TRIGGERS:
            if re.search(pattern, prompt_lower):
                trigger_count += 1
        
        # Decide baseado em triggers
        if trigger_count >= 2:
            return True
        
        # Long prompt + mentions de ano recente
        if len(prompt) > 100 and re.search(r'\b(202[4-6]|2023)\b', prompt):
            return True
        
        # URL no prompt
        if re.search(r'https?://', prompt):
            return True
        
        # Default: não buscar
        return False
    
    @classmethod
    def get_search_intent(cls, prompt: str) -> str:
        """
        Extrai intent de busca para cache key.
        """
        # Normaliza prompt para cache
        intent = prompt.lower().strip()
        intent = re.sub(r'\s+', ' ', intent)  # Normaliza espaços
        intent = re.sub(r'[^\w\s]', '', intent)  # Remove pontuação
        
        return intent
```

### 3. Cache de Busca Web

```python
# backend/web_search/cache.py (NOVO)
import asyncio
import hashlib
import time
from typing import Optional, Dict, List
from dataclasses import dataclass
import aiosqlite

@dataclass
class SearchCacheEntry:
    """Entrada no cache de busca."""
    query_hash: str
    query: str
    results: List[Dict]
    cached_at: float
    ttl_seconds: int = 600  # 10 minutos default

class WebSearchCache:
    """
    Cache de resultados de busca web.
    
    TTL: 10-15 minutos (configurável)
    Key: hash normalizado da query
    """
    
    def __init__(self, ttl_seconds: int = 600):
        self._ttl = ttl_seconds
        self._cache: Dict[str, SearchCacheEntry] = {}
        self._lock = asyncio.Lock()
    
    def _hash_query(self, query: str) -> str:
        """Gera hash da query normalizada."""
        normalized = query.lower().strip()
        normalized = ' '.join(normalized.split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]
    
    async def get(self, query: str) -> Optional[List[Dict]]:
        """Busca resultado cacheado."""
        async with self._lock:
            query_hash = self._hash_query(query)
            entry = self._cache.get(query_hash)
            
            if entry and time.time() < entry.cached_at + entry.ttl_seconds:
                return entry.results
            elif entry:
                # Expired
                del self._cache[query_hash]
            
            return None
    
    async def set(self, query: str, results: List[Dict]):
        """Armazena resultado no cache."""
        async with self._lock:
            query_hash = self._hash_query(query)
            self._cache[query_hash] = SearchCacheEntry(
                query_hash=query_hash,
                query=query,
                results=results,
                cached_at=time.time(),
                ttl_seconds=self._ttl,
            )
    
    async def clear_expired(self):
        """Remove entradas expiradas."""
        async with self._lock:
            now = time.time()
            expired = [
                h for h, e in self._cache.items()
                if now > e.cached_at + e.ttl_seconds
            ]
            for h in expired:
                del self._cache[h]
            return len(expired)
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas do cache."""
        return {
            "entries": len(self._cache),
            "ttl_seconds": self._ttl,
        }


# Singleton
web_search_cache = WebSearchCache(ttl_seconds=600)
```

### 4. Integração com Web Search Agent

```python
# backend/web_search/agent.py (modificado)
from .decision import WebSearchDecision
from .cache import web_search_cache

async def run_web_search(prompt: str, conversation_history: list = None):
    """
    Executa busca na web com decisões heurísticas e cache.
    """
    # Decide se deve buscar
    should_search = WebSearchDecision.should_search(
        prompt, 
        conversation_history
    )
    
    if not should_search:
        return {
            "search_performed": False,
            "reason": "heuristics",
            "results": [],
        }
    
    # Check cache
    cached_results = await web_search_cache.get(prompt)
    if cached_results:
        return {
            "search_performed": True,
            "source": "cache",
            "results": cached_results,
        }
    
    # Executa busca real
    results = await perform_search(prompt)
    
    # Cacheia resultado
    await web_search_cache.set(prompt, results)
    
    return {
        "search_performed": True,
        "source": "live",
        "results": results,
    }


async def perform_search(query: str) -> List[Dict]:
    """Executa busca real (ddgs ou outro motor)."""
    # Implementação existente
    pass
```

### 5. Integração com Conversations

```python
# backend/routers/conversations.py (modificado)
from backend.conversations.title_generator import TitleGenerator

@router.post("/conversations")
async def create_conversation(request: CreateConversationRequest):
    """
    Cria nova conversa com título heurístico.
    """
    # Gera título automaticamente
    title = TitleGenerator.generate_title(request.messages)
    
    # Cria conversa
    conv = await db.execute(
        "INSERT INTO conversations (title, created_at) VALUES (?, ?)",
        (title, datetime.now())
    )
    
    return {"id": conv.lastrowid, "title": title}
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/conversations/title_generator.py    # Heurística de título
backend/web_search/decision.py              # Decisão de busca
backend/web_search/cache.py                 # Cache de buscas
```

### Arquivos a Modificar
```
backend/web_search/agent.py                 # Integrar decisão + cache
backend/routers/conversations.py            # Usar título heurístico
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Chamadas LLM para título | 1 por conversa | 0 (fallback só se necessário) | **-100%** |
| Chamadas LLM para decisão de busca | 1 por interação | 0 | **-100%** |
| Buscas web重复 (mesma query) | 100% request | ~10% (após TTL) | **-90%** |
| Latência criação conversa | 500ms+ | 1ms | **-99%** |
| Latência decisão busca | 500ms+ | 1ms | **-99%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_heuristics.py
import pytest
from backend.conversations.title_generator import TitleGenerator
from backend.web_search.decision import WebSearchDecision
from backend.web_search.cache import WebSearchCache

@pytest.mark.asyncio
async def test_title_extraction_question():
    """Título deve extrair pergunta."""
    messages = [
        {"role": "user", "content": "Como funciona o Python?"}
    ]
    title = TitleGenerator.generate_title(messages)
    assert "Python" in title
    assert len(title) <= 50

@pytest.mark.asyncio
async def test_title_truncation():
    """Título longo deve ser truncado."""
    messages = [
        {"role": "user", "content": "Quero saber tudo sobre programación em Python para iniciantes com exemplos práticos"}
    ]
    title = TitleGenerator.generate_title(messages)
    assert len(title) <= 50
    assert title.endswith("...")

@pytest.mark.asyncio
async def test_search_decision_trigger():
    """Busca deve ser acionada por gatilhos temporais."""
    assert WebSearchDecision.should_search("Qual o preço do Bitcoin hoje?") == True
    assert WebSearchDecision.should_search("Últimas notícias sobre IA") == True

@pytest.mark.asyncio
async def test_search_decision_no_trigger():
    """Busca não deve ser acionada para triviais."""
    assert WebSearchDecision.should_search("Oi, tudo bem?") == False
    assert WebSearchDecision.should_search("Obrigado!") == False
    assert WebSearchDecision.should_search("Me explica Python") == False

@pytest.mark.asyncio
async def test_search_cache():
    """Cache de busca deve funcionar."""
    cache = WebSearchCache(ttl_seconds=60)
    
    # Set
    await cache.set("python tutorial", [{"title": "Python 101"}])
    
    # Get (deve cache)
    results = await cache.get("python tutorial")
    assert results == [{"title": "Python 101"}]
    
    # Get (miss - query diferente)
    results = await cache.get("javascript tutorial")
    assert results is None

@pytest.mark.asyncio
async def test_search_cache_expiry():
    """Cache deve expirar."""
    cache = WebSearchCache(ttl_seconds=1)
    
    await cache.set("test query", [{"result": "data"}])
    
    # Aguarda expirar
    await asyncio.sleep(1.1)
    
    # Deve retornar None
    results = await cache.get("test query")
    assert results is None
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Heurística de título
  - [ ] Criar `title_generator.py`
  - [ ] Implementar extração de pergunta
  - [ ] Implementar clean/truncate
  - [ ] Testar com mensagens variadas

- [ ] **Step 2:** Decisão de busca
  - [ ] Criar `decision.py`
  - [ ] Implementar triggers
  - [ ] Implementar no-search patterns
  - [ ] Testar com prompts variados

- [ ] **Step 3:** Cache de busca
  - [ ] Criar `cache.py`
  - [ ] Implementar TTL (10 min)
  - [ ] Implementar stats
  - [ ] Testar expiração

- [ ] **Step 4:** Integração
  - [ ] Atualizar `web_search/agent.py`
  - [ ] Atualizar `conversations.py`
  - [ ] Testar fluxo completo

- [ ] **Step 5:** Deploy
  - [ ] Deploy staging
  - [ ] Monitorar uso de LLM
  - [ ] Ajustar thresholds se necessário

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Heurística erra título | Média | Baixo | Fallback para LLM se título < 5 chars |
| Heurística erra decisão de busca | Baixa | Médio | Usuário pode forçar busca manualmente |
| Cache stale (informação desatualizada) | Média | Baixo | TTL curto (10 min) + forced refresh |
| Falso positivo (busca desnecessária) | Baixa | Baixo | Logar para ajuste fino |

---

## 📈 Monitoramento

```python
# Adicionar métricas
TITLE_GENERATED_HEURISTIC = Counter(
    'title_heuristic_total',
    'Títulos gerados por heurística'
)

TITLE_GENERATED_LLM = Counter(
    'title_llm_total',
    'Títulos gerados por LLM (fallback)'
)

SEARCH_DECIDED_HEURISTIC = Counter(
    'search_heuristic_total',
    'Decisões de busca por heurística'
)

SEARCH_CACHE_HIT = Counter(
    'search_cache_hit_total',
    'Buscas com hit no cache'
)

SEARCH_CACHE_MISS = Counter(
    'search_cache_miss_total',
    'Buscas com miss no cache'
)
```

---

## ⚠️ Considerações Importantes

1. **Fallback para LLM:**
   - Se heurística gera título muito genérico (< 5 chars), usa LLM
   - Se usuário force busca (botão), ignora heurística

2. **TTL Configurável:**
   - Default: 10 minutos
   - Admin pode ajustar via `/api/admin/search-cache/config`

3. **Query Normalization:**
   - "Python tutorial" == "python tutorial" == " PYTHON  tutorial "
   - Normalização case-insensitive + spaces collapsed

4. **Clear Manual:**
   - Endpoint para limpar cache se necessário
   - `/api/admin/search-cache/clear`

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #8*  
*Responsável: Hermes Agent*
