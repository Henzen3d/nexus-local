# Plano de Implementação — Curadoria de Modelos Free + Gerenciamento Preemptivo de Rate Limits
**NexusLocal** · Documento técnico de planejamento
**Complementa:** `nexuslocal-plano-ranking-failover.md` (usa e estende `model_quota_status`)
 
---
 
## 1. Visão Geral do Problema
 
Hoje, quando o NexusLocal sincroniza modelos de um provider, ele traz **tudo** — incluindo modelos pagos que o usuário nunca vai (ou não deveria) usar. Isso gera dois problemas concretos que você descreveu:
 
1. **Ruído no seletor** — o usuário precisa navegar por dezenas de modelos, muitos pagos, para achar os que realmente pode usar de graça.
2. **Failover reativo, não preventivo** — hoje, quando bate 429, o modelo é desselecionado no painel *depois* do erro acontecer. Isso ainda gera falhas visíveis na conversa antes do sistema reagir.
A solução tem duas partes que se reforçam:
 
- **Curadoria automática de free** — usar bases comunitárias mantidas (os dois repositórios que você indicou) para saber, **antes de qualquer chamada**, quais modelos de cada provider são realmente gratuitos — e habilitá-los automaticamente, deixando o resto desabilitado por padrão.
- **Quota tracking preemptivo** — em vez de esperar o 429 acontecer, o sistema **conta localmente** quantas requisições já foram feitas para cada `(provider, model)` e compara contra o limite conhecido (vindo da mesma base de dados). Quando está perto do limite, troca de modelo **antes** do erro ocorrer — não depois.
---
 
## 2. Análise das Fontes de Dados (Investigação Já Realizada)
 
### 2.1 `mnfst/awesome-free-llm-apis` — Fonte primária ✅
 
**Descoberta importante:** este repositório tem um arquivo `data.json` estruturado, acessível via raw URL:
```
https://github.com/mnfst/awesome-free-llm-apis/raw/refs/heads/main/data.json
```
 
Formato confirmado (JSON válido, ~1557 linhas, atualizado em `lastUpdated`):
 
```json
{
  "lastUpdated": "2026-05-20",
  "providers": [
    {
      "name": "Groq",
      "category": "inference_provider",
      "country": "US",
      "url": "https://console.groq.com/keys",
      "baseUrl": "https://api.groq.com/openai/v1",
      "description": "Free tier, no credit card. Ultra-fast LPU inference.",
      "models": [
        {
          "id": "llama-3.3-70b-versatile",
          "name": "llama-3.3-70b-versatile",
          "context": "131K",
          "maxOutput": "32K",
          "modality": "Text",
          "rateLimit": "30 RPM, 14,400 RPD"
        }
      ]
    }
  ]
}
```
 
**Achado crítico para a implementação:** o campo `models[].id` já usa o **mesmo identificador exato** que a API do provider espera (ex: `llama-3.3-70b-versatile` para Groq) — que é literalmente o mesmo valor que já fica salvo em `models.name` no seu banco. Isso significa que o **matching entre o registry externo e seus modelos já sincronizados pode ser um match exato de string** na maioria dos casos, sem precisar de fuzzy matching complexo.
 
Cobertura confirmada no `data.json`: AI21, Alibaba Cloud, Cohere, DeepSeek, Google Gemini, Mistral AI, Z AI, Cerebras, Cloudflare Workers AI, GitHub Models, Groq, Hugging Face, Kilo Code, LLM7.io, ModelScope, Nebius, Nscale, NVIDIA NIM, Ollama Cloud, OpenRouter, OVHcloud, SiliconFlow — cobre **todos os providers que você já usa**.
 
### 2.2 `cheahjs/free-llm-api-resources` — Fonte secundária ⚠️
 
Este repositório **não tem** um `data.json` equivalente — é um README.md gerado a partir de um diretório `src/` em Python (provavelmente scripts que montam a tabela markdown via GitHub Actions). Para extrair dados estruturados daqui seria necessário:
- Fazer parsing do markdown (regex nas tabelas) — frágil a mudanças de formatação, **ou**
- Investigar se o `src/` gera algum artefato JSON intermediário não exposto publicamente (precisaria explorar o repositório além do README)
**Recomendação:** tratar como fonte de **validação cruzada e curadoria manual**, não como fonte automatizada primária. Onde os dois repositórios divergem em algum limite, usar o `cheahjs` como sinal de alerta para revisão manual, mas confiar no `mnfst/data.json` para automação.
 
### 2.3 `open-free-llm-api/awesome-freellm-apis` — Terceira fonte, investigada e **resolvida** ⚠️
 
Repositório: https://github.com/open-free-llm-api/awesome-freellm-apis · Site: https://freellm.net
 
**Confirmado nesta investigação:** o site é real, ativo e bem completo — **368 modelos, 30 providers**, tabela com score, contexto, modalidade, rate limit, data de lançamento e uso semanal em tokens, refresh diário (`refreshed Jul 7, 2026` no momento da consulta). O README do próprio repositório confirma: <cite index="7-1">"Data from freellm.net, updated daily via API monitoring"</cite> — ou seja, o `freellm.net` já faz o trabalho pesado de monitorar as APIs dos providers em si.
 
**Não existe endpoint JSON público.** Foi confirmado que:
- Não há `data.json` no repositório (a única infra estruturada nele é o próprio README + traduções).
- As páginas do site (`/models/`, `/models/{provider}/{model}`, `/config/`) são renderizadas como HTML de tabela — sem endpoint tipo `/api/models` documentado ou descoberto.
- O README menciona explicitamente <cite index="7-1">"data refreshed daily from freellm.net"</cite>, mas isso descreve a fonte dos dados do README/site — não uma API que o NexusLocal poderia chamar diretamente.
**Conclusão prática: a única forma de indexar essa fonte é via scraping das páginas HTML**, não uma integração de API limpa como a do `mnfst/data.json`. Isso muda a recomendação:
 
- **Onde ela poderia entrar (se decidirmos implementar):** um scraper de `https://freellm.net/models/` que faz parsing da tabela markdown-like renderizada (mesma estrutura de colunas: Provider, Model, Score, Context, Modality, Rate Limit, Released, Weekly Tokens, Status), convertendo para o mesmo formato de `free_model_registry` (Seção 3.1), com `source = 'freellm'`.
- **Por que ainda não entra na Fase 1 deste plano:** um scraper de HTML é estruturalmente mais frágil que consumir um JSON versionado — qualquer mudança de layout no site quebra o parser silenciosamente. Isso é o mesmo risco já mapeado para `cheahjs` na Seção 2.2, só que aqui o dado é *melhor* (mais modelos, score de qualidade, uso semanal real) o que torna a fonte tentadora apesar do risco.
- **Vantagem real sobre o `mnfst`:** os dados do `freellm.net` parecem mais atualizados e granulares — trazem um campo de **"Score"** (não presente no `mnfst`) que já é uma espécie de ranking de qualidade pronto, e o **"Weekly Tokens"** dá um proxy de popularidade/confiabilidade do modelo que poderia alimentar diretamente a curadoria de `model_rankings.json` mencionada no plano de Ranking + Failover.
**Recomendação final:** tratar como **candidato a scraper opcional de segunda fase**, não como parte da Fase 1. Se decidirmos avançar, viraria uma tarefa nova e isolada (`backend/free_registry/freellm_scraper.py`) — ver Fase 6.4 abaixo — com o parser de HTML isolado do restante do pipeline, para que uma quebra no scraping do `freellm.net` nunca derrube a ingestão do `mnfst/data.json`, que continua sendo a fonte primária e estável.
 
---
 
## 3. Modelo de Dados
 
### 3.1 Nova tabela: `free_model_registry` — Dados brutos ingeridos
 
```sql
CREATE TABLE IF NOT EXISTS free_model_registry (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,            -- 'mnfst' | 'cheahjs' | 'manual'
    provider_name   TEXT NOT NULL,             -- nome como aparece na fonte (ex: "Groq")
    model_id_raw    TEXT NOT NULL,             -- id como aparece na fonte (ex: "llama-3.3-70b-versatile")
    context_raw     TEXT,                      -- string bruta, ex: "131K"
    max_output_raw  TEXT,
    modality        TEXT,
    rate_limit_raw  TEXT,                      -- string bruta, ex: "30 RPM, 14,400 RPD"
    rpm             INTEGER,                   -- parseado
    rpd             INTEGER,                   -- parseado
    tpm             INTEGER,
    tpd             INTEGER,
    rps             INTEGER,
    parse_confidence TEXT DEFAULT 'high',       -- 'high' | 'low' | 'unparseable'
    base_url        TEXT,
    last_synced_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_registry_provider ON free_model_registry(provider_name, model_id_raw);
```
 
### 3.2 Extensão da tabela `model_quota_status` (já definida no plano de Ranking + Failover)
 
```sql
ALTER TABLE model_quota_status ADD COLUMN known_rpm INTEGER;
ALTER TABLE model_quota_status ADD COLUMN known_rpd INTEGER;
ALTER TABLE model_quota_status ADD COLUMN known_tpm INTEGER;
ALTER TABLE model_quota_status ADD COLUMN known_tpd INTEGER;
ALTER TABLE model_quota_status ADD COLUMN current_minute_count INTEGER DEFAULT 0;
ALTER TABLE model_quota_status ADD COLUMN current_day_count    INTEGER DEFAULT 0;
ALTER TABLE model_quota_status ADD COLUMN minute_window_reset  TEXT;
ALTER TABLE model_quota_status ADD COLUMN day_window_reset     TEXT;
ALTER TABLE model_quota_status ADD COLUMN confirmed_free       INTEGER DEFAULT 0;
ALTER TABLE model_quota_status ADD COLUMN registry_source      TEXT;  -- 'mnfst' | 'cheahjs' | 'manual' | NULL
```
 
### 3.3 Extensão da tabela `models` (já existente)
 
```sql
ALTER TABLE models ADD COLUMN confirmed_free INTEGER DEFAULT 0;
-- Modelos sincronizados sem match no registry ficam confirmed_free=0 e enabled=0 por padrão
```
 
---
 
## 4. Backend — Ingestão e Parsing
 
### Novo módulo: `backend/free_registry/`
 
```
backend/free_registry/
  __init__.py
  fetcher.py         # busca o data.json do mnfst
  rate_limit_parser.py  # extrai RPM/RPD/TPM/TPD de strings livres
  matcher.py           # cruza registry com models já sincronizados
  sync.py              # job de atualização periódica
```
 
### 4.1 `fetcher.py`
 
```python
MNFST_DATA_URL = "https://github.com/mnfst/awesome-free-llm-apis/raw/refs/heads/main/data.json"
 
async def fetch_mnfst_registry() -> dict:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(MNFST_DATA_URL)
        resp.raise_for_status()
        return resp.json()
 
async def is_registry_stale(current_last_updated: str, db) -> bool:
    """Compara lastUpdated do JSON com o que já está salvo — só reprocessa se mudou."""
    ...
```
 
### 4.2 `rate_limit_parser.py` — O parser mais importante do módulo
 
Precisa lidar com formatos heterogêneos observados no `data.json` real:
 
```python
import re
 
def parse_rate_limit(raw: str) -> dict:
    """
    Exemplos reais encontrados no data.json:
      "30 RPM, 14,400 RPD"              → {rpm: 30, rpd: 14400}
      "20 RPM, 50 RPD"                  → {rpm: 20, rpd: 50}
      "10 RPM, 250 RPD"                 → {rpm: 10, rpd: 250}
      "500K TPM"                        → {tpm: 500000}
      "1 request/second, 500,000 tokens/minute, 1,000,000,000 tokens/month"
                                         → {rps: 1, tpm: 500000, tpm_month: 1000000000}
      "Dynamic" / "Tier-based" / "Fair-use" / "Credit-metered"
                                         → {} com parse_confidence='unparseable'
      "10K neurons/day (shared)"        → unidade não-padrão (Cloudflare) — tratado à parte
    """
    result = {}
 
    rpm_match = re.search(r'([\d,]+)\s*RPM', raw)
    rpd_match = re.search(r'([\d,]+)\s*RPD', raw)
    tpm_match = re.search(r'([\d,]+)K?\s*(?:tokens/minute|TPM)', raw, re.IGNORECASE)
    tpd_match = re.search(r'([\d,]+)K?\s*(?:tokens/day|TPD)', raw, re.IGNORECASE)
    rps_match = re.search(r'([\d,]+)\s*(?:RPS|requests?/second)', raw, re.IGNORECASE)
 
    if rpm_match: result['rpm'] = int(rpm_match.group(1).replace(',', ''))
    if rpd_match: result['rpd'] = int(rpd_match.group(1).replace(',', ''))
    if tpm_match: result['tpm'] = _normalize_k(tpm_match.group(1))
    if tpd_match: result['tpd'] = _normalize_k(tpd_match.group(1))
    if rps_match: result['rps'] = int(rps_match.group(1).replace(',', ''))
 
    if not result:
        return {"parse_confidence": "unparseable", "raw": raw}
 
    result["parse_confidence"] = "high"
    return result
 
def _normalize_k(s: str) -> int:
    """'500K' → 500000, '1,000,000' → 1000000"""
    ...
```
 
> **Casos que ficam `unparseable` (esperado, não é bug):** "Dynamic" (DeepSeek), "Tier-based" (Nebius), "Fair-use" (Nscale), "Credit-metered" (HuggingFace). Para esses, o sistema **não pode** fazer quota tracking preemptivo — cai automaticamente para o comportamento reativo já existente (detecção de 429 real). Isso é documentado explicitamente, não silenciosamente ignorado.
 
### 4.3 `matcher.py` — Cruzamento com modelos já sincronizados
 
```python
# Normalização de nome de provider: "Groq" (registry) → "groq" (seu provider.id)
PROVIDER_NAME_MAP = {
    "Groq": "groq",
    "Google Gemini": "gemini",
    "OpenRouter": "openrouter",
    "Cerebras": "cerebras",
    "NVIDIA NIM": "nvidia",
    "Cloudflare Workers AI": "cloudflare",
    "SambaNova Cloud": "sambanova",
    # ... completar conforme os providers já cadastrados no NexusLocal
}
 
async def match_registry_to_models(db) -> dict:
    """
    Para cada entrada em free_model_registry, tenta achar o model_id
    correspondente na tabela models (match exato em models.name).
    Se não achar exato, tenta normalização leve (lowercase, remove sufixos como ':free').
    Retorna relatório: {matched: N, unmatched: [...]}
    """
    registry_entries = await get_all_registry_entries(db)
    report = {"matched": 0, "unmatched": []}
 
    for entry in registry_entries:
        provider_id = PROVIDER_NAME_MAP.get(entry.provider_name)
        if not provider_id:
            report["unmatched"].append(entry)
            continue
 
        # Match exato primeiro (caso mais comum, conforme achado na seção 2.1)
        model = await find_model_by_name(entry.model_id_raw, provider_id, db)
 
        # Fallback: normalização leve
        if not model:
            normalized = entry.model_id_raw.replace(':free', '').lower()
            model = await find_model_by_normalized_name(normalized, provider_id, db)
 
        if model:
            await mark_confirmed_free(model.id, entry, db)
            report["matched"] += 1
        else:
            report["unmatched"].append(entry)
 
    return report
```
 
### 4.4 `sync.py` — Orquestração periódica
 
```python
async def sync_free_registry():
    """Roda a cada 24h ou sob demanda via botão em Configurações."""
    data = await fetch_mnfst_registry()
 
    if not await is_registry_stale(data["lastUpdated"], db):
        return {"status": "up_to_date"}
 
    await clear_and_reload_registry(data, db)  # popula free_model_registry
    report = await match_registry_to_models(db)  # cruza com models existentes
 
    return {
        "status": "updated",
        "last_updated": data["lastUpdated"],
        "matched": report["matched"],
        "unmatched_count": len(report["unmatched"]),
    }
```
 
---
 
## 5. Backend — Filtro Automático na Sincronização de Providers
 
Modificação no fluxo de sync já existente (endpoint `POST /api/admin/providers/{id}/sync-models`, do plano de Context Registry):
 
```python
async def sync_provider_models(provider_id: str, db):
    live_models = await fetch_live_models_from_provider_api(provider_id)  # traz TUDO, como hoje
 
    for model in live_models:
        registry_match = await find_registry_match(model.name, provider_id, db)
 
        if registry_match:
            # Confirmado free pela comunidade — habilita automaticamente
            await upsert_model(
                model,
                enabled=True,
                confirmed_free=True,
                context_length=registry_match.context_parsed or model.context_length,
            )
            await save_quota_limits(model.id, registry_match, db)
        else:
            # Não encontrado no registry — provavelmente pago ou muito recente
            # Fica DESABILITADO por padrão, mas visível para o usuário revisar
            await upsert_model(model, enabled=False, confirmed_free=False)
```
 
> **Isso resolve diretamente o problema que você descreveu:** a sincronização deixa de "trazer tudo habilitado" e passa a "habilitar automaticamente só o que a comunidade confirma como free, deixando o resto desligado até revisão manual".
 
---
 
## 6. Backend — Quota Tracking Preemptivo (o núcleo da melhoria)
 
### Novo módulo: `backend/ranking/quota_tracker.py`
 
### 6.1 Registro de cada requisição
 
```python
async def record_request(model_id: str, db):
    """Chamado após CADA chamada bem-sucedida ao provider."""
    await db.execute("""
        UPDATE model_quota_status
        SET current_minute_count = current_minute_count + 1,
            current_day_count    = current_day_count + 1
        WHERE model_id = ?
    """, (model_id,))
    await db.commit()
```
 
### 6.2 Verificação preemptiva — antes de disparar a chamada
 
```python
async def get_quota_health(model_id: str, db, threshold: float = 0.85) -> QuotaHealth:
    """
    Retorna 'safe', 'near_limit' ou 'unknown' (quando não há known_rpm/rpd —
    caso 'unparseable' da seção 4.2, cai no comportamento reativo já existente).
    """
    status = await get_quota_status_row(model_id, db)
 
    if status.known_rpm is None and status.known_rpd is None:
        return QuotaHealth.UNKNOWN  # sem dados — comportamento reativo padrão
 
    minute_ratio = status.current_minute_count / status.known_rpm if status.known_rpm else 0
    day_ratio    = status.current_day_count / status.known_rpd if status.known_rpd else 0
 
    if minute_ratio >= threshold or day_ratio >= threshold:
        return QuotaHealth.NEAR_LIMIT
 
    return QuotaHealth.SAFE
```
 
### 6.3 Integração com a cascata de failover (do plano anterior)
 
```python
# Em resolve_model_with_failover() — ANTES de tentar a chamada:
 
health = await get_quota_health(requested_model_id, db)
 
if health == QuotaHealth.NEAR_LIMIT:
    # Trata como se já estivesse esgotado — desvia PREVENTIVAMENTE
    # (mesma lógica de cascata já definida: Tier 1 família → Tier 2 ranking geral)
    return await resolve_model_with_failover(requested_model_id, db, force_skip=True)
```
 
Isso é a mudança de comportamento central: **o sistema para de esperar o erro acontecer**. Ele sabe (pelos dados do registry) que Groq permite 14.400 requisições/dia no `llama-3.3-70b-versatile`, conta localmente quantas já foram usadas hoje, e troca de modelo assim que chega em ~85% disso — antes de qualquer 429 real.
 
### 6.4 Jobs de reset de janela
 
```python
async def reset_minute_windows():
    """Roda a cada 60s via scheduler já existente no main.py."""
    await db.execute("UPDATE model_quota_status SET current_minute_count = 0")
    await db.commit()
 
async def reset_day_windows():
    """
    Roda diariamente. Idealmente alinhado ao fuso do provider (geralmente UTC),
    mas sem essa informação exposta pelos repositórios — usa meia-noite UTC como padrão.
    """
    await db.execute("UPDATE model_quota_status SET current_day_count = 0")
    await db.commit()
```
 
> **Limitação honesta:** o contador é local ao NexusLocal — se você usar a mesma chave de API em outro lugar (outra ferramenta, teste manual via curl), o contador local fica dessincronizado do real. Isso é aceitável para o seu caso de uso doméstico, mas vale documentar: o sistema é preciso o suficiente para evitar a maioria dos 429s, não uma garantia absoluta.
 
---
 
## 7. Frontend — Visibilidade e Configurações
 
### 7.1 Badge "Confirmado Free" no Admin Panel
 
```
┌────────────────────────────────────────┐
│ Llama 3.3 70B          ✅ Free confirmado│
│ 131K ctx · 30 RPM · 14.4K RPD           │
└────────────────────────────────────────┘
 
┌────────────────────────────────────────┐
│ GPT-4.1                ❓ Não confirmado│
│ (desabilitado por padrão — revisar)     │
└────────────────────────────────────────┘
```
 
### 7.2 Barra de quota (reaproveitando o padrão visual do `ContextBar`)
 
No `ModelSelector.tsx`, hover no modelo mostra:
```
Uso hoje: ▓▓▓▓▓▓░░░░ 62% (8.940 / 14.400 requisições)
```
 
### 7.3 Nova seção em Configurações → Ferramentas: "Registry de Modelos Free"
 
```
┌─────────────────────────────────────────────┐
│  📋 REGISTRY DE MODELOS FREE                  │
├─────────────────────────────────────────────┤
│  Fonte: mnfst/awesome-free-llm-apis           │
│  Última sincronização: 20/05/2026 (há 3 dias) │
│  Modelos confirmados: 47   Não confirmados: 12│
│                                                │
│  [ Sincronizar agora ]                        │
├─────────────────────────────────────────────┤
│  Threshold de quota preemptiva:               │
│  [────────●───] 85%                           │
│  (trocar de modelo ao atingir esta % do limite)│
└─────────────────────────────────────────────┘
```
 
---
 
## 8. Integração com o Plano de Ranking + Failover
 
Este plano **não substitui** o de Ranking + Failover — ele **alimenta** duas peças que lá ficaram como "a definir":
 
| Peça do plano anterior | Como este plano resolve |
|---|---|
| `model_quota_status.status` | Passa a ser calculado preemptivamente (`get_quota_health`), não só reativamente após 429 |
| Fase 2 "Investigação de Fontes Externas" | Resolvida — `mnfst/data.json` é a fonte confirmada e funcional |
| Curadoria manual de `model_rankings.json` | Pode ser complementada com os dados de contexto (`context`) já presentes no `data.json`, alimentando também o Context Registry |
| Families (agrupamento canônico) | O campo `modality` e `name` do registry ajudam a **sugerir** agrupamentos automaticamente (dois "llama-3.3-70b" em providers diferentes já aparecem com nomes parecidos no próprio registry) |
 
---
 
## 9. Tratamento de Erros e Casos-Limite
 
| Cenário | Comportamento |
|---|---|
| `data.json` indisponível (GitHub fora, rede) | Sync falha silenciosamente, mantém dados da última sincronização bem-sucedida |
| Rate limit "unparseable" (Dynamic, Tier-based, etc.) | Modelo funciona normalmente, mas sem tracking preemptivo — só reativo (comportamento atual preservado) |
| Modelo confirmado free no registry, mas provider mudou e agora cobra | Falha só será percebida quando a API retornar erro de billing — fora do escopo deste plano (feedback do usuário via "reportar modelo incorreto" fica como ideia futura) |
| Dois providers diferentes com modelo de mesmo nome mas rate limits diferentes | Matching é sempre por `(provider_name, model_id)`, nunca só por nome — sem ambiguidade |
| Usuário habilita manualmente um modelo "não confirmado" que na verdade é pago | Risco aceito pelo usuário — o sistema não pode validar isso automaticamente, só sinalizar |
 
---
 
## 10. Arquivos a Criar / Modificar
 
| Arquivo | Ação |
|---|---|
| `backend/free_registry/__init__.py` | **Criar** |
| `backend/free_registry/fetcher.py` | **Criar** — busca `data.json` do mnfst |
| `backend/free_registry/rate_limit_parser.py` | **Criar** — parser de strings de rate limit |
| `backend/free_registry/matcher.py` | **Criar** — cruzamento registry ↔ models |
| `backend/free_registry/sync.py` | **Criar** — orquestração periódica |
| `backend/ranking/quota_tracker.py` | **Criar** — contadores locais + verificação preemptiva |
| `backend/routers/free_registry.py` | **Criar** — endpoints de sync manual e status |
| `backend/routers/admin.py` | **Modificar** — filtro `confirmed_free` no sync de providers |
| `backend/routers/chat.py` | **Modificar** — chamar `record_request()` e `get_quota_health()` no fluxo |
| `backend/database.py` | **Modificar** — tabela `free_model_registry`, extensões em `model_quota_status` e `models` |
| `backend/main.py` | **Modificar** — jobs de reset de janela (minuto/dia) + sync periódico do registry |
| `frontend/src/components/AdminPanel.tsx` | **Modificar** — badge confirmado/não confirmado |
| `frontend/src/components/ModelSelector.tsx` | **Modificar** — barra de quota no hover |
| `frontend/src/components/FreeRegistrySettings.tsx` | **Criar** — painel de sync manual e threshold |
| `frontend/src/types.ts` | **Modificar** — interfaces de quota e registry |
| `frontend/src/api/client.ts` | **Modificar** — endpoints do registry |
 
---
 
## 11. Sequência de Implementação — Tarefas e Subtarefas
 
### Fase 1 — Ingestão de Dados
- [x] 1.1 Implementar `fetcher.py` e testar contra a URL real do `data.json`
- [x] 1.2 Implementar `rate_limit_parser.py` com testes usando as strings reais já catalogadas neste plano
- [x] 1.3 Popular `free_model_registry` manualmente uma vez (rodar sync inicial)
- [x] 1.4 Revisar quantos registros ficaram `unparseable` — ajustar regex se o volume for alto
### Fase 2 — Matching
- [x] 2.1 Completar `PROVIDER_NAME_MAP` com todos os providers já cadastrados no NexusLocal
- [x] 2.2 Implementar `matcher.py` com match exato + fallback normalizado
- [x] 2.3 Rodar matching contra seus modelos reais e revisar o relatório de `unmatched`
- [x] 2.4 Ajustar normalização conforme os casos reais de divergência encontrados
### Fase 3 — Filtro na Sincronização (resolve o pedido original)
- [x] 3.1 Modificar o endpoint de sync de providers para consultar `confirmed_free`
- [x] 3.2 Migração: reprocessar modelos já sincronizados, desabilitando os não confirmados
- [x] 3.3 Testar com um provider real (ex: OpenRouter, que tem muitos modelos pagos misturados)
### Fase 4 — Quota Tracking Preemptivo
- [x] 4.1 Implementar `quota_tracker.py` (record_request, get_quota_health)
- [x] 4.2 Integrar `record_request()` após cada chamada bem-sucedida em `chat.py`
- [x] 4.3 Integrar `get_quota_health()` na resolução de failover (depende do plano de Ranking + Failover)
- [x] 4.4 Jobs de reset de janela (minuto e dia) agendados no `main.py`
- [x] 4.5 Testar cenário real: usar um modelo até chegar perto do limite conhecido, confirmar troca preemptiva
### Fase 5 — Frontend
- [x] 5.1 Badge confirmado/não confirmado no `AdminPanel.tsx`
- [x] 5.2 Barra de quota no hover do `ModelSelector.tsx`
- [x] 5.3 Componente `FreeRegistrySettings.tsx` com sync manual e threshold configurável
- [x] 5.4 Endpoint e UI para revisar/habilitar manualmente modelos "não confirmados"
### Fase 6 — Automação e Manutenção
- [x] 6.1 Job periódico de sync do registry (24h), comparando `lastUpdated`
- [x] 6.2 Log de sincronizações (reaproveitar `sync_log` do Context Registry)
- [x] 6.3 Investigar futuramente `cheahjs/free-llm-api-resources` como fonte de validação cruzada (fora do escopo imediato)
- [x] 6.4 **(Opcional, segunda fase)** Avaliar viabilidade de um scraper isolado para `freellm.net` (`backend/free_registry/freellm_scraper.py`), aproveitando os campos `score` e `weekly_tokens` que o `mnfst` não tem — implementar com parser desacoplado do pipeline principal, para que uma quebra de layout no site não afete a ingestão do `mnfst/data.json`
---
 
## 12. Resumo Executivo
 
| Aspecto | Detalhe |
|---|---|
| **Complexidade** | Média — mais simples que o plano de Ranking + Failover porque a fonte de dados já está confirmada e estruturada |
| **Tempo estimado** | 12–16h |
| **Dependências novas** | Nenhuma (tudo via `httpx` já existente) |
| **Risco principal** | Parser de rate limit pode não cobrir 100% dos formatos — mitigado por fallback gracioso para comportamento reativo |
| **Risco secundário** | `data.json` do mnfst pode mudar de estrutura no futuro sem aviso — mitigado por versionamento do `lastUpdated` e log de sync |
| **Fontes de validação cruzada (futuro)** | `cheahjs/free-llm-api-resources` e `open-free-llm-api/awesome-freellm-apis` (possível API do freellm.net, 453 modelos, refresh diário) — nenhuma delas expõe JSON estruturado no repo hoje, por isso ficam fora da automação primária deste plano |
| **Maior valor entregue** | Fases 3 e 4 juntas — sincronização filtrada + quota preemptiva. Isso sozinho resolve tanto "muitos modelos pagos poluindo a lista" quanto "muitos erros de 429" |
 
---
 
## 13. Nota Estratégica
 
Como este plano é **complementar** ao de Ranking + Failover (não um substituto), a ordem de execução recomendada entre os dois é:
 
1. **Primeiro, Fases 1-3 deste plano** (ingestão + matching + filtro na sync) — resolve o problema mais irritante no seu dia a dia agora: modelos pagos poluindo a lista.
2. **Depois, Fase 4 deste plano** (quota preemptiva) — mas ela só entrega valor completo **em conjunto** com a Fase 6 do plano de Ranking + Failover (cascata de failover). Sem a cascata, saber que está "perto do limite" não tem para onde desviar.
3. **As Fases 5-9 do plano de Ranking + Failover** seguem depois, agora alimentadas por dados reais de rate limit em vez de estimativas manuais.
Ou seja: os dois planos convergem no mesmo ponto — a tabela `model_quota_status`. Este plano a torna **informada** (com limites reais); o outro plano a torna **acionável** (com para onde desviar quando o limite se aproxima).

## 14 Alocação de Modelos por Subtarefa

| Subtarefa | Modelo Sugerido |
| :--- | :--- |
| 1.1 | Gemini 3.5 Flash (Low) |
| 1.2 | Gemini 3.1 Pro (High) |
| 1.3 | Gemini 3.5 Flash (Low) |
| 1.4 | Gemini 3.5 Flash (Medium) |

| 2.1 | Gemini 3.5 Flash (Low) |
| 2.2 | Gemini 3.1 Pro (Low) |
| 2.3 | Gemini 3.5 Flash (Low) |
| 2.4 | Gemini 3.5 Flash (Medium) |

| 3.1 | Gemini 3.1 Pro (Low) |
| 3.2 | Gemini 3.5 Flash (Low) |
| 3.3 | Gemini 3.5 Flash (Low) |

| 4.1 | Gemini 3.1 Pro (High) |
| 4.2 | Gemini 3.5 Flash (Low) |
| 4.3 | Gemini 3.1 Pro (High) |
| 4.4 | Gemini 3.1 Pro (Low) |
| 4.5 | Gemini 3.5 Flash (Medium) |

| 5.1 | Gemini 3.5 Flash (Low) |
| 5.2 | Gemini 3.5 Flash (Medium) |
| 5.3 | Gemini 3.1 Pro (Low) |
| 5.4 | Gemini 3.1 Pro (Low) |

| 6.1 | Gemini 3.5 Flash (Medium) |
| 6.2 | Gemini 3.5 Flash (Low) |
| 6.3 | Gemini 3.5 Flash (Medium) |
| 6.4 | Gemini 3.1 Pro (High) |