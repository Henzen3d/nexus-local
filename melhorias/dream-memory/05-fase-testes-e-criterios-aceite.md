# 🧪 Fase 5: Testes Automatizados e Critérios de Aceite Mensuráveis

## 1. Objetivo Técnico
Garantir a confiabilidade absoluta, integridade referencial, isolamento entre contas e segurança do sistema de memória através de uma suíte completa de testes automatizados com `pytest` e validações de estresse.

---

## 2. Cenários de Teste Essenciais (Suíte Pytest)

### A. Testes Unitários de Schema, Sincronização e Snapshots
Arquivo: `backend/tests/test_dream_schema.py`
- [ ] `test_schema_migration_idempotent`: Garante que múltiplas inicializações não duplicam colunas nem corrompem índices existentes.
- [ ] `test_status_and_is_active_sync`: Valida que qualquer mudança em `status` reflete instantaneamente em `is_active` (`status='active' ➔ is_active=1`, outros ➔ `0`).
- [ ] `test_create_snapshot_integrity`: Valida que o JSON do snapshot contém hash SHA-256 válido e campos necessários para reconstrução exata.
- [ ] `test_surgical_rollback_preserves_new_user_facts`:
  * Insere fatos e tira snapshot.
  * Executa consolidação criando novos fatos com `source_dream_id`.
  * Insere um novo fato manual criado pelo usuário (`source_dream_id IS NULL`).
  * Executa rollback do snapshot e valida que os fatos antigos voltaram a `active`, os consolidados foram desativados e o **novo fato manual do usuário permaneceu 100% intacto**.

---

### B. Testes do Motor de Consolidação e Regras de Segurança
Arquivo: `backend/tests/test_dream_consolidator.py`
- [ ] `test_deduplication_and_merge`: Fornece 3 fatos similares e valida se são fundidos em 1, com os 3 originais marcados como `merged` e `superseded_by_id` populado.
- [ ] `test_relative_date_conversion`: Fornece fatos com *"começou semana passada"* associados a uma data histórica `2026-05-10` e verifica se o resultado consolida para `2026-05-03`.
- [ ] `test_contradiction_resolution`: Fornece *"Mora em Curitiba"* (recente) e *"Mora em Santos"* (antigo); valida se o mais recente prevalece e o antigo fica `superseded`.
- [ ] `test_pinned_facts_intransigent_protection`:
  * Valida que nenhum fato com `is_pinned = 1` pode sofrer `archive` ou ser descartado.
  * Valida que se um fato fixado sofrer merge, o fato resultante herda `is_pinned = 1`.
- [ ] `test_safety_threshold_abort_on_hallucination`:
  * Simula proposta do LLM descartando > 60% dos fatos ou esvaziando a memória.
  * Valida que o pipeline aborta com `status = 'aborted_safety'` e nenhuma alteração é aplicada ao banco.
- [ ] `test_malformed_llm_json_safety`: Simula retorno truncado ou inválido do LLM com 3 tentativas e valida rollback limpo com status `failed`.

---

### C. Testes de Integração, Concorrência e Isolamento Multi-Usuário
Arquivo: `backend/tests/test_dream_lifecycle.py`
- [ ] `test_cross_user_isolation`: Cria usuário A e usuário B com memórias conflitantes. Valida que a consolidação de A não lê nem afeta nenhuma memória de B.
- [ ] `test_no_sqlite_lock_during_llm_inference`:
  * Inicia consolidação com mock de LLM demorando 3 segundos.
  * Durante a espera do mock, executa escrita concorrente de mensagem no SQLite.
  * Valida que a mensagem é inserida instantaneamente sem travar no bloqueio do banco (transação flash comprovada).
- [ ] `test_project_memory_slug_isolation`:
  * Insere fatos sob `project.portal_react` e `project.bot_python`.
  * Valida que o consolidador isola os domínios e nunca funde fatos de slugs de projeto distintos.
- [ ] `test_dream_idle_coordination_with_lock`: Valida que o job do Dream aguarda a liberação do lock se o `run_memory_idle_extraction_job` estiver em andamento.
- [ ] `test_concurrent_dream_single_execution`: Garante que disparos simultâneos para o mesmo usuário executam apenas uma vez sequencialmente.
- [ ] `test_cache_invalidation_after_dream`: Valida se o fingerprint de memória muda após o sonho, invalidando hits desatualizados no semantic cache.
- [ ] `test_build_context_reflects_consolidated_facts`: Valida que o contexto montado para o system prompt por [`build_context.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/build_context.py) contém apenas os fatos consolidados ativos e exclui fatos desativados.
- [ ] `test_interrupted_dream_startup_recovery`: Simula servidor desligado com `dream_logs.status = 'running'` e valida autorrecuperação automática ao religar.
- [ ] `test_clear_all_memory_purges_snapshots`: Valida que acionar "Esquecer Tudo" remove 100% dos fatos, snapshots e resumos vinculados (privacidade LGPD).

---

### D. Testes de Casos Limítrofes (Edge Cases)
Arquivo: `backend/tests/test_dream_edge_cases.py`
- [ ] `test_zero_facts_dream`: Dream com 0 fatos ativos é no-op elegante sem erro.
- [ ] `test_single_fact_dream`: Dream com apenas 1 fato ativo mantém o fato intacto.
- [ ] `test_all_pinned_facts`: Quando 100% dos fatos são fixados, nenhuma operação destrutiva ocorre.
- [ ] `test_anti_churn_preserves_stable_facts`: Executa 2 ciclos sucessivos sem novos fatos e valida que nenhum fato consolidado teve seu `id` ou `version` alterado por capricho cosmético.
- [ ] `test_temporal_decay_heuristic`: Valida que fatos datados de eventos ocorridos há mais de 90 dias sem fixação sofrem arquivamento ou atenuação de confiança.
- [ ] `test_unicode_and_emojis`: Garante integridade de acentos, caracteres japoneses/árabes e emojis nos fatos consolidados.
- [ ] `test_dry_run_preview_has_zero_side_effects`: Executa o endpoint `/api/memory/dream-preview` e valida que o estado do banco permanece exatamente idêntico antes e depois.

---

## 3. Critérios de Aceite Mensuráveis (KPIs & Definition of Done)


| Métrica / Critério | Alvo Esperado | Como Medir |
| :--- | :--- | :--- |
| **Taxa de Compressão de Ruído** | Redução de 25% a 45% no número de fatos brutos | `(facts_before - facts_after) / facts_before` registrado em `dream_logs`. |
| **Integridade de Linhagem** | 100% dos fatos fundidos/substituídos possuem `superseded_by_id` válido | `SELECT COUNT(*) FROM user_memory WHERE status IN ('merged','superseded') AND superseded_by_id IS NULL` deve ser `0`. |
| **Retenção de Fatos Fixados** | 0 fatos `is_pinned` perdidos ou desfixados | Validação em testes com assert estrito sobre cada id marcado como pinned. |
| **Taxa de Erro do Rollback** | 0 falhas | Teste de estresse com 500 fatos revertidos sem perda de caracteres nem de fatos novos do usuário. |
| **Tempo de Execução (GPU)** | < 45 segundos por usuário (modelo 7B com GPU) | Medição de `duration_ms` em `dream_logs`. |
| **Tempo de Execução (CPU / API)** | < 4 min (CPU local) ou < 15s (Groq/Gemini API) | Medição de `duration_ms` em `dream_logs`. |
| **Invalidação de Cache Semântico** | 100% de novos fingerprints gerados pós-sucesso | Comparação do hash `build_memory_fingerprint` antes e após o ciclo. |

---

## 4. Métricas de Qualidade e Saúde a Longo Prazo (Long-Term Health & Drift)

Para garantir que o motor de consolidação continue saudável ao longo de semanas e meses de uso contínuo:

| Métrica de Longo Prazo | Limiar de Alerta | Ação Automática / Recomendação |
| :--- | :--- | :--- |
| **Taxa de Reversão (Rollback Rate)** | > 20% dos sonhos revertidos pelo usuário | Dispara alerta sugerindo troca de modelo (ex: de 3B para 7B ou API remota) por baixa precisão. |
| **Correção Pós-Sonho (Post-Dream Edit)** | Fato consolidado editado pelo usuário em < 24h | Sinaliza no log que a síntese foi imprecisa, ajustando temperatura para 0.0 na próxima rodada. |
| **Detecção de Degradação (Drift / Over-simplification)** | Comprimento médio dos fatos caindo > 50% continuamente | Alerta de perda de riqueza semântica; impede descarte de detalhes em novos merges. |
| **Taxa de Pinned Intocados** | 100% de integridade | Zero tolerância para perda de fatos fixados. |

---

## 5. Checklist Geral de Entrega da Fase 5

- [ ] Suíte `pytest backend/tests/test_dream_*.py` passando com 100% de sucesso.
- [ ] Nenhuma regressão nos testes existentes de `test_projects.py` ou `test_family_access.py`.
- [ ] Painel de telemetria refletindo tanto KPIs imediatos quanto métricas de longo prazo.
- [ ] Documentação de API atualizada em [`DOCUMENTATION.md`](file:///j:/Arquivos%20Osmar/Multi+/DOCUMENTATION.md).


