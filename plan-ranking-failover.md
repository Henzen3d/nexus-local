# Plano de Implementação — Ranking de Modelos + Roteamento Automático por Falha (Failover)
**NexusLocal** · Documento técnico de planejamento

---

## 1. Visão Geral

Esta funcionalidade tem três objetivos que se apoiam mutuamente:

1. **Ranking de modelos** — ordenar/badge os modelos no seletor com base em qualidade (benchmarks) e popularidade (uso real), em vez de ordem alfabética arbitrária.
2. **Dashboard de uso pessoal** — um "OpenRouter Rankings", só que da sua própria instância: quais modelos você e a Vera mais usam, quantos tokens cada um processou, quantas vezes houve failover.
3. **Roteamento automático por esgotamento (o núcleo real do pedido)** — se o `DeepSeek V4` no OpenRouter bater rate limit, o sistema troca sozinho para `DeepSeek V4` no Groq (mesmo modelo, outro provider) sem que o usuário perceba. Se esgotar em todos os providers que oferecem esse modelo, cai para o próximo modelo mais bem ranqueado disponível.

### O conceito central que viabiliza tudo: **Model Family (Família de Modelo)**

Hoje o NexusLocal trata cada `(provider, model)` como uma entidade isolada — `groq/llama-3.3-70b` e `openrouter/llama-3.3-70b-instruct:free` são registros completamente separados, mesmo sendo **o mesmo modelo subjacente**. Para o failover funcionar, é preciso primeiro **agrupar** essas entradas equivalentes sob uma identidade canônica:

```
Família "DeepSeek V4"
  ├─ openrouter/deepseek-v4:free    (rank 1 na família — prioridade)
  ├─ groq/deepseek-v4                (rank 2 na família — fallback)
  └─ cerebras/deepseek-v4            (rank 3 na família — fallback)
```

Sem esse agrupamento, o sistema não tem como saber que dois `model_id` diferentes são "a mesma coisa em outro provider" — essa é a peça de arquitetura que todo o resto depende.

---

## 2. Conceitos-Chave

| Conceito | Definição |
|---|---|
| **Model Family** | Agrupamento de modelos equivalentes (mesmo peso/arquitetura) disponíveis em providers diferentes |
| **Ranking de Qualidade** | Pontuação baseada em benchmarks (MMLU, GSM8K, HumanEval etc.), vinda de fontes externas como llm-stats.com |
| **Ranking de Popularidade** | Pontuação baseada em volume de uso real, vinda do OpenRouter Rankings |
| **NexusLocal Score** | Pontuação combinada (qualidade + popularidade + uso interno) que define o badge e a ordenação |
| **Cascata de Failover** | Sequência de fallback: 1º modelo da família → 2º modelo da família → ... → família esgotada → próximo modelo do ranking geral |
| **Quota Status** | Estado de disponibilidade de um `(provider, model)`: `available`, `degraded`, `exhausted` |

---

## 3. Fontes de Dados de Ranking — Investigação Necessária Primeiro

Antes de programar qualquer coisa, é preciso confirmar **o que é tecnicamente acessível** em cada fonte. Isso é uma tarefa de descoberta, não de implementação.

### 3.1 OpenRouter Rankings (openrouter.ai/rankings)

- [ ] Verificar se existe endpoint JSON público por trás da página de rankings (inspecionar Network tab do navegador)
- [ ] Verificar se o endpoint já conhecido `GET https://openrouter.ai/api/v1/models` retorna algum campo de popularidade/uso (ex: `"tokens_processed"`, `"rank"`)
- [ ] Se não houver API oficial, avaliar viabilidade de scraping da página (`web_fetch` + parsing HTML) — **último recurso**, frágil a mudanças de layout
- [ ] Documentar a decisão: API oficial, scraping, ou curadoria manual periódica

### 3.2 llm-stats.com/leaderboards

- [ ] Verificar se há exportação CSV/JSON pública da tabela de benchmarks
- [ ] Verificar se há API documentada
- [ ] Caso não haja, considerar curadoria manual periódica (mesmo padrão já usado no Context Registry — Fase 1 daquele plano)

### 3.3 Fallback: Curadoria Manual (Registry Estático)

Independente do resultado da investigação acima, criar **desde já** um arquivo `backend/data/model_rankings.json` curado manualmente com os modelos que você já usa — mesmo princípio do `context_registry.json` já implementado para `context_length`:

```json
{
  "version": "2026-07",
  "rankings": {
    "deepseek-v4": { "quality_score": 88, "popularity_rank": 3 },
    "llama-3.3-70b": { "quality_score": 82, "popularity_rank": 1 },
    "gemini-2.0-flash": { "quality_score": 85, "popularity_rank": 2 }
  }
}
```

Este arquivo é o **fallback confiável** caso as fontes externas não tenham API estável — segue a mesma filosofia de "registry estático + fetch automático quando disponível" já validada no plano de Context Registry.

---

## 4. Banco de Dados

### 4.1 Tabela `model_families` — Agrupamento canônico

```sql
CREATE TABLE IF NOT EXISTS model_families (
    id            TEXT PRIMARY KEY,       -- 'deepseek-v4', 'llama-3.3-70b'
    display_name  TEXT NOT NULL,          -- 'DeepSeek V4'
    description   TEXT
);
```

### 4.2 Tabela `model_family_members` — Modelos que pertencem a cada família

```sql
CREATE TABLE IF NOT EXISTS model_family_members (
    id              TEXT PRIMARY KEY,
    family_id       TEXT NOT NULL REFERENCES model_families(id) ON DELETE CASCADE,
    model_id        TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    fallback_order  INTEGER NOT NULL,     -- 1 = prioridade, 2 = primeiro fallback, etc.
    UNIQUE(family_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_family_members_family ON model_family_members(family_id, fallback_order);
```

### 4.3 Tabela `model_rankings` — Pontuações de qualidade e popularidade

```sql
CREATE TABLE IF NOT EXISTS model_rankings (
    model_id           TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    quality_score      REAL DEFAULT 0,     -- normalizado 0-100, de llm-stats
    popularity_rank    INTEGER,             -- posição no OpenRouter Rankings
    nexuslocal_score   REAL DEFAULT 0,     -- combinado (calculado)
    source             TEXT DEFAULT 'manual',  -- 'manual' | 'openrouter' | 'llm-stats' | 'hybrid'
    updated_at         TEXT DEFAULT (datetime('now'))
);
```

### 4.4 Tabela `model_quota_status` — Estado de disponibilidade em tempo real

```sql
CREATE TABLE IF NOT EXISTS model_quota_status (
    model_id            TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    status              TEXT DEFAULT 'available',  -- 'available' | 'degraded' | 'exhausted'
    consecutive_errors  INTEGER DEFAULT 0,
    exhausted_at        TEXT,
    estimated_reset_at  TEXT,               -- estimativa de quando volta a funcionar
    last_error_message  TEXT
);
```

### 4.5 Tabela `model_usage_log` — Base de dados do dashboard

```sql
CREATE TABLE IF NOT EXISTS model_usage_log (
    id                    TEXT PRIMARY KEY,
    model_id              TEXT NOT NULL,
    provider_id           TEXT NOT NULL,
    conversation_id       TEXT,
    user_id               TEXT,             -- já existe sistema de login (JWT) — rastrear por usuário
    tokens_est            INTEGER DEFAULT 0,
    was_fallback          INTEGER DEFAULT 0,
    fallback_from_model_id TEXT,
    fallback_reason        TEXT,             -- 'rate_limit' | 'error' | 'manual'
    created_at             TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_usage_model ON model_usage_log(model_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user  ON model_usage_log(user_id, created_at);
```

> **Nota sobre múltiplos usuários:** como você já tem JWT/bcrypt implementado para separar você e a Vera, o `model_usage_log` guarda `user_id` para permitir dashboard filtrável por pessoa — mas o `model_quota_status` é **necessariamente global**, já que as chaves de API são compartilhadas pela casa toda (se o Groq esgotar para você, esgotou para ela também).

---

## 5. Backend — Módulo de Ranking

### Novo módulo: `backend/ranking/`

```
backend/ranking/
  __init__.py
  sources.py        # adapters para OpenRouter/llm-stats (fetch ou scraping)
  scorer.py          # normalização e cálculo do NexusLocal Score
  sync.py            # job periódico de atualização
```

### 5.1 `sources.py` — Ingestão de dados externos

```python
class OpenRouterRankingSource:
    async def fetch(self) -> list[RankingEntry]:
        """Tenta endpoint JSON; se indisponível, faz fallback para registry estático."""
        ...

class LLMStatsSource:
    async def fetch(self) -> list[RankingEntry]:
        """Idem — tenta fonte externa, cai para registry estático em caso de falha."""
        ...

class StaticRegistrySource:
    def load(self) -> list[RankingEntry]:
        """Sempre disponível — lê backend/data/model_rankings.json"""
        ...
```

### 5.2 `scorer.py` — Cálculo do NexusLocal Score

```python
def calculate_nexuslocal_score(
    quality_score: float,       # 0-100, de llm-stats
    popularity_rank: int,        # posição no OpenRouter (1 = mais usado)
    internal_usage_count: int,   # quantas vezes VOCÊ usou esse modelo
) -> float:
    """
    Combina três sinais com pesos configuráveis:
    - 50% qualidade (benchmark)
    - 30% popularidade externa (confiança da comunidade)
    - 20% uso interno (sua própria preferência prática)
    """
    normalized_popularity = 100 - min(popularity_rank, 100)
    normalized_internal = min(internal_usage_count / MAX_EXPECTED_USAGE * 100, 100)

    return (
        quality_score * 0.5 +
        normalized_popularity * 0.3 +
        normalized_internal * 0.2
    )
```

### 5.3 `sync.py` — Atualização periódica

Job em background (mesmo padrão do `sync_log` já usado no Context Registry — Fase 2):

```python
async def sync_rankings():
    """Roda a cada 24h ou sob demanda via botão manual em Configurações."""
    external_data = await try_fetch_external_sources()
    internal_usage = await aggregate_internal_usage_stats()

    for model in all_models:
        score = calculate_nexuslocal_score(...)
        await save_ranking(model.id, score, source="hybrid")
```

---

## 6. Backend — Model Families (Agrupamento Canônico)

### 6.1 Endpoint de gerenciamento manual

Como a detecção automática de "esses dois modelos são equivalentes" é tecnicamente difícil (nomes diferem entre providers: `deepseek-v4:free` vs `DeepSeek-V4-Instruct`), a abordagem inicial é **curadoria manual assistida**:

```
POST /api/families                       → cria uma família
POST /api/families/{id}/members          → adiciona um model_id à família
DELETE /api/families/{id}/members/{mid}  → remove
GET  /api/families                        → lista todas com seus membros
```

### 6.2 Sugestão semi-automática (assistente de agrupamento)

Para reduzir o trabalho manual, um endpoint auxiliar que sugere possíveis famílias com base em similaridade de nome:

```python
def suggest_family_groupings(all_models: list[Model]) -> list[SuggestedFamily]:
    """
    Agrupa por normalização de nome:
    'deepseek-v4:free', 'deepseek-v4-instruct', 'DeepSeek-V4' 
    → normalizado para 'deepseek-v4' → mesma família sugerida
    Usuário confirma ou ajusta manualmente na UI.
    """
    ...
```

Isso não precisa ser perfeito — é um **assistente**, não uma automação total. O usuário sempre revisa antes de confirmar.

---

## 7. Backend — Sistema de Failover Automático (o núcleo do pedido)

### 7.1 Detecção de esgotamento

Modificação em `backend/providers/base.py` (adapter OpenAI-compat já existente):

```python
class RateLimitError(Exception):
    def __init__(self, retry_after: int | None = None):
        self.retry_after = retry_after

async def stream_chat(self, model, messages, ...):
    try:
        # chamada normal já existente
        ...
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            retry_after = e.response.headers.get("Retry-After")
            raise RateLimitError(retry_after=int(retry_after) if retry_after else None)
        raise
```

### 7.2 Lógica de cascata — `backend/ranking/failover.py`

```python
async def resolve_model_with_failover(
    requested_model_id: str,
    db
) -> tuple[str, str, bool]:
    """
    Retorna (model_id_final, provider_id_final, houve_failover)
    """
    quota = await get_quota_status(requested_model_id, db)

    if quota.status == "available":
        return requested_model_id, get_provider_id(requested_model_id), False

    # Tier 1 — tentar outro membro da mesma família
    family = await get_family_for_model(requested_model_id, db)
    if family:
        for member in family.members_by_fallback_order:
            member_quota = await get_quota_status(member.model_id, db)
            if member_quota.status == "available":
                return member.model_id, member.provider_id, True

    # Tier 2 — família inteira esgotada, cair para o próximo do ranking geral
    next_best = await get_next_best_ranked_model(
        exclude_families=[family.id] if family else [],
        db=db
    )
    if next_best:
        return next_best.model_id, next_best.provider_id, True

    raise NoAvailableModelError("Todos os modelos configurados estão indisponíveis.")
```

### 7.3 Integração no `chat.py`

```python
model_id, provider_id, was_failover = await resolve_model_with_failover(requested_model_id, db)

if was_failover:
    await ws.send_json({
        "type": "failover_notice",
        "original_model": requested_display_name,
        "fallback_model": model_display_name,
        "reason": "rate_limit"
    })

try:
    async for token in provider.stream_chat(model=model_id, ...):
        ...
except RateLimitError as e:
    await mark_model_exhausted(model_id, e.retry_after, db)
    # Tenta novamente com o próximo da cascata (recursivo, com limite de tentativas)
    ...
```

### 7.4 Liberação automática de quota

Job periódico (a cada poucos minutos) que verifica `model_quota_status` e reverte modelos `exhausted` para `available` quando `estimated_reset_at` já passou:

```python
async def release_expired_quotas():
    """Roda a cada 5 min. Providers geralmente resetam por minuto/hora/dia —
    sem header de Retry-After, assume um cooldown conservador padrão (ex: 60s)
    e ajusta para cima se o erro se repetir."""
    ...
```

---

## 8. Backend — Endpoints de Dashboard

```
GET /api/dashboard/usage-summary        → totais por modelo/provider
GET /api/dashboard/usage-timeline       → série temporal (mensagens por dia)
GET /api/dashboard/failover-events      → histórico de trocas automáticas
GET /api/dashboard/quota-status         → status atual de todos os modelos
```

---

## 9. Frontend — Badge no Seletor de Modelos

### Modificação em `ModelSelector.tsx`

```tsx
<div className="model-option">
  <span className="model-option-name">{m.display_name}</span>
  <RankBadge rank={m.nexuslocal_rank} score={m.nexuslocal_score} />
  {m.quota_status === 'exhausted' && <ExhaustedIndicator />}
</div>
```

### Novo componente: `RankBadge.tsx`

```
🥇 #1   → top 3 (ouro/prata/bronze com ícone)
#4-10   → badge numérico neutro
Sem badge → fora do top 10, mas ainda ordenado por score
```

Hover mostra breakdown: `Qualidade: 88 · Popularidade: #3 · Seus usos: 47`

### Toggle de ordenação em Configurações

```
Ordenar modelos por: ( ) Ranking  ( ) Alfabética
```

---

## 10. Frontend — Gerenciamento de Families (Configurações)

Novo componente: `FamilySettings.tsx`, na aba Ferramentas:

```
┌─────────────────────────────────────────────┐
│  🔗 FAMÍLIAS DE MODELOS (Failover)            │
├─────────────────────────────────────────────┤
│  DeepSeek V4                                  │
│    1. OpenRouter · DeepSeek V4 (free)  [🗑]  │
│    2. Groq · DeepSeek V4                [🗑]  │
│    3. Cerebras · DeepSeek V4            [🗑]  │
│    [+ Adicionar membro]                       │
├─────────────────────────────────────────────┤
│  [+ Nova família]                             │
│  [Sugerir agrupamentos automaticamente]       │
└─────────────────────────────────────────────┘
```

---

## 11. Frontend — Dashboard de Uso

Nova rota/aba: `frontend/src/components/UsageDashboard.tsx`

```
┌───────────────────────────────────────────────┐
│  📊 DASHBOARD NEXUSLOCAL                        │
├───────────────────────────────────────────────┤
│  Modelos mais usados (30 dias)                 │
│  ▓▓▓▓▓▓▓▓▓▓▓▓ Llama 3.3 70B (Groq)      142x  │
│  ▓▓▓▓▓▓▓▓ Gemini 2.0 Flash               98x  │
│  ▓▓▓▓ DeepSeek V4 (OpenRouter)            51x  │
├───────────────────────────────────────────────┤
│  Eventos de Failover (7 dias)                  │
│  🔄 DeepSeek V4: OpenRouter → Groq   3x        │
│  🔄 Llama 3.3: Groq → Cerebras       1x        │
├───────────────────────────────────────────────┤
│  Status atual dos providers                    │
│  🟢 Groq          🟢 Gemini        🔴 OpenRouter│
│  🟢 Cerebras      🟡 NVIDIA (degradado)         │
└───────────────────────────────────────────────┘
```

Bibliotecas de gráfico já disponíveis no ecossistema de artifacts do projeto (recharts) podem ser reaproveitadas aqui se a UI migrar para um componente de visualização similar.

---

## 12. Transparência ao Usuário — Aviso de Failover

Seguindo o mesmo padrão já estabelecido no Vision Relay (nunca esconder completamente um desvio automático):

```
┌──────────────────────────────────────────────┐
│ 🔷 DeepSeek V4 (Groq)   14:32                  │
│ 🔄 OpenRouter esgotado — usando Groq          │  ← aviso discreto
│                                                │
│ Resposta gerada normalmente...                │
└──────────────────────────────────────────────┘
```

Hover: "O DeepSeek V4 no OpenRouter atingiu o limite de requisições. O sistema trocou automaticamente para o mesmo modelo no Groq."

---

## 13. Integração com Funcionalidades Existentes

| Funcionalidade | Impacto |
|---|---|
| **Fusion** | Cada modelo do preset Fusion deve resolver failover independentemente — se um membro do preset esgotar, ele é substituído pelo próximo da família **antes** do disparo paralelo, não durante |
| **Cache** | Cache exato/semântico continua por `model_id` — um cache hit no modelo original não deveria "vazar" para o fallback sem marcação clara de que a resposta veio de um modelo diferente |
| **Context Registry** | `model_family_members` pode aproveitar o mesmo `context_registry.json` para popular `context_length` de todos os membros de uma família de uma vez |
| **Vision Relay** | Sem conflito direto — mas o modelo intérprete do relay também deveria ter failover próprio, já que é crítico para toda a funcionalidade de imagem |

---

## 14. Tratamento de Erros e Casos-Limite

| Cenário | Comportamento |
|---|---|
| Todos os membros da família esgotados E nenhum modelo do ranking geral disponível | Erro claro ao usuário: "Todos os modelos configurados estão indisponíveis no momento. Tente novamente em alguns minutos." |
| Família configurada com apenas 1 membro (sem fallback real) | Aviso em Configurações: "Esta família não tem fallback — considere adicionar outro provider" |
| Modelo "sobe" de status (`exhausted` → `available`) mas o job de liberação ainda não rodou | Tentativa manual do usuário força uma verificação de status antes de aceitar o erro |
| Rate limit do tipo "diário" vs "por minuto" | Sem header explícito, adotar heurística conservadora (assumir diário se o erro persistir por >5 tentativas em minutos diferentes) |
| Usuário desativa failover completamente | Toggle global em Configurações: "Failover automático" ligado/desligado — quando desligado, comportamento atual (erro direto) é preservado |

---

## 15. Arquivos a Criar / Modificar

| Arquivo | Ação |
|---|---|
| `backend/ranking/__init__.py` | **Criar** |
| `backend/ranking/sources.py` | **Criar** — adapters OpenRouter/llm-stats/registry estático |
| `backend/ranking/scorer.py` | **Criar** — cálculo do NexusLocal Score |
| `backend/ranking/sync.py` | **Criar** — job periódico de atualização |
| `backend/ranking/failover.py` | **Criar** — lógica de cascata de fallback |
| `backend/data/model_rankings.json` | **Criar** — registry estático curado |
| `backend/routers/ranking.py` | **Criar** — endpoints de ranking e badge |
| `backend/routers/families.py` | **Criar** — CRUD de model families |
| `backend/routers/dashboard.py` | **Criar** — endpoints de uso e failover events |
| `backend/routers/chat.py` | **Modificar** — integrar `resolve_model_with_failover`, capturar `RateLimitError`, registrar `model_usage_log` |
| `backend/providers/base.py` | **Modificar** — capturar 429 e levantar `RateLimitError` com `retry_after` |
| `backend/database.py` | **Modificar** — 5 novas tabelas (families, members, rankings, quota_status, usage_log) |
| `backend/main.py` | **Modificar** — registrar routers, agendar jobs de sync e liberação de quota |
| `frontend/src/components/RankBadge.tsx` | **Criar** |
| `frontend/src/components/FamilySettings.tsx` | **Criar** |
| `frontend/src/components/UsageDashboard.tsx` | **Criar** |
| `frontend/src/components/ModelSelector.tsx` | **Modificar** — exibir badge, indicador de quota, toggle de ordenação |
| `frontend/src/components/MessageBubble.tsx` | **Modificar** — aviso de failover na mensagem |
| `frontend/src/types.ts` | **Modificar** — interfaces de ranking, family, quota, usage |
| `frontend/src/api/client.ts` | **Modificar** — métodos para os novos endpoints |

---

## 16. Sequência de Implementação — Tarefas e Subtarefas

### Fase 1 — Fundação de Dados (pré-requisito de tudo)
- [x] 1.1 Criar as 5 tabelas novas em `database.py`
- [x] 1.2 Criar `model_rankings.json` curado manualmente com os modelos que você já usa
- [x] 1.3 Popular `model_families` e `model_family_members` manualmente para os casos que você já conhece (ex: DeepSeek, Llama 3.3)
- [x] 1.4 Migração: rodar script único para popular `model_rankings` inicial a partir do JSON

### Fase 2 — Investigação de Fontes Externas
- [x] 2.1 Inspecionar se OpenRouter tem endpoint JSON de rankings
- [x] 2.2 Inspecionar se llm-stats.com tem exportação/API
- [x] 2.3 Documentar decisão final (API real, scraping, ou só curadoria manual)
- [x] 2.4 Implementar `sources.py` conforme decisão

### Fase 3 — Motor de Ranking
- [x] 3.1 Implementar `scorer.py` com o cálculo do NexusLocal Score
- [x] 3.2 Implementar `sync.py` (job periódico + botão manual em Configurações)
- [x] 3.3 Endpoint `GET /api/ranking` retornando scores calculados
- [x] 3.4 Testar cálculo com dados reais dos seus modelos configurados

### Fase 4 — Badge e Ordenação (valor visível rápido)
- [x] 4.1 Componente `RankBadge.tsx`
- [x] 4.2 Integrar badge no `ModelSelector.tsx`
- [x] 4.3 Toggle de ordenação (ranking vs alfabética) em Configurações
- [x] 4.4 Tooltip com breakdown do score

### Fase 5 — Detecção de Esgotamento
- [x] 5.1 Modificar `providers/base.py` para capturar 429 e criar `RateLimitError`
- [x] 5.2 Implementar `mark_model_exhausted()` e `model_quota_status`
- [x] 5.3 Job de liberação automática (`release_expired_quotas`)
- [x] 5.4 Testar com um provider real até bater rate limit de propósito

### Fase 6 — Cascata de Failover (o núcleo do pedido)
- [x] 6.1 Implementar `resolve_model_with_failover()` completo (Tier 1 + Tier 2)
- [x] 6.2 Integrar no `chat.py` — resolução antes de cada chamada
- [x] 6.3 Notificação WS `failover_notice` + persistência em `model_usage_log`
- [x] 6.4 Badge de transparência na mensagem (`MessageBubble.tsx`)
- [x] 6.5 Toggle global "Failover automático" em Configurações

### Fase 7 — Gerenciamento de Families (UI)
- [x] 7.1 Endpoints CRUD (`routers/families.py`)
- [x] 7.2 Assistente de sugestão de agrupamento (`suggest_family_groupings`)
- [x] 7.3 Componente `FamilySettings.tsx` completo

### Fase 8 — Dashboard de Uso
- [x] 8.1 Endpoints de agregação (`routers/dashboard.py`)
- [x] 8.2 Componente `UsageDashboard.tsx` com gráficos
- [x] 8.3 Seção de eventos de failover recentes
- [x] 8.4 Seção de status atual de quota por provider

### Fase 9 — Integrações Finas e Testes
- [x] 9.1 Fusion: resolver failover por modelo do preset antes do disparo paralelo
- [x] 9.2 Vision Relay: aplicar failover também ao modelo intérprete
- [x] 9.3 Testes de borda: família com 1 membro só, todos esgotados, rate limit diário vs por minuto
- [x] 9.4 Ajuste fino dos pesos do NexusLocal Score com base no uso real

---

## 17. Resumo Executivo

| Aspecto | Detalhe |
|---|---|
| **Complexidade** | Alta — é a funcionalidade mais arquiteturalmente complexa do roadmap até agora |
| **Tempo estimado** | 24–32h, dividido nas 9 fases acima |
| **Dependências novas** | Nenhuma obrigatória (tudo via `httpx` já existente); scraping eventual não requer libs além do já usado em `web_fetch`-like calls |
| **Risco principal** | Fontes externas (OpenRouter/llm-stats) podem não ter API estável — mitigado pelo registry estático como fallback sempre confiável |
| **Risco secundário** | Agrupamento de families é manual/semi-assistido — não existe forma 100% automática de saber que "DeepSeek V4 no Groq" e "DeepSeek V4 no OpenRouter" são o mesmo modelo sem comparação humana |
| **Maior valor entregue** | Fase 6 (cascata de failover) — é literalmente o problema que você descreveu, resolvido |

---

## 18. Nota Estratégica — Ordem de Prioridade Real

Dado que você mencionou o failover como "o mais importante", sugiro **inverter a ordem cronológica natural** e priorizar assim:

**Prioridade 1 — Fases 1, 5 e 6** (Fundação + Detecção + Cascata)
Isso sozinho já resolve 100% do problema prático que você descreveu — trocar de DeepSeek OpenRouter para DeepSeek Groq automaticamente. Ranking bonito e dashboard são "nice to have" comparado a isso.

**Prioridade 2 — Fase 7** (Gerenciamento de Families via UI)
Sem isso, você populery as famílias direto no banco via SQL manualmente — funciona, mas não escala bem se você for adicionar muitos modelos novos.

**Prioridade 3 — Fases 2, 3, 4** (Ranking externo + Badge)
Cosmético e informativo, mas não crítico — o sistema de failover funciona mesmo com um `model_rankings.json` bem simples, sem depender de scraping externo funcionando.

**Prioridade 4 — Fase 8** (Dashboard)
O mais dispensável no curto prazo — é analytics, não funcionalidade core. Fica bem para uma fase "de luxo" depois que o failover já estiver rodando de forma confiável há algumas semanas.

**Sugestão concreta de primeiro sprint:** implemente manualmente 2-3 families que você já sabe que precisa (DeepSeek, Llama 3.3, algum outro modelo popular que exista em múltiplos dos seus providers), direto via SQL/seed, e foque o esforço de código nas Fases 5 e 6. Isso já resolve o problema real em poucos dias, e o resto (ranking bonito, dashboard, UI de gerenciamento) vem depois com calma.
