# 🛡️ Diretrizes e Regras Operacionais para Agentes de IA (AGENTS.md)
**Multi+ / NexusLocal**

Este arquivo é a base de conhecimento de regras de comportamento e restrições operacionais para agentes de IA (Antigravity, Gemini, Claude, Hermes Agent e outros colaboradores automatizados).

---

## 🚨 1. Regras Férreas de Produção e Host (Hermes Agent)

### A. Banco de Dados ao Vivo (`nexuslocal.db`)
1. **Estado Real de Produção:** O banco ativo em produção (`nexuslocal.db`) contém dados vitais: ~1633 modelos cadastrados, logs de auditoria de uso, quotas, configurações de provedores e conversas de usuários.
2. **Integridade Obrigatória:** Antes de qualquer alteração de esquema ou deploy crítico, a integridade deve ser atestada via:
   ```sql
   PRAGMA integrity_check;
   ```
3. **ISOLAMENTO TOTAL DE TESTES:**
   * **NUNCA execute `pytest`, testes unitários ou scripts de teste contra o `nexuslocal.db` ao vivo.**
   * Todas as execuções de teste devem ocorrer obrigatoriamente em uma **cópia temporária**, banco em memória (`:memory:`) ou arquivo temporário descartável (`tempfile.mkstemp(suffix='.db')`).
   * Testes rodando no banco vivo causam corrupção de dados, locks de escrita no WAL (`aiosqlite`) e perda de histórico de usuários.

### B. Ausência de Índice GitNexus no Host
1. **Host sem GitNexus:** Este servidor/host de execução **NÃO possui** índice GitNexus e **NÃO realiza** indexação semântica de código para o Hermes Agent.
2. **Proibido nos Prompts de Deploy:** **JAMAIS** inclua instruções como "reindexar o código no GitNexus" ou "gerar embeddings do repositório" nos prompts ou scripts destinados ao Hermes Agent ou ao deploy em produção.

### C. Infraestrutura do Host & Fluxo Padrão de Deploy (Hermes Agent)
1. **Ambiente Baseado em Docker:** O host roda estritamente sob **Docker / Docker Compose** (`docker-compose.yml`). **NÃO utiliza PM2 nem systemd** para gerenciar o NexusLocal.
2. **Aviso de Portas (Porta 8000 é do Portainer):** A porta `8000` no host pertence ao painel web do **Portainer**! O backend do FastAPI roda dentro da rede Docker isolada (`nexus_net`), escutando internamente na porta 8000 do container `nexus_backend`, com o frontend Nginx e o túnel Cloudflare (`cloudflared`) servindo o tráfego. Nunca tente acessar `http://localhost:8000` no host esperando a API do NexusLocal.
3. **Pipeline Oficial de Deploy no Host:**
   1. **Backup & Integridade Primeiro:** Antes de qualquer `git pull`, validar e criar snapshot:
      ```bash
      sqlite3 backend/nexuslocal.db "PRAGMA integrity_check;"
      cp backend/nexuslocal.db "backend/nexuslocal_backup_$(date +%Y%m%d_%H%M%S).db"
      ```
   2. **Git Pull:** `git pull origin main`.
   3. **Rebuild dos Containers:** Reconstruir os containers sem cache para compilar o novo frontend e backend:
      ```bash
      docker compose build --no-cache backend frontend
      ```
   4. **Restart dos Serviços:** Subir os containers recriados mantendo o volume do banco:
      ```bash
      docker compose up -d --force-recreate backend frontend
      ```
   5. **Limpeza de Imagens:** `docker image prune -f`.
   6. **Health Check & Logs:**
      ```bash
      docker compose ps
      docker exec nexus_backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
      docker compose logs --tail=40 backend
      ```

---

## 🛠️ 2. Padrões de Desenvolvimento no Repositório

### A. Python / Backend
* **Ambiente Virtual:** Sempre utilizar o Python do `.venv` (`.venv/Scripts/python.exe` no Windows ou `.venv/bin/python` no Linux).
* **Migrações Incrementais:** Novas tabelas e colunas devem ser adicionadas em blocos `try/except sqlite3.OperationalError` dentro de `init_db()` em `backend/database.py`, garantindo retrocompatibilidade total com bancos existentes de produção.
* **Índices SQLite:** Nunca criar índices diretamente no `SCHEMA` de inicialização para colunas criadas incrementalmente via `ALTER TABLE`. Índices devem ser criados após o bloco de migração das colunas.

### B. Frontend
* **Vanilla CSS First:** Utilizar o sistema de design tokens (`var(--primary)`, `var(--surface-soft)`, `var(--hairline)`, `var(--ink)`) e arquivos CSS puros. Não adicionar Tailwind CSS sem solicitação explícita.
* **Radical Aesthetics:** Manter estilo glassmórfico refinado, tooltips contextuais, animações suaves e contraste impecável tanto no tema claro quanto no escuro.
* **I18n Rigoroso:** Todas as novas strings devem possuir correspondentes em `pt-BR.json`, `en-US.json` e `es-ES.json`.
* **TypeScript Estrito:** A compilação `npm run build` deve sempre passar com 0 erros de tipagem antes de qualquer commit.

## 🧭 3. Módulo "Assistente Proativo" (`backend/proactive/`, `frontend/src/components/Proactive*.tsx`)

Pesquisa espontânea opt-in: detecta interesse na mensagem do usuário, pesquisa na web e entrega um resumo curto com fontes **sem interromper** a conversa. Plano, contratos e critérios de aceite vivem em `melhorias/assistente-proativo/` (índice no `README.md` da pasta; guia da família em `docs/guia-assistente-proativo.md`).

* **Invariantes (não quebrar):** opt-in por usuário (`proactive_user_settings.enabled`, padrão 0); nunca pesquisa `private_person`; insights só do dono (IDOR ⇒ 404); entrega só após o fim do turno (`service.TurnGuard`/`wait_turn_end`); nunca entrega expirado; máx. `max_pending` pendentes; URLs privadas/locais nunca são buscadas nem listadas (`web_search.reader.is_safe_public_url` + `researcher.is_public_looking_url`); texto sintetizado ≤ `synthesizer.MAX_TEXT_CHARS`.
* **Config:** `proactive.config.load_config()` — `meta` (`proactive_*`, painel admin) > env `PROACTIVE_*` > padrão. Kill-switch = `enabled_global`; rollout do convite = `onboarding_enabled`.
* **Tarefas assíncronas:** nunca `asyncio.create_task` solto — use `service.track_task(...)` (cancelamento no kill-switch, contagem em `pending_tasks()` e no admin-stats). Boot: `main.recover_interrupted_proactive()` marca `detected|researching` órfãos como `failed:restart`.
* **Logs:** `service.log_stage(...)` — sempre `insight_id`, `stage`, `latency_ms`; **jamais** o texto do usuário nem o texto sintetizado (vale também para `GET /api/proactive/logs`, que só expõe `LOG_COLUMNS`).
* **Testes:** `backend/tests/test_proactive_*.py` com os fakes compartilhados de `backend/tests/fakes/proactive.py` (`FakeProvider`, `FakeSearch`, `FakeReader`, `FakeSocket`). Rodar da raiz: `.venv/bin/python -m pytest backend/tests -q` (o `conftest.py` já aponta `DB_PATH` para um SQLite temporário).
* **Frontend:** strings novas em `proactive.*` nos 8 locales; `npm run check:i18n` compara as chaves de `pt-BR` com os demais (`check:i18n:all` cobre o app inteiro). Mensagens `kind: 'proactive'` não alimentam o auto-TTS.

