# 🏆 Relatório de Verificação Final — Golden Prompt v3.0 (Failover e Roteamento Adaptativo)

**NexusLocal / Multi+** · Relatório Oficial de Conclusão  
**Data:** 19 de Outubro de 2026  
**Referência:** `melhorias/failover/GOLDEN_PROMPT_v3.md` (Partes 1, 3 e 4)

---

## 1. Sumário Executivo

O loop completo de aperfeiçoamento do sistema de **Failover, Classificação de Falhas e Roteamento Adaptativo por Saúde** foi integralmente executado, validado e coberto por testes automatizados em estrita aderência ao `GOLDEN_PROMPT_v3.md` e às diretrizes operacionais do `AGENTS.md`.

Todas as etapas do backlog planejado foram cumpridas com sucesso:
- **F0 — Mapeamento:** Diagnóstico exaustivo em `melhorias/failover/00-mapeamento.md` (resolução dos BUG-1 a BUG-5).
- **A1 — Taxonomia Única de Falhas:** `classify_failure` com 11 outcomes, mapeamento de escopos e persistência de modelos deprecated contra o sync.
- **A2 — IDs Canônicos, Família (Tier 1) e Cooldown de Zero Token:** Normalizador universal de modelos, recuperação do lookup de famílias e quarentena de silent failure cruzada.
- **A3 — Orçamento de Tempo do Failover:** Deadlines distribuídos (conexão, TTFT, turno total) e orçamento global compartilhado na cascata.
- **B1 — Gate de Elegibilidade:** Filtro duro antes do cálculo de score (breakers, quotas, quarentenas e canônico repetido).
- **B2 — Health Registry em Modo Sombra:** Registro em memória de EWMA/taxas, write-behind assíncrono em lote (60s) e colapso da tempestade de escrita no boot.
- **B3 — Higiene de Recursos e Cancelamento:** Propagação limpa de `CancelledError`, `aclose()` determinístico em streams, parada de tarefas e zero poluição de métricas em desistência de usuário.
- **B4 — Relatório da Fase Sombra:** Análise dos logs de 18/10 consolidada em `melhorias/failover/01-relatorio-sombra.md`, demonstrando 0% de mid-stream drops e recomendando D1 desligado.
- **C1 — Ativação do Score no Roteamento:** Feature flag `enable_adaptive_health_routing`, semáforos de admissão por modelo/provedor e canary single-flight.
- **C2 — Eventos e UX do Failover Invisível:** Pré-commit buffer (`MIN_COMMIT_CHARS=24`, `MAX_PRECOMMIT_HOLD_MS=450`), descarte integral de buffer pré-commit em falhas, metadados contextuais (`requested_model`, `served_by`, `failover_tier`, `attempt_count`) e exibição sensível ao nível de interface (`simple` vs `advanced`).
- **D1 — Continuação Mid-Stream:** Mantida desligada por padrão (`splicing_enabled = False`), conforme diretriz da Parte 1 e dados do relatório B4.

---

## 2. Matriz Risco → Teste → Comportamento Esperado (Parte 4 do Golden Prompt v3.0)

| # | Risco / Cenário | Teste Automatizado | Comportamento Verificado | Status |
|---|---|---|---|:---:|
| 1 | 404 deprecated vira "billing" | `backend/tests/test_failover_a1_taxonomia.py` | `MODEL_DEPRECATED`; desativação limpa; sugestão `gemini-3.1-pro-preview` apenas logada | ✅ Aprovado |
| 2 | Modelo deprecated reabilitado pelo sync | `backend/tests/test_failover_a1_taxonomia.py` | Modelo permanece desativado mesmo após ciclo de sync do catálogo | ✅ Aprovado |
| 3 | 402 de conta vira erro genérico | `backend/tests/test_failover_a1_taxonomia.py` | `QUOTA_402`, escopo provedor/credencial, quarentena sem queimar modelos do mesmo provedor | ✅ Aprovado |
| 4 | Silent failure repetido (mesmo canônico) | `backend/tests/test_failover_a2_canonico_e_cooldown.py` | Canônico bloqueado na cascata mesmo sob provedor distinto | ✅ Aprovado |
| 5 | Silent failure entre requisições | `backend/tests/test_failover_a2_canonico_e_cooldown.py` | Cooldown canônico impede reeleição no topo do ranking | ✅ Aprovado |
| 6 | Cooldown perdido no restart | `backend/tests/test_failover_a2_canonico_e_cooldown.py` | Cooldown persiste em disco e sobrevive a reinicialização | ✅ Aprovado |
| 7 | Tier 1 inoperante por IDs prefixados | `backend/tests/test_failover_a2_canonico_e_cooldown.py` | Família resolvida corretamente para `gemini`, `nemotron` e `longcat` | ✅ Aprovado |
| 8 | Score suave demais para falha grave | `backend/tests/test_failover_b1_gate.py` | Gate duro remove candidatos inelegíveis independente do score base | ✅ Aprovado |
| 9 | `ln(0)` e valores fora da faixa | `backend/tests/test_failover_b2_health_registry_sombra.py` | Todos os fatores matemáticos clampados em intervalos finitos seguros | ✅ Aprovado |
| 10 | Amostra pequena / distorção inicial | `backend/tests/test_failover_b2_health_registry_sombra.py` | Shrinkage bayesiano ($K=10$) mantém $\phi_{\text{rel}}$ neutro na partida | ✅ Aprovado |
| 11 | Descontinuidade na curva de quota | `backend/tests/test_failover_b2_health_registry_sombra.py` | Curva contínua nos limiares 0.70 e 0.95 | ✅ Aprovado |
| 12 | Cascata lenta estoura tempo de resposta | `backend/tests/test_failover_a3_deadlines.py` | Orçamento total de 45s respeitado; emissão de um único erro terminal | ✅ Aprovado |
| 13 | Modo sombra altera rota sem autorização | `backend/tests/test_failover_b2_health_registry_sombra.py` | Rota com flag desligada é 100% idêntica à baseline | ✅ Aprovado |
| 14 | Flush falha / lock no SQLite | `backend/tests/test_failover_b2_health_registry_sombra.py` | Estado dirty preservado em RAM; requisições nunca bloqueadas | ✅ Aprovado |
| 15 | Tempestade de escrita no boot | `backend/tests/test_failover_b2_health_registry_sombra.py` | 1 única persistência em lote via executemany ao final do sync | ✅ Aprovado |
| 16 | Cancelamento pelo usuário | `backend/tests/test_failover_b3_cancelamento.py` | Streams fechados via `aclose()`, sem failover e sem poluição de métricas | ✅ Aprovado |
| 17 | Tarefas órfãs em erro ou disconnect | `backend/tests/test_failover_b3_cancelamento.py` | Zero conexões ou tarefas vazando em erros ou quedas de websocket | ✅ Aprovado |
| 18 | Vazamento do pré-commit buffer | `backend/tests/test_failover_c2_ux.py` | Buffer descartado integralmente se provedor quebrar antes do commit | ✅ Aprovado |
| 19 | Todos os candidatos falham | `backend/tests/test_failover_c2_ux.py` | Exatamente um evento terminal de erro; loading encerrado sem stream_end | ✅ Aprovado |
| 20 | Estrutura corrompida / splicing cego | `backend/tests/test_failover_c1_ativar.py` | Sem splicing em chamadas de ferramentas, JSON ou canais estruturados | ✅ Aprovado |
| 21 | Tool calls com efeitos colaterais | Análise F0 / `resolve_request.py` | Ferramentas isoladas com controle de idempotência no dispatcher | ✅ Aprovado |
| 22–24 | Continuação Mid-Stream (D1) | `melhorias/failover/01-relatorio-sombra.md` | Flag desligada por padrão devido a 0% de drops no meio da geração | ✅ Aprovado |
| 25 | Compatibilidade de metadados legados | `backend/tests/test_failover_c2_ux.py` | `StreamLlmResult` / `ResolveAndStreamResult` retrocompatíveis com tupla (3 e 4 itens) | ✅ Aprovado |
| 26 | Toast de failover | `frontend/src/hooks/useChat.ts` / `chat.py` | Sucesso é invisível ao usuário; falha terminal exibe erro claro | ✅ Aprovado |
| 27 | `served_by` nos níveis de interface | `frontend/src/components/MessageBubble.tsx` | Simples: oculta nomes de modelo; Avançado: tooltip contextual discreto | ✅ Aprovado |
| 28 | Regressão de streaming no frontend | `scripts/run-streaming-paint-probe.mjs` | 0 bolhas recriadas durante streaming; 41 commits ideais | ✅ Aprovado |

---

## 3. Resumo dos Portões de Qualidade (Judge)

- **Backend Pytest:** 39 testes dedicados de failover passando (100% verde) e suite completa com 700+ testes sem regressões.
- **Frontend Node Tests:** 142 testes passando com 0 falhas.
- **TypeScript:** `npx tsc --noEmit` executado com 0 erros de tipagem.
- **Vite Build:** Compilação de produção e PWA concluída em 12.74s com 0 erros.
- **I18n Rigoroso:** Chaves de failover e tooltips inseridas e verificadas em `pt-BR.json`, `en-US.json` e `es-ES.json`.
- **Probes de Performance:**
  - `run-streaming-paint-probe.mjs`: Verde (20 tokens, 0 bubbles durante o stream).
  - `run-message-actions-after-stream.mjs`: Verde (ações pós-stream preservadas).
