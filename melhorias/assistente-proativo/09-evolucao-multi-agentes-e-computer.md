# 🤖 09 — Evolução Multi-Agentes, Computer Sandbox & Rotinas Autônomas (F8)
**Multi+ / NexusLocal — Assistente Proativo v2**

> **Referência Arquitetural:** Inspirado na engenharia reversa do projeto open-source **[Rakazo](https://github.com/elie222/rakazo)** (`elie222/rakazo`), adaptado cirurgicamente aos padrões de produção, segurança e banco SQLite WAL (`nexuslocal.db`) do NexusLocal.

---

## 🎯 1. Visão Geral e Objetivo do Upgrade

O **Assistente Proativo v1 (Fases 1 a 7)** cumpriu com maestria sua missão fundacional: detectar empolgação/interesse no chat comum, pesquisar em segundo plano e entregar resumos sem interromper o usuário.

Entretanto, para transformar o NexusLocal em uma plataforma de ponta de **Agentes de Equipe Autônomos (AI Teammates)**, identificamos três gargalos do modelo v1:
1. **Limitação de Leitura HTTP Estática:** Sites modernos (Sympla, Eventim, Amazon, portais protegidos por Cloudflare ou SPAs React/Vue) bloqueiam requisições HTTP simples, retornando telas vazias ou captchas.
2. **Proatividade Apenas Reativa:** O assistente atual só age se o usuário falar algo no chat. Não há capacidade de monitoramento temporal contínuo (*cron/rotinas*).
3. **Agente Monolítico vs. Especialistas:** Um único assistente tenta resolver todos os assuntos, sem persona, memória segmentada ou ferramentas dedicadas.

### A Solução v2 (Fase 8)
Incorporar os quatro maiores pilares do Rakazo dentro do ecossistema do NexusLocal:
1. **O "Nexus Computer" (Sandbox & Browser Real):** Um container leve com Chromium/Playwright e executor de código, permitindo que o bot navegue como humano, tire screenshots de páginas dinâmicas e processe dados.
2. **Equipe de Bots Especialistas:** Em vez de uma IA genérica, uma banca de especialistas com avatares orgânicos vivos (*Kawaii Tech* com microexpressões `idle` vs `working`).
3. **Motor de Rotinas & Monitoramento Agendado (Cron):** Bots que executam tarefas programadas (ex: checar ingressos de hora em hora ou gerar resumo matinal às 06:00).
4. **Interface Tridimensional (3 Colunas):** Layout de alta densidade estética composto por:
   - **Coluna Esquerda:** Roster de bots com preview assíncrono.
   - **Coluna Central:** Linha do tempo com cartões de ação do computador e checklists estruturados.
   - **Coluna Direita:** Monitor da tela do bot em tempo real com botão de intervenção humana (*Take Control*) e lista de rotinas.

---

## 🏛️ 2. Arquitetura do Sistema: O "Nexus Computer"

Diferente do Rakazo, que exige PostgreSQL, Prisma e múltiplos serviços pesados, o NexusLocal mantém sua fundação leve baseada em **Docker Compose**, **FastAPI** e **SQLite**.

### Diagrama de Infraestrutura

```
┌────────────────────────────────────────────────────────────────────────┐
│                        HOST (DOCKER COMPOSE)                           │
│                                                                        │
│  ┌───────────────────────┐                  ┌───────────────────────┐  │
│  │   nexus_frontend      │◄── WebSockets ──►│    nexus_backend      │  │
│  │   (React 19 / Nginx)  │       e SSE      │   (FastAPI / Python)  │  │
│  └───────────────────────┘                  └───────────┬───────────┘  │
│                                                         │              │
│                           ┌─────────────────────────────┼───────────┐  │
│                           ▼                             ▼           │  │
│               ┌───────────────────────┐    ┌──────────────────────┐ │  │
│               │    nexuslocal.db      │    │  backend/proactive/  │ │  │
│               │ (SQLite WAL Produção) │    │  • Detector          │ │  │
│               └───────────────────────┘    │  • Routines Engine   │ │  │
│                                            │  • Computer Manager  │ │  │
│                                            └────────────┬─────────┘ │  │
└─────────────────────────────────────────────────────────┼───────────┘  │
                                     REDE ISOLADA DOCKER  │              │
                                        (`nexus_net`)     ▼              │
┌─────────────────────────────────────────────────────────────────────┐  │
│  CONTAINER: nexus_computer                                          │  │
│  • Headless Chromium (Playwright CDP)                               │  │
│  • Sandbox Python Runner (Timeout 30s / Max 1GB RAM)                │  │
│  • /workspace isolado montado por usuário                           │  │
│  • TOTALMENTE ISOLADO do host, do nexuslocal.db e da porta 8000     │  │
└─────────────────────────────────────────────────────────────────────┘  │
                                                          ▲              │
                                         (Opcional Nuvem) │              │
                                                          │              │
                                             ┌────────────┴───────────┐  │
                                             │  E2B / Daytona Cloud   │  │
                                             │  (BYOK para VPS leves) │  │
                                             └────────────────────────┘  │
```

### Regras Férreas de Segurança (`AGENTS.md`)
* O container `nexus_computer` roda estritamente dentro da rede isolada `nexus_net`.
* **Zero acesso ao banco de dados:** Ele nunca enxerga o arquivo `nexuslocal.db`. Toda comunicação ocorre via API REST/gRPC interna autenticada por token efêmero.
* **Preservação de Portas do Host:** A porta `8000` do host continua reservada exclusivamente ao Portainer. O tráfego do container de computação não expõe portas públicas no host.

---

## 🎨 3. Design da Interface: Layout de 3 Colunas

Inspirado na tela do Rakazo (registrada em [`Rakazo-Open-source-Grok-Bot-alternative-10-15-2026_08_15_PM.png`](./Rakazo-Open-source-Grok-Bot-alternative-10-15-2026_08_15_PM.png)):

```
┌─────────────────┬───────────────────────────────────┬───────────────────────┐
│ BOTS (Sidebar)  │ CHAT & ATIVIDADES DO BOT          │ COMPUTADOR & ROTINAS  │
├─────────────────┼───────────────────────────────────┼───────────────────────┤
│ [🔍 Buscar] [+] │ 🤖 Radar Cultural                 │ [🖥️ Tela do Bot]   ⚙ ✕│
│                 │ ───────────────────────────────── │ ┌───────────────────┐ │
│ 🟣 Radar Tech   │ [Usuário]: "Tem ingresso pro show │ │ [mail.google.com] │ │
│    há 12 min    │ do Coldplay em Curitiba?"         │ │ ┌───────────────┐ │ │
│                 │                                   │ │ │ ✓ Pista: R$180│ │ │
│ 🟢 Radar Shows  │ [Bot]: "Verificando no site       │ │ └───────────────┘ │ │
│    ativo agora  │ oficial agora..."                 │ └───────────────────┘ │
│                 │                                   │ [🎮 Take Control]     │
│ 🟠 Monitor Preço│ ┌───────────────────────────────┐ │                       │
│    ontem        │ │ 🖥️ Computador (Concluído)      │ │ ROTINAS DO BOT      │
│                 │ │ [Miniatura da Tela / Sympla]  │ │ ⏰ Monitor Diário   │
│ 🔵 Curador News │ └───────────────────────────────┘ │    Todo dia às 09:00  │
│    ontem        │                                   │ ⏰ Checagem Horária   │
│                 │ ┌───────────────────────────────┐ │    A cada 1 hora      │
│                 │ │ ✓ Encontrado → 2 datas em Nov │ │                       │
│                 │ │ ✓ Preço → Pista R$ 180 (Lote2)│ │ [+ Nova Rotina]       │
│                 │ │ ⚠ Alerta → Menos de 10% restam│ │                       │
│                 │ └───────────────────────────────┘ │                       │
│                 │                                   │                       │
│ [Perfil Usuário]│ [+ Mensagem para o bot...]     [^]│                       │
└─────────────────┴───────────────────────────────────┴───────────────────────┘
```

### 3.1 Avatares Orgânicos Vetoriais ("Kawaii Tech")
Cada bot possui um avatar SVG morfogenético com olhos animados e dois estados:
1. **`idle`:** Respiração suave em 5 segundos, piscada ocasional, cores sutis.
2. **`working`:** Pulsação mais rápida (2s), brilho perimetral (`filter: drop-shadow(0 0 6px var(--bot-color))`) e olhos que acompanham o processamento.

---

## 🗄️ 4. Modelo de Dados e Banco (SQLite WAL)

Novas tabelas incrementais adicionadas em `init_db()` em [`database.py`](file:///j:/Arquivos%20Osmar/Multi+/backend/database.py) dentro de blocos seguros `try/except sqlite3.OperationalError`:

### 4.1 Tabela de Bots Especialistas (`proactive_bots`)
```sql
CREATE TABLE IF NOT EXISTS proactive_bots (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    title TEXT,
    description TEXT,
    system_instructions TEXT,
    color_hex TEXT NOT NULL DEFAULT '#3EC5A8',
    avatar_shape TEXT NOT NULL DEFAULT 'circle',
    computer_mode TEXT NOT NULL DEFAULT 'shared', -- 'shared' | 'dedicated'
    ambient_enabled INTEGER NOT NULL DEFAULT 1,
    ambient_rules TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proactive_bots_user ON proactive_bots(user_id);
```

### 4.2 Tabela de Rotinas Agendadas (`proactive_routines`)
```sql
CREATE TABLE IF NOT EXISTS proactive_routines (
    id TEXT PRIMARY KEY,
    bot_id TEXT NOT NULL REFERENCES proactive_bots(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    timing_type TEXT NOT NULL, -- 'cron' | 'interval' | 'once'
    timing_value TEXT NOT NULL, -- ex: '0 8 * * *' ou '3600'
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proactive_routines_next ON proactive_routines(is_active, next_run_at);
```

### 4.3 Tabela de Memórias em Markdown (`proactive_memories`)
```sql
CREATE TABLE IF NOT EXISTS proactive_memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    bot_id TEXT, -- NULL se for memória compartilhada
    scope TEXT NOT NULL DEFAULT 'shared', -- 'shared' | 'isolated'
    topic TEXT NOT NULL,
    content_markdown TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proactive_memories_lookup ON proactive_memories(user_id, topic);
```

---

## 🚀 5. Roadmap de Implementação em 4 Ondas

| Onda | Nome | Entregáveis | Complexidade |
| :---: | :--- | :--- | :---: |
| **Onda 1** | **Frontend: Avatares Orgânicos & Cards de Ação** | Componente `<OrganicAvatar />` com estados `idle/working`, `<ComputerActionBlock />` com preview de desktop e badges estruturados (`✓`). | Média |
| **Onda 2** | **Roster de Bots & Escuta Ambiente** | Tela de 3 colunas (`view === 'agents'`), cadastro de bots especialistas e regras declarativas de ambient listening. | Média |
| **Onda 3** | **Container `nexus_computer` (Playwright Sandbox)** | Container Docker com headless Chromium + CDP, serviço Python `BaseComputer` com `navigate_and_extract()` e captura de screenshots. | Alta |
| **Onda 4** | **Motor de Rotinas & Monitoramento Contínuo** | Agendador assíncrono em segundo plano (APScheduler / asyncio loop) executando rotinas cron e disparando alertas no Sininho 🔔. | Alta |

---

## 🔒 6. Invariantes Mantidas (Não Quebrar!)
1. **Opt-in Rigoroso:** O sistema só atua para usuários que ativaram o recurso explicitamente.
2. **Pessoas Privadas Protegidas:** O detector continua descartando categoricamente menções a pessoas da família, amigos e colegas.
3. **TurnGuard Ativo:** Insights em conversas abertas só são entregues após a IA do chat terminar o turno de fala.
4. **Isolamento de Testes:** Testes unitários NUNCA rodam no `nexuslocal.db` ao vivo; usam estritamente bancos temporários descartáveis.
