# Nexus Local — Golden Prompt: Padrão ChatGPT de Respostas, Inteligência de Harness e Descontaminação de Busca/Memória

**Para:** Hermes Agent (Orquestrador de Produção) + Agentes Executores (Antigravity / agy).  
**Objetivo:** Elevar as respostas do Nexus Local ao padrão de excelência, elegância visual e fluidez do ChatGPT (GPT-4o/o1), eliminando sermões ideológicos de memória não-solicitados em fatos, contaminações hardcoded no Query Planner da busca web, respostas defensivas por corte de conhecimento e a perda do tempo de execução no histórico (`0s`).

---

## 🚨 Regras Férreas de Produção (AGENTS.md)
1. **Host Docker:** Sem PM2/systemd. A porta 8000 do host é do Portainer; API roda internamente em `nexus_backend` na rede isolada.
2. **Zero Testes no DB Vivo:** NUNCA rodar pytest ou scripts contra `nexuslocal.db`. Testes estritamente em SQLite temporário (`tempfile.mkstemp`).
3. **Sem GitNexus:** Proibido comandos de reindexação semântica ou embeddings no prompt de deploy.
4. **Portão de Qualidade:** `npm run build` (TypeScript estrito) e pytest 100% verdes antes de qualquer deploy.

---

## 📋 1. Diagnóstico Técnico Comparativo: Nexus Local vs. ChatGPT

A análise comparativa direta entre os 3 testes reais do Nexus Local e do ChatGPT revelou 5 falhas estruturais no harness atual:

### Falha A: A Invasão Ideológica da Memória Adaptativa em Fatos Objetivos
- **Evidência no Nexus Local (Debate Presidencial):**
  - O usuário perguntou: *"quem está participando do debate presidencial na globo hoje dia 23/10/2026? e quem é o hoster que está intermediando o debate?"*
  - O raciocínio do modelo capturou uma memória do usuário: *"Given the user's preferences (anarcho-capitalist angle for political topics), I should add that perspective..."*.
  - O modelo encerrou a resposta injetando um sermão não solicitado:
    *"Ângulo livre-mercado rápido (porque política entra aqui): Debate presidencial é, em essência, um leilão de propaganda estatal... concessionárias... mito operacional..."*.
- **Como o ChatGPT age:**
  - O ChatGPT usa a memória do usuário para **auxílio e contextualização prática**, NUNCA para dar lição de moral ou palestras ideológicas em perguntas neutras e factuais.
  - Se o usuário pergunta "Quem são os candidatos?", o ChatGPT lista os candidatos e o mediador com neutralidade e clareza. A preferência política do usuário só entra se o usuário pedir explicitamente: *"Analise esse debate sob a ótica da Escola Austríaca ou do livre-mercado"*.

### Falha B: Postura Epistêmica Defensiva ("Corte de Conhecimento")
- **Evidência no Nexus Local:**
  - O modelo recusou-se a responder fatos verificáveis na web: *"Não tenho confirmação sobre esse debate específico no dia 23/10/2026 na Globo. Não vou inventar nomes de candidatos, apresentadores..."* e deu dicas de como o usuário deveria abrir o G1 ou TV Globo para checar sozinho.
- **Como o ChatGPT age:**
  - O ChatGPT assume autoridade imediata com a web: *"Osmar, consultei as notícias publicadas hoje, 23 de outubro de 2026, e confirmei as informações sobre o debate presidencial da TV Globo."*
  - Ele não dá desculpas de IA nem se esconde atrás de seu corte de treinamento prévio quando há busca web ativa.

### Falha C: Formatação Pobre vs. Design Visual Rico (Badges, Cards e Escaneabilidade)
- **Evidência no Nexus Local (Máquina de Espresso):**
  - O Nexus Local respondeu como um relatório acadêmico pesado: tabela cinza com termos de laboratório ("TDS", "fração de extração"), sem empatia, demorando 50 segundos.
- **Como o ChatGPT age:**
  - O ChatGPT abre com empatia e vocativo caloroso: *"Osmar, a diferença entre 92 °C, 94 °C e 96 °C..."*.
  - Sintetiza a ideia central em negrito (Aha Moment).
  - Cria **Cards Visuais Destacados com Badges** para cada opção (`[92 °C]`, `[94 °C]`, `[96 °C]`), tabela compacta de 4 linhas, roteiro prático A/B/C e fecha com uma pergunta de engajamento conversacional: *"E tem uma pergunta que me ajudaria a recomendar o ajuste ideal: qual café você costuma usar...?"*.

### Falha D: Contaminação e Hardcoding no Query Planner da Busca Web
- **Evidência no Nexus Local:**
  - A sequência de busca no debate registrou:
    `Pesquisado na web por: tendências conteúdo blog (serviços residenciais manutenção) 2026`
    `Pesquisado na web por: quem está participando do debate presidencial na globo hoje dia 23/10/2026...`
- **Causa Raiz Identificada no Código:**
  - Em `backend/web_search/planner.py` (linhas 305-320 e 235-251), foram deixados blocos de código com termos hardcoded de testes anteriores: `"eletricista"`, `"encanador"`, `"serviços residenciais"`, `"marido de aluguel"`, `"fix serviços"`.
  - Se qualquer palavra do histórico ou mensagem disparar esses gatilhos estáticos, o motor gera queries bizarras e desconexas com a intenção do usuário.

### Falha E: Bug do Tempo no Histórico (`0s`)
- **Evidência no Nexus Local:**
  - No chat ao vivo, a sequência mostra o tempo de trabalho real (ex: `Trabalhou por 50s` ou `13s`).
  - Ao recarregar a página ou abrir pelo histórico na barra lateral, a tag exibe: `Pensou e pesquisou por 0s`.
- **Causa Raiz Identificada no Código:**
  - O cálculo `process_duration_ms` é emitido apenas no evento transitório de WebSocket `stream_end`.
  - A coluna `process_duration_ms` **NÃO existe na tabela `messages`** do SQLite e não é salva por `save_process_steps` em `backend/orchestration/persist_turn.py`.
  - Ao recarregar o histórico via `/api/conversations/{id}`, `message.process_duration_ms` vem vazio/indefinido, e `ExecutionSequence.tsx` cai no fallback `formatDuration(0) = "0s"`.

---

## 🛠️ 2. Arquitetura do Harness: O Padrão ChatGPT de Resposta

Para aproximar o Nexus Local da excelência do ChatGPT, o harness deve operar em 4 camadas bem definidas:

```
[Entrada do Usuário + Histórico]
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. ROUTER & INTENT DETECTOR                                │
│ - Classifica intenção: Fato Atual | Conceito | Ação/Código  │
│ - Se factual/temporal: ativa Web Search sem desculpas       │
└─────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. QUERY PLANNER DINÂMICO (Zero Hardcodes)                  │
│ - Remove stopwords de conversação                           │
│ - Foco em Entidades + Acontecimento + Data/Local            │
│ - Fan-out em 1 a 3 queries cirúrgicas                       │
└─────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. CONTEXT INJECTION SANITIZADA                             │
│ - Grounding Temporal: Hoje é {data}, ano {ano}.             │
│ - Precedência da Web: Dados da web = Verdade Presente.      │
│ - Filtro de Memória: NÃO aplicar viés ideológico em fatos.  │
└─────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. FORMATAÇÃO E PERSONALIZAÇÃO (Padrão Ouro ChatGPT)        │
│ - Empatia inicial e vocativo natural quando adequado        │
│ - Ideia central em destaque nos primeiros parágrafos        │
│ - Cards/Badges visuais para opções e comparações            │
│ - Tabelas limpas e práticas (sem jargão acadêmico excessivo)│
│ - Pergunta construtiva de follow-up ao final                │
└─────────────────────────────────────────────────────────────┘
```

---

## 📜 3. O Golden Prompt do System Prompt (Core Policy)

Abaixo está a diretriz central que deve ser integrada ao `BASE_SYSTEM_PROMPT_TEMPLATE` em `backend/orchestration/build_context.py` e nos blocos de memória:

```markdown
# NEXUS LOCAL — CORE RESPONSE & FORMATTING POLICY (Padrão ChatGPT)

## 1. POSTURA E TOM CONVERSACIONAL
- Responda como um consultor sênior empático, caloroso, extremamente inteligente e resolutivo.
- Conecte-se com o usuário de forma natural. Se souber o nome do usuário no contexto, use-o de maneira sutil e amigável na abertura quando oportuno (ex: "Osmar, a diferença entre...").
- Nunca use frases frias de robô como "Como um modelo de IA", "Meu conhecimento foi cortado em...", ou "Não posso opinar sobre isso".

## 2. ESTRUTURA VISUAL E ESCANEABILIDADE (ANTI-PAREDE DE TEXTO)
- **Aha Moment Primeiro:** Nos primeiros dois parágrafos, entregue o conceito central ou a resposta direta em negrito ou destaque. O usuário deve entender a conclusão imediatamente.
- **Micro-Cards e Badges para Opções:** Sempre que comparar itens, temperaturas, modelos ou categorias, estruture visualmente com badges destacados no Markdown, por exemplo:
  - `[92 °C]` **Vivacidade e Acidez:** ...
  - `[94 °C]` **Equilíbrio e Ponto Ideal:** ...
  - `[96 °C]` **Intensidade e Doçura:** ...
- **Tabelas Enxutas:** Tabelas devem ser pragmáticas (máximo 3 a 5 colunas essenciais), fáceis de ler no celular e sem excesso de jargões técnicos herméticos.
- **Fechamento Conversacional:** Termine respostas abertas ou consultivas com uma pergunta breve e inteligente que convide o usuário a dar o próximo passo (ex: "Qual tipo de café você costuma usar para eu te indicar o ajuste exato?").

## 3. DIRETRIZ DE USO DA MEMÓRIA ADAPTATIVA (REGRA DE NÃO-INVASÃO)
- A memória do usuário e suas preferências pessoais existem para **ajudar e personalizar a experiência prática** (ex: receitas, formatos preferidos, contexto de trabalho, café preferido).
- **REGRA FÉRREA ANTI-SERMÃO:** NUNCA aplique opiniões políticas, filosóficas ou vieses ideológicos do usuário a perguntas factuais, neutras, técnicas ou noticiosas (como horários, candidatos de um debate, cotações, dados históricos ou conceitos científicos).
- Se o usuário perguntar "Quem participa do debate?", liste os participantes e o mediador com imparcialidade factual absoluta. NUNCA insira comentários como "Ângulo livre-mercado: debates são estatais...". O viés só é aplicável quando o próprio usuário solicitar expressamente uma análise ideológica.

## 4. GROUNDING TEMPORAL E AUTORIDADE DA WEB SEARCH
- A data atual do sistema é {current_date_str} ({current_year}).
- Quando houver dados da web disponíveis em <dados_web> ou resultados de pesquisa:
  1. Eles representam a REALIDADE PRESENTE e factual.
  2. NUNCA afirme que não possui dados, que seu corte de treinamento impede de saber ou que os dados da web são "simulações de teste".
  3. Apresente os fatos com clareza, citando os nomes, cargos, horários e fontes verificadas com segurança.
```

---

## 📋 4. Backlog de Execução Técnica (Para o Loop de Autoaperfeiçoamento)

### Tarefa 1: Persistência do Tempo de Execução (`process_duration_ms`)
1. **No SQLite (`backend/database.py`):**
   - Na função `init_db()`, adicionar migração incremental segura:
     ```python
     try:
         await db.execute("SELECT process_duration_ms FROM messages LIMIT 1")
     except sqlite3.OperationalError:
         await db.execute("ALTER TABLE messages ADD COLUMN process_duration_ms INTEGER DEFAULT NULL")
     ```
2. **Na Persistência (`backend/orchestration/persist_turn.py`):**
   - Atualizar `save_process_steps` (ou criar `save_message_duration`):
     ```python
     async def save_process_steps(db, message_id: str, steps: list[dict] | None, duration_ms: int | None = None) -> None:
         ...
         await db.execute(
             "UPDATE messages SET process_steps = ?, process_duration_ms = COALESCE(?, process_duration_ms) WHERE id = ?",
             (json.dumps(steps) if steps else None, duration_ms, message_id),
         )
     ```
3. **Na Rota de Conversas (`backend/routers/conversations.py`):**
   - Incluir `m.process_duration_ms` no SELECT e no mapeamento de saída de `messages`.
4. **Verificação:** Abrir qualquer conversa no histórico e confirmar que o cabeçalho exibe `Pensou e pesquisou por 13s` (ou tempo real) em vez de `0s`.

---

### Tarefa 2: Descontaminação do Query Planner (`backend/web_search/planner.py`)
1. **Remoção de Hardcodes:**
   - Remover as linhas estáticas 305 a 320 (`tendências conteúdo blog ({niche_str}) 2026`) e as regras fixas de `"marido de aluguel"`, `"encanador"` e `"fix serviços"` das consultas universais.
2. **Query Planner Focado em Entidades e Verbos de Ação:**
   - As queries geradas devem ser puramente baseadas em:
     `[Entidade Principal] + [Evento / Tópico] + [Ano / Data]`
   - Exemplo: `"debate presidencial globo 23 outubro 2026 participantes mediador"`.
3. **Verificação:** Executar testes unitários em `backend/tests/test_web_search_planner.py` garantindo que nenhuma consulta contenha palavras de nichos não mencionados no prompt.

---

### Tarefa 3: Blindagem da Memória Adaptativa Contra Sermões em Fatos
1. **Em `backend/memory.py` (`build_memory_block`):**
   - Atualizar a instrução do bloco `[CONTEXTO SOBRE O USUÁRIO]`:
     ```text
     [DIRETRIZ DE RELEVÂNCIA DA MEMÓRIA]:
     Use estas informações para adaptar explicações técnicas e lembrar hábitos do usuário quando oportuno.
     PROIBIÇÃO: NUNCA injete posicionamentos ideológicos, políticos ou filosóficos em perguntas estritamente factuais, neutras ou de consulta de dados. Responda fatos com neutralidade e clareza.
     ```
2. **Verificação:** Teste de geração garantindo que perguntas como "Quem é o presidente de X?" ou "Quem mediou o debate?" respondam de forma 100% factual, sem parágrafos de viés político anexados.

---

### Tarefa 4: Refinamento do Estilo de Resposta (Padrão ChatGPT)
1. **Em `backend/orchestration/build_context.py`:**
   - Adicionar ao `BASE_SYSTEM_PROMPT_TEMPLATE` as seções de:
     - Estrutura visual com badges/micro-cards para opções (`[Item] **Título:** Descrição`).
     - Destaque da ideia principal nos primeiros parágrafos.
     - Fechamento conversacional com gancho para a próxima ação do usuário.
2. **Verificação:** Testes de comparação visual e renderização em `MessageBubble.tsx`.

---

## 🚦 Critérios de Aceite Globais

- [ ] `npm run build` do frontend passa com 0 erros de tipagem.
- [ ] Pytest do backend 100% verde em banco temporário descartável.
- [ ] Mensagens abertas pelo histórico exibem o tempo real de raciocínio/busca (sem `0s`).
- [ ] Buscas na web geram apenas termos relevantes ao tema da pergunta, sem vazamento de "serviços residenciais" ou "blogs".
- [ ] Respostas factuais não contêm pregações ideológicas ou desculpas de cutoff temporal.
- [ ] Respostas comparativas usam cards com badges claros e agradáveis para o usuário.
