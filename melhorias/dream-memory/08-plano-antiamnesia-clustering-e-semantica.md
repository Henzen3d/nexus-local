# 🧠 Plano de Ação 2: Anti-Amnésia, Clustering Semântico e Preservação de Nuances

> **Foco:** Inteligência Superior, Eliminação de Alucinações, Resolução Real de Conflitos e Fidedignidade  
> **Localização:** `melhorias/dream-memory/08-plano-antiamnesia-clustering-e-semantica.md`  
> **Status:** Pronto para Execução  
> **Dependência:** Plano 1 (`07-plano-blindagem-concorrencia-e-integridade.md`)  

---

## 1. Visão Geral e Justificativa

O maior diferencial de um assistente verdadeiramente inteligente não é apenas armazenar textos, mas **lembrar com a profundidade e a precisão de um ser humano dedicado**. 

Usuários de soluções comerciais como ChatGPT Memory e Claude frequentemente reclamam de três sintomas de "burrice artificial":
1. **Amnésia por fatiamento isolado:** O sistema não percebe que duas frases ditas em meses diferentes se contradizem porque elas caem em lotes separados.
2. **"Summarization Smear" (Achatamento de Nuances):** Ao tentar resumir, a IA descarta quando e por que o usuário prefere algo (ex: destrói regras como *"uso React para o trabalho e Svelte para projetos pessoais"* transformando em *"usa React e Svelte"*).
3. **Destruição de dados biográficos antigos:** Regras cegas de expiração de 90 dias apagam memórias permanentes cruciais (como formação acadêmica, aniversários, alergias ou casamentos).

Este plano implementa o algoritmo de **Clustering Semântico Pré-Consolidação**, a **Matriz de Volatilidade de Memória** e as **Barreiras Determinísticas Anti-Alucinação**.

---

## 2. Tarefas e Subtarefas Detalhadas

### 📋 Tarefa 1: Agrupamento Semântico Pré-Lote (Semantic Clustering)
**Objetivo:** Eliminar o fatiamento sequencial cego. Garantir que fatos sobre o mesmo tema, projeto, ferramenta ou pessoa sejam sempre agrupados no mesmo lote de inferência para que o LLM resolva contradições de forma evidente.

* [ ] **Subtarefa 1.1: Pipeline de Clusterização de Fatos em 2 Níveis.**
  * Substituir o particionamento sequencial de [`backend/memory_dream.py:170`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L170) por um pipeline inteligente de 2 níveis:
    1. **Nível 1 (Escopo Rígido):** Segregar fatos por `Escopo` (`project:<slug>`, `family`, e categorias base: `tech`, `personal`, `preference`, `professional`, `identity`). Fatos de escopos distintos nunca são misturados no mesmo cluster.
    2. **Nível 2 (Similaridade Vetorial no mesmo Escopo):** Para cada categoria, utilizar os embeddings FastEmbed já existentes (`embedding` em `user_memory`) para calcular uma matriz de afinidade semântica.
  * Agrupar itens com similaridade de cosseno $> 0.55$ no mesmo sub-bloco.

* [ ] **Subtarefa 1.2: Empacotador de Lotes com Respeito aos Clusters.**
  * Montar os chunks para a janela de contexto de 6.000 tokens preservando a integridade dos clusters: se um cluster de 15 fatos sobre "Infraestrutura e Docker" cabe no lote, ele é inserido como uma unidade atômica.
  * Se um cluster exceder o orçamento de um chunk isolado, subdividi-lo pelo método de bissecção mantendo os fatos mais próximos vetorialmente juntos.

* [ ] **Subtarefa 1.3: Relatório de Clusters no Modo Preview.**
  * No retorno do `/dream-preview`, exibir quantos clusters semânticos foram formados e quais temas foram analisados em conjunto.

---

### 📋 Tarefa 2: Blindagem Anti-Amnésia Temporal e Proteção de Fatos Biográficos (>90 dias)
**Objetivo:** Evitar que o consolidador arquive dados permanentes de vida sob o pretexto de "evento ocorrido há mais de 90 dias".

* [ ] **Subtarefa 2.1: Taxonomia Estrita de Volatilidade no System Prompt.**
  * Atualizar a Regra 9 do `_DREAM_SYSTEM_PROMPT` em [`backend/memory_dream.py:83`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L83):
    ```markdown
    9. ATENUAÇÃO TEMPORAL VS. FATOS PERMANENTES:
       - PROIBIDO ARQUIVAR FATOS BIOGRÁFICOS OU DURÁVEIS: Informações de formação acadêmica, estado civil, histórico familiar, condições médicas/alergias, traços de identidade, preferências duradouras ou marcos profissionais NUNCA devem ser arquivadas por antiguidade, mesmo que tenham ocorrido há anos.
       - ARQUIVAMENTO RESTRITO A EVENTOS EFÊMEROS E TAREFAS PASSADAS: Apenas arquive fatos que representavam ações passageiras pontuais já superadas (ex: "preciso consertar a torneira", "estou gripado hoje", "viajando no fim de semana"), desde que o evento tenha ocorrido há mais de 30 dias e não tenha impacto futuro.
    ```

* [ ] **Subtarefa 2.2: Ancoragem Temporal Absoluta Baseada em `CriadoEm`.**
  * Instruir o modelo a calcular a data exata da ocorrência usando a data original do registro ([CriadoEm: YYYY-MM-DD]), evitando referências ambíguas:
    * De: `[CriadoEm: 2025-05-10] "comecei na nova empresa semana passada"`
    * Para: `"Ingressou na empresa em maio de 2025."` (e NÃO com base na data de hoje de 2026).

---

### 📋 Tarefa 3: Preservação de Nuances Condicionais (Anti-"Summarization Smear")
**Objetivo:** Garantir que preferências contextuais refinadas do usuário não sejam reduzidas a generalizações genéricas e empobrecidas.

* [ ] **Subtarefa 3.1: Regra de Ouro de Preservação de Condicionais.**
  * Incluir nova regra mandatória no System Prompt:
    ```markdown
    PRESERVAÇÃO DE CONDIÇÕES E CONTEXTO:
    Se o usuário especificou critérios condicionais (ex: "prefere X quando Y", "usa ferramenta A para frontend mas B para scripts rápidos", "gosta de café de manhã mas chá à noite"), o fato consolidado resultante DEVE OBRIGATORIAMENTE manter ambas as condições explícitas.
    É estritamente proibido achatar para um genérico "usa ferramenta A e B" eliminando os critérios de escolha.
    ```

* [ ] **Subtarefa 3.2: Barreira de Retenção de Densidade Informativa.**
  * Em `verify_dream_safety` ([`backend/memory_dream.py:354`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L354)), implementar checagem heurística de densidade de compressão:
    * Se uma operação de `merge` junta 3 ou mais fatos cuja soma de caracteres era $> 300$, e o fato resultante possui menos de $70$ caracteres, emitir alerta de perda de nuance e rejeitar a simplificação excessiva.

---

### 📋 Tarefa 4: Entity Anchoring e Barreira Determinística de Família e Projetos
**Objetivo:** Impossibilitar por código (e não apenas por prompt) que atributos de parentes, dependentes, animais ou projetos vazem para o perfil pessoal do titular.

* [ ] **Subtarefa 4.1: Validação Determinística de Herança de Entidade em `verify_dream_safety`.**
  * Em [`backend/memory_dream.py:329`](file:///j:/Arquivos%20Osmar/Multi+/backend/memory_dream.py#L329), adicionar verificação no loop de validação:
    ```python
    # Se qualquer fato de origem pertencia ao escopo familiar ou projeto
    for sid in op.source_fact_ids or [op.old_fact_id]:
        src_fact = existing_ids.get(sid, {})
        src_key = src_fact.get("fact_key") or ""
        
        # 1. Barreira Familiar
        if src_key.startswith("family.") or src_fact.get("category") == "family":
            if not (op.new_fact.fact_key or "").startswith("family."):
                raise DreamSafetyError(f"Violação de Entidade: Fato familiar {sid} não pode ser fundido em chave não-familiar.")
                
        # 2. Barreira de Projeto
        if src_key.startswith("project."):
            proj_slug = src_key.split(".")[1]
            if not (op.new_fact.fact_key or "").startswith(f"project.{proj_slug}"):
                raise DreamSafetyError(f"Violação de Isolamento: Fato do projeto {proj_slug} não pode vazar para outro escopo.")
    ```

* [ ] **Subtarefa 4.2: Proibição de Fusões Heterogêneas Cross-Entidade.**
  * Rejeitar qualquer operação de `merge` cujos `source_fact_ids` contenham simultaneamente um fato do titular e um fato com prefixo `family.*`.

---

### 📋 Tarefa 5: Prevenção de Alucinação Cascata e Checagem de Fidedignidade
**Objetivo:** Garantir que o LLM não invente fatos, cargos, ferramentas ou detalhes não presentes nos fatos originais.

* [ ] **Subtarefa 5.1: Verificador de Entidades Nomeadas e Substantivos Novos (Token Novelty Guard).**
  * Extrair palavras com letras maiúsculas e termos técnicos dos fatos de origem.
  * Se o novo fato introduzir nomes próprios ou tecnologias não presentes em nenhum dos fatos de origem (ex: adicionar *"Docker"* em um fato que falava apenas de *"Python e FastAPI"*), rejeitar a operação por suspeita de alucinação sintética.

* [ ] **Subtarefa 5.2: Herança Calibrada de Confiança.**
  * Em vez de fixar arbitrariamente `confidence = 0.95` em todos os novos fatos criados, calcular:
    $$\text{confidence}_{\text{novo}} = \min(0.98, \text{média}(\text{conf}_{\text{origens}}) + 0.05)$$
  * Isso assegura que memórias consolidadas a partir de suposições incertas do usuário continuem com grau de confiança honesto e calibrado.

---

## 3. Critérios de Aceite da Fase Semântica
1. Fatos sobre o mesmo assunto distribuídos em diferentes momentos no banco são agrupados no mesmo cluster e resolvidos com sucesso.
2. Nenhuma informação biográfica com mais de 90 dias é arquivada indevidamente durante a consolidação.
3. Teste de regressão comprova que fatos condicionais mantêm suas condições intactas pós-fusão.
4. Qualquer tentativa do LLM de desclassificar um fato de dependente para fato pessoal do titular é bloqueada e registrada no log de segurança (`aborted_safety`).
