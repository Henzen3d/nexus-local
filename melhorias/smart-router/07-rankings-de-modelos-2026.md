# 🏆 07. Rankings de Modelos — base determinística e visão por disponibilidade (2026-10)
**Multi+ / NexusLocal** · Configurações → Rankings de Modelos · complemento do doc 06 (Smart Router)

---

## 1. Sintoma relatado

Na tela **Configurações → Rankings de Modelos** todos os modelos pareciam iguais: qualidade 96–98,
popularidade #2–#4, scores 77,6–78,1, provedor sempre "Local / Outro", um modelo de **imagem**
(`agnes-image-2.1-flash`) em 3º lugar e provedores que **não são mais usados** (Qwen com assinatura
expirada, ZenMux desativado) ainda listados.

## 2. Diagnóstico (causas-raiz no código)

| # | Causa | Efeito observado |
|---|---|---|
| 1 | `backend/routers/admin.py` → `sync_provider_models` semeava `model_rankings` para cada modelo novo com **valores aleatórios**: `quality_score = random.uniform(60, 99)`, `popularity_rank = random.randint(1, 100)`, `source = 'auto-seed'`. | Ranking plano e sem significado (~77–78 para todos), modelo de imagem no pódio, ordem diferente a cada reinstalação. |
| 2 | O job `sync_rankings` (OpenRouter + `model_rankings.json`) **nunca era agendado** em `main.py`; só cobria 16 famílias de 2024/25 por `LIKE '%/chave%'` (R1 = 98 também batia em `deepseek-r1-distill-*`). | Nenhuma qualidade real chegava ao banco; o pouco que existia estava noutra escala. |
| 3 | `GET /api/ranking` devolvia `model_rankings` cru (sem provedor, sem flags). O frontend procurava o provedor na lista do seletor (`/api/models`, só modelos utilizáveis) e caía em `'Local / Outro'` para qualquer modelo fora dela. | Todo modelo desabilitado/sem chave aparecia como "Local / Outro" — e aparecia. |
| 4 | Nenhum filtro de disponibilidade nem de capacidade (chat × imagem × embedding). | Qwen/ZenMux expirados e modelos de imagem no ranking de chat. |
| 5 | Efeito colateral no **Roteador Inteligente**: `load_routing_catalog` trata `quality_score > 50` como ranking real → os valores aleatórios do `auto-seed` sobrescreviam a qualidade heurística (`model_profile.baseline_quality`) em produção. | A escolha dentro do mesmo porte virava ruído. |

## 3. O que mudou

### 3.1 Qualidade determinística — `backend/ranking/sources.py`
- `resolve_quality(...)` → **curadoria local** (`model_rankings.json`, correspondência **exata** por nome
  normalizado) ou **heurística de família/geração** do `model_profile.py` — a mesma base do roteador.
  Nunca aleatória. Modelos não conversacionais ficam limitados a `NON_CHAT_QUALITY_CAP = 25`.
- `normalize_model_key(...)` converge nomes entre provedores: `llama3.1:8b` (Ollama),
  `llama-3.1-8b-instant` (Groq), `@cf/meta/llama-3.1-8b-instruct-fp8` (Cloudflare) e
  `meta-llama/llama-3.1-8b-instruct` (OpenRouter) → `llama-3.1-8b`.
- `build_popularity_index` / `match_popularity` casam a lista `most-popular` do OpenRouter por
  chave normalizada (exata, depois encurtando sufixos de build), para **todos** os modelos.
- `backend/data/model_rankings.json` rebaseado para a escala 2026 (fronteira ~90–95, grandes
  ~80–88, pequenos ~55–70) e documentado como *override* manual.

### 3.2 Sync e migração — `backend/ranking/sync.py`
- `sync_rankings(db=None, fetch_popularity=True, openrouter_source=None)` grava qualidade +
  popularidade para todos os modelos, recalcula e persiste os scores. Se o OpenRouter falhar, a
  popularidade anterior é preservada (nunca zerada).
- `seed_missing_rankings(db)` substitui o sorteio em `sync_provider_models` (sem rede).
- `migrate_legacy_rankings(db)` roda em `init_db()` (bloco incremental try/except): troca linhas
  `auto-seed`/`hybrid`/`manual` legadas pela base determinística. Idempotente.
- `main.py` agenda `run_ranking_sync_job()` (45 s após o boot e a cada 24 h).
- `POST /api/ranking/sync` (admin) força a sincronização; botão **Sincronizar agora** na tela.

### 3.3 Score — `backend/ranking/scorer.py`
- Popularidade em curva logarítmica: #1 → 100, #10 → ~60, #100 → ~19, ≥ #300 → 0; sem posição →
  35 (neutro). Antes era linear com corte em #100 (modelo "conhecido mas pouco usado" valia menos
  do que "desconhecido").
- `build_ranking_overview(db, user_id, scope)` monta o ranking a partir de `models ⨝ providers`
  com provedor real, tags do perfil (porte, raciocínio, coder, visão), `is_free`/`is_local`,
  `available` e `unavailable_reason` (`provider_disabled` | `model_disabled` | `missing_key` |
  `unconfirmed_free`). A regra de chave utilizável é a mesma do seletor
  (`backend/ranking/availability.py`, compartilhada com `GET /api/models`).

### 3.4 API — `backend/routers/ranking.py`
- `GET /api/ranking?scope=available` (padrão) → só modelos de chat utilizáveis pelo usuário.
- `GET /api/ranking?scope=all` → inclui desabilitados/sem chave, marcados.
- Modelos de imagem/embedding/TTS/OCR nunca entram.

### 3.5 UI — `frontend/src/components/RankingsView.tsx`
- Provedor vem do backend (fim do "Local / Outro").
- Chips: porte (Nano…Fronteira), Raciocínio, Código, Visão, Local; motivo de indisponibilidade.
- Barra relativa à faixa real de scores em cada linha e eixo do gráfico ajustado (`min−8 … max+2`).
- Toggle **Mostrar indisponíveis**, resumo "N modelos utilizáveis · scores de X a Y" e botão
  **Sincronizar agora** (admin). Strings em pt-BR, en-US, es-ES, es-419, de-DE, fr-FR, ja, ko.

## 4. Resultado esperado (catálogo de teste)

| # | Modelo | Provedor | Qualidade | Pop. | Score |
|---|---|---|---|---|---|
| 1 | gemini-2.5-flash | Google Gemini | 87 | #1 | 73,5 |
| 2 | gemini-2.5-pro | Google Gemini | 92 | #5 | 67,5 |
| 3 | deepseek-chat-v3.1 | OpenRouter | 88 | #4 | 66,7 |
| … | | | | | |
| 23 | llama-3.1-8b-instant | Groq | 66 | #12 | 49,9 |
| 26 | gemma3:4b | Ollama | 60 | — | 40,5 |

Faixa de ~33 pontos (antes: 0,5), fortes no topo, pequenos na base; ZenMux/Qwen e modelos de
imagem fora da visão padrão.

## 5. Validação em produção (após o deploy)

1. Logs do backend ~45 s após subir: `Ranking sincronizado: N modelos (… curados, … heurísticos), K com popularidade OpenRouter.`
2. Configurações → Rankings de Modelos: provedores reais, scores espalhados, sem Qwen/ZenMux
   (marque **Mostrar indisponíveis** para vê-los com o motivo), sem `agnes-image`.
3. Admin: **Sincronizar agora** → mensagem "Ranking atualizado: N modelos, K com popularidade…".
4. Roteador: Configurações → Roteamento Inteligente → Testar o roteador continua escolhendo
   pequeno para "Oi" e pensante para análise (a qualidade agora é a mesma nos dois lugares).

## 6. Testes

`backend/tests/test_model_rankings_quality.py` (28 testes, banco temporário): normalização de
nomes, casamento de popularidade com fixture do OpenRouter, qualidade curada × heurística,
semeadura determinística, migração do legado via `init_db()`, sync com fonte simulada
(dispersão ≥ 20 pontos, popularidade preservada sem rede), visão por disponibilidade e endpoint
(`scope`, `422` para escopo inválido, `POST /api/ranking/sync`).
