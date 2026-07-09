# Plano de Implementação — Busca Web (Manual + Heurística Automática)
**NexusLocal** · Documento técnico de planejamento

---

## 1. Visão Geral

Nenhum dos providers free do NexusLocal (Groq, Cerebras, OpenRouter free, NVIDIA NIM, SambaNova) tem busca web nativa integrada na API. Gemini tem essa capacidade ("Grounding with Google Search"), mas normalmente não está disponível no free tier. Portanto, a busca web precisa ser **construída como um pipeline de pré-processamento** — o mesmo padrão arquitetural já usado no Vision Relay e no Fusion: o backend enriquece o prompt com informação externa antes de chamar o modelo.

```
Usuário pergunta algo
        ↓
Decisão: buscar na web? (manual OU heurística — este plano cobre ambas)
        ↓ sim
Backend chama API de busca externa
        ↓
Resultados (título + snippet + URL) formatados como contexto
        ↓
Injetados no prompt: "[Resultados de busca: ...] + pergunta original"
        ↓
Modelo responde normalmente, com informação atualizada
```

Este plano cobre **duas abordagens de decisão** (o "quando buscar"), que podem coexistir no mesmo sistema:

1. **Manual** — usuário ativa um toggle explícito antes de perguntar
2. **Heurística automática** — backend detecta padrões na pergunta e decide buscar sem que o usuário precise pedir

> Function calling (o modelo decidindo sozinho via tool use) fica fora deste plano — é tratado como evolução futura, já que poucos modelos free têm essa capacidade bem implementada.

---

## 2. Escolha da API de Busca

| Serviço | Free tier | Qualidade | Facilidade de integração |
|---|---|---|---|
| **Brave Search API** | 2.000 queries/mês | Boa, resultados limpos | REST simples, resposta em JSON direto |
| **SerpAPI** | 100 queries/mês | Muito boa (espelha Google) | REST simples, mas tier pequeno |
| **Google Custom Search** | 100 queries/dia | Boa | Requer configurar um "Search Engine ID" (CSE) |
| **DuckDuckGo (não-oficial)** | Ilimitado, sem chave | Variável | Sem SLA, pode quebrar sem aviso |

**Recomendação:** Brave Search API como padrão — melhor equilíbrio entre free tier generoso e facilidade de integração. Estruturar o backend para múltiplos providers de busca (mesmo padrão de abstração já usado para os providers de LLM), permitindo trocar ou adicionar DuckDuckGo como fallback gratuito ilimitado.

---

## 3. Banco de Dados

### Nova tabela: `web_search_config`

```sql
CREATE TABLE IF NOT EXISTS web_search_config (
    id                    INTEGER PRIMARY KEY DEFAULT 1,
    enabled               INTEGER DEFAULT 1,
    search_provider       TEXT DEFAULT 'brave',      -- 'brave' | 'serpapi' | 'google_cse' | 'duckduckgo'
    api_key               TEXT DEFAULT '',
    max_results           INTEGER DEFAULT 5,
    heuristic_enabled     INTEGER DEFAULT 0,          -- ativa detecção automática
    heuristic_sensitivity TEXT DEFAULT 'medium',       -- 'low' | 'medium' | 'high'
    injection_template    TEXT DEFAULT '...'           -- como os resultados são formatados no prompt
);
```

### Nova tabela: `web_search_log`

Registro de buscas realizadas — útil para acompanhar consumo do free tier e depurar decisões da heurística:

```sql
CREATE TABLE IF NOT EXISTS web_search_log (
    id             TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id     TEXT,
    query          TEXT NOT NULL,
    trigger_type   TEXT NOT NULL,     -- 'manual' | 'heuristic'
    results_count  INTEGER,
    created_at     TEXT DEFAULT (datetime('now'))
);
```

### Extensão na tabela `messages`

```sql
ALTER TABLE messages ADD COLUMN web_search_used  INTEGER DEFAULT 0;
ALTER TABLE messages ADD COLUMN web_search_query TEXT;
ALTER TABLE messages ADD COLUMN web_search_sources TEXT;  -- JSON array de {title, url}
```

> Guardar as fontes usadas permite mostrar um badge "🌐 Buscado na web" com as URLs consultadas — transparência similar à que já planejamos para o Vision Relay.

---

## 4. Backend — Módulo de Busca

### Novo módulo: `backend/web_search/`

```
backend/web_search/
  __init__.py
  providers.py      # adapters para Brave/SerpAPI/Google CSE/DuckDuckGo
  heuristics.py      # lógica de detecção automática
  formatter.py         # formata resultados para injeção no prompt
```

### 4.1 `providers.py` — Abstração de busca

```python
from abc import ABC, abstractmethod

class SearchProvider(ABC):
    @abstractmethod
    async def search(self, query: str, max_results: int) -> list[SearchResult]:
        ...

class BraveSearchProvider(SearchProvider):
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # GET https://api.search.brave.com/res/v1/web/search?q={query}
        # Header: X-Subscription-Token: {api_key}
        ...

class DuckDuckGoProvider(SearchProvider):
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        # Sem chave — usa endpoint não-oficial ou biblioteca duckduckgo-search
        ...
```

### 4.2 `formatter.py` — Injeção no prompt

```python
def format_search_results(results: list[SearchResult], query: str) -> str:
    blocks = "\n\n".join([
        f"[{i+1}] {r.title}\n{r.snippet}\nFonte: {r.url}"
        for i, r in enumerate(results)
    ])
    return f"""Resultados de busca para "{query}":

{blocks}

---
Use essas informações para responder a pergunta do usuário abaixo,
citando as fontes quando relevante."""
```

---

## 5. Abordagem 1 — Busca Manual (Toggle)

### 5.1 Comportamento

Reaproveita o mesmo padrão visual do toggle Fusion já planejado: um botão de estado no header ou na barra de ações do input.

```
┌──────────────────────────────────────────────┐
│  textarea de mensagem...                     │
├──────────────────────────────────────────────┤
│  [+] [Groq · Llama ▾]  [🌐 Web]   [✦][🎙][▷]│
└──────────────────────────────────────────────┘
```

Quando `🌐 Web` está ativo (highlight visual), a próxima mensagem enviada automaticamente passa pelo pipeline de busca antes de chegar ao modelo. O toggle permanece ativo entre mensagens até o usuário desativar — não é "só para essa mensagem", é um modo de conversa (similar ao Fusion).

### 5.2 Fluxo no WebSocket

Payload existente ganha um novo campo:

```json
{
  "conversation_id": "...",
  "message": "quem ganhou as eleições municipais de Blumenau em 2024?",
  "model_id": "groq/llama-3.3-70b",
  "provider_id": "groq",
  "web_search": true
}
```

### 5.3 Lógica no backend (`chat.py`)

```python
if payload.get("web_search"):
    query = await extract_search_query(user_message)  # ver seção 5.4
    results = await search_provider.search(query, max_results=config.max_results)

    await ws.send_json({"type": "search_start", "query": query})

    search_context = format_search_results(results, query)
    final_message = f"{search_context}\n\n---\n\nPergunta: {user_message}"

    await ws.send_json({
        "type": "search_done",
        "sources": [{"title": r.title, "url": r.url} for r in results]
    })
else:
    final_message = user_message
```

### 5.4 Extração da query de busca

A pergunta do usuário nem sempre é a melhor query de busca. Duas opções:

**Opção simples (v1):** usar a mensagem do usuário diretamente como query.

**Opção refinada (v2):** um passo extra e leve — usar um modelo rápido (Groq/Llama 8B, latência baixíssima) para reescrever a pergunta como query de busca otimizada:

```python
async def extract_search_query(user_message: str) -> str:
    # Chamada rápida a um modelo leve, prompt: "Extraia uma query de busca
    # concisa e eficaz para a seguinte pergunta: {user_message}"
    # Retorna algo como: "eleições municipais Blumenau 2024 resultado"
    ...
```

> Recomendação: implementar a v1 primeiro (query = mensagem do usuário). É suficiente na maioria dos casos e evita uma chamada extra de API. Migrar para v2 só se notar queries ruins na prática.

### 5.5 Frontend — Componente do Toggle

**Novo componente:** `frontend/src/components/WebSearchToggle.tsx`

```typescript
interface WebSearchToggleProps {
  active: boolean
  onToggle: () => void
}
```

Visual: pill compacta, ícone de globo, muda de cor quando ativo (reutilizar `--accent` ou `--teal`).

```css
.web-search-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: var(--radius-pill);
  font-size: 12.5px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text-3);
  transition: all 0.15s;
}
.web-search-toggle.active {
  background: var(--teal);
  color: white;
  border-color: var(--teal);
}
```

### 5.6 Feedback visual durante a busca

Similar ao card de status do Fusion, mas mais simples — uma linha de status transitória:

```
🌐 Buscando "eleições municipais Blumenau 2024"...
```

Substituída, ao concluir, pelo badge de fontes na resposta final:

```
┌──────────────────────────────────────────────┐
│ 🔷 Llama 3.3 70B   14:32                       │
│ 🌐 3 fontes consultadas                        │  ← clicável, expande lista de URLs
│                                                │
│ Nas eleições municipais de 2024, Blumenau...  │
└──────────────────────────────────────────────┘
```

---

## 6. Abordagem 2 — Heurística Automática

### 6.1 Conceito

O backend analisa a mensagem do usuário e decide **sem que ele precise ativar nada** se a pergunta provavelmente precisa de informação atual/externa. Se detectar, busca automaticamente e injeta os resultados — mesmo pipeline da abordagem manual, mas o gatilho é diferente.

### 6.2 Sinais de heurística

```python
# backend/web_search/heuristics.py

TEMPORAL_KEYWORDS = [
    "hoje", "agora", "atual", "atualmente", "recente", "recentemente",
    "última", "últimas", "últimos", "esse ano", "este ano", "2025", "2026",
    "notícia", "notícias", "acontecendo", "novidade",
]

FACTUAL_QUERY_PATTERNS = [
    r"\bquem (é|foi|ganhou|venceu)\b",
    r"\bquando (foi|será|ocorre)\b",
    r"\bqual (é|foi) o (preço|valor|cotação)\b",
    r"\bpreço (do|da|de)\b",
    r"\bcotação\b",
    r"\bresultado (do|da|de)\b",
]

DOMAIN_SIGNALS = [
    "eleição", "eleições", "presidente", "prefeito",
    "bolsa de valores", "dólar", "criptomoeda",
    "jogo", "placar", "campeonato",
]

def should_search(message: str, sensitivity: str = "medium") -> tuple[bool, float]:
    """
    Retorna (deve_buscar, confiança).
    Sensibilidade ajusta o threshold de confiança necessário.
    """
    score = 0.0

    if any(kw in message.lower() for kw in TEMPORAL_KEYWORDS):
        score += 0.4
    if any(re.search(p, message.lower()) for p in FACTUAL_QUERY_PATTERNS):
        score += 0.35
    if any(d in message.lower() for d in DOMAIN_SIGNALS):
        score += 0.25

    thresholds = {"low": 0.6, "medium": 0.4, "high": 0.25}
    threshold = thresholds.get(sensitivity, 0.4)

    return score >= threshold, score
```

### 6.3 Configuração de sensibilidade

Três níveis, configuráveis em **Configurações → Ferramentas → Busca Web**:

| Nível | Threshold | Comportamento |
|---|---|---|
| **Baixa** | 0.6 | Só busca em casos muito óbvios (múltiplos sinais fortes simultâneos) |
| **Média** (padrão) | 0.4 | Equilíbrio — busca em perguntas claramente temporais ou factuais |
| **Alta** | 0.25 | Busca de forma mais liberal, arrisca falsos positivos |

### 6.4 Fluxo de decisão combinado

```python
async def resolve_web_search(payload: dict, config: WebSearchConfig, user_message: str):
    if payload.get("web_search"):  # manual, toggle explícito
        return True, "manual"

    if config.heuristic_enabled:
        should, confidence = should_search(user_message, config.heuristic_sensitivity)
        if should:
            return True, "heuristic"

    return False, None
```

> **Prioridade:** o toggle manual sempre vence — se o usuário ativou explicitamente, busca acontece independente da heurística. A heurística só atua quando o toggle está desativado.

### 6.5 Transparência quando a heurística dispara

Diferente do toggle manual (onde o usuário já sabe que pediu busca), a heurística precisa ser **visível o suficiente para não parecer mágica ou incontrolável**:

```
┌──────────────────────────────────────────────┐
│ 🔷 Llama 3.3 70B   14:32                       │
│ 🌐 Busca automática · 3 fontes consultadas    │  ← indica que foi automático
│                                                │
│ O dólar hoje está cotado a R$ 5,42...         │
└──────────────────────────────────────────────┘
```

Hover: "Detectamos que sua pergunta provavelmente precisa de informação atual e buscamos na web automaticamente. Desative isso em Configurações → Ferramentas → Busca Web."

### 6.6 Evitar buscas desnecessárias — Cache de heurística

Se o usuário reformular a mesma pergunta várias vezes (comum em conversas), evitar buscar de novo desnecessariamente. Reaproveitar o **cache semântico já implementado no NexusLocal** — se a pergunta for semanticamente similar a uma busca recente na mesma conversa, reutilizar os resultados em vez de buscar de novo.

```python
# Antes de disparar uma nova busca heurística, verificar se já buscamos
# algo muito similar nos últimos N minutos na mesma conversa
recent_search = await get_recent_similar_search(conversation_id, user_message, db)
if recent_search:
    results = recent_search.results  # reaproveita
else:
    results = await search_provider.search(query)
```

---

## 7. Frontend — Configurações

### Novo componente: `frontend/src/components/WebSearchSettings.tsx`

Nova seção em **Configurações → Ferramentas**, ao lado do Enhancer, Fusion e Vision Relay:

```
┌─────────────────────────────────────────────┐
│  🌐 BUSCA WEB                                │
├─────────────────────────────────────────────┤
│  Provider de busca:  [ Brave Search ▾ ]      │
│  Chave de API:       [ ••••••••••••• ] [👁]  │
│  Máx. resultados:     [ 5 ▾ ]                 │
├─────────────────────────────────────────────┤
│  ☐ Ativar detecção automática (heurística)   │
│     Sensibilidade:  ○ Baixa ● Média ○ Alta   │
├─────────────────────────────────────────────┤
│  [ Salvar ]                                  │
└─────────────────────────────────────────────┘
```

### Log de buscas (aba de diagnóstico)

Reaproveitando o padrão do `CachePanel.tsx` (lista de entradas com hits), uma lista simples mostrando:

```
Últimas buscas:
🌐 "eleições municipais Blumenau 2024"    [manual]     3 resultados   14:32
🌐 "cotação dólar hoje"                   [heurística] 5 resultados   14:28
```

Útil para o usuário auditar quando a heurística disparou e ajustar a sensibilidade se estiver muito agressiva ou muito tímida.

---

## 8. Integração com Funcionalidades Existentes

### Cache
Resultados de busca **não devem** ser cacheados pelo cache exato/semântico do jeito que está hoje — informação de busca web é por natureza temporal e cachear por dias renderia respostas obsoletas. Sugestão: TTL curto e próprio para cache de busca (5-15 minutos), separado do cache principal de respostas.

### ContextBar
Resultados de busca somam tokens ao prompt — a estimativa de contexto (`utils/tokens.ts`) precisa incluir o texto injetado pela busca, mesmo princípio já aplicado a anexos.

### Fusion
Quando Fusion e busca web estiverem ativos simultaneamente: a busca acontece **uma única vez** (não uma por modelo paralelo) e os resultados são injetados igualmente no prompt de todos os modelos do preset — mesmo padrão já definido para o Vision Relay.

### Vision Relay
Sem sobreposição direta — um lida com imagens, outro com informação textual externa. Podem coexistir na mesma mensagem sem conflito.

---

## 9. Tratamento de Erros

| Cenário | Comportamento |
|---|---|
| API de busca sem chave configurada | Toggle manual fica desabilitado com tooltip explicativo; heurística não dispara |
| Rate limit do provider de busca atingido | Erro claro: "Limite de buscas do mês atingido. Configure outro provider ou aguarde a renovação." |
| Busca retorna zero resultados | Prompt segue sem contexto de busca, aviso discreto: "Nenhum resultado encontrado — respondendo sem busca web" |
| Heurística com falso positivo recorrente | Usuário reduz sensibilidade em Configurações; log de buscas ajuda a identificar o padrão problemático |
| Timeout da API de busca | Fallback: segue sem busca, não bloqueia a resposta do modelo principal |

---

## 10. Arquivos a Criar / Modificar

| Arquivo | Ação |
|---|---|
| `backend/web_search/__init__.py` | **Criar** |
| `backend/web_search/providers.py` | **Criar** — adapters Brave/SerpAPI/Google CSE/DuckDuckGo |
| `backend/web_search/heuristics.py` | **Criar** — lógica de detecção automática |
| `backend/web_search/formatter.py` | **Criar** — formatação de resultados para injeção |
| `backend/routers/web_search.py` | **Criar** — endpoints de configuração e log |
| `backend/routers/chat.py` | **Modificar** — aceitar flag `web_search`, resolver heurística, injetar resultados |
| `backend/database.py` | **Modificar** — tabelas `web_search_config`, `web_search_log`; colunas em `messages` |
| `backend/cache/manager.py` | **Modificar** — TTL curto separado para cache de busca (opcional) |
| `backend/main.py` | **Modificar** — registrar router de web_search |
| `requirements.txt` | **Modificar** — adicionar `duckduckgo-search` se optar por esse fallback |
| `frontend/src/components/WebSearchToggle.tsx` | **Criar** |
| `frontend/src/components/WebSearchSettings.tsx` | **Criar** |
| `frontend/src/components/MessageInput.tsx` | **Modificar** — integrar toggle |
| `frontend/src/components/MessageBubble.tsx` | **Modificar** — badge de fontes consultadas |
| `frontend/src/utils/tokens.ts` | **Modificar** — incluir texto de busca na estimativa |
| `frontend/src/types.ts` | **Modificar** — adicionar interfaces de busca |
| `frontend/src/api/client.ts` | **Modificar** — métodos de configuração e envio |

---

## 11. Sequência de Implementação Recomendada

```
1. Escolha e configuração da API de busca
   → Criar conta Brave Search, obter chave
   → Testar chamada manual via curl/Postman antes de integrar

2. Backend — Módulo de busca base
   → providers.py com BraveSearchProvider
   → formatter.py para injeção no prompt
   → Testar isoladamente (sem UI ainda)

3. Backend — Busca Manual
   → Endpoint de configuração (web_search_config)
   → Integração no chat.py com flag web_search
   → Badge de fontes na mensagem persistida

4. Frontend — Toggle Manual
   → WebSearchToggle.tsx
   → Integração no MessageInput
   → Feedback visual de busca em andamento

5. Backend — Heurística
   → heuristics.py com scoring por sinais
   → Configuração de sensibilidade
   → web_search_log para auditoria

6. Frontend — Configurações
   → WebSearchSettings.tsx completo
   → Visualização do log de buscas

7. Integrações finas
   → ContextBar: incluir tokens de busca
   → Fusion: busca compartilhada entre modelos paralelos
   → Cache: TTL curto e separado para resultados de busca

8. Testes de borda
   → Zero resultados, rate limit, timeout
   → Ajuste fino da sensibilidade heurística com casos reais
```

---

## 12. Resumo Executivo

| Aspecto | Detalhe |
|---|---|
| **Complexidade** | Média |
| **Tempo estimado** | 10–14h (manual: ~5h, heurística: ~5h, integrações: ~3h) |
| **Dependências novas** | Nenhuma obrigatória (Brave Search é REST puro); `duckduckgo-search` opcional |
| **Risco principal** | Heurística com falsos positivos/negativos até calibrar a sensibilidade |
| **Mitigação** | Começar com busca manual apenas; heurística como segunda entrega, com log de auditoria desde o início |
| **Dependência de custo** | Free tier do Brave (2.000/mês) é generoso para uso doméstico — monitorar via `web_search_log` se necessário |

---

## 13. Nota Estratégica

Sugiro **duas entregas**:

**Entrega 1 — Busca Manual**
- Toggle simples, funciona com qualquer modelo (não depende de tool calling)
- Você e a Vera controlam exatamente quando gastar uma chamada de busca
- Valor imediato: perguntas sobre notícias, cotações, eventos recentes
- ~6h de trabalho

**Entrega 2 — Heurística Automática**
- Depende da Entrega 1 estar estável (usa o mesmo pipeline de busca e injeção)
- Requer um período de calibração — comece com sensibilidade "baixa" e ajuste observando o `web_search_log`
- Considere manter **desativada por padrão** mesmo após implementada, deixando como opt-in explícito em Configurações — evita buscas surpresa até você confiar no comportamento
- ~6-8h de trabalho, incluindo tempo de ajuste fino
