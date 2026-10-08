# Plano de Implementação — Assistente Proativo (Multi/Nexus Local)

**Data:** 2026-10-07  
**Status:** Design aprovado, pronto para implementação  
**Estimativa:** 14 horas de desenvolvimento

---

## 1. Visão Geral

Transformar o Nexus Local (Multi) de chat reativo para assistente proativo que:
- Detecta interesse genuíno nas mensagens do usuário (emoção + entidade)
- Pesquisa automaticamente em background
- Entrega resumos em linguagem natural, como conversa entre amigos
- Funciona 100% com conteúdo público (sem login)

**Caso de uso exemplo:**
```
Usuário: "Gente, vi que Gabriel e Shirley vão tocar em Balneário Camboriú, tô muito animado!"
IA (detecta interesse): [pesquisa em background]
IA (entrega): "Fiquei curioso e pesquisei: tem show dia 15/11 no Beach Park, ingressos a partir de R$89. Quer mais info?"
```

---

## 2. Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MULTI CHAT INTERFACE                          │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐  │
│  │  User Input  │───→│  Detector    │───→│  Research Pipeline   │  │
│  │  (WebSocket) │    │  (emotion +  │    │  (web search +       │  │
│  │              │    │   entities)  │    │   browser fallback)  │  │
│  └──────────────┘    └──────────────┘    └──────────┬───────────┘  │
│                                                      │              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────▼───────────┐  │
│  │  Delivery    │←───│  Synthesis   │←───│  Cache (24h TTL)     │  │
│  │  (smart)     │    │  (LLM)       │    │  (avoid redundancy)  │  │
│  └──────────────┘    └──────────────┘    └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Componentes Técnicos

### 3.1 Módulo Detector (`backend/proactive/detector.py`)

**Responsabilidade:** Analisar mensagem do usuário e decidir se há interesse suficiente para pesquisa.

**Inputs:**
- `message: str` — texto da mensagem do usuário
- `conversation_context: list[dict]` — últimas 5 mensagens (para contexto)

**Outputs:**
- `should_research: bool` — true se interesse detectado
- `confidence: float` — 0.0 a 1.0
- `entities: list[str]` — entidades nomeadas detectadas
- `intent: str` — tipo de intenção (evento, notícia, curiosidade, etc)

**Implementação:**
```python
# Heurística híbrida:
# 1. Regex para padrões de emoção (animo, curiosidade, preocupação, etc)
# 2. NER leve para entidades (pessoa, lugar, evento, produto)
# 3. LLM call (se configured) para validação de contexto

EMOTION_PATTERNS = [
    r'\b(animado|empolgad|curios|interessad|preocupad|surpres|inquieta)\b',
    r'\btô [mM]uito [aAiI]\b',
    r'\bisso é incrível|não acredito|que notícia bom'
]

ENTITY_PATTERNS = {
    'pessoa': r'\b[a-zA-Z]+ [a-zA-Z]+\b',  # Nome próprio
    'lugar': r'\b(Balneário|Camboriú|Florianópolis|Brasil)\b',
    'evento': r'\b(show|concerto|festival|lançamento)\b'
}
```

**Threshold:** 0.7 para confiança mínima

---

### 3.2 Módulo Pesquisa (`backend/proactive/researcher.py`)

**Responsabilidade:** Executar pesquisa em múltiplas fontes e agregar resultados.

**Fases:**

**Fase 1 — Web Search (rápido, 5-10s)**
- Usar providers existentes (`backend/web_search/providers.py`)
- Brave Search (se API key configurada)
- DuckDuckGo (fallback grátis)
- Max 5 resultados

**Fase 2 — Browser Fallback (se necessário, 10-30s)**
- Playwright em container isolado
- Para sites que bloqueiam APIs ou precisam de JS
- Timeout: 30s
- Headless, sem interação humana

**Fase 3 — Agregação**
- Deduplicação por URL
- Ranking por relevância
- Max 3 fontes principais

**Interface:**
```python
class ResearchResult:
    query: str
    sources: list[dict]  # {url, title, snippet, content}
    elapsed_ms: int
    cache_hit: bool

async def research(query: str, max_results: int = 5) -> ResearchResult:
    # Implementação
```

---

### 3.3 Módulo Síntese (`backend/proactive/synthesizer.py`)

**Responsabilidade:** Transformar resultados brutos em linguagem natural.

**Prompt template:**
```
Você é um assistente proativo que detecta interesses e pesquisa informações relevantes.

Contexto da conversa:
{conversation_context}

O usuário demonstrou interesse em: {intent}
Entidades detectadas: {entities}

Resultados da pesquisa:
{research_results}

Gere uma resposta natural, como se fosse um amigo que pesquisou para você.
Seja conciso (max 3 frases), útil e engajador.
Inclua links relevantes.
```

**Output:**
```python
class SynthesisResult:
    message: str          # Texto para entrega
    follow_up_questions: list[str]  # Sugestões de aprofundamento
    sources_summary: list[str]      # Links resumidos
```

---

### 3.4 Módulo Cache (`backend/proactive/cache.py`)

**Responsabilidade:** Evitar pesquisas redundantes.

**Estratégia:**
- Key: hash(query + entities)
- TTL: 24 horas
- Storage: SQLite ou arquivo JSON local
- Tamanho máximo: 1000 entradas

**Interface:**
```python
async def get_cached(key: str) -> Optional[ResearchResult]
async def set_cached(key: str, result: ResearchResult) -> None
async def invalidate(key: str) -> None
```

---

### 3.5 Router API (`backend/routers/proactive.py`)

**Endpoints:**

```python
# Status da pesquisa em andamento
GET /api/proactive/status/{conversation_id}
→ {researching: bool, progress: str}

# Configurações do assistente proativo
GET /api/proactive/settings
→ {enabled: bool, sensitivity: float, rate_limit: int}

PUT /api/proactive/settings
→ {ok: bool}

# Logs de pesquisas (admin)
GET /api/proactive/logs?limit=50
→ list[{timestamp, query, entities, confidence, elapsed_ms}]
```

---

### 3.6 Frontend Components

#### `ProactiveIndicator.tsx`
- Spinner sutil quando pesquisa está rodando
- Posição: junto ao input de mensagem
- Opacity: 0.5 quando idle, 1.0 quando ativo

#### `ProactiveMessage.tsx`
- Bubble de mensagem estilo "nota espontânea"
- Cor diferente (azul claro, não o laranja padrão)
- Ícone de lupa 🔍 no canto
- Botão "Quero saber mais" para expandir

#### `useProactiveResearch.ts`
- Hook que escuta WebSocket para resultados
- Gerencia estado local (idle/researching/done)
- Debounce para evitar múltiplas pesquisas rápidas

---

## 4. Integração com Chat Existente

### 4.1 Hook no Fluxo de Mensagens

```python
# Em backend/orchestration/handle_message.py (ou similar)

async def handle_user_message(user_id, message, conversation_id):
    # ... código existente ...
    
    # NOVO: Verificar se deve disparar pesquisa proativa
    if should_trigger_proactive(message, conversation_id):
        asyncio.create_task(run_proactive_research(
            user_id=user_id,
            message=message,
            conversation_id=conversation_id
        ))
    
    # ... resto do código existente ...
```

### 4.2 WebSocket Event

```python
# Quando pesquisa termina, enviar para usuário específico
await websocket.send_json({
    "type": "proactive_research_complete",
    "conversation_id": conversation_id,
    "message": synthesis_result.message,
    "sources": synthesis_result.sources_summary,
    "follow_up": synthesis_result.follow_up_questions
})
```

---

## 5. Configuração

### 5.1 Variáveis de Ambiente

```env
# .env ou config.yaml
PROACTIVE_ENABLED=true
PROACTIVE_SENSITIVITY=0.7
PROACTIVE_RATE_LIMIT=3  # pesquisas/hora/conversa
PROACTIVE_CACHE_TTL=86400  # 24h em segundos
PROACTIVE_MAX_QUERY_LENGTH=200
```

### 5.2 Settings no Frontend

Painel de configurações → "Assistente Proativo":
- Toggle liga/desliga
- Slider de sensibilidade (baixa/média/alta)
- Botão "Limpar cache de pesquisas"
- Link para logs (admin)

---

## 6. Plano de Implementação (Fases)

### Fase 1 — Spike de Detecção (2h)
**Objetivo:** Validar se detector funciona com accuracy >80%

**Entregáveis:**
- [ ] Script isolado `test_detector.py`
- [ ] Dataset de 50 mensagens de teste
- [ ] Métricas: precision, recall, F1
- [ ] Ajuste de threshold

**Código:**
```python
# backend/proactive/detector.py
# tests/test_proactive_detector.py
```

**Critério de sucesso:**
- >85% accuracy em detectar interesse genuíno
- <5% falsos positivos em conversas normais

---

### Fase 2 — Pipeline de Pesquisa (4h)
**Objetivo:** Pesquisar e agregar resultados confiáveis

**Entregáveis:**
- [ ] `backend/proactive/researcher.py`
- [ ] Integração com web search existente
- [ ] Browser fallback com Playwright
- [ ] Cache 24h
- [ ] Tests unitários

**Testes:**
```python
# tests/test_proactive_researcher.py
async def test_web_search_integration()
async def test_browser_fallback()
async def test_cache_hits()
```

---

### Fase 3 — Síntese e Entrega (3h)
**Objetivo:** Transformar dados em linguagem natural

**Entregáveis:**
- [ ] `backend/proactive/synthesizer.py`
- [ ] Templates de prompt
- [ ] WebSocket event handler
- [ ] Integration tests

---

### Fase 4 — Interface Frontend (2h)
**Entregáveis:**
- [ ] `ProactiveIndicator.tsx`
- [ ] `ProactiveMessage.tsx`
- [ ] `useProactiveResearch.ts`
- [ ] Integração com chat existente

---

### Fase 5 — Configuração e UX (2h)
**Entregáveis:**
- [ ] Settings panel no Admin
- [ ] Toggle liga/desliga
- [ ] Controle de sensibilidade
- [ ] Logs de pesquisa (admin)

---

### Fase 6 — Testes e Refinamento (3h)
**Entregáveis:**
- [ ] Teste com usuários reais (família)
- [ ] Ajuste de thresholds
- [ ] Otimização de performance
- [ ] Documentação

---

## 7. Arquivos a Criar/Modificar

### Backend (Novos)
```
backend/proactive/
├── __init__.py
├── detector.py
├── researcher.py
├── synthesizer.py
├── cache.py
└── router.py

backend/tests/
└── test_proactive_*.py
```

### Backend (Modificados)
```
backend/orchestration/handle_message.py  # Adicionar hook proativo
backend/web_search/providers.py          # Reutilizar
backend/routers/__init__.py              # Registrar novo router
```

### Frontend (Novos)
```
frontend/src/components/
├── ProactiveIndicator.tsx
└── ProactiveMessage.tsx

frontend/src/hooks/
└── useProactiveResearch.ts
```

### Frontend (Modificados)
```
frontend/src/components/ChatWindow.tsx     # Adicionar indicator
frontend/src/api/client.ts                 # Novos endpoints
frontend/src/i18n/locales/pt-BR.json       # Strings novas
```

### Config
```
docs/design-assistente-proativo.md         # Já criado
docs/plano-assistente-proativo.md          # Este arquivo
```

---

## 8. Riscos e Mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|-------|--------------|---------|-----------|
| Falsos positivos (spam) | Alta | Médio | Threshold 0.7 + rate limit 3/hora |
| Latência alta (>30s) | Média | Alto | Timeout 60s + cache 24h |
| Custo API (Brave) | Baixa | Baixo | Fallback DuckDuckGo grátis |
| Complexidade excessiva | Média | Médio | MVP simples primeiro, evoluir depois |
| Privacidade (dados pessoais) | Baixa | Alto | Só conteúdo público, sem salvar logs |

---

## 9. Métricas de Sucesso

**Técnicas:**
- [ ] Detecção accuracy >85%
- [ ] Pesquisa completa <30s (web) / <60s (browser)
- [ ] Zero crashes em produção
- [ ] <100ms overhead no chat principal

**Usuário:**
- [ ] Usuários percebem valor ("mais útil que antes")
- [ ] <5% desativam o recurso nas configurações
- [ ] Zero reclamações de "spam"

---

## 10. Próximos Passos Imediatos

1. ✅ Design doc aprovado
2. ⏳ Iniciar Fase 1 (Spike de Detecção)
3. ⏸️ Aguardar feedback do spike antes de continuar
4. ⏸️ Implementar Fase 2-6 sequencialmente
5. ⏸️ Deploy em staging para teste com família
6. ⏸️ Ajustes finais e deploy production

---

**Documento criado em:** 2026-10-07  
**Próxima revisão:** Após conclusão do spike de detecção (Fase 1)
