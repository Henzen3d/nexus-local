# 🧭 06. Diagnóstico e Calibração 2026 (Perfil de Modelos + Seleção por Fit)
**Multi+ / NexusLocal** · Smart Intent Router — revisão pós-homologação

---

## 1. Sintoma relatado

Em 3 testes com perguntas de tipos distintos (saudação, código, análise), o modo **Auto** escolheu
**sempre o mesmo modelo** e, dentro de uma mesma conversa, nunca trocava de modelo ao mudar o tipo
de pergunta ("Oi" → pergunta complexa).

## 2. Diagnóstico (causas-raiz no código)

O roteamento **já era reavaliado a cada mensagem** (`backend/routers/chat.py` → `_run_turn`); o
problema estava inteiro na **seleção** (`backend/ranking/smart_router.py`):

| # | Causa | Efeito observado |
|---|---|---|
| 1 | `INTENT_FAMILY_MAPPING` e `get_default_quality_score` conheciam apenas famílias de 2024/25 (`llama-3.1-8b`, `qwen-2.5-coder`, `deepseek-r1`, `gemini-2.0-flash`, `mistral-large`…). | Com o catálogo gratuito atual (Kimi K2.x, GLM-4.7/5, DeepSeek V3.2/V4, Qwen3/3.5, gpt-oss, Nemotron 3, Gemini 2.5, Llama 4) quase nenhum modelo casava com família alguma → `candidate_pool = todos os modelos` para **todas** as intenções. |
| 2 | Modelos sem ranking recebiam **qualidade fixa 60**. `backend/data/model_rankings.json` cobre 16 famílias antigas. | Empate geral em 60 → o vencedor era decidido pela **ordem das linhas do SQL**: o mesmo modelo para saudação, código e raciocínio. |
| 3 | Sticky routing mantinha o modelo anterior se estivesse a ≤ 15 % do melhor score (5 % em código/raciocínio). | Com todos empatados, o 1º modelo da conversa ficava "colado" até o fim. |
| 4 | A seleção ignorava capacidades já presentes no catálogo (`models.reasoning_control`, `supports_vision`), porte do modelo e velocidade do provedor. | O roteador não distinguia "8B rápido" de "1T pensante". |
| 5 | Classificador só com palavras-chave em PT; complexidade = tamanho do texto; sem detecção de perguntas analíticas/multi-partes. | Perguntas complexas sem as palavras mágicas viravam `general_chat` → pool genérico. |

## 3. O que mudou

### 3.1 `backend/ranking/model_profile.py` (novo, função pura, cacheada)
`profile_model(id, nome, provedor, reasoning_control, supports_vision)` deriva do catálogo:

| Campo | Como é inferido | Exemplos |
|---|---|---|
| `size_tier` | overrides por família → parâmetros no nome (`70b`, `30b-a3b`, `8x7b`) → palavras (`mini`, `lite`, `pro`) | nano (≤4B), small (≤16B), medium (≤45B), large (≤200B), frontier (K2, V3/V4, GLM-5, Gemini Pro…) |
| `reasoning_mode` | `reasoning_control` do banco (prevalece) → `resolve_family()` → nome | `always_on` (R1, QwQ, *-thinking, Magistral, o-series), `dial` (Gemini 2.5/3, gpt-oss, GPT-5, Claude 3.7+), `hybrid` (Qwen3, DeepSeek V3.1+/V4, GLM-4.5+, Kimi K2.5+, Nemotron 3), `none` |
| `is_coder` / `is_vision` / `is_chat_capable` | nome + `supports_vision` + provedor Gemini; embed/OCR/TTS/moderation são excluídos | `qwen3-coder`, `devstral`, `kimi-k2.7-code`; `mistral-embed` → não roteável |
| `speed_score` | porte + provedor rápido (Groq/Cerebras/SambaNova) + sufixos (`instant`, `-fast`, `flash-lite`) − thinking forçado | `groq/llama-3.1-8b-instant` ≈ 0.92; `deepseek-r1` ≈ 0.0 |
| `baseline_quality` | tabela por família/geração (≈ 45–95) → fallback por porte | usada **somente** quando não há ranking real (`model_rankings.quality_score > 50`) |

### 3.2 Seleção por adequação (`score_candidate` / `rank_candidates`)
Cada candidato recebe um **fit** para a intenção × complexidade × política:

| Intenção | Fórmula (resumo) |
|---|---|
| `trivial_quick` | `0.25·q + 45·speed + porte(nano +12, small +15, medium +8, large 0, frontier −6)`; `always_on` −25, `dial` −3 |
| `general_chat` (média) | `0.6·q + porte(−18, −6, +4, +10, +10) + 6·speed`; `always_on` −12 |
| `general_chat` (pesada) | `0.65·q + porte(−30, −15, 0, +10, +14)`; raciocínio +5…+8 |
| `deep_reasoning` | `0.6·q + porte(−30, −15, 0, +10, +14)`; `always_on` +16, `dial` +15, `hybrid` +10; frontier +4 se pesada |
| `code_engineering` | `0.6·q + porte(−30, −12, +2, +9, +12)`; especialista em código +14; raciocínio +2…+4 |
| `creative_longform` | `0.6·q + porte(−25, −10, +2, +10, +12)`; `always_on` −10; coder −6 |
| `web_research` | `0.6·q + porte(−20, −8, +2, +8, +10) + 8·speed`; contexto ≥ 64k/128k +5/+7 |
| `multimodal_vision` | filtro duro por visão; `0.65·q + porte(−15, −5, +3, +8, +10)` |

Ajustes transversais: afinidade de família +3; **custo** para modelos não gratuitos
(econômica −35/−30/−20, equilibrada −15/−8/−3, máxima 0 — por complexidade leve/média/pesada);
cota degradada −8; modelos não conversacionais −100. Desempate: qualidade → NexusLocal score → id.

### 3.3 Sticky Routing condicionado à adequação
O modelo anterior só é mantido se continuar adequado: tolerância de **2,5 pts** em código/raciocínio/visão,
**4 pts** nas demais intenções e **8 pts** em follow-ups herdados por *topic momentum*. Mudança de intenção
ou escalada de complexidade ("Oi" → análise financeira) troca de modelo; o sinal `model_switch` é emitido.

### 3.4 Classificador
- `estimate_complexity()` (0–1): tamanho, nº de perguntas, enumerações, pistas analíticas
  (comparar/avaliar/por quê/cenários/riscos/orçamento…), expressões numéricas/matemáticas.
- Perguntas analíticas pesadas **sem** palavras-chave fortes → `deep_reasoning` ("Análise & Raciocínio",
  sinal `complexity_high:<score>`).
- Palavras-chave em inglês para código, raciocínio, redação e saudações.
- Saudações curtas após um turno técnico ("valeu!") **não** herdam o especialista.

### 3.5 Esforço de raciocínio adaptativo (modo Auto)
`recommend_reasoning_effort()`: LIGHT → `low`; MEDIUM → nível configurado em Auto (padrão `medium`);
HEAVY / raciocínio profundo → `high` (ou o nível do usuário, se maior). O valor é aproximado aos níveis
aceitos pelo modelo; modelos sem dial recebem `None` — o parâmetro não é enviado e a UI deixa de receber
`effort_dropped` a cada turno.

### 3.6 Transparência e verificação
- Evento `auto_route_decision` (e `AutoRouteDecisionInfo`) ganhou `complexity`, `fit_score`,
  `reasoning_effort`, `model_tags` e `alternatives` (retrocompatível).
- **`POST /api/dashboard/auto-router/preview`** — simulação sem gastar tokens: intenção, decisão e
  ranking de fit (com *breakdown*) para o catálogo real. Exposto no painel **Roteamento Inteligente →
  "Testar o roteador"**, com opção de simular como continuação da simulação anterior.

## 4. Como validar no ambiente real
1. Configurações → Roteamento Inteligente → **Testar o roteador**.
2. Simular, em sequência, marcando "Simular como continuação":
   `Oi` → modelo pequeno/rápido (Groq/Cerebras 8B ou similar) ·
   `Analise a viabilidade financeira de…` → modelo pensante grande (Gemini 2.5 Pro, DeepSeek R1/V3.2, GLM-5, gpt-oss-120b…) ·
   `e se o aluguel subir 20%?` → mantém o anterior (KV-Cache) ·
   `me indica um filme leve pra hoje?` → volta ao pequeno.
3. Se um modelo específico não estiver bem posicionado, o ranking mostra o *breakdown* (qualidade, porte,
   velocidade, custo) — ajuste `_QUALITY_TABLE`/`_TIER_OVERRIDES` em `model_profile.py` ou alimente
   `model_rankings` (ranking real prevalece sobre a heurística).

## 5. Testes
`backend/tests/test_smart_router_calibration.py` (banco temporário exclusivo, catálogo realista 2026):
perfis por nome, gradiente de qualidade, classificador (complexidade, inglês), seleção pura por intenção,
fluxo de conversa com trocas e KV-Cache, cota esgotada, ranking real > heurística e endpoint de preview.
Os testes anteriores (`test_smart_router.py`, `test_failover_provider_disabled.py`) permanecem verdes.
