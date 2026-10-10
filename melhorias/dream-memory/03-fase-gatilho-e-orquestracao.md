# ⏰ Fase 3: Orquestração, Gatilhos, Fuso Horário e Seleção de Modelo

## 1. Objetivo Técnico
Configurar o ciclo de disparo e resiliência do Dream Memory:
1. **Gatilho Ciente de Fuso Horário (*Timezone-Aware*):** Execução noturna na janela de sono do usuário (ex: entre 03:00 e 05:00 no horário local do usuário, e não UTC do servidor).
2. **Coordenação com o Extrator Ocioso:** Prevenir colisão entre `run_memory_idle_extraction_job` (que descobre novos fatos) e o Dream (que consolida fatos), garantindo sequência limpa via `asyncio.Lock`.
3. **Escalonamento Multi-Usuário com Proteção ao SQLite:** Processamento sequencial entre contas para evitar contenção de escrita (*write lock*) no SQLite.
4. **Circuito de Proteção (*Circuit Breaker*):** Pausa automática após 3 falhas consecutivas com notificação defensiva.
5. **Autocura na Inicialização:** Detecção e reversão automática de ciclos interrompidos abruptamente por reinício do servidor.
6. **Modo Simulação (*Dry-Run / Preview*):** Capacidade de simular a consolidação sem persistir alterações.

---

## 2. Especificação dos Gatilhos

### Condição A: Agendamento Noturno Local (Cron em Segundo Plano)
* Um loop em segundo plano (`run_dream_nightly_job`) em [`backend/main.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/main.py) acorda a cada 30 minutos e para cada usuário ativo verifica:
  1. A hora local no fuso horário configurado (`dream_timezone` via `zoneinfo.ZoneInfo`, fallback para timezone do sistema) está entre `03:00` e `05:00`?
  2. Já se passaram mais de 20 horas desde a última execução com status `success` para este usuário?
  3. O usuário possui mais de 10 fatos ativos e acumulou novos fatos/mensagens desde o último sonho?
  4. O usuário não está em estado de *circuit breaker* ativo (falhas consecutivas < 3).

### Condição B: Limite por Atividade (*Session-based Threshold*)
* Inspirado no Claude Code:
  * Se o usuário conversou ativamente e acumulou **≥ 5 novas conversas** ou **≥ 15 novos fatos extraídos** e o último sonho foi há **≥ 24 horas**, o sistema agenda o sonho para o próximo período ocioso verificado.

### Condição C: Verificação Robusta de Ociosidade (*Idle Check*)
O ciclo só inicia se:
* Não houver conexões ativas no WebSocket daquele usuário.
* Nenhuma mensagem tiver sido enviada nos últimos 10 minutos (conferência em `messages.created_at`).
* O extrator ocioso (`run_memory_idle_extraction_job`) NÃO estiver em execução naquele instante.

---

## 3. Coordenação de Concorrência, Transação Flash & Multi-Usuário

```
                       ┌─────────────────────────────────────────────────┐
                       │     Lock Global: _memory_pipeline_lock          │
                       └────────────────────────┬────────────────────────┘
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
  ┌───────────────────────────────┐                             ┌───────────────────────────────┐
  │  Idle Memory Extractor Job    │                             │    Dream Consolidator Job     │
  │  (Executa a cada 15 min)      │                             │    (Janela Noturna / Ociosa)  │
  └──────────────┬────────────────┘                             └──────────────┬────────────────┘
                 │                                                             │
                 │ Adquire Lock                                                │ Aguarda liberação +
                 ▼                                                             │ Cooldown de 5 minutos
  [Extrai fatos de chats ociosos]                                              ▼
                 │ Libera Lock                                  [Itera usuários sequencialmente]
                 └─────────────────────────────────────────────►│ User 1: 
                                                                │  1. Leitura rápida dos fatos (10ms)
                                                                │  2. Fecha conexão SQLite
                                                                │  3. Inferência LLM Ollama (~25s)
                                                                │  4. Pipelining VRAM (unload se GPU <8GB)
                                                                │  5. BEGIN IMMEDIATE (escrita <80ms)
                                                                │  6. Batch FastEmbed (fora de lock)
                                                                │ sleep(2s)
                                                                │ User 2: repete pipeline
```

* **Transação Flash Desacoplada:** É estritamente proibido abrir transação no SQLite antes de chamar o LLM e mantê-la aberta aguardando a resposta. O LLM leva de 15 a 45 segundos para responder. Manter o banco em transação por esse período travaria todas as outras escritas do sistema (mensagens, configurações). O padrão adotado é:
  1. *Fase de Leitura:* Abre conexão, lê fatos ativos, grava snapshot e **fecha a conexão imediatamente**.
  2. *Fase Analítica:* Executa o LLM (Ollama ou API remota) sem nenhuma conexão aberta no banco.
  3. *Fase de Escrita:* Abre conexão, executa `BEGIN IMMEDIATE`, aplica as operações em menos de 80ms e faz `COMMIT`.
* **Pipelining de Recursos de Hardware (GPU VRAM):**
  * Em máquinas locais com placas de 6GB/8GB VRAM (como RTX 3060/4060), carregar o modelo Ollama 7B (~5.5GB VRAM) simultaneamente ao modelo FastEmbed ONNX e possíveis processos de TTS/STT pode disparar CUDA Out of Memory (OOM).
  * O worker noturno garante pipelining sequencial: a inferência do Ollama conclui e o FastEmbed só entra em execução em seguida.
* **Isolamento Hermético de Perfis Familiares:**
  * O consolidador filtra estritamente por titular (`is_owner = 1`). Conversas e memórias de dependentes/perfis infantis nunca são mescladas à memória raiz do usuário titular.

---

## 4. Waterfall de Seleção de Modelo

```
┌────────────────────────────────────────────────────────┐
│ 1. Ollama Local (Detectado em localhost:11434)          │
│    Modelos recomendados: qwen2.5:7b, llama3.2:3b       │
│    (Configurado com options: num_ctx=8192)             │
│    (100% Offline, Privacidade Absoluta, Custo Zero API)│
└──────────────────────────┬─────────────────────────────┘
                           │ Fallback se Ollama offline
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Provedor Gratuito Remoto (Groq ou Gemini Free Tier) │
│    Modelos: groq/llama-3.3-70b-versatile,              │
│    gemini/gemini-2.0-flash, gemini/gemini-2.5-flash    │
└──────────────────────────┬─────────────────────────────┘
                           │ Fallback se sem chaves
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Modelo do Enhancer / Provedor Padrão Configurado    │
└────────────────────────────────────────────────────────┘
```

---

## 5. Divisão de Tarefas e Subtarefas

### Tarefa 3.1: Configurações do Dream na Tabela `meta`
- [ ] **3.1.1**: Adicionar parâmetros persistentes em `meta`:
  * `dream_enabled`: `1`
  * `dream_cron_hour`: `3`
  * `dream_timezone`: `""` (vazio = detecta automaticamente pelo sistema)
  * `dream_min_conversations`: `5`
  * `dream_provider_id`: `""`
  * `dream_model_id`: `""`
- [ ] **3.1.2**: Endpoints em [`backend/routers/memory.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/memory.py):
  * `GET /api/memory/dream-config`
  * `PUT /api/memory/dream-config`
  * `POST /api/memory/dream-preview` — **Modo Dry-Run:** calcula operações de merge/supersede/keep sem aplicá-las no banco.
  * `POST /api/memory/dream-run-now` — Disparo manual com Server-Sent Events (SSE) para streaming de progresso em tempo real.

### Tarefa 3.2: Orquestrador em `backend/main.py` e Startup
- [ ] **3.2.1**: Implementar `run_dream_nightly_job()` com agendamento adaptativo e verificação a cada 30 minutos.
- [ ] **3.2.2**: Criar `_memory_pipeline_lock = asyncio.Lock()` compartilhado entre idle extraction e dream.
- [ ] **3.2.3**: **Recuperação de Interrupção no Startup:**
  * Em `@app.on_event("startup")`, buscar registros em `dream_logs` com `status = 'running'`.
  * Se localizados, executar rollback seguro baseado no `snapshot_id`, registrando `status = 'failed'` e `interrupted_fixed = 1`.
- [ ] **3.2.4**: Aplicar isolamento estrito de perfis familiares: garantir que apenas registros do titular sejam submetidos à consolidação.

### Tarefa 3.3: Mecanismo de Circuit Breaker
- [ ] **3.3.1**: Monitorar histórico recente em `dream_logs`: se as últimas 3 tentativas falharem, desativar temporariamente o agendamento automático para o usuário.
- [ ] **3.3.2**: Emitir aviso no frontend com opção de rearmar o circuito.

### Tarefa 3.4: Auto-Detecção do Ollama e Conector Local
- [ ] **3.4.1**: Provedor local assíncrono com checagem de integridade em `http://localhost:11434/api/tags`.
- [ ] **3.4.2**: Injeção obrigatória de `num_ctx: 8192` nas chamadas ao Ollama para impedir truncamento silencioso.
- [ ] **3.4.3**: Fallback transparente para chaves remotas gratuitas caso o serviço local esteja inacessível.

---

## 6. Critérios de Aceite (Definition of Done)
* [ ] A conexão do SQLite NUNCA é mantida aberta durante a execução do LLM (transação flash garantida).
* [ ] O job noturno dispara com base no horário do fuso local do usuário, nunca apenas UTC puro.
* [ ] Conflito de escrita entre o Dream e o extrator ocioso é nulo devido ao lock coordenado.
* [ ] O desligamento forçado do servidor durante o sonho resulta em autorrecuperação íntegra ao religar.
* [ ] Após 3 falhas seguidas, o sistema entra em circuit breaker e não insiste em loops noturnos com erro.
* [ ] Perfis de dependentes/familiares nunca poluem a memória pessoal do titular.


