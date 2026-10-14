# 🔬 Resultados do Spike F1 — Detector de Interesse

**Data:** 2026-10-14 · **Branch:** `arena/add50947-nexus-local` · **Plano:** [`02-fase-1-spike-detector.md`](./02-fase-1-spike-detector.md)

## 1. O que foi entregue

| Entregável | Caminho | Observações |
|---|---|---|
| Porteiro léxico (estágio 1) | `backend/proactive/detector.py::gate` | puro, síncrono, sem I/O; **≈ 0,3 ms** por mensagem (teste exige < 1 ms) |
| Classificador (estágio 2) | `backend/proactive/detector.py::classify` / `classify_with_meta` | `stream_chat`, `temperature=0`, `max_tokens=300`, timeout 8 s, fail-closed |
| Prompt JSON estrito | `backend/proactive/prompts.py` | schema de `InterestSignal`, calibração 0–1, regras de descarte, 6 exemplos (pt/en/es) |
| Pós-regras | `detector.py::evaluate` + `threshold_for` | `private_person` ⇒ descarte · threshold low/medium/high = 0,8/0,7/0,6 · `category=other` ⇒ descarte · query de fallback ≤ 120 chars |
| Modelo utilitário compartilhado | `backend/providers/utility_model.py::resolve_utility_model` | cascata extraída de `memory._get_extractor_provider_and_model` (que agora delega) + degrau de override `meta.proactive_detector_provider_id/model_id` |
| Dataset gold | `backend/tests/fixtures/proactive_gold.jsonl` | 60 linhas: 30 positivas (10 eventos · 8 notícias · 6 produtos · 6 lugares; 6 en-US + 4 es-ES) e 30 negativas-armadilha; campo `gate_expect` documenta de quem é a responsabilidade (`reject` = porteiro, `llm` = classificador) |
| Avaliação | `backend/proactive/evaluation.py` + `scripts/proactive_eval.py` | métricas do porteiro; `--llm` roda o classificador com **DB temporário** e chaves do `.env`; varredura de threshold 0,50–0,90; relatório Markdown/JSON |
| Testes | `backend/tests/test_proactive_detector.py` | 105 testes (regras do porteiro, entidades, idioma, parser, `classify` com provedor fake, pós-regras, cascata do modelo em DB temporário, validade do gold, métricas) + `test_gold_llm_metrics` (skip sem `PROACTIVE_EVAL_PROVIDER`) |

Nada do chat foi tocado: `_process_turn`, WebSocket e banco de produção seguem iguais. A única alteração fora de arquivos novos é a delegação em `backend/memory.py` (comportamento preservado por teste de regressão).

## 2. Estágio 1 — porteiro léxico (medido)

Saída de `.venv/bin/python scripts/proactive_eval.py` neste commit:

| Métrica | Valor | Meta |
|---|---|---|
| Negativas rejeitadas sem LLM | **25/30 (83,3 %)** | ≥ 70 % ✅ |
| Positivas perdidas | **0/30 (0,0 %)** | ≤ 10 % ✅ |
| Latência média | ≈ 0,3 ms | < 1 ms ✅ |

Motivos de rejeição das negativas: `no_emotion` 5 · `no_entity` 5 · `direct_question` 4 · `explicit_search_request` 3 · `code_or_paste` 3 · `sensitive_topic` 3 · `web_search_used` 2.

| Idioma | Positivas (perdidas) | Negativas (rejeitadas) |
|---|---|---|
| pt-BR | 20 (0) | 16 (14) |
| en-US | 6 (0) | 9 (7) |
| es-ES | 4 (0) | 5 (4) |

As 5 negativas que chegam ao classificador são exatamente as que o porteiro **não tem como** decidir: pessoa privada (g46–g49: "minha prima Ana vai casar…", "my boss Karen…", "mi hermano Luis…") e sarcasmo com produto real (g59: "Oh great, another Windows update…"). Isso é intencional — `private_person` é regra do estágio 2 e do prompt.

### Decisões de projeto registradas durante o spike
- **Três léxicos sempre ativos** (pt/en/es) em vez de escolher pelo idioma detectado: zero custo e evita perder positivas em mensagens misturadas. A detecção de idioma (`detect_language`) vira apenas *hint* para o prompt e dimensão das métricas.
- **Regra extra `sensitive_topic`** no porteiro (não estava no plano): termo de saúde/finanças/luto até 4 palavras **depois** de um marcador de primeira pessoa, na mesma frase. "Minha mãe foi diagnosticada com câncer" é barrado; "Nossa, o Ozzy Osbourne morreu 😭" (notícia pública) passa. Defesa em profundidade além do prompt.
- **Entidades sem maiúsculas:** substantivo de evento + marcador temporal ("vai ter festival … mês que vem") conta como candidato — necessário para mensagens todas em minúsculas, comuns no chat.
- **Início de frase:** token capitalizado no começo só vira entidade se for sigla/camelCase/alfanumérico ou se um verbo de evento vier logo depois ("Coldplay anunciou…"); artigos e pronomes na frente são removidos ("O iPhone 17" → "iPhone 17").
- **`interest` fora de 0–1:** ≥ 10 é lido como porcentagem, 1–10 como escala de 0 a 10; NaN/texto ⇒ `parse_error` (fail-closed).

## 3. Estágio 2 — classificador (pendente de execução local)

A sandbox onde este spike foi desenvolvido **não tem saída de rede para os provedores**, então as métricas do classificador com modelo real não puderam ser medidas aqui. Tudo está pronto para rodar em qualquer máquina com o `.env` do projeto:

```bash
# na raiz do repositório
PROACTIVE_EVAL_PROVIDER=groq PROACTIVE_EVAL_MODEL=llama-3.1-8b-instant \
  .venv/bin/python scripts/proactive_eval.py --llm \
  --markdown-out melhorias/assistente-proativo/resultados-spike-f1-llm.md \
  --json-out /tmp/proactive-f1.json

# segunda opinião com Gemini Flash (grátis)
PROACTIVE_EVAL_PROVIDER=gemini PROACTIVE_EVAL_MODEL=gemini-2.0-flash \
  .venv/bin/python scripts/proactive_eval.py --llm --markdown-out /tmp/f1-gemini.md

# o mesmo critério como teste automatizado
PROACTIVE_EVAL_PROVIDER=groq PROACTIVE_EVAL_MODEL=llama-3.1-8b-instant \
  .venv/bin/python -m pytest backend/tests/test_proactive_detector.py -k gold_llm -q
```

O script cria um SQLite temporário, roda `init_db()` nele só para obter o catálogo de provedores, injeta a chave do `.env` como chave do usuário de avaliação e apaga tudo ao final — **nunca abre `backend/nexuslocal.db`**.

### Metas a conferir no relatório gerado
| Métrica | Meta | Onde olhar |
|---|---|---|
| Precisão (threshold 0,70) | ≥ 0,85 | tabela "Estágio 2" |
| Taxa de falsos positivos | ≤ 5 % (≤ 1 das 30 negativas) | idem |
| Vazamentos `private_person` | 0 | linha "Vazamentos" |
| Latência p95 | ≤ 4 000 ms | idem |
| Threshold default | manter `medium = 0,70` se estiver dentro das metas; caso contrário adotar o "melhor threshold dentro das metas" da varredura e **atualizar `SENSITIVITY_THRESHOLDS`** | tabela "Varredura de threshold" |

Cole a saída Markdown do script na seção 5 deste arquivo.

## 4. Decisão go/no-go

| Componente | Decisão | Justificativa |
|---|---|---|
| Porteiro léxico | **GO** | 83 % das negativas barradas sem custo; 0 % de positivas perdidas; < 1 ms; testes por regra |
| Classificador | **GO condicional** | implementação completa e testada com provedor fake (JSON bom, quebrado, erro, timeout); falta medir precisão/FP com um modelo gratuito real — comandos acima |
| Integração no chat (F2) | **Liberada após** o relatório do classificador cumprir precisão ≥ 0,85 e FP ≤ 5 % | se *no-go*: iterar prompt/léxico (máx. 2 iterações, conforme plano) antes de considerar modelo maior |

Pendências que não dependem de código:
- **F1.3.4** — revisão humana dupla dos 60 rótulos (anotar divergências no campo `note` do JSONL).
- **Seção 5** — colar métricas do classificador.

## 5. Métricas do classificador (preencher após execução local)

_Ainda não executado. Cole aqui a saída de `scripts/proactive_eval.py --llm --markdown-out …` (modelo, precisão, recall, F1, FP, matriz por categoria/idioma, latência p50/p95, tokens, varredura de threshold e exemplos de erro)._
