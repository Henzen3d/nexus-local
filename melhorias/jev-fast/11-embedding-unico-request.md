# Plano: Embedding Único por Request

**Status:** 🆕 Novo  
**Tempo Estimado:** 45 min  
**Risco:** Baixo

---

## 📋 Resumo

Oportunidade identificada pela análise Claude: calcular embedding apenas uma vez por request e reutilizá-lo em cache semântico, RAG de projetos e recuperação de memória.

---

## 🔍 Problema Identificado

```
Request: "Me ajuda com meu projeto Python"
┌────────────────────────────────────────────────────────┐
│ Pipeline atual (3 embeddings):                         │
│                                                        │
│ 1. Cache semântico:                                    │
│    - embed_text(prompt) → 100ms                        │
│    - scan 132 entries → 13ms                           │
│                                                        │
│ 2. RAG de Projetos:                                    │
│    - embed_text(prompt) → 100ms (DUPLICADO!)          │
│    - busca similaridade → 5ms                          │
│                                                        │
│ 3. Recuperação de memória:                             │
│    - embed_text(prompt) → 100ms (DUPLICADO!)          │
│    - busca memória relevante → 10ms                    │
│                                                        │
│ TOTAL: ~318ms (3x embedding)                            │
└────────────────────────────────────────────────────────┘
```

---

## ✅ Solução Proposta

### 1. RequestContext com Memoização

```python
# backend/context/request_context.py (NOVO)
import asyncio
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class RequestContext:
    """Contexto compartilhado entre fases do request."""
    
    # Inputs
    user_id: str
    conversation_id: str
    messages: list
    project_id: Optional[str] = None
    has_attachment: bool = False
    web_search_active: bool = False
    
    # Outputs (populados durante o request)
    embedding: Optional[bytes] = field(default=None, repr=False)
    embedding_computed: bool = False
    embedding_error: Optional[str] = None
    
    # Stats
    phases: Dict[str, float] = field(default_factory=dict)
    
    def get_embedding(self, text: str, loop: asyncio.AbstractEventLoop) -> Optional[bytes]:
        """
        Obtém embedding com memoização.
        
        Se embedding já foi computado para este request, reutiliza.
        Caso contrário, calcula e armazena.
        """
        if self.embedding_computed:
            return self.embedding
        
        # Calcula embedding
        from backend.projects import embedder
        try:
            blob = embedder.embed_text(text)
            self.embedding = blob
            self.embedding_computed = True
            return blob
        except Exception as e:
            self.embedding_error = str(e)
            logger.error(f"Embedding error: {e}")
            return None
    
    def reset(self):
        """Reseta estado para novo request."""
        self.embedding = None
        self.embedding_computed = False
        self.embedding_error = None
        self.phases.clear()
```

### 2. Integração com CacheManager

```python
# backend/cache/manager.py (modificado)

async def get(
    self,
    model_id: str,
    messages: list,
    context_fingerprint: str | None = None,
    request_ctx: Optional[RequestContext] = None,  # NOVO
) -> Optional[CacheHit]:
    # ... existing logic ...
    
    if settings["semantic_enabled"] and _HAS_NUMPY:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"),
            None,
        )
        if last_user:
            # Usa embedding do request context se disponível
            if request_ctx and not request_ctx.embedding_computed:
                loop = asyncio.get_event_loop()
                request_ctx.embedding = await loop.run_in_executor(
                    None, _embed_text, last_user
                )
            
            # Reutiliza embedding
            blob = request_ctx.embedding if request_ctx else None
            if blob is None:
                blob = await loop.run_in_executor(None, _embed_text, last_user)
            
            # ... resto da lógica ...
```

### 3. Integração com Projects RAG

```python
# backend/projects/rag.py (modificado)

async def search_projects(
    self,
    prompt: str,
    request_ctx: RequestContext,  # NOVO
) -> List[Dict]:
    # Usa embedding do request context
    if not request_ctx.embedding_computed:
        loop = asyncio.get_event_loop()
        request_ctx.embedding = await loop.run_in_executor(
            None, _embed_text, prompt
        )
    
    blob = request_ctx.embedding
    # ... busca por similaridade ...
```

### 4. Integração com Memory Retrieval

```python
# backend/memory.py (modificado)

async def get_relevant_memories(
    self,
    user_id: str,
    prompt: str,
    request_ctx: RequestContext,  # NOVO
) -> List[MemoryEntry]:
    # Usa embedding do request context
    if not request_ctx.embedding_computed:
        loop = asyncio.get_event_loop()
        request_ctx.embedding = await loop.run_in_executor(
            None, _embed_text, prompt
        )
    
    blob = request_ctx.embedding
    # ... busca de memórias ...
```

### 5. Atualização do Pipeline Principal

```python
# backend/routers/chat.py (modificado)

@router.post("/chat/completions")
async def chat_completions(request: ChatRequest):
    # Cria contexto de request
    ctx = RequestContext(
        user_id=current_user.id,
        conversation_id=request.conversation_id,
        messages=request.messages,
        project_id=request.project_id,
        has_attachment=len(request.attachments) > 0,
        web_search_active=request.web_search,
    )
    
    # Fase 1: Router (usa ctx)
    intent = await smart_router.classify_intent(request.prompt, ctx)
    
    # Fase 2: Build Context (usa ctx)
    context = await build_context(ctx)
    
    # Fase 3: Cache Check (usa ctx)
    cache_hit = await cache_manager.get(
        model_id=intent.model_id,
        messages=request.messages,
        context_fingerprint=context.fingerprint,
        request_ctx=ctx,
    )
    
    # Fase 4: RAG (usa ctx - embedding reutilizado)
    if intent.needs_rag:
        rag_results = await rag_manager.search(
            prompt=request.prompt,
            request_ctx=ctx,
        )
    
    # Fase 5: Memory (usa ctx - embedding reutilizado)
    memories = await memory_manager.get_relevant(
        user_id=current_user.id,
        prompt=request.prompt,
        request_ctx=ctx,
    )
    
    # ... restante do pipeline ...
```

---

## 🔧 Arquivos a Criar/Modificar

### Novos Arquivos
```
backend/context/request_context.py   # RequestContext com memoização
```

### Arquivos a Modificar
```
backend/cache/manager.py             # Aceitar request_ctx
backend/projects/rag.py              # Usar embedding do ctx
backend/memory.py                    # Usar embedding do ctx
backend/routers/chat.py              # Criar e passar ctx
backend/orchestration/build_context.py  # Receber ctx
```

---

## 📊 Métricas Esperadas

| Métrica | Antes | Depois | Variação |
|---------|-------|--------|----------|
| Embeddings por request | 1-3 | 1 | **-66%** |
| Latência request com RAG+Memória | ~318ms | ~118ms | **-63%** |
| CPU usage (embedder) | 3x | 1x | **-66%** |
| Tempo de bloqueio do event loop | 300ms | 100ms | **-66%** |

---

## 🧪 Testes Requeridos

```python
# tests/test_embedding_memoization.py
import pytest
import asyncio

@pytest.mark.asyncio
async def test_embedding_reused_across_phases():
    """Embedding deve ser calculado uma vez e reutilizado."""
    ctx = RequestContext(
        user_id="user1",
        conversation_id="conv1",
        messages=[{"role": "user", "content": "Teste"}],
    )
    
    # Simula cálculo no cache
    blob1 = await ctx.get_embedding("Teste", asyncio.get_event_loop())
    
    # Simula uso no RAG
    blob2 = await ctx.get_embedding("Teste", asyncio.get_event_loop())
    
    # Simula uso na memória
    blob3 = await ctx.get_embedding("Teste", asyncio.get_event_loop())
    
    assert blob1 is blob2 is blob3  # Mesmo objeto (memoização)
    assert ctx.embedding_computed == True

@pytest.mark.asyncio
async def test_embedding_per_request():
    """Embedding deve ser resetado entre requests."""
    ctx1 = RequestContext(...)
    ctx2 = RequestContext(...)
    
    blob1 = await ctx1.get_embedding("Teste", loop)
    blob2 = await ctx2.get_embedding("Teste", loop)
    
    assert blob1 == blob2  # Mesmo valor
    assert blob1 is not blob2  # Objetos diferentes

@pytest.mark.asyncio
async def test_embedder_runs_in_executor():
    """Embedding deve rodar em thread pool, não bloquear event loop."""
    ctx = RequestContext(...)
    
    start = time.time()
    blob = await ctx.get_embedding("Teste", asyncio.get_event_loop())
    elapsed = time.time() - start
    
    assert blob is not None
    assert elapsed < 0.5  # Deve completar em < 500ms
```

---

## 📝 Checklist de Implementação

- [ ] **Step 1:** Criar RequestContext
  - [ ] Definir dataclass com fields necessários
  - [ ] Implementar `get_embedding()` com memoização
  - [ ] Implementar `reset()` para limpeza

- [ ] **Step 2:** Integrar com CacheManager
  - [ ] Adicionar parâmetro `request_ctx` opcional
  - [ ] Reutilizar embedding quando disponível
  - [ ] Fallback para cálculo direto

- [ ] **Step 3:** Integrar com Projects RAG
  - [ ] Adicionar parâmetro `request_ctx`
  - [ ] Reutilizar embedding

- [ ] **Step 4:** Integrar com Memory
  - [ ] Adicionar parâmetro `request_ctx`
  - [ ] Reutilizar embedding

- [ ] **Step 5:** Atualizar pipeline principal
  - [ ] Criar RequestContext em cada request
  - [ ] Passar ctx para todas as fases
  - [ ] Reset ctx após resposta

- [ ] **Step 6:** Testes
  - [ ] Testar memoização
  - [ ] Testar isolamento entre requests
  - [ ] Benchmark de performance

---

## 🚨 Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Memória vazando (ctx não limpa) | Média | Baixo | Garantir reset() em finally |
| Concorrência (dois requests mesmo ctx) | Baixa | Alto | Criar ctx por request, não global |
| Embedding incorreto (texto errado) | Baixa | Médio | Validar texto antes de calcular |
| Break changes na API | Média | Médio | Parâmetro opcional, fallback |

---

## 📈 Monitoramento

```python
# Adicionar métricas
EMBEDDINGS_COMPUTED = Counter(
    'embeddings_computed_total',
    'Total de embeddings calculados'
)

EMBEDDINGS_REUSED = Counter(
    'embeddings_reused_total',
    'Total de embeddings reutilizados do ctx'
)

EMBEDDING_SAVED_MS = Histogram(
    'embedding_saved_ms',
    'Ms economizados por reutilização'
)
```

---

*Documento criado: 2026-10-13*  
*Fonte: Análise Claude - Oportunidade #2*  
*Responsável: Hermes Agent*
