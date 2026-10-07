# 🌙 Dream Memory: Diagnóstico, Decisão e Visão Geral da Arquitetura

## 1. Diagnóstico do Sistema Atual (Auditoria Técnica)

O **NexusLocal** possui um sistema de memória em camadas implementado em [`backend/memory.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py), [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py) e [`backend/orchestration/build_context.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/orchestration/build_context.py).

### Pontos Fortes Mapeados:
1. **Extração Pós-Turno e em Ociosidade:**
   * Extração assíncrona pós-chat em [`backend/memory.py:660`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py#L660) (`extract_user_memory_background`).
   * Varredura periódica de conversas ociosas há 2h em [`backend/main.py:214`](file:///j:/Arquivos%20Osmar/Multi+/backend/main.py#L214) (`run_memory_idle_extraction_job`).
2. **Busca Semântica Híbrida:**
   * Ranqueamento em [`backend/database.py:1454`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1454) (`get_relevant_memory`) combinando fatos fixados (`is_pinned`), embeddings vetoriais locais (via FastEmbed) e confiança.
3. **Resumos Rolling:**
   * Tabela `user_memory_summaries` ([`backend/database.py:1163`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1163)) gerando resumos globais e por projeto.
4. **Proteção de Cache Semântico:**
   * Cálculo de `fingerprint` em [`backend/memory.py:1168`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py#L1168) que invalida respostas em cache quando memórias são alteradas.

### Gargalos e Dores Estruturais Identificados:
1. **Inchaço e Fragmentação (Sem Consolidação):**
   * O extrator gera múltiplos micro-fatos isolados para o mesmo assunto.
   * O teto é arbitrário (200 fatos ativos por usuário em [`backend/database.py:1414`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1414)). Ao atingir 200, o sistema desativa o fato mais antigo por descarte ingênuo (FIFO), perdendo contexto histórico valioso.
2. **Datas Relativas Não Canônicas:**
   * O extrator captura expressões do usuário como *"comecei o projeto ontem"* ou *"vou viajar mês que vem"*. Sem normalização para datas absolutas (`YYYY-MM-DD`), essas informações envelhecem e tornam-se inconsistentes.
3. **Contradições Não Resolvidas:**
   * Mudanças de ferramentas ou rotina criam fatos conflitantes se as chaves `fact_key` não coincidirem exatamente (ex: `tech.lang_go` e `tech.rust` permanecem ambos ativos).
4. **Sem Histórico de Evolução (*Supersede*):**
   * Hoje o sistema apenas sobrescreve o fato in-place ou desativa com `is_active = 0`. Não há rastro de linhagem explicando *por qual motivo* um fato foi substituído e *qual novo fato* o substituiu.
5. **Lacuna na UI:**
   * No painel [`frontend/src/components/UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx), não existe edição direta do texto dos fatos existentes.

---

## 2. Decisão Fundamentada

| Critério | Avaliação | Conclusão |
| :--- | :--- | :--- |
| **Já temos algo equivalente ao Dream?** | **Parcial** | Temos background jobs e resumos heurísticos, mas **zero consolidação inteligente**, desduplicação profunda ou resolução de contradições. |
| **Melhoraria os resultados práticos?** | **Sim, substancialmente** | Limpa o contexto injetado no system prompt (economizando tokens no teto de 4.000 caracteres), elimina ambiguidades e mantém a memória fresca e precisa. |
| **Esforço de Implementação** | **Médio** | O motor assíncrono já existe no FastAPI (`asyncio.create_task`), SQLite já suporta transações seguras e o FastEmbed já está instalado. |
| **Custo de Execução** | **Custo Zero** | Pode rodar 100% local com Ollama (ex: Llama 3.2 3B ou Qwen 2.5 7B) durante a madrugada ou com modelos gratuitos da Groq/Gemini. |
| **Riscos & Mitigações** | **Controlados** | Risco de perda de informação é mitigado pela preservação de linhagem (*supersede* sem hard delete) e snapshot atômico pré-consolidação com rollback em 1 clique. |

> **Veredito:** **APROVADO.** Vale a pena implementar o **Dream Memory Consolidator** no NexusLocal.

---

## 3. Arquitetura de Referência (Kimi + Claude Code + Mem0)

```
                       ┌─────────────────────────────────────────────────────────┐
                       │          Fluxo do Dream Memory Consolidator             │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                 Gatilho: Cron Noturno (ex: 03:30h) OU (24h + 5 novas conversas)
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   1. Snapshot de Segurança (backup atômico SQLite)      │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   2. Seleção de Modelo (Ollama Local -> Fallback API)   │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   3. Agrupamento & Análise de Fatos Ativos              │
                       │      - Detecção de contradições                         │
                       │      - Conversão de datas relativas para absolutas      │
                       │      - Fusão (Merge) de micro-fatos fragmentados        │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   4. Aplicação no SQLite (Transação Atômica)            │
                       │      - Fatos antigos: status='superseded'               │
                       │      - Ponteiro: superseded_by_id = novo_fato_id        │
                       │      - Novos fatos consolidados: status='active'        │
                       │      - Registro em dream_logs (auditoria e métricas)    │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   5. Feedback na UI (UserMemoryPanel)                   │
                       │      - Linha do tempo de sonhos                         │
                       │      - Botão de Rollback instantâneo em 1 clique        │
                       └─────────────────────────────────────────────────────────┘
```

---

## 4. Ordem e Fases do Projeto

1. **[Fase 1: Esquema de Dados, Linhagem e Snapshots](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/01-fase-esquema-e-historico.md)**
   * Alterações nas tabelas `user_memory`, criação de `memory_snapshots` e `dream_logs`.
2. **[Fase 2: Motor de Consolidação e Prompt Analítico](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/02-fase-motor-de-consolidacao.md)**
   * Pipeline de merge, supersede, normalização de datas e prompt de consolidação.
3. **[Fase 3: Orquestração, Gatilhos e Modelo Local](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/03-fase-gatilho-e-orquestracao.md)**
   * Agendamento noturno inteligente, integração com Ollama (local) e fallback.
4. **[Fase 4: Interface de Usuário, Edição Inline e Auditoria](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/04-fase-interface-e-auditoria-ui.md)**
   * Edição inline na UI, visualizador do histórico do sonho e botão de restauração/rollback.
5. **[Fase 5: Testes Automatizados e Critérios de Aceite](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/05-fase-testes-e-criterios-aceite.md)**
   * Cobertura de testes unitários/integração, validação de integridade e métricas.
