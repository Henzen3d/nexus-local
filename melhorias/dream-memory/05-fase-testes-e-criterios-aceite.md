# 🧪 Fase 5: Testes Automatizados e Critérios de Aceite Mensuráveis

## 1. Objetivo Técnico
Garantir a confiabilidade absoluta, integridade referencial e segurança do sistema de memória através de uma suíte completa de testes automatizados com `pytest` e validações de estresse.

---

## 2. Cenários de Teste Essenciais (Suíte Pytest)

### A. Testes Unitários de Schema e Migração
Arquivo: `backend/tests/test_dream_schema.py`
- [ ] `test_schema_migration_idempotent`: Garante que múltiplas inicializações não duplicam colunas nem corrompem índices.
- [ ] `test_create_snapshot_integrity`: Valida que o JSON do snapshot contém todos os campos necessários para reconstrução exata.
- [ ] `test_rollback_accuracy`: Insere fatos, tira snapshot, aplica alterações caóticas, executa rollback e compara igualdade exata dos fatos restaurados.

### B. Testes do Motor de Consolidação
Arquivo: `backend/tests/test_dream_consolidator.py`
- [ ] `test_deduplication_and_merge`: Fornece 3 fatos similares e valida se são fundidos em 1, com os 3 originais marcados como `superseded` e `superseded_by_id` populado.
- [ ] `test_relative_date_conversion`: Fornece fatos com *"começou semana passada"* associados a uma data histórica `2026-05-10` e verifica se o resultado consolida para `2026-05-03`.
- [ ] `test_contradiction_resolution`: Fornece *"Mora em Curitiba"* (recente) e *"Mora em Santos"* (antigo); valida se o mais recente prevalece e o antigo fica `superseded`.
- [ ] `test_malformed_llm_json_safety`: Simula retorno truncado ou inválido do LLM e valida que o banco sofre rollback sem alterar nenhum fato do usuário.

### C. Testes de Integração e Concorrência
Arquivo: `backend/tests/test_dream_lifecycle.py`
- [ ] `test_dream_idle_trigger`: Valida se o job só dispara quando o usuário está ocioso e as regras de 24h/conversas são atendidas.
- [ ] `test_cache_invalidation_after_dream`: Valida se o fingerprint de memória muda após o sonho, invalidando hits desatualizados no semantic cache.

---

## 3. Critérios de Aceite Mensuráveis (KPIs & Definition of Done)

| Métrica / Critério | Alvo Esperado | Como Medir |
| :--- | :--- | :--- |
| **Taxa de Compressão de Ruído** | Redução de 25% a 45% no número de fatos brutos | `(facts_before - facts_after) / facts_before` registrado em `dream_logs`. |
| **Integridade de Linhagem** | 100% dos fatos fundidos/substituídos possuem `superseded_by_id` válido | `SELECT COUNT(*) FROM user_memory WHERE status IN ('merged','superseded') AND superseded_by_id IS NULL` deve ser `0`. |
| **Taxa de Erro do Rollback** | 0 falhas | Teste de estresse com 1.000 fatos revertidos sem perda de caracteres. |
| **Tempo de Execução Noturna** | < 30 segundos por usuário em modelo local de 7B | Medição de `duration_ms` em `dream_logs`. |
| **Retenção de Fatos Críticos** | 0 fatos `is_pinned` alterados sem consentimento | Fatos fixados nunca são desativados sem flag explícita. |

---

## 4. Checklist Geral de Entrega da Fase 5

- [ ] Suíte `pytest backend/tests/test_dream_*.py` passando com 100% de sucesso.
- [ ] Nenhuma regressão nos testes existentes de `test_projects.py` ou `test_family_access.py`.
- [ ] Documentação de API atualizada em [`DOCUMENTATION.md`](file:///j:/Arquivos%20Osmar/Multi+/DOCUMENTATION.md).
