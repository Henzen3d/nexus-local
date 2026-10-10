# ⚡ Plano de Ação 3: Escala, Desempenho e Busca Híbrida Ilimitada (FTS5 + Vetorial)

> **Foco:** Armazenamento Ilimitado de Longo Prazo, Zero Degradação de Latência no Chat e Busca Híbrida  
> **Localização:** `melhorias/dream-memory/09-plano-escala-desempenho-e-retrieval-infinito.md`  
> **Status:** Pronto para Execução  
> **Dependência:** Plano 1 (`07-plano-blindagem-concorrencia-e-integridade.md`)  

---

## 1. Visão Geral e Justificativa

O usuário estabeleceu uma diretriz arquitetural clara:
> *"não temos limitação de espaço para armazenamento de memórias, a menos que o numero grande demais prejudique o desempenho, lembrando que o processo de memória é no geral algo pago então é uma funcionalidade que tras grande diferencial ao nosso sistema"*.

No SQLite, cada fato de memória ocupa em média apenas 200 a 400 bytes. Mesmo um usuário ultra-ativo com **10.000 memórias** consome menos de **4 MB em disco**. O armazenamento é praticamente gratuito.

No entanto, existem dois gargalos reais que precisam ser eliminados:
1. **Tetos artificiais herdados:** O código antigo descarta memórias ativas ao atingir 200 fatos ([`backend/database.py:1557`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1557)) e limita a consolidação a 500 fatos ([`backend/memory_dream.py:663`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L663)).
2. **Gargalo no Chat Retrieval:** Ao enviar cada mensagem, o sistema lê todos os fatos não-fixados do disco e roda um loop Python puro calculando cosseno um por um. Em bases grandes, isso adiciona latência indesejada. Além disso, a busca puramente vetorial falha em termos técnicos exatos, códigos e nomes próprios.

Este plano remove os tetos artificiais, implementa a **Busca Híbrida (FTS5 BM25 + Vetores)** e otimiza a recuperação com **Decaimento Temporal Calibrado**.

---

## 2. Tarefas e Subtarefas Detalhadas

### 📋 Tarefa 1: Remoção Definitiva de Tetos Artificiais de Armazenamento
**Objetivo:** Permitir crescimento ilimitado de memórias no banco de dados local sem qualquer descarte automático silencioso.

* [ ] **Subtarefa 1.1: Eliminar o cap de 200 fatos em `add_memory_fact`.**
  * Em [`backend/database.py:1553-1567`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1553-L1567), remover o bloco que arquiva a memória mais antiga quando `count >= 200`.
  * Substituir por uma verificação saudável de sanidade (ex: alerta informativo nos logs se ultrapassar 50.000 fatos, mas sem nunca descartar dados do usuário).

* [ ] **Subtarefa 1.2: Suporte a Consolidação em Ondas (Wave Consolidation) para Bases Grandes.**
  * Em [`backend/memory_dream.py:663`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L663) e [`backend/main.py:326`](file:///j:/Arquivos%20Osmar/Multi+/backend/main.py#L326), remover o `limit=500` e `limit=200`.
  * Implementar partição por ondas quando o usuário tiver mais de 500 fatos ativos:
    * Executar o Dream nos clusters semânticos que tiveram novas conversas ou que não são consolidados há mais tempo, iterando em batches sustentáveis até cobrir toda a base ativa.

* [ ] **Subtarefa 1.3: Exposição de Métricas de Armazenamento no Painel.**
  * No endpoint de estatísticas de memória, retornar: total de memórias ativas, memórias consolidadas, total de clusters e tamanho em KB ocupado no banco.

---

### 📋 Tarefa 2: Motor de Busca Híbrida Avançada (FTS5 BM25 + FastEmbed)
**Objetivo:** Combinar precisão cirúrgica de palavras exatas (nomes próprios, portas, siglas, modelos) com similaridade conceitual vetorial.

* [ ] **Subtarefa 2.1: Criação da Tabela Virtual FTS5 no SQLite.**
  * Adicionar tabela virtual de busca textual de alto desempenho em [`backend/database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py):
    ```sql
    CREATE VIRTUAL TABLE IF NOT EXISTS user_memory_fts USING fts5(
        fact_id UNINDEXED,
        user_id UNINDEXED,
        fact_text,
        category,
        tokenize='unicode61 remove_diacritics 1'
    );
    ```
  * Configurar sincronização automática em `add_memory_fact`, edições inline e no consolidador Dream via triggers ou rotinas transacionais.

* [ ] **Subtarefa 2.2: Algoritmo de Ranqueamento Híbrido com Recency Decay.**
  * Em [`backend/database.py:1597`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py#L1597) (`get_relevant_memory`), substituir a lógica atual pela fórmula de fusão híbrida:
    $$Score = (0.50 \times Sim_{\text{vetorial}}) + (0.30 \times Score_{\text{BM25}}) + (0.20 \times e^{-\lambda \cdot \Delta t_{\text{dias}}})$$
  * Onde:
    * Fatos fixados (`is_pinned = 1`) continuam com pontuação prioritária garantida no topo.
    * Termos exatos pontuam alto pelo BM25 do FTS5 mesmo que o modelo vetorial tenha similaridade morna.
    * $\lambda = 0.005$ atenua suavemente memórias muito antigas em favor de afirmações recentes sobre o mesmo tópico.

---

### 📋 Tarefa 3: Otimização de Performance na Busca Vetorial (Escala para 10.000+ Fatos)
**Objetivo:** Garantir que a injeção de contexto no chat execute em menos de 15ms mesmo com milhares de memórias ativas.

* [ ] **Subtarefa 3.1: Vetorização em Batch com NumPy Matricial.**
  * Eliminar o loop individual `for r in unpinned: _cosine_similarity(...)` em Python puro.
  * Se `numpy` estiver disponível:
    * Empilhar os vetores das memórias ativas em uma matriz 2D única ($N \times D$).
    * Calcular todos os produtos escalares em uma única operação $C$-acelerada:
      ```python
      # Multiplicação matricial instantânea em C/BLAS: 10.000 vetores calculados em < 3ms
      sim_scores = np.dot(embeddings_matrix, query_vector)
      ```

* [ ] **Subtarefa 3.2: Cache em Memória dos Embeddings Ativos do Usuário.**
  * Manter em memória do processo FastAPI um array dos embeddings ativos do usuário, invalidado cirurgicamente apenas quando novas memórias são adicionadas ou consolidadas.
  * Evitar leitura de BLOBs do disco a cada mensagem digitada no chat.

---

### 📋 Tarefa 4: Dynamic Context Injector no Chat (Injeção Estruturada no Prompt)
**Objetivo:** Injetar o conjunto ideal de memórias no system prompt de cada conversa sem poluir o contexto nem causar distração no modelo.

* [ ] **Subtarefa 4.1: Orçamento Rígido e Seleção Adaptativa (Top-K Balanceado).**
  * Configurar injeção seletiva de no máximo 20 a 30 fatos mais relevantes por turno de chat, respeitando um teto de 3.000 caracteres.
  * Balanceamento estruturado:
    * Top 5 fatos fixados do usuário (`is_pinned = 1`).
    * Top 10 fatos híbridos específicos relevantes à pergunta atual do usuário.
    * Top 5 preferências globais mais recentes.

* [ ] **Subtarefa 4.2: Seção Formatada e Legível no System Prompt.**
  * Em [`backend/memory.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory.py) (`build_memory_block`), formatar o bloco injetado com cabeçalhos semânticos claros:
    ```markdown
    <user_memory>
    [DIRETRIZES FUNDAMENTAIS DO USUÁRIO]:
    - Responde sempre em Português do Brasil de forma concisa. (Fixado)
    [PREFERÊNCIAS & STACK]:
    - Stack backend: Python com FastAPI e SQLite em modo WAL.
    [CONTEXTO RECENTE]:
    - Ingressou em novo projeto de IA em outubro de 2026.
    </user_memory>
    ```

---

## 3. Critérios de Aceite da Fase de Desempenho e Escala
1. Um usuário com 5.000 memórias cadastradas no banco tem sua recuperação de contexto (`get_relevant_memory`) concluída em menos de 25 milissegundos.
2. Nenhuma memória é arquivada compulsoriamente pelo sistema ao ultrapassar 200 ou 500 fatos.
3. Consultas por códigos específicos (ex: `"servidor vps-01"` ou `"porta 8080"`) retornam o fato exato correspondente através do FTS5 mesmo sem correspondência vetorial perfeita.
