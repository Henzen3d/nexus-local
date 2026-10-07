# ⚙️ Fase 2: Motor de Consolidação e Prompt Analítico

## 1. Objetivo Técnico
Construir o componente central `DreamConsolidator` em [`backend/memory_dream.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py) responsável por:
1. Agrupar memórias por domínio/categoria e semelhança semântica.
2. Identificar e resolver contradições (ex: stacks antigas vs stacks atuais).
3. Converter datas e referências relativas (*"ontem"*, *"semana que vem"*, *"ano passado"*) em datas absolutas ISO (`YYYY-MM-DD`) com base na data de criação do fato original.
4. Fundir (merge) múltiplos micro-fatos fragmentados em registros densos, concisos e atômicos.
5. Aplicar o padrão *Supersede*: marcar os fatos originais com `status = 'superseded'` ou `'merged'`, gravando o `superseded_by_id` sem nunca deletar dados do banco.

---

## 2. Prompt do Agente Consolidador (System Prompt)

```markdown
Você é o Dream Consolidator, o agente noturno de consolidação e higiene de memória do NexusLocal.
Sua missão é reorganizar o banco de memórias do usuário, eliminando redundâncias, resolvendo contradições e ancorando o tempo.

DATA DE REFERÊNCIA HOJE: {CURRENT_DATE}

REGRAS DE OURO:
1. PRESERVAÇÃO DA VERDADE: Nunca invente informações novas. Só sintetize ou descarte com base no que já existe.
2. ANCORAGEM TEMPORAL: Transforme referências flutuantes ("ontem", "no mês passado", "atualmente", "ano que vem") em marcos absolutos com base na data original de cada fato informada na lista (ex: [Origem: 2026-03-10] "comecei no novo emprego semana passada" -> "Iniciou no novo emprego em 2026-03-03").
3. RESOLUÇÃO DE CONTRADIÇÕES: Se o usuário dizia "mora em São Paulo" em janeiro e em outubro disse "mudou-se para Curitiba", a informação mais recente PREVALECE. A informação antiga deve ser marcada para SUPERSEDE.
4. FUSÃO (MERGE): Agrupe múltiplos fatos fragmentados do mesmo tópico em um único fato coeso e rico. Exemplo:
   Fato A: "Usa React no frontend"
   Fato B: "Prefere Tailwind e TypeScript"
   -> Fato Fundido: "Stack frontend: React com TypeScript e Tailwind CSS."
5. DISTINÇÃO TITULAR vs FAMÍLIA: Nunca misture atributos de dependentes/cônjuge com os do titular da conta.

FORMATO DE RESPOSTA OBRIGATÓRIO (JSON PURO):
{
  "summary_of_changes": "Resumo em 1 parágrafo das mudanças realizadas para o log.",
  "operations": [
    {
      "action": "merge",
      "source_fact_ids": ["id_1", "id_2"],
      "new_fact": {
        "category": "tech",
        "fact_key": "tech.frontend_stack",
        "fact": "Stack frontend: React com TypeScript e Tailwind CSS",
        "confidence": 0.95
      }
    },
    {
      "action": "supersede",
      "old_fact_id": "id_3",
      "new_fact": {
        "category": "personal",
        "fact_key": "location.city",
        "fact": "Reside em Curitiba (mudou-se em 2026-10)",
        "confidence": 0.95
      }
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
│ 1. Coleta: Seleciona todos os fatos com status='active'      │
│    (incluindo id, category, fact_key, fact, created_at)      │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 2. Chunking & Agrupamento:                                   │
│    Se houver > 60 fatos, agrupa por categoria (tech,         │
│    professional, personal, family, project, preference)     │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. Execução LLM (Ollama / Fallback):                         │
│    Envia fatos com data original de cada linha               │
│    Temperatura baixa (0.05 ou 0.1) para evitar alucinação   │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. Validação Estrutural:                                     │
│    Valida JSON de resposta contra schema Pydantic            │
│    Garante que nenhum source_fact_id inexistente foi citado  │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. Aplicação no Banco (Transação Atômica):                   │
│    - Insere novos fatos consolidados com versionamento       │
│    - Atualiza fatos antigos com status='superseded'/'merged' │
│      e superseded_by_id apontando para o novo id             │
│    - Gera embeddings para os novos fatos consolidados        │
│    - Atualiza os resumos rolling (user_memory_summaries)     │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 2.1: Estruturas de Dados e Schemas Pydantic
- [ ] **2.1.1**: Criar [`backend/memory_dream.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py) com modelos Pydantic: `DreamOperation`, `NewFactPayload`, `DreamResponseSchema`.
- [ ] **2.1.2**: Implementar validação estrita que rejeita respostas LLM com IDs forjados ou referências cruzadas inválidas.

### Tarefa 2.2: Lógica de Normalização de Datas
- [ ] **2.2.1**: Injetar o carimbo `created_at` original de cada fato na string enviada ao LLM: `[ID: abc123 | Data: 2026-04-12] Fato: ...`.
- [ ] **2.2.2**: Adicionar instruções expressas de conversão temporal no prompt.

### Tarefa 2.3: Transação de Aplicação no SQLite
- [ ] **2.3.1**: Implementar `apply_dream_operations(db, user_id, operations) -> DreamStats`:
  * Para `merge`: insere novo fato, marca fatos de origem como `merged`, grava `superseded_by_id`.
  * Para `supersede`: insere novo fato, marca fato anterior como `superseded`, grava `superseded_by_id`.
  * Para `keep`: mantém fato inalterado.
- [ ] **2.3.2**: Gerar novos vetores FastEmbed para os novos fatos criados.
- [ ] **2.3.3**: Recalcular resumos rolling globais e por projeto após o término.

---

## 5. Critérios de Aceite (Definition of Done)
* [ ] Fatos antigos nunca são excluídos fisicamente do banco de dados (preservação histórica garantida).
* [ ] Nenhuma contradição flagrante permanece entre dois fatos ativos após o ciclo do sonho.
* [ ] Se o LLM falhar no parse ou gerar JSON inválido, a transação sofre rollback e os fatos permanecem intactos.
