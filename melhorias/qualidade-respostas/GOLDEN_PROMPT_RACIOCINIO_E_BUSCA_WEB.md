# NexusLocal — Golden Prompt: Raciocínio Completo, Contexto Conversacional na Busca Web e Auto-Trigger

**Para:** Hermes Agent (orquestrador de produção) + Agentes Executores (Antigravity / Agy).  
**Objetivo:** Eliminar o problema de respostas vazias após raciocínios longos (estouro de tokens dentro do pensamento), garantir resolução anafórica no Query Planner da busca web (evitando buscas literais genéricas de comandos como "pegue o telefone deles") e auto-ativar a pesquisa web em perguntas comerciais/locais ou ordens explícitas em linguagem natural.

---

## 🚨 Regras Férreas do Projeto (AGENTS.md)

1. **Ambiente Docker no Host:** Servidor roda sob Docker Compose (`docker compose`). Porta 8000 no host pertence ao Portainer; a API do NexusLocal roda na rede interna `nexus_net`.
2. **Zero Testes no Banco Vivo:** NUNCA executar `pytest`, migrações soltas ou scripts contra o `backend/nexuslocal.db` em produção. Testes rodam estritamente em SQLite temporário descartável (`tempfile.mkstemp`).
3. **Sem GitNexus:** Proibido incluir instruções de "reindexação no GitNexus" ou embeddings semânticos no prompt de deploy.
4. **Portão de Qualidade:** `npm run build` (TypeScript estrito) e pytest 100% verdes antes de qualquer commit ou deploy.

---

## 📋 Diagnóstico Técnico dos 3 Incidentes Observados

### 1. Raciocínio Longo sem Resposta (Bolha Fantasma / "Trabalhou por 1m 53s")
- **Evidência:** O modelo (Hunyuan 4 Preview Free) pensou por 1m 53s. Ao final, o bloco de pensamento truncou no meio da palavra (`"...teste (principalmente em elétrica/h"`). Nenhuma resposta foi renderizada no chat, mesmo após *hard refresh*.
- **Causa Raiz:**
  - Modelos de raciocínio (DeepSeek R1, Hunyuan 4, Qwen Thinking) consomem o limite de saída (`max_tokens`) somando tokens de pensamento (`<think>`) + tokens de resposta final.
  - O backend passa `max_tokens: 4096` como padrão. Quando o modelo raciocina exaustivamente, ele atinge o teto de 4096 tokens **dentro do bloco `<think>`**, antes de emitir a tag de fechamento `</think>` e antes de gerar o primeiro caractere da resposta.
  - O stream é interrompido pelo provedor com `finish_reason: "length"`.
  - O parser de frontend (`ThinkingParser.ts`) recebe um bloco sem fechamento e classifica 100% do conteúdo acumulado como `reasoning`, deixando `answer: ""`.
  - O componente `MessageBubble.tsx` não renderiza nada no corpo da resposta se `answer` for vazio, resultando em uma bolha "fantasma" que contém apenas o accordion de raciocínio truncado.

### 2. Query Planner sem Contexto do Histórico (Busca Web Genérica)
- **Evidência:** Ao solicitar *"pode ir até a web e pegar o telefone deles"*, o sistema buscou no Google literalmente a frase `"pode ir até a web e pegar o telefone deles"`. O Deep Reader leu artigos genéricos de VoIP (`tecnobits.com`, `blacktel.io`) e respondeu com tutoriais de ligação gratuita em vez do telefone da **Fix Serviços de Blumenau**.
- **Causa Raiz:**
  - O `execute_agentic_search` em `backend/web_search/agent.py` recebe apenas a `user_message` do turno corrente (`"pode ir até a web e pegar o telefone deles"`), **sem acesso ao histórico de mensagens da conversa**.
  - O `plan_search_queries` em `backend/web_search/planner.py` não realiza resolução anafórica para pronomes e referências contextuais (*"deles"*, *"dela"*, *"dessa empresa"*, *"desse serviço"*).
  - O filtro de stopwords não remove ordens conversacionais como *"pode ir até a web e pegar o"*.
  - A pontuação de relevância em `score_search_result` procurava termos de conteúdo no próprio prompt do usuário. Como a palavra *"Fix"* ou *"Blumenau"* só estava no turno anterior, os resultados sobre VoIP receberam pontuação suficiente para serem lidos pelo Deep Reader.

### 3. Falha no Auto-Trigger de Busca Web para Consultas Comerciais/Locais
- **Evidência:** Perguntas como *"como posso contratar a fix serviços de blumenau sc?"* e *"pode acessar a web e pegar o telefone deles"* não dispararam a busca web automaticamente.
- **Causa Raiz:**
  - As heurísticas em `backend/web_search/heuristics.py` focam quase que exclusivamente em atualidades temporais (*"eleições"*, *"presidente"*, *"cotação"*, *"notícias de 2026"*).
  - Não há padrões heurísticos para dados comerciais/locais: *"telefone"*, *"whatsapp"*, *"contato"*, *"endereço"*, *"como contratar"*, *"site oficial"*, *"horário de atendimento"*.
  - Ordens imperativas explícitas (*"acesse a web"*, *"busque na internet"*, *"pesquise no google"*, *"veja no site deles"*) não ativam o gatilho sem o botão manual de pesquisa ativado no frontend.

---

## 🛠️ Backlog de Execução (Fases R1 a R4)

### R1 — Proteção contra Esgotamento de Tokens no Raciocínio (Anti-Truncamento)
**Objetivo:** Evitar que modelos de raciocínio estourem o limite dentro de `<think>` e garantir tratamento elegante se o teto de tokens for atingido.

1. **Aumento Dinâmico de `max_tokens` para Modelos de Raciocínio:**
   - Em `backend/orchestration/resolve_request.py` e `backend/providers/base.py`:
     - Detectar se o modelo possui capacidade de raciocínio (presença de `reasoning_effort`, família `deepseek-r1`, `tencent/hy4`, `qwen-max`, etc.).
     - Elevar o `max_tokens` padrão para **8192** (ou 16384 quando suportado pelo provedor) para modelos de raciocínio, evitando que o pensamento consuma a cota da resposta.
2. **Salvaguarda de Truncamento no Backend (`finish_reason == "length"`):**
   - Se o modelo finalizar com `finish_reason: "length"` (ou parar) enquanto ainda estiver em `in_thinking == True`:
     - Fechar defensivamente a tag `</think>\n\n`.
     - Se nenhum token de resposta final foi gerado fora do `<think>`, acionar failover para o próximo modelo com instrução de esforço mais sucinto, OU anexar aviso transparente:
       *"[Aviso: O modelo esgotou seu limite de geração durante a etapa de raciocínio. Tente reduzir o esforço de raciocínio ou reformular a pergunta.]"*.
3. **Resgate de Resposta no Frontend (`ThinkingParser.ts` e `MessageBubble.tsx`):**
   - Se `answer` resultar vazio após o término do stream, mas houver conteúdo em `reasoning`:
     - Exibir um card/alerta de sistema na bolha: *"O raciocínio foi concluído, mas o modelo não gerou a resposta final devido ao limite de tokens."* com botão de retry de 1 clique com menor esforço de raciocínio.
- **Critério de Aceite:** Turnos com modelos de raciocínio nunca deixam a tela em branco / sem resposta após a finalização do pensamento.

---

### R2 — Resolução de Contexto Conversacional no Query Planner da Busca Web
**Objetivo:** Garantir que buscas disparadas por frases como *"pegue o telefone deles"* utilizem a entidade correta mencionada em turnos anteriores.

1. **Injeção de Histórico no `execute_agentic_search`:**
   - Em `backend/routers/chat.py` (`_resolve_web_search`):
     - Passar as últimas 2 a 3 mensagens da conversa (`history[-3:]`) para o `execute_agentic_search`.
2. **Resolução de Entidades e Pronomes Anafóricos (`backend/web_search/planner.py`):**
   - Criar extrator de contexto anafórico:
     - Identificar pronomes/referências: *"deles"*, *"dela"*, *"dele"*, *"dessa empresa"*, *"desse local"*, *"do site"*.
     - Se o prompt atual contiver referências anafóricas e não especificar a entidade, extrair entidades nomeadas (empresas, marcas, cidades, pessoas) das últimas mensagens do usuário ou assistente.
     - Exemplo: Turno anterior: *"como contratar a Fix Serviços de Blumenau"* + Turno atual: *"pegue o telefone deles"* $\rightarrow$ Query gerada: `"Fix Serviços de Blumenau telefone WhatsApp contato"`.
3. **Limpeza Agressiva de Comandos de Ação:**
   - Expandir `FILLER_WORDS` em `planner.py` para remover prefixos de ordem à IA:
     - `pode ir até a web e pegar`, `acesse a web e veja`, `procure na internet`, `pesquise no site`, `entre no google e busque`.
- **Critério de Aceite:** O teste unitário deve validar que `"pode ir até a web e pegar o telefone deles"` com histórico anterior sobre `"Fix Serviços Blumenau"` gera queries com `"Fix Serviços Blumenau telefone"`.

---

### R3 — Auto-Trigger para Consultas Comerciais, Locais e Ordens Explícitas
**Objetivo:** Disparar a busca web automaticamente quando o usuário solicita informações factuais de contato ou quando ordena verbalmente o acesso à web.

1. **Novos Padrões em `backend/web_search/heuristics.py`:**
   - Adicionar padrões de consulta comercial e dados de contato:
     - `\b(telefone|whatsapp|contato|email|endere[cç]o|site oficial|site deles)\b`
     - `\bcomo (contratar|comprar|falar com|agendar)\b`
     - `\b(hor[aá]rio de atendimento|localiza[cç][aã]o|onde fica|fica em)\b`
   - Adicionar padrões de ordem explícita de busca em linguagem natural:
     - `\b(acesse|acessar|consulte|consultar|veja|olhe|busque|pesquise|v[aá] at[eé])\s+(a|na|no)?\s*(web|internet|google|online|site)\b`
2. **Classificação no Smart Router (`backend/ranking/smart_router.py`):**
   - Mapear essas intenções diretamente para `IntentKey.WEB_RESEARCH`, garantindo que o Auto-Router ative a flag `web_search` mesmo se o toggle manual estiver desligado.
- **Critério de Aceite:** Perguntas como *"como posso contratar a fix serviços de blumenau sc?"* e *"pode ir até a web e pegar o telefone"* disparam `web_search_used = True` de forma autônoma.

---

### R4 — Filtro de Relevância Rígido e Prevenção de Fontes Genéricas
**Objetivo:** Impedir que o Deep Reader perca tempo raspando tutoriais irrelevantes de VoIP quando a busca é sobre uma empresa específica.

1. **Validação de Entidade Obrigatória (`score_search_result` em `agent.py`):**
   - Se a busca envolver uma entidade ou empresa identificada (ex: *"Fix Serviços"*, *"Facilita Vistorias"*), o score de resultados que não mencionam nem o nome da entidade nem a cidade deve ser forçado a `0.0`.
   - Ignorar domínios genéricos de tutoriais (`tecnobits.com`, `melhorplano.net`, `falemaisvoip.com.br`) quando a intenção for busca de dados de uma empresa específica.
2. **Mensagem Honesta e Construtiva em Falta de Fontes:**
   - Se o mecanismo de busca não encontrar resultados indexados da empresa, instruir o modelo a responder com clareza:
     *"Não foram encontrados telefones públicos indexados para a Fix Serviços em Blumenau nos resultados da busca web. Se você tiver o contato ou o site oficial, pode informá-lo aqui."*
- **Critério de Aceite:** O sistema nunca mais cita tutoriais de ligação VoIP para perguntas sobre telefones de empresas locais.

---

## 🚦 Critérios de Aceite e Verificação Final

1. **Frontend:**
   - `npm run build` passa com 0 erros de tipagem.
   - `npm test` passa 100% dos testes unitários e de UI.
   - Respostas truncadas no pensamento exibem alerta claro e opção de retry, sem deixar espaço em branco.
2. **Backend:**
   - Testes unitários com fakes de histórico garantem resolução anafórica no Query Planner.
   - Heurísticas cobrem termos de contato comercial e ordens explícitas de busca.
   - Testes pytest executados estritamente em SQLite temporário.
3. **Validação Funcional End-to-End:**
   - Pergunta: *"como posso contratar a fix serviços de blumenau sc?"* aciona busca automaticamente.
   - Mensagem seguinte: *"pode ir até a web e pegar o telefone deles"* busca por `"Fix Serviços Blumenau telefone"`, sem trazer tutoriais de VoIP.
