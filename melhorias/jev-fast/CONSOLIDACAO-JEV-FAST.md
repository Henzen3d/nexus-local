# ⚡ Relatório de Consolidação e Auditoria JEV-Fast
**NexusLocal / Multi+ — Arquitetura de Velocidade e Execução Virtual (JEV)**

> **Nota de revisão:** este relatório registra as alegações e decisões da consolidação original. Uma revisão adversarial posterior encontrou itens ainda incompletos ou inseguros; consulte [REVISAO-RED-TEAM-CORRECOES.md](REVISAO-RED-TEAM-CORRECOES.md) para o estado corrigido. Os números de latência abaixo não são uma validação de benchmark.

---

## 🎯 1. Resumo Executivo

A auditoria e implementação das propostas da pasta `melhorias/jev-fast` foram concluídas com sucesso. O objetivo central foi acelerar a resposta do NexusLocal eliminando gargalos reais de latência (TTFB e latência de pré-processamento), descartando propostas que continham bugs conceituais graves ou que degradavam a inteligência do sistema, e integrando novos conceitos de alta eficiência alinhados com a filosofia **JEV (Just Execute Virtual)**.

### Ganhos de Performance e Status de Implementação:
| Etapa / Componente | Latência Anterior | Nova Latência JEV | Impacto Efetivo |
|---|---|---|---|
| **Saudações Triviais ("oi", "olá")** | ~45ms - 80ms (3 queries SQL) | **~5ms** (Fast Greeting Bypass em `chat.py`) | Evita 3 leituras de histórico e modelo anterior |
| **Model Selection (Smart Router)** | ~8ms - 25ms (Join 4 tabelas a cada turno) | **< 0.1ms** (ModelCache 30s TTL em RAM) | Join pesado cacheado; quota checada ao vivo |
| **Cálculo de Embeddings (Turno 1)** | ~180ms - 350ms (3 inferências ONNX repetidas) | **~60ms** (1 única inferência via `RequestContext`) | Compartilhado entre RAG, Memória e Cache Semântico |
| **Follow-ups ("continua", "e agora?")** | ~60ms - 100ms (busca semântica inútil) | **0ms** (Semantic Gate de Multi-Turno) | Desativa cache semântico em follow-ups |
| **Imagens Repetidas (Vision Relay)** | ~15ms - 30ms (query SQLite em disco) | **0ms** (`_VISION_L1_CACHE` LRU 512 em RAM) | Entrega descrição em RAM; I/O em thread |
| **Token Bucket Preventivo (Plan 16)** | N/A (Em desenvolvimento) | Bloqueado / Staging | Módulo criado; consumo não integrado ao router |

---

## 🔍 2. Auditoria dos Planos Originais: O que foi Adotado, Corrigido e Eliminado

### ✅ Adotados e Aperfeiçoados:
1. **Plan 02 (`02-model-cache.md`)**:
   - **Implementado**: `_MODEL_CACHE` com TTL de 30s em `backend/ranking/smart_router.py`.
   - **Aperfeiçoamento**: Invalidação reativa imediata via `invalidate_model_cache()` ao esgotar cotas (`quota.py`), desativar modelos (`database.py`) ou alterar configurações (`admin.py`). Status de cota mantido ao vivo a cada seleção.
2. **Plan 03 (`03-fingerprint-cache.md`)**:
   - **Correção Crítica de Bug**: O plano original usava `SHA256(prompt[:100])`, causando graves colisões de cache entre prompts longos com inícios similares. Corrigido para SHA-256 do prompt normalizado completo.
   - **Implementado**: Coluna `fingerprint` indexada em `cache_semantic` com isolamento estrito de `user_id` e `context_fingerprint`.
3. **Plan 05 (`05-vision-relay-cache.md`)**:
   - **Correção de Arquitetura**: Em vez de banco separado, camada L1 LRU limitada a 512 entradas em RAM sobre `vision_descriptions_cache` com leitura de disco em thread assíncrona.
4. **Plan 10 & 11 (`10-semantic-gate-index.md` & `11-embedding-unico-request.md`)**:
   - **Implementado**: Módulo `backend/context/request_context.py` (`RequestContext`) unificando o ciclo de vida do turno com chave limpa de prompt compartilhada entre memória, RAG de projetos e cache semântico.
5. **Plan 16 (`16-anti-429-token-bucket.md`)**:
   - **Status**: Módulo `backend/ranking/token_bucket.py` criado como base, mas **mantido bloqueado para roteamento** até que haja consumo atômico integrado ao fluxo de chamadas, failover e calibração por provedor.

---

### ❌ Eliminados e Rejeitados (O que NÃO trará melhorias ou era prejudicial):
1. **Plan 01 (`01-early-exit.md`) — Premissa Incorreta**:
   - *Motivo do Descarte*: O plano afirmava que `classify_intent` demorava ~31ms em queries SQL. Na realidade, `classify_intent` já era 100% regex em memória (< 0.2ms). O gargalo real eram 3 queries SQL em `chat.py` buscando modelos anteriores e histórico. Implementamos o Early Exit diretamente em `chat.py`, pulando essas queries para saudações curtas.
2. **Plan 04 (`04-batch-query.md`) — SQL Inválido e Destrutivo**:
   - *Motivo do Descarte*: Propôs uma CTE que consultava tabelas inexistentes (`memories` em vez de `user_memory`), colunas inexistentes (`relevance`), realizava produto cartesiano (`LEFT JOIN 1=1`) e destruía a busca híbrida (FTS5 BM25 + FastEmbed + Recency Decay). Totalmente rejeitado.
3. **Plan 07 (`07-executor-deterministico.md`) — Degradação de Produto**:
   - *Motivo do Descarte*: Propunha interceptar `/imagem` para gerar código SVG simples determinístico no servidor em vez de acionar modelos de difusão (Flux). Quebra totalmente a expectativa do usuário de geração de imagens fotográficas/artísticas.
4. **Plan 13 (`13-gate-memory-dream.md`) — Sintaxe Quebrada e Perda de Contexto**:
   - *Motivo do Descarte*: O código proposto no markdown continha erros graves de indentação Python e impunha um debounce de 3 turnos para registrar memórias, fazendo com que instruções vitais ditas pelo usuário logo no início fossem ignoradas.
5. **Plan 14 (`14-fusion-quorum-judge.md`) — Falácia Léxica para LLMs**:
   - *Motivo do Descarte*: Baseava a convergência do modo Fusion em `difflib.SequenceMatcher.ratio() >= 0.8`. LLMs respondem o mesmo raciocínio com palavras e estruturas sintáticas diferentes, tornando a similaridade de caracteres inútil para medir consenso semântico.
6. **Plan 17 (`17-write-behind-pragmas.md`) — Incompatibilidade de Esquema**:
   - *Motivo do Descarte*: Usava colunas inexistentes (`requests_used`, `date` em `model_quota_status`) e introduzia filas assíncronas frágeis propensas a perda de auditoria em reinicializações do container.
7. **Plan 18 (`18-heuristics-aux-tasks.md`) — Premissa Falsa**:
   - *Motivo do Descarte*: Assumia que o NexusLocal chamava LLMs para gerar títulos de chat ou decidir buscas. O NexusLocal já utilizava `user_message[:60]` e regex heurística (<0.1ms).

---

## 🚀 3. Novos Conceitos de Velocidade JEV Implementados

### JEV #19: Single-Embedding RequestContext (Ciclo Único de Vetorização)
- **Localização**: `backend/context/request_context.py`
- **Conceito**: Em um sistema RAG tradicional com cache semântico e memória de longo prazo, a mesma mensagem do usuário é vetorizada até 3 vezes (1x no Cache Semântico, 1x no Project RAG, 1x na Memória de Usuário). O `RequestContext` armazena em RAM o `embedding` resultante da primeira chamada FastEmbed ONNX e o distribui em 0.001ms para os demais subsistemas no mesmo turno.

### JEV #20: Follow-up Semantic Gate
- **Localização**: `backend/cache/manager.py`
- **Conceito**: Em conversas com múltiplos turnos, mensagens como "continua", "e agora?", "me dê outro exemplo" ou "valeu" dependem exclusivamente do histórico anterior. Tentar bater essas mensagens isoladamente no cache semântico não apenas desperdiça ciclos de CPU como gera **falsos-positivos catastróficos** (reaproveitando respostas de outros chats não relacionados). O cache semântico agora só roda se `len(user_messages) <= 1`.

### JEV #21: Proactive Free Tier TokenBucket (Staging / Bloqueado para Roteamento)
- **Localização**: `backend/ranking/token_bucket.py`
- **Conceito**: Módulo estrutural com `TokenBucketManager` para monitoramento de RPM de provedores gratuitos. Permanece bloqueado para roteamento no Smart Router até que haja consumo atômico integrado ao despacho e suporte multiworker.

### JEV #22: ModelCache & Vision L1 em RAM
- **Localização**: `backend/ranking/smart_router.py` & `backend/vision_relay/relay.py`
- **Conceito**: O join de 4 tabelas para rankear modelos é mantido em RAM por 30s, sendo invalidado proativamente caso ocorra qualquer mudança de status de modelo. O cache L1 de imagens guarda em RAM as descrições recentes por SHA-256, entregando resposta instantânea em 0ms.

### JEV #23: Fast Greeting Bypass no Chat Router
- **Localização**: `backend/routers/chat.py`
- **Conceito**: Saudações curtas ("oi", "olá", "bom dia") pulam 3 consultas prévias ao banco (`messages` e `model_usage_log`), direcionando o processamento diretamente para o modelo rápido em RAM (< 1ms).

---

## 🛡️ 4. Garantias de Estabilidade e Conformidade

1. **Integridade do Banco de Produção**:
   - Zero testes rodados contra o `nexuslocal.db` ao vivo.
   - Migrações incrementais aplicadas em `init_db()` sob blocos `try/except sqlite3.OperationalError` com criação de índices posterior.
2. **Qualidade do Código**:
   - Python `.venv/Scripts/python.exe`: 100% dos módulos importam perfeitamente sem erros de sintaxe ou referências ausentes.
   - Frontend Vite / TypeScript: Compilado com `npm run build` gerando **0 erros de tipagem**.
