# 🐾 10 — Nexus Pet: Assistente Proativo Estilo "Clippy Moderno", Mascotes e Engenharia Reversa do OpenMausBot (F9)

Este documento estabelece a especificação completa para a evolução do Assistente Proativo em um **Companheiro Virtual ("Pet / Amigo")**, combinando a **engenharia reversa do repositório OpenMausBot**, a esteira de **32 mascotes originais** da coleção do NexusLocal e o conceito atemporal do **Clippy (Microsoft Office 97)** reinventado com inteligência artificial contextual moderna, ética de não-intrusão e sincronia desktop/celular.

---

## 🔬 1. Análise Cirúrgica & Engenharia Reversa do OpenMausBot

O **OpenMausBot** (`milind-soni/OpenMausBot`, anteriormente *OpenGrokBot / MausBot*) é uma alternativa open-source sob licença Apache 2.0 inspirada no Grok Bot da xAI, Meta Muse, OpenAI Dots e Cue da Manus. Uma dissecação aprofundada de seu código-fonte revela 5 subsistemas de alto valor arquitetural para o NexusLocal:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                ARQUITETURA OPENMAUSBOT                                 │
└────────────────────────────────────────────────────────────────────────────────────────┘
  DISPOSITIVO MÓVEL (Celular iOS/Android)
         │
         │ (Tailscale / LAN / HTTPS com Token SHA-256 e HPKE)
         ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ COMPANION SIDECAR (:8810)                                    │
  │ • Descoberta mDNS / Bonjour (sem digitar IP)                 │
  │ • Autenticação de Pareamento via QR Code (2 min, uso único)   │
  │ • Whitelist restrita de rotas (Default Deny)                 │
  │ • Espelhamento VNC / Streaming de tela (viewer-relay.ts)     │
  └──────────────────────────────┬───────────────────────────────┘
                                 │ Loopback Only (127.0.0.1)
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ LOCAL HARNESS SERVER (:8799)                                 │
  │ • Processos dos Agentes (Claude CLI, Codex CLI, Grok CLI)    │
  │ • Roteamento Rápido de Decisão (Jev / OpenRouter <300ms)     │
  │ • Permission Broker (Approval Cards / Ask Cards)             │
  │ • Armazenamento local-first em ~/.openmausbot                │
  └──────────────────────────────┬───────────────────────────────┘
                                 │
                                 ▼
  ┌──────────────────────────────────────────────────────────────┐
  │ FRONTEND ELECTRON / REACT 19                                 │
  │ • Motor de Mascotes Paramétrico (CursorAvatar / MausAvatar)   │
  │ • 10 Formas de Corpo + Física de Molas (Springs/Bob/Squash)  │
  │ • Gaze Pointer Tracking (olhos seguem cursor do mouse)       │
  │ • 34 Estados de Emoção + Sistema de Partículas/Confetes      │
  └──────────────────────────────────────────────────────────────┘
```

### 1.1 Motor de Mascotes & Expressões Vetoriais (`Avatar.tsx` / `CursorAvatar.tsx`)
1. **Separação Rosto vs. Corpo (`MASCOT_BODIES`):**
   - 10 corpos geométricos reutilizáveis: `cursor`, `blob`, `circle`, `squircle`, `capsule`, `drop`, `shield`, `hexagon`, `diamond`, `star`.
   - Cada corpo possui uma matriz de ancoragem (`anchor: { x, y, scale }`) que garante que qualquer rosto ou expressão caiba perfeitamente sem deformação ou corte (*clipping*).
2. **Matriz de Física e Movimento (`BodyMotion`):**
   - O avatar não usa GIFs pesados ou vídeos pré-renderizados: sua animação é puramente procedural em SVG e CSS Transforms alimentados por uma física de molas (*spring physics*):
     - `bob: [distância, período_ms]` (salto para cima e para baixo).
     - `sway: [ângulo, período_ms]` (balanço lateral de curiosidade ou dúvida).
     - `pulse: [escala, período_ms]` (respiração orgânica em repouso).
     - `squash: fator` (compressão elástica no impacto ao pousar ou falar).
     - `tilt: graus` (inclinação de cabeça empática).
     - `jitter: [intensidade, ms]` (vibração de alerta ou esforço de processamento).
3. **Rastreamento de Olhar (*Gaze Pointer Tracking*):**
   - Os olhos interpolam sua pupila suavemente na direção das coordenadas `(clientX, clientY)` do mouse ou do foco de digitação do usuário, criando a sensação palpável de que o assistente está prestando atenção no que o usuário faz.
4. **Grupos de Estados e Reações:**
   - **Ciclo de Vida:** `sleeping` (dormindo), `waking` (acordando), `idle` (repouso atento), `listening` (ouvindo voz/leitura), `thinking` (pensando), `searching` (buscando na web), `working` (executando código/tarefa).
   - **Reações Emocionais:** `happy`, `curious`, `excited`, `proud`, `confused`, `suspicious`, `playful`, `celebrate`.
   - **Efeitos de Celebração:** Disparo de confetes vetoriais (`CONFETTI_COLORS`) e fitas luminosas quando uma tarefa longa é concluída com sucesso.

### 1.2 Sidecar Companion & Pareamento Celular (`companion/`)
1. **Isolamento de Loopback Férreo:**
   - O servidor central de agentes nunca se expõe diretamente à rede externa; escuta estritamente em `127.0.0.1`.
   - O processo `companion` roda como um processo auxiliar (*utilityProcess* no Electron ou container leve no Docker) na porta `8810`.
2. **Pareamento Seguro via QR Code:**
   - O desktop gera um QR Code com credencial de alta entropia válida por 2 minutos de uso único.
   - O celular escaneia o QR, troca por um token de dispositivo armazenado no banco apenas como hash SHA-256 e estabelece canal criptografado via envelope HPKE (High-Performance Key Exchange).
3. **Descoberta Local mDNS (Bonjour):**
   - O companion anuncia o serviço na rede local via mDNS. O aplicativo móvel abre e encontra *"NexusLocal de [Usuário]"* instantaneamente, sem que o usuário precise descobrir ou digitar o IP da máquina.
4. **Streaming de Tela e Aprovações:**
   - Módulo `viewer-relay.ts` transmite frames da tela para o celular caso o usuário queira acompanhar de longe o bot trabalhando no computador.

### 1.3 Approval Broker & Inline Cards (`ApprovalCard.tsx`, `AskCard.tsx`)
- Toda ação de risco (executar script, abrir porta, editar arquivo crítico, enviar requisição externa com custo de quota) gera um **card interativo de aprovação** na interface ou notificação push no celular:
  - Botões claros: `[Permitir uma vez]`, `[Permitir sempre para este domínio]`, `[Recusar]`.
  - Permite que o assistente não fique bloqueado silenciosamente nem tome decisões invasivas sem consentimento.

---

## 🐱 2. O Ecossistema de Mascotes do NexusLocal (32 Personas)

A coleção oficial em [`Coleção de Mascotes Assistentes Virtuais.png`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/assistente-proativo/Coleção%20de%20Mascotes%20Assistentes%20Virtuais.png) fornece uma família rica de **32 personagens únicos**, cada um projetado para uma personalidade e arquétipo de trabalho:

| # | Mascote | Função Primária | Arquétipo Visual | Tom de Voz do Balão |
|---|---|---|---|---|
| 1 | **Nex** | Parceiro Principal | Robô branco com visor azul | Confiável, ágil, prestativo |
| 2 | **Lumi** | Sempre Positiva | Gatinha/criatura felpuda branca | Acolhedora, calorosa, entusiasmada |
| 3 | **Zed** | Foco e Produtividade | Bot cibernético com fones cyan | Direto, objetivo, focado em metas |
| 4 | **Neko** | Organização | Brotinho verde kawaii | Metódico, limpo, estruturado |
| 5 | **Pip** | Motivação | Pompom roxo com coração | Encorajador, amigável, carinhoso |
| 6 | **Koda** | Criatividade | Rapazinho de capuz laranja | Inspirador, artístico, fora da caixa |
| 7 | **Mimi** | Carinho e Apoio | Robô felina com olhos de coração | Empática, reconfortante, doce |
| 8 | **Blu** | Curiosidade | Gotinha de água azul luminosa | Questionador, explorador, vivaz |
| 9 | **Orion** | Análise e Estratégia | Bot escuro tático com visor azul | Lógico, estratégico, detalhista |
| 10 | **Rex** | Bom Humor | Raposinha laranja felpuda | Divertido, bem-humorado, leve |
| 11 | **Tico** | Tarefas do Dia a Dia | Robô bege com brotinho | Prático, checklist-driven, prestativo |
| 12 | **Pingo** | Aprendizado | Pinguim fofo com headphones | Didático, curioso, paciente |
| 13 | **Stella** | Sonhos e Ideias | Bolha cósmica estelar | Sonhadora, conceitual, visionária |
| 14 | **Taro** | Soluções Práticas | Golem de pedra com musgo | Calmo, resiliente, pé no chão |
| 15 | **Bibi** | Gentileza | Coelhinha branca com blush rosa | Polida, gentil, delicada |
| 16 | **Flux** | Tecnologia | Esfera negra com anel neon | Tecnológico, geek, inovador |
| 17 | **Nuvem** | Equilíbrio | Nuvenzinha sorridente | Sereno, zen, desestressante |
| 18 | **Pixel** | Games e Diversão | Gato preto com olhos dourados | Gamer, descontraído, sagaz |
| 19 | **Shelly** | Paciência | Tartaruguinha bebê | Calma, reflexiva, cuidadosa |
| 20 | **Kai** | Estudos e Conhecimento | Robô estudante com tablet | Acadêmico, referenciado, preciso |
| 21 | **Lali** | Alegria | Criatura felpuda arco-íris | Festiva, energética, alto astral |
| 22 | **Jin** | Disciplina | Ninja de capuz tático | Focado, disciplinado, pontual |
| 23 | **Fogo** | Energia | Gota de chama sorridente | Energético, dinâmico, proativo |
| 24 | **Sumi** | Descanso | Gatinho preto dorminhoco (zZz) | Lembrete de pausas ergonômicas |
| 25 | **Jax** | Trabalho e Projetos | Bot com óculos de sol pixelados | Executivo moderno, pragmático |
| 26 | **Boo** | Exploração | Criatura creme com anteninha | Aventureiro, pesquisador de tendências |
| 27 | **Vox** | Comunicação | Esfera holográfica sonora | Articulado, comunicativo, claro |
| 28 | **Balu** | Proteção | Ursinho com casaco moletom | Cuidadoso com segurança e privacidade |
| 29 | **Zen** | Calma | Robô minimalista com antena | Meditativo, equilibrado, conciso |
| 30 | **Kiro** | Curiosidade sem Limites | Espírito fuligem com olhões | Inquisitivo, rastreador de detalhes |
| 31 | **Liko** | Natureza | Esfera de água com plantinha | Consciente, sustentável, orgânico |
| 32 | **Byte** | Soluções Digitais | Monitor retrô sorridente | Clássico, saudosista amigável, hacker |

O usuário pode escolher seu **Pet Companheiro Favorito** como mascote principal de toda a aplicação (por exemplo, **Lumi**, **Nex** ou **Byte**), ou deixar no modo dinâmico onde cada bot especialista no sistema assume a persona que combina com sua função.

---

## 📎 3. O Conceito "Clippy Moderno": Companheiro Amigo com Balões de Fala Não-Intrusivos

### 3.1 A Redenção do Clippy
O Clippy original (Office 97) tornou-se lendário por dois motivos:
- **O que ele acertou:** Personalidade, calor humano, presença animada e a tentativa de antecipar a necessidade do usuário antes de ser chamado.
- **O que ele errou:** Era burro (disparava na hora errada), repetitivo (*"Parece que você está escrevendo uma carta"*), interrompia a digitação com caixas de diálogo modais e não tinha dados contextuais reais.

O **Nexus Pet** resolve exatamente essas falhas:
1. **Nunca Interrompe o Fluxo de Trabalho:** O pet vive em uma camada flutuante sutil no canto inferior direito ou ancorado na barra lateral. Ele não rouba o foco do teclado nem abre popups modais no meio da tela.
2. **Memória de Longo Prazo e Acúmulo de Tópicos em Background:**
   - O pet não reage a uma palavra solta. Ele usa o **`MemoryTopicAccumulator`** para correlacionar pesquisas e ações ao longo do tempo.
3. **Balões de Fala Glassmórficos com Micro-Interações:**
   - Quando um gatilho de alto valor é detectado, o pet faz uma micro-animação (ex: inclina a cabeça, seus olhinhos brilham) e abre um balão de fala macio e estilizado.

```
                  ┌─────────────────────────────────────────────────────────────┐
                  │ ✦ Oi! Notei que você está pesquisando sobre Natal/RN,       │
                  │   rotas e hotéis nos últimos dias...                        │
                  │                                                             │
                  │   Montei um roteiro de férias de 4 dias com passeios pelas  │
                  │   dunas e 3 opções de hotéis beira-mar bem avaliados!       │
                  │                                                             │
                  │   ┌────────────────────────┐  ┌───────────────────────────┐ │
                  │   │ ✦ Ver Roteiro Completo │  │ ☕ Guardar para mais tarde│ │
                  │   └────────────────────────┘  └───────────────────────────┘ │
                  └─────────────────────────┬───────────────────────────────────┘
                                           /
                                          /
                                  ╭──────╮
                                  │ ◕  ◕ │  (Mascote Lumi / Nex animado)
                                  │  ▽   │  [Física de mola suave + sway]
                                  ╰──────╯
```

---

## 🧠 4. Arquitetura de Detecção e Acúmulo em Background (`MemoryTopicAccumulator`)

O caso de uso de viagem citado pelo usuário requer uma inteligência de agregação temporal:

```
Turno 1: Usuário pesquisa "voos para Natal ou Fortaleza"
         └── Assistente Proativo extrai: { categoria: 'viagem', destino_candidato: ['Natal', 'Fortaleza'] }
         └── Não interrompe! Armazena no Grafo de Interesse do Usuário (pontuação: 1/3)

Turno 2 (2 horas depois ou no dia seguinte): Usuário pesquisa "melhores praias de Natal"
         └── Assistente Proativo correlaciona: destino confirmado = 'Natal'
         └── Atualiza Grafo: { topico: 'viagem_natal', termos: ['praias', 'voos'], score: 2/3 }
         └── Inicia pesquisa silenciosa em background (pesquisa atrações, roteiros e clima)

Turno 3: Usuário pesquisa "hotéis com café da manhã beira-mar"
         └── Gatilho ativado! Score 3/3 atingido (convergência de rota + destino + hospedagem).
         └── Sintetizador compila o "Roteiro de Férias Natal/RN".
         └── Pet aciona estado `curious` -> `excited` e projeta o Balão de Fala Amigável.
```

### 4.1 Estrutura do Tópico em Background (`proactive_memories`)
```sql
CREATE TABLE IF NOT EXISTS proactive_memories (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    topic_category TEXT NOT NULL,      -- 'travel', 'coding', 'purchase', 'learning'
    topic_key TEXT NOT NULL,           -- 'trip:natal_rn', 'lang:rust', 'gpu:rtx5090'
    signal_count INTEGER DEFAULT 1,    -- Número de vezes que o usuário tocou no assunto
    accumulated_context TEXT NOT NULL, -- JSON com termos, links pesquisados e entidades
    insight_ready_id TEXT,             -- ID do insight proativo sintetizado em background
    status TEXT DEFAULT 'accumulating',-- 'accumulating', 'ready_to_prompt', 'delivered', 'archived'
    last_signal_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_proactive_memories_user_status ON proactive_memories(user_id, status);
```

---

## 🎨 5. Componentes Frontend: O Widget do Pet Virtual (`NexusPetWidget.tsx`)

### 5.1 Anatomia do Componente
O widget do Pet é implementado com arquitetura multi-camada:
1. **`NexusPetWidget.tsx`:** Container flutuante com suporte a arrastar (*drag-and-drop*), minimizar para a bandeja e alternar posições (canto inferior direito, gaveta ou barra de ferramentas).
2. **`PetAvatar.tsx`:** Renderizador SVG vetorial que implementa os algoritmos de mola (*springs*) e estados emocionais herdados do OpenMausBot, carregando as texturas e traços faciais do mascote selecionado.
3. **`PetSpeechBalloon.tsx`:** Balão de diálogo com tipografia moderna, suporte a markdown suave, botões de ação e fechamento inteligente.
4. **`PetSettingsModal.tsx`:** Seletor visual dos 32 mascotes da coleção, ajustes de sensibilidade e controle de presença.

### 5.2 Estilos e Design Tokens (Vanilla CSS First)
Respeitando as regras rígidas do projeto (`AGENTS.md`), o Pet utiliza os tokens de design existentes:
```css
/* Exemplo de integração nos tokens do NexusLocal */
.nexus-pet-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 999;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  pointer-events: none; /* Apenas o pet e o balão capturam cliques */
}

.nexus-pet-balloon {
  pointer-events: auto;
  max-width: 380px;
  background: var(--surface-soft, rgba(255, 255, 255, 0.85));
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid var(--hairline, rgba(255, 255, 255, 0.2));
  border-radius: 20px 20px 4px 20px;
  padding: 16px 20px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.12);
  margin-bottom: 12px;
  animation: balloonPopIn 0.35s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.nexus-pet-avatar {
  pointer-events: auto;
  cursor: pointer;
  width: 72px;
  height: 72px;
  filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.15));
  transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.nexus-pet-avatar:hover {
  transform: scale(1.08) translateY(-4px);
}
```

---

## 📱 6. Acompanhamento Multi-Dispositivo (PC & Celular)

Para cumprir o desejo do usuário de *"acompanhar o trabalho no computador ou celular"*, adaptamos a arquitetura do **Companion Sidecar** do OpenMausBot:

1. **No Desktop (NexusLocal Web / App):**
   - O Pet vive ativo na tela, observando o contexto de trabalho e oferecendo ajuda oportuna.
2. **No Celular (PWA / Nexus Companion):**
   - O usuário pareia seu smartphone via QR Code em **Configurações → Conectar Celular**.
   - O celular recebe via SSE/WebSocket as mesmas notificações e balões de fala do Pet.
   - Se o usuário estiver longe do PC e o assistente concluir um roteiro de viagem ou pesquisa demorada, o Pet manda um push carinhoso:
     *"Lumi aqui! Acabei de compilar seu roteiro de Natal/RN. Quer ver agora no celular ou prefere abrir no PC mais tarde?"*
   - O usuário pode aprovar ou responder direto pelo smartphone.

---

## 📋 7. Plano de Entregas & Tarefas (Fase 9 — Nexus Pet)

### Sprint 9.1 — Acúmulo de Tópicos em Segundo Plano
- [ ] **F9.1.1 (Backend):** Criar tabela `proactive_memories` e migração incremental em `backend/database.py`.
- [ ] **F9.1.2 (Backend):** Criar módulo `backend/proactive/accumulator.py` para agrupar sinais esparsos (ex: viagem, tecnologia, compras) antes de acionar o sintetizador.
- [ ] **F9.1.3 (Backend):** Testes unitários com banco SQLite em memória isolado (`conftest.py`).

### Sprint 9.2 — Motor de Mascotes & Física Vetorial
- [ ] **F9.2.1 (Frontend):** Implementar `PetAvatar.tsx` com física de molas SVG (adaptação do `CursorAvatar.tsx` do OpenMausBot).
- [ ] **F9.2.2 (Assets):** Mapear as 32 variantes do arquivo [`Coleção de Mascotes Assistentes Virtuais.png`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/assistente-proativo/Coleção%20de%20Mascotes%20Assistentes%20Virtuais.png) para perfis de cores e traços.
- [ ] **F9.2.3 (Frontend):** Implementar o rastreador suave de cursor do mouse (*pointer tracking*).

### Sprint 9.3 — Balões de Fala & Interação Estilo Clippy
- [ ] **F9.3.1 (Frontend):** Componente `PetSpeechBalloon.tsx` com animações suaves e botões de ação imediata.
- [ ] **F9.3.2 (Frontend):** Componente mestre `NexusPetWidget.tsx` com controle de arraste e minimização.
- [ ] **F9.3.3 (I18n):** Adicionar strings em `pt-BR.json`, `en-US.json` e `es-ES.json` para as saudações e falas do pet.

### Sprint 9.4 — Companion Móvel & Sincronia
- [ ] **F9.4.1 (Backend/API):** Criar rota de pareamento `/api/companion/pair` com geração de QR Code de alta entropia.
- [ ] **F9.4.2 (Frontend/Mobile):** Adaptar visualização do pet e aprovações rápidas para telas sensíveis ao toque.
