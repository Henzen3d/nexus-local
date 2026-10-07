# ⏰ Fase 3: Orquestração, Gatilhos e Seleção de Modelo

## 1. Objetivo Técnico
Configurar o ciclo de disparo do Dream Memory:
1. **Gatilho Híbrido:** Execução noturna (ex: 03:30h da manhã) OU quando a condição *"pelo menos 24 horas desde o último sonho E mais de 5 novas conversas interagidas"* for atingida (padrão Claude Code Auto Dream).
2. **Seleção Inteligente de Modelo:** Priorizar modelo local (Ollama) para privacidade total e custo zero de tokens, com fallback configurável para provedores remotos com cotas gratuitas (Groq, Gemini, OpenRouter).
3. **Gerenciador de Concorrência:** Garantir que o processo não concorra com conversas em andamento ou bloqueie a interface.

---

## 2. Especificação dos Gatilhos

### Condição A: Agendamento Noturno (Cron em Segundo Plano)
* Um loop em segundo plano (`run_dream_nightly_job`) em [`backend/main.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/main.py) acorda a cada 30 minutos e verifica:
  1. A hora local atual está na janela noturna configurada (padrão: entre `03:00` e `05:00`)?
  2. Já se passaram mais de 20 horas desde a última execução de sucesso para este usuário?
  3. Houve novas mensagens/fatos desde o último sonho?

### Condição B: Limite por Atividade (*Session-based Threshold*)
* Inspirado no Claude Code:
  * Se o usuário conversou ativamente e acumulou **≥ 5 novas conversas** ou **≥ 15 novos fatos extraídos** e o último sonho foi há **≥ 24 horas**, o sistema agenda o sonho para o próximo momento de ociosidade (idle).

### Condição C: Disparo Manual pelo Usuário
* Botão *"Executar Consolidação Agora"* no painel de configurações para o usuário testar ou rodar sob demanda.

---

## 3. Waterfall de Seleção de Modelo

Para preservar privacidade e custo:

```
┌────────────────────────────────────────────────────────┐
│ 1. Ollama Local (Detectado em localhost:11434)          │
│    Modelos recomendados: qwen2.5:7b, llama3.2:3b       │
│    (Custo Zero, 100% Privado no Computador)            │
└──────────────────────────┬─────────────────────────────┘
                           │ Fallback se Ollama offline
                           ▼
┌────────────────────────────────────────────────────────┐
│ 2. Provedor Gratuito Remoto (Groq ou Gemini Free Tier) │
│    Modelos: groq/llama-3.3-70b-versatile,              │
│    gemini/gemini-2.0-flash                             │
└──────────────────────────┬─────────────────────────────┘
                           │ Fallback se sem chaves
                           ▼
┌────────────────────────────────────────────────────────┐
│ 3. Modelo do Enhancer / Provedor Padrão Configurado    │
└────────────────────────────────────────────────────────┘
```

---

## 4. Divisão de Tarefas e Subtarefas

### Tarefa 3.1: Configuração do Dream em `meta` e API
- [ ] **3.1.1**: Adicionar chaves de configuração na tabela `meta`:
  * `dream_enabled`: `1` (ativado por padrão)
  * `dream_cron_hour`: `3` (03:00 da manhã)
  * `dream_min_conversations`: `5`
  * `dream_provider_id`: `""` (vazio = auto-detect Ollama primeiro)
  * `dream_model_id`: `""`
- [ ] **3.1.2**: Endpoints em [`backend/routers/memory.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/routers/memory.py):
  * `GET /api/memory/dream-config`
  * `PUT /api/memory/dream-config`
  * `POST /api/memory/dream-run-now` (disparo manual com streaming de progresso)

### Tarefa 3.2: Worker Assíncrono em `backend/main.py`
- [ ] **3.2.1**: Implementar `run_dream_consolidation_job()` como task em `startup()` do FastAPI.
- [ ] **3.2.2**: Adicionar verificação de ociosidade: não iniciar se o usuário estiver ativamente conversando no WebSocket naquele instante.
- [ ] **3.2.3**: Tratar graceful shutdown: se o servidor for desligado durante o sonho, o snapshot assegura integridade total ao reiniciar.

### Tarefa 3.3: Conector de Modelo Local (Ollama)
- [ ] **3.3.1**: Implementar auto-detecção do endpoint do Ollama local (`http://localhost:11434/api/tags`).
- [ ] **3.3.2**: Fallback elegante com log claro se o Ollama não estiver instalado ou rodando.

---

## 5. Critérios de Aceite (Definition of Done)
* [ ] O job noturno roda automaticamente sem exigir intervenção humana.
* [ ] Se o Ollama estiver disponível localmente, o processo executa 100% offline.
* [ ] Se o Ollama não estiver rodando, o sistema realiza failover limpo para a chave gratuita configurada.
* [ ] O disparo manual pela UI executa o mesmo pipeline em menos de 15 segundos para bases médias.
