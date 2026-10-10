# ⚙️ Fase 2: Motor de Consolidação, Pipeline Analítico e Regras de Segurança

## 1. Objetivo Técnico
Construir o componente central `DreamConsolidator` em [`backend/memory_dream.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py) responsável por:
1. **Pipeline em Duas Passadas:**
   * **Passada 1 (Intra-categoria):** Fusão (*merge*) de micro-fatos fragmentados e desduplicação por domínio.
   * **Passada 2 (Cross-categoria):** Detecção e resolução de contradições globais entre domínios (ex: mudança de carreira impactando stacks de tecnologia).
2. **Ancoragem Temporal Precisa:** Converter referências relativas (*"ontem"*, *"semana que vem"*, *"ano passado"*) em datas absolutas ISO (`YYYY-MM-DD`) ancoradas no `created_at` original de cada fato.
3. **Proteção Rigorosa a Fatos Fixados (`is_pinned`):** Fatos marcados pelo usuário nunca podem ser desativados sem consentimento e herdam status de fixado se fundidos.
4. **Padrão *Supersede* e Rastreabilidade:** Marcar fatos originais como `superseded`, `merged` ou `archived`, populando `superseded_by_id`, `source_dream_id` e mantendo `is_active = 0` sincronizado sem jamais deletar fisicamente.
5. **Barreira Anti-Alucinação (Sanity Pre-Check):** Bloqueio automático de transação caso o modelo proponha descarte anormal de memórias ou produza artefatos inconsistentes.

---

## 2. Prompt do Agente Consolidador (System Prompt)

```markdown
Você é o Dream Consolidator, o agente noturno de consolidação e higiene de memória do NexusLocal.
Sua missão é reorganizar o banco de memórias do usuário, eliminando redundâncias, resolvendo contradições e ancorando o tempo.

DATA DE REFERÊNCIA HOJE: {CURRENT_DATE}

REGRAS DE OURO:
1. PRESERVAÇÃO DA VERDADE: Nunca invente informações novas. Só sintetize ou reorganize com base no que já existe.
2. ANCORAGEM TEMPORAL: Transforme referências temporais flutuantes ("ontem", "no mês passado", "atualmente", "ano que vem") em marcos absolutos baseando-se na data original informada na linha de cada fato (ex: [Origem: 2026-03-10] "comecei no novo emprego semana passada" -> "Iniciou no novo emprego em 2026-03-03").
3. RESOLUÇÃO DE CONTRADIÇÕES: Se o usuário dizia "mora em São Paulo" em janeiro e em outubro disse "mudou-se para Curitiba", a informação mais recente PREVALECE. A informação antiga deve ser marcada como SUPERSEDE.
4. FUSÃO (MERGE): Agrupe múltiplos fatos fragmentados do mesmo assunto em um único fato denso e informativo. Exemplo:
   Fato A: "Usa React no frontend"
   Fato B: "Prefere Tailwind e TypeScript"
   -> Fato Fundido: "Stack frontend: React com TypeScript e Tailwind CSS."
5. FATOS FIXADOS (📌 PINNED) SÃO PROTEGIDOS: Fatos sinalizados com [PINNED: TRUE] são explicitamente prioritários para o usuário. Você NUNCA pode arquivá-los ou marcá-los como supersede isoladamente. Se um fato pinned participar de um MERGE, o novo fato resultante DEVE obrigatoriamente manter "is_pinned": true.
6. DISTINÇÃO TITULAR vs FAMÍLIA/DEPENDENTES: Nunca misture atributos ou preferências de dependentes/cônjuge com os do titular da conta. Mantenha fatos familiares isolados sob categorias ou chaves com prefixo "family.*".
7. ISOLAMENTO DE PROJETOS DISTINTOS: Fatos com categoria "project" ou prefixo "project.<slug>" devem ser mantidos estritamente dentro do seu próprio escopo. NUNCA misture requisitos ou stacks de dois projetos diferentes.
8. ESTABILIDADE & ANTI-CHURN: Se um fato já estiver claro, denso e consolidado e não houver fatos novos ou contradições a seu respeito, MANTENHA-O com ação "keep". É estritamente proibido fazer alterações cosméticas de vocabulário, estilo ou pontuação.
9. ATENUAÇÃO TEMPORAL (TEMPORAL DECAY): Se um fato descreve um evento pontual ancorado em data passada há mais de 90 dias (ex: "preparação para viagem em 2026-01-10") e não for fixado (pinned), marque-o como "archive" se já perdeu a relevância durável, ou reduza sua confiança para 0.70.
10. ARQUIVAMENTO RESTRITO: Só marque ação "archive" para fatos comprovadamente efêmeros ou ruídos sem qualquer valor durável. Sempre forneça a justificativa em "reason".

FORMATO DE RESPOSTA OBRIGATÓRIO (JSON PURO SEM MARKDOWN ADICIONAL):
{
  "summary_of_changes": "Resumo em 1 parágrafo das mudanças realizadas para o log de auditoria.",
  "operations": [
    {
      "action": "merge",
      "source_fact_ids": ["id_1", "id_2"],
      "new_fact": {
        "category": "tech",
        "fact_key": "tech.frontend_stack",
        "fact": "Stack frontend: React com TypeScript e Tailwind CSS",
        "confidence": 0.95,
        "is_pinned": false
      }
    },
    {
      "action": "supersede",
      "old_fact_id": "id_3",
      "new_fact": {
        "category": "personal",
        "fact_key": "location.city",
        "fact": "Reside em Curitiba (mudou-se em 2026-10)",
        "confidence": 0.95,
        "is_pinned": false
      }
    },
    {
      "action": "archive",
      "fact_id": "id_5",
      "reason": "Evento pontual ocorrido há mais de 90 dias sem valor contínuo"
    },
    {
      "action": "keep",
      "fact_id": "id_4"
    }
  ]
}
```

---

## 3. Fluxo de Execução do Motor de Consolidação

```
┌──────────────────────────────────────────────────────────────┐
│ 1. Coleta & Snapshot Flash:                                  │
│    - Seleciona fatos com status='active' e fecha conexão     │
│    - Cria snapshot com hash SHA-256 em memory_snapshots      │
│    - Registra dream_logs com status='running'                │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Pipeline em Duas Passadas (com Isolamento de Projetos):   │
│    Passada 1: Particiona por domínio (tech, personal) e      │
│               subdivide por slug de projeto (project.app1,   │
│               project.app2). Executa merge intra-domínio.    │
│    Passada 2: Submete fatos consolidados para detecção       │
│               de contradições cross-categoria (lote único).  │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Execução LLM com num_ctx Fixado & Escalação:              │
│    - Configuração obrigatória Ollama: num_ctx=8192           │
│      (previne truncamento silencioso de tokens)              │
│    - Tentativa 1: temp=0.05, max_tokens=4096                 │
│    - Tentativa 2: temp=0.15, max_tokens=6144 (se falhar JSON)│
│    - Tentativa 3: temp=0.20, max_tokens=8192 (se truncar)   │
│    - Pipelining de VRAM: descarrega modelo LLM se GPU < 8GB  │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Barreira Anti-Alucinação (Sanity Pre-Check):              │
│    - Rejeita IDs inexistentes ou referências forjadas        │
│    - ABORTA se > 60% dos fatos forem desativados/arquivados  │
│    - Garante que nenhum fato is_pinned foi arquivado/perdido │
│    - Rejeita novos fatos com texto vazio ou < 5 caracteres   │
│    - Se falhar: Rollback, dream_logs status='aborted_safety' │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. Aplicação Cirúrgica (Transação Flash < 100ms):            │
│    - Conexão aberta apenas agora: BEGIN IMMEDIATE            │
│    - Insere novos fatos consolidados (source_dream_id setado)│
│    - Fatos de origem: status='superseded'/'merged'/'archived'│
│      superseded_by_id=novo_id, is_active=0 sincronizado      │
│    - COMMIT imediato e liberação de lock do SQLite           │
│    - FastEmbed: calcula embeddings em lote fora do lock      │
│    - Recalcula resumos rolling (refresh_memory_summaries)    │
│    - Invalida cache semântico via build_memory_fingerprint   │
│    - Atualiza dream_logs com status='success' e métricas     │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 2.1: Modelos Pydantic e Validação Estrutural Estrita
- [x] **2.1.1**: Criar [`backend/memory_dream.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py) com modelos: `NewFactPayload`, `DreamOperation`, `DreamResponseSchema`.
- [x] **2.1.2**: Implementar validação cruzada que rejeita respostas LLM que façam referência a IDs inexistentes no lote submetido.
- [x] **2.1.3**: Adicionar filtro de preservação de fatos fixados: levantar exceção de validação caso um fato `is_pinned = 1` seja alvo de `archive` ou `supersede` sem herança do pin.

### Tarefa 2.2: Sanitização, Formatação e Injeção de Contexto Ollama
- [x] **2.2.1**: Formatador de entrada para o LLM injetando metadados estritos:
  `[ID: {id} | CriadoEm: {created_at} | Pinned: {is_pinned} | Escopo: {scope}] {fact}`
- [x] **2.2.2**: Configurar explicitamente payload HTTP para o Ollama com `"options": {"num_ctx": 8192, "temperature": 0.05}` para impedir cortes silenciosos.
- [x] **2.2.3**: Injetar data de referência `{CURRENT_DATE}` resolvida no timezone do usuário.

### Tarefa 2.3: Pipeline de Duas Passadas, Isolamento de Projetos e Anti-Alucinação
- [x] **2.3.1**: Implementar agrupamento estrito: agrupa por categoria e sub-agrupa por slug de projeto (`project.<slug>.*`). Fatos de projetos distintos nunca entram no mesmo lote de merge.
- [x] **2.3.2**: Implementar `verify_safety_thresholds(facts_before, operations) -> bool`:
  * Aborta e sinaliza `aborted_safety` se taxa de arquivamento/descarte > 60%.
  * Aborta se o saldo total de fatos cair abaixo de 20% do volume original sem justificativa explícita.
- [x] **2.3.3**: Aplicar regra de estabilidade (*anti-churn*): validar que fatos idênticos não sofram supersede por meras variações de pontuação.

### Tarefa 2.4: Transação Flash Desacoplada e Reconciliação
- [x] **2.4.1**: Implementar `apply_dream_operations(db, user_id, dream_id, operations) -> DreamStats`:
  * Executa a escrita exclusivamente após o término da inferência LLM via transação curta `BEGIN IMMEDIATE`.
  * Atualiza simultaneamente `status` e `is_active`.
  * Grava `source_dream_id = dream_id` nos novos registros.
- [x] **2.4.2**: Pipelining de hardware: garantir que o modelo Ollama seja liberado da VRAM antes de engatilhar o batch do FastEmbed se o host tiver GPU de memória compartilhada.
- [x] **2.4.3**: Chamar `refresh_memory_summaries(user_id, use_llm=False)` para regenerar os resumos consolidados.
- [x] **2.4.4**: Calcular novo `build_memory_fingerprint` e atualizar timestamp de invalidação de cache.

---

## 5. Critérios de Aceite (Definition of Done)
* [x] Nenhuma chamada ao Ollama é executada sem o parâmetro explícito `num_ctx: 8192`.
* [x] Fatos de projetos distintos nunca são fundidos entre si.
* [x] Fatos já consolidados não sofrem reescrita cosmética diária sem fatos novos (zero churn desnecessário).
* [x] A transação de escrita no SQLite leva menos de 200ms, sem prender o banco durante a inferência do LLM.
* [x] Zero fatos com `is_pinned = 1` são perdidos, arquivados ou desfixados sem intenção expressa.
* [x] Os resumos rolling e o cache semântico refletem os dados consolidados imediatamente após o término do ciclo.


