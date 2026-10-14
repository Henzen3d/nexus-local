# 🔬 Fase 1 — Spike do Detector (offline, sem tocar no chat)

**Objetivo:** provar, antes de qualquer integração, que conseguimos detectar "interesse genuíno" com **precisão ≥ 0,85 e falsos positivos ≤ 5 %**, gastando token só quando vale a pena.
**Estimativa:** 4 h · **Dependências:** nenhuma · **Bloqueia:** F2.

> **Status (2026-10-14):** código, dataset, script e testes entregues — ver [`resultados-spike-f1.md`](./resultados-spike-f1.md). Porteiro **GO** (83,3 % / 0 %). Classificador implementado e testado com provedor fake; métricas com modelo real pendentes de execução local (`scripts/proactive_eval.py --llm`).

**Entregáveis**
- `backend/proactive/__init__.py`, `backend/proactive/detector.py`
- `backend/tests/fixtures/proactive_gold.jsonl` (60 mensagens rotuladas)
- `backend/tests/test_proactive_detector.py`
- `scripts/proactive_eval.py` (métricas offline, opcionalmente contra um modelo real)

---

## Tarefa F1.1 — Porteiro léxico (estágio 1, custo zero)

Reprova rapidamente a maioria das mensagens sem chamar modelo. Deve rejeitar ≥ 70 % das negativas do dataset e **nunca** rejeitar mais de 10 % das positivas.

- [x] **F1.1.1** Criar `backend/proactive/detector.py` com `dataclass GateResult(passed: bool, reason: str, emotion_hits: list[str], entity_candidates: list[str])`.
- [x] **F1.1.2** Léxico de emoção/interesse em **pt-BR, en-US e es-ES** (listas por idioma, com variações informais: "tô animado", "muito louco", "não vejo a hora", "adorei", "que demais", "curioso", "preocupado", "nossa", "sério?!", exclamações múltiplas, emojis 🤩😍🔥🎉😱). Detectar idioma por heurística simples (stopwords) ou aceitar os três léxicos de uma vez.
- [x] **F1.1.3** Candidatos a entidade: sequências de palavras capitalizadas fora do início de frase, termos entre aspas, nomes com "&"/"e" entre capitalizadas ("Gabriel e Shirley"), datas/meses próximos a verbos de evento ("vai tocar", "lança", "estreia", "inaugura", "abre"), hashtags.
- [x] **F1.1.4** Regras de rejeição imediata: mensagem < 25 caracteres; é pergunta direta à IA ("qual", "como", "quando" + "?") sem emoção; é pedido explícito de pesquisa ("pesquisa", "procura", "busca pra mim" — isso é a busca web normal, não proatividade); é código/colagem (≥ 40 % de símbolos ou blocos ```); contém apenas emoção sem candidato a entidade; o turno **já usou** web search (`web_search_used=1`).
- [x] **F1.1.5** Função `gate(message: str, *, web_search_used: bool) -> GateResult` pura e síncrona (< 1 ms), sem I/O.
- [x] **F1.1.6** Testes unitários do porteiro cobrindo cada regra (positivo e negativo).

**Arquivos:** `backend/proactive/detector.py`, `backend/tests/test_proactive_detector.py`
**Pronto quando:** cobertura de cada regra; ≥ 70 % das negativas do gold rejeitadas pelo porteiro; ≤ 10 % das positivas rejeitadas.

---

## Tarefa F1.2 — Classificador com modelo utilitário (estágio 2)

- [x] **F1.2.1** `dataclass InterestSignal(interest: float, topic: str, entities: list[str], entity_type: Literal["public_figure","event","product","place","organization","private_person","other"], category: Literal["event","news","product","place","other"], suggested_query: str, time_sensitive: bool, emotion: str, language: str, reason: str)`.
- [x] **F1.2.2** Prompt do classificador (arquivo `backend/proactive/prompts.py`): instruções curtas, exemplos positivos/negativos, exigência de **JSON estrito** com o schema acima, `interest` calibrado (0.9 = "quero muito saber mais", 0.5 = menção neutra, 0.1 = sem interesse). Entrada: mensagem atual + **no máximo as 3 mensagens anteriores** (texto truncado a 600 chars cada) — nunca o histórico inteiro.
- [x] **F1.2.3** Parser tolerante: extrair o primeiro bloco `{...}` da resposta, `json.loads`, validar campos e faixas; qualquer falha ⇒ `interest=0` (fail-closed) e log de debug.
- [x] **F1.2.4** Resolução do modelo: reutilizar `backend/memory.py::_get_extractor_provider_and_model` (ou extrair dele um helper comum `backend/providers/utility_model.py::resolve_utility_model(db, user_id, fallback_provider_id, fallback_model_id)` — refactor pequeno, com teste). Permitir override por `meta.proactive_detector_provider_id/model_id` (admin, F4).
- [x] **F1.2.5** `async def classify(message, context_msgs, *, provider, model_name, timeout=8.0) -> InterestSignal` usando o streaming já existente dos providers (`stream_chat`) com `max_tokens≈300`, `temperature=0`.
- [x] **F1.2.6** Regras pós-classificação: `entity_type == "private_person"` ⇒ descarte (`reason="private_person"`); `interest < threshold` ⇒ descarte; `suggested_query` vazia ⇒ montar a partir de `topic + entities` (≤ 120 chars).
- [x] **F1.2.7** Sensibilidade do usuário ⇒ threshold: `low=0.8`, `medium=0.7`, `high=0.6`.

**Arquivos:** `backend/proactive/detector.py`, `backend/proactive/prompts.py`, (opcional) `backend/providers/utility_model.py`
**Pronto quando:** `classify()` devolve `InterestSignal` válido para 100 % das respostas bem-formadas e `interest=0` para respostas quebradas (teste com provider fake).

---

## Tarefa F1.3 — Dataset gold (60 mensagens)

- [x] **F1.3.1** Criar `backend/tests/fixtures/proactive_gold.jsonl` com campos `{"text", "label" (1/0), "category", "entity_type", "lang", "note"}`.
- [x] **F1.3.2** **30 positivas** distribuídas: 10 eventos/shows, 8 notícias, 6 lançamentos/produtos, 6 lugares/viagens; pelo menos 6 em en-US/es-ES; variações com emoji, gíria regional (SC/BR), erro de digitação.
- [x] **F1.3.3** **30 negativas "armadilha"**: pergunta direta ("quando é o show do X?"), pedido explícito de pesquisa, entidade sem emoção ("reunião com o João às 15h"), emoção sem entidade ("tô muito feliz hoje!"), **pessoa privada** ("minha prima Ana vai casar, tô animada" — positiva em emoção, mas `private_person` ⇒ label 0), conteúdo técnico/código, desabafo sensível (saúde/finanças — nunca pesquisar), mensagem já respondida com web search, sarcasmo ("que animação, mais uma reunião…").
- [ ] **F1.3.4** (pendente) Revisão humana dos rótulos (2 pessoas) — anotar divergências no campo `note`.

**Arquivos:** `backend/tests/fixtures/proactive_gold.jsonl`
**Pronto quando:** 60 linhas válidas (`jsonl` parseável), 30/30, revisadas.

---

## Tarefa F1.4 — Avaliação e calibração

- [x] **F1.4.1** `scripts/proactive_eval.py`: roda porteiro em todo o gold (métricas do estágio 1) e, com flag `--llm`, roda o classificador com um provedor/modelo informado por env (`PROACTIVE_EVAL_PROVIDER/MODEL`) usando o **DB temporário** (nunca o real) e chaves do `.env`.
- [x] **F1.4.2** Métricas: precisão, recall, F1, FP rate, matriz de confusão por categoria e por idioma; latência p50/p95 do classificador; tokens médios.
- [x] **F1.4.3** Varredura de threshold (0.5–0.9) e escolha do default `medium=0.7` (ou ajuste documentado).
- [x] **F1.4.4** Teste `test_proactive_detector.py::test_gold_gate_metrics` (sem LLM) garantindo as metas do porteiro; teste `test_gold_llm_metrics` marcado `@pytest.mark.skipif(not os.getenv("PROACTIVE_EVAL_PROVIDER"))`.
- [~] **F1.4.5** Registrar resultados em `melhorias/assistente-proativo/resultados-spike-f1.md` (modelo usado, métricas, exemplos de erro, decisão go/no-go).

**Arquivos:** `scripts/proactive_eval.py`, `backend/tests/test_proactive_detector.py`, `melhorias/assistente-proativo/resultados-spike-f1.md`
**Pronto quando:** precisão ≥ 0,85, FP ≤ 5 % com pelo menos um modelo gratuito disponível no deploy (ex.: Groq Llama 3.x 8B ou Gemini Flash); decisão go/no-go documentada.

---

## Critérios de aceite da fase
- [x] Porteiro: ≥ 70 % das negativas rejeitadas sem LLM; ≤ 10 % das positivas perdidas. **Medido: 83,3 % / 0 %** (`scripts/proactive_eval.py`).
- [ ] Classificador: precisão ≥ 0,85; FP ≤ 5 %; `private_person` 100 % descartado. **Pendente de execução local** — comandos em [`resultados-spike-f1.md`](./resultados-spike-f1.md) §3.
- [ ] Latência p95 do classificador ≤ 4 s com modelo gratuito. **Pendente (mesma execução).**
- [x] Nenhum teste toca `backend/nexuslocal.db` (conftest já garante; o script de avaliação cria SQLite temporário próprio).
- [~] Decisão **go/no-go** registrada: porteiro **GO**; classificador **GO condicional** às métricas acima ([`resultados-spike-f1.md`](./resultados-spike-f1.md) §4). Se *no-go*: iterar prompt/léxico (máx. 2 iterações) antes de considerar modelo maior.
