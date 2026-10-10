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
   * O teto é arbitrário (200 fatos ativos por usuário em [`backend/database.py:1444`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1444)). Ao atingir 200, o sistema desativa o fato com menor confiança e mais antigo (`confidence ASC, updated_at ASC`, ignorando fatos `is_pinned`), o que atenua perdas mas ainda descarta histórico valioso sem sintetizá-lo previamente.
2. **Datas Relativas Não Canônicas:**
   * O extrator captura expressões do usuário como *"comecei o projeto ontem"* ou *"vou viajar mês que vem"*. Sem normalização para datas absolutas (`YYYY-MM-DD`), essas informações envelhecem e tornam-se inconsistentes.
3. **Contradições Não Resolvidas:**
   * Mudanças de ferramentas ou rotina criam fatos conflitantes se as chaves `fact_key` não coincidirem exatamente (ex: `tech.lang_go` e `tech.rust` permanecem ambos ativos).
4. **Sem Histórico de Evolução (*Supersede*):**
   * Hoje o sistema apenas sobrescreve o fato in-place ou desativa com `is_active = 0`. Não há rastro de linhagem explicando *por qual motivo* um fato foi substituído e *qual novo fato* o substituiu.
5. **Dessincronização de Resumos Rolling e Cache Semântico:**
   * Os resumos em `user_memory_summaries` ([`backend/database.py:1163`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1163)) e os fingerprints de cache semântico ([`backend/memory.py:1168`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py#L1168)) precisam de um ponto único e confiável de reconciliação pós-consolidação.
6. **Lacuna na UI:**
   * No painel [`frontend/src/components/UserMemoryPanel.tsx`](file:///j:/Arquivos%20Osmar/Multi+/frontend/src/components/UserMemoryPanel.tsx), não existe edição direta do texto dos fatos existentes.

---

## 2. Decisão Fundamentada

| Critério | Avaliação | Conclusão |
| :--- | :--- | :--- |
| **Já temos algo equivalente ao Dream?** | **Parcial** | Temos background jobs e resumos heurísticos, mas **zero consolidação inteligente**, desduplicação profunda ou resolução de contradições cross-categoria. |
| **Melhoraria os resultados práticos?** | **Sim, substancialmente** | Limpa o contexto injetado no system prompt (economizando tokens no teto de 4.000 caracteres), elimina ambiguidades e mantém a memória fresca e precisa. |
| **Esforço de Implementação** | **Médio** | O motor assíncrono já existe no FastAPI (`asyncio.create_task`), SQLite já suporta transações seguras e o FastEmbed já está instalado. |
| **Custo de Execução** | **Sem Custo de API** | Custo zero em tokens de API com Ollama local (ex: Qwen 2.5 7B ou Llama 3.2 3B) ou cotas gratuitas (Groq/Gemini). Custo computacional local moderado (~4-6 GB VRAM ou processamento em CPU em segundo plano). |
| **Riscos & Mitigações** | **Controlados** | Risco de perda de informação é mitigado pela preservação de linhagem (*supersede* sem hard delete), proteção estrita de fatos fixados (`is_pinned`), limite anti-alucinação e snapshot atômico pré-consolidação com rollback em 1 clique. |

> **Veredito:** **APROVADO.** Vale a pena implementar o **Dream Memory Consolidator** no NexusLocal.

---

## 3. Arquitetura de Referência (Kimi + Claude Code + Mem0)

```
                       ┌─────────────────────────────────────────────────────────┐
                       │          Fluxo do Dream Memory Consolidator             │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                 Gatilho: Cron Noturno (fuso local) OU (24h + 5 novas conversas)
                 + Verificação de Ociosidade (cooperação com idle extraction)
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   1. Snapshot de Segurança & Leitura Inicial            │
                       │      - Serializa estado pré-sonho e grava hash SHA-256  │
                       │      - Retenção circular de até 7 snapshots             │
                       │      - Conexão SQLite fechada (sem lock durante o LLM)  │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   2. Seleção de Modelo & Janela de Contexto             │
                       │      - Detecção de Ollama com num_ctx fixado em 8192    │
                       │      - Pipelining de VRAM (libera modelo pós-inferência)│
                       │      - Failover para Groq / Gemini Free Tier            │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   3. Agrupamento & Análise de Fatos Ativos              │
                       │      - Proteção intransigente a fatos fixados (pinned)  │
                       │      - Isolamento estrito por slug de projeto & família │
                       │      - Passada 1: Fusão intra-categoria (anti-churn)    │
                       │      - Passada 2: Detecção de contradições cross-domain │
                       │      - Ancoragem temporal & decay de eventos passados   │
                       │      - Sanity Check: Aborta se alteração > 60% (ruído)  │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   4. Aplicação Cirúrgica (Transação Flash < 100ms)      │
                       │      - Abre transação BEGIN IMMEDIATE apenas para salvar│
                       │      - Fatos antigos: status='superseded'/'merged'      │
                       │      - Novos fatos: status='active', source_dream_id    │
                       │      - Vetores FastEmbed gerados após inferência        │
                       │      - Atualização de user_memory_summaries & cache fp  │
                       │      - Registro em dream_logs (auditoria e métricas)    │
                       └────────────────────────────┬────────────────────────────┘
                                                    │
                                                    ▼
                       ┌─────────────────────────────────────────────────────────┐
                       │   5. Feedback na UI (UserMemoryPanel)                   │
                       │      - Notificação discreta pós-sonho ("-38% ruído")    │
                       │      - Contadores segregados (ativos vs histórico)      │
                       │      - Rollback seguro em 1 clique (com flag can_roll)  │
                       │      - Edição inline direta & preview (dry-run)         │
                       └─────────────────────────────────────────────────────────┘
```

---

## 4. Ordem e Fases do Projeto

1. **[Fase 1: Esquema de Dados, Linhagem, Compatibilidade e Snapshots](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/01-fase-esquema-e-historico.md)**
   * Colunas `status`, `superseded_by_id`, `source_dream_id`, sincronização `is_active`, criação de `memory_snapshots` com SHA-256/compressão, flag `can_rollback`, suporte a importações externas e expurgo LGPD em `clear_all_memory`.
2. **[Fase 2: Motor de Consolidação, Pipeline em Duas Passadas e Regras de Segurança](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/02-fase-motor-de-consolidacao.md)**
   * Fixação de `num_ctx: 8192`, isolamento por slug de projeto, separação de perfil familiar, regras anti-churn (estabilidade), atenuação temporal (*decay* de eventos passados), prompt analítico e barreira anti-alucinação.
3. **[Fase 3: Orquestração, Timezone, Gatilhos e Modelo Local](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/03-fase-gatilho-e-orquestracao.md)**
   * Transação flash desacoplada da inferência LLM (zero bloqueio de WAL), pipelining de VRAM entre Ollama e FastEmbed, agendamento por fuso local, coordenação via lock com extração ociosa, circuit breaker e modo dry-run.
4. **[Fase 4: Interface de Usuário, Edição Inline, Diário e Auditoria](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/04-fase-interface-e-auditoria-ui.md)**
   * Contadores transparentes (ativos vs arquivados), busca filtrada, desativação graciosa do rollback se snapshot expirou (`can_rollback`), streaming SSE de 5 etapas e modal de simulação/preview.
5. **[Fase 5: Testes Automatizados, Isolamento e Critérios de Aceite](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/05-fase-testes-e-criterios-aceite.md)**
   * Testes de ausência de lock de banco durante LLM, testes de isolamento de projetos e família, proteção anti-churn, atenuação temporal e telemetria de degradação a longo prazo.

---

## 5. Auditoria de Vulnerabilidades 2.0 e Planos de Otimização Avançada

Após a implementação dos commits do Hermes (`37fda98`, `0a35f08`, `4dfd974`, `4fe3e0d`, `30682a6`), uma nova auditoria minuciosa mapeou riscos adicionais e lições da indústria (ChatGPT, Claude, Mem0), resultando nos novos planos de ação:

* 📄 **[06: Auditoria de Falhas, Riscos e Lições do Mercado](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/06-auditoria-falhas-vulnerabilidades-online.md)**
* 🛡️ **[07: Plano de Blindagem de Concorrência, Integridade e SQLite Resiliente](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/07-plano-blindagem-concorrencia-e-integridade.md)**
* 🧠 **[08: Plano Anti-Amnésia, Clustering Semântico e Preservação de Nuances](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/08-plano-antiamnesia-clustering-e-semantica.md)**
* ⚡ **[09: Plano de Escala, Desempenho e Busca Híbrida Ilimitada (FTS5 + Vetorial)](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/09-plano-escala-desempenho-e-retrieval-infinito.md)**
* 🔐 **[10: Plano de Segurança PII/Secrets, Linhagem na UI e Desambiguação Ativa](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/10-plano-seguranca-pii-e-experiencia-ui.md)**
* 🗺️ **[ROADMAP MESTRE DE CONSOLIDAÇÃO E OTIMIZAÇÃO](file:///j:/Arquivos%20Osmar/Multi+/melhorias/dream-memory/ROADMAP-CONSOLIDACAO-MEMORIA.md)**



