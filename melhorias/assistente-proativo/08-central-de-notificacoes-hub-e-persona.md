# 🔔 08 — Central de Notificações, Hub na Sidebar e Identidade do Assistente (F7)

Este documento especifica a **camada de interface e presença visual** do Assistente Proativo no NexusLocal, atendendo à necessidade do usuário de descobrir, acionar, acompanhar e interagir com o assistente de forma clara, amigável e com baixíssima fricção, tanto no desktop quanto no mobile.

---

## 🎯 1. Visão Geral e Problema Resolvido

### O Problema Atual
1. **Invisibilidade:** O assistente proativo opera em segundo plano, mas o usuário não sabe quando ele está ativo, como chamá-lo ou onde encontrar as pesquisas já feitas.
2. **Confusão no Chat:** Ao perguntar no chat *"como chamar o assistente proativo?"*, o modelo remoto (LLM) responde de forma genérica sobre atalhos de SO, pois não conhece a interface do NexusLocal.
3. **Falta de um Hub Central:** Não existe uma página ou local onde o usuário possa revisar todos os insights já entregues, gerenciar tópicos ou solicitar uma investigação proativa manual.

### A Solução Integrada (Fase 7)
Uma tríade visual complementar:
1. **Sininho no Topo (Notificações Rápidas):** Notificador assíncrono com badge numérico ao lado de *"Apoiar o NexusLocal"*.
2. **Hub na Sidebar (Navegação Principal):** Link fixo `✦ Assistente Proativo` abaixo de *Artefatos*, abrindo um painel completo de descobertas e controles.
3. **Canal de Diálogo Dedicado (Desktop Drawer / Mobile Sheet):** Espaço para conversar com o assistente sem poluir o chat principal de trabalho.
4. **Identidade Visual Acolhedora ("Kawaii Tech"):** Avatar com personalidade e microexpressões, com opção de alternar para estilo geométrico sóbrio.

---

## 🏛️ 2. Arquitetura da Interface

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ [Logo NexusLocal]                    [🔍 Buscar conversas...]    [🔔 (3)] [☕ Apoiar] │
└──────────────────────────────────────────────────────────────────────┬─────────────────┘
  SIDEBAR                                                              │
  ┌────────────────────────┐                                           ▼
  │ [＋ Nova conversa]     │                               ┌───────────────────────────┐
  │                        │                               │ 🔔 Descobertas Proativas  │
  │ 💬 Conversas           │                               ├───────────────────────────┤
  │ 📁 Projetos            │                               │ ✦ Pesquisei sobre Rust…   │
  │ 🖼️ Biblioteca          │                               │   há 12 min · 3 fontes    │
  │ ✨ Artefatos           │                               │   [Abrir] [Me conta aqui] │
  │ ✦ Assistente Proativo  │──► Abre Painel Hub            ├───────────────────────────┤
  │    (Badge: [3])        │    (Histórico + Controles)    │ ✦ Novo show do artista X… │
  │                        │                               │   há 1 h · 2 fontes       │
  └────────────────────────┘                               └───────────────────────────┘
```

---

## 🔔 3. Pilar 1: O Sininho de Notificações (`NotificationBell`)

### 3.1 Posicionamento & Visual
- **Desktop:** No canto superior direito (`chat-header-right`), posicionado imediatamente à esquerda do botão de *"Apoiar o NexusLocal"*.
- **Mobile:** Fixo no cabeçalho superior do chat, ao lado do botão de menu/ações, acessível com um toque.
- **Badge Numérico:**
  - Mostra o total de insights pendentes não vistos (`pendingInsights.length`).
  - Cor: Coral com alto contraste (`var(--primary, #E06C53)`), fonte bold 11px, com animação de escala suave (*pop-in*) ao receber um novo insight.
  - Se `count === 0`, o badge desaparece e o sininho fica discreto em tom neutro.

### 3.2 Menu Suspenso (Popover no Desktop / Bottom Sheet no Mobile)
Ao clicar no sininho:
- **Desktop:** Abre um card flutuante glassmórfico (`min-width: 360px`, `max-height: 480px`) ancorado ao botão.
- **Mobile:** Abre uma folha deslizante (`BottomSheet`) que sobe suavemente pelo rodapé.
- **Conteúdo de cada item:**
  1. Ícone faísca (`✦`) e tópico em destaque.
  2. Idade relativa: *"há 8 min"*, *"há 2 h"*.
  3. Trecho do resumo sintetizado (até 140 caracteres).
  4. Favicons e domínios das fontes consultadas.
  5. Ações diretas:
     - **`[Abrir conversa]`**: Navega para a conversa de origem com a bolha proativa.
     - **`[Me conta aqui]`**: Dispara o endpoint `/expand` com `mode='new_chat'`, criando um chat novo onde a IA começa falando sobre a descoberta.
     - **`[✕]` Dispensar**: Marca como visto/dispensado sem abrir.

---

## 🧭 4. Pilar 2: Hub na Sidebar (`view === 'proactive'`)

### 4.1 Novo Link na Navegação Fixa
Na `Sidebar.tsx`, logo abaixo de `Artefatos`:
```tsx
<button
  type="button"
  className={`sidebar-fixed-nav-item ${view === 'proactive' ? 'selected' : ''}`}
  onClick={() => setView('proactive')}
>
  <Sparkles size={20} />
  <span>{t('sidebar.proactiveAssistant')}</span>
  {unreadCount > 0 && <span className="nav-badge">{unreadCount}</span>}
</button>
```

### 4.2 Tela do Hub do Assistente (`ProactiveHubPanel.tsx`)
Uma interface dedicada com 3 abas/seções:
1. **Feed de Descobertas (Histórico):**
   - Lista completa de todas as pesquisas espontâneas que o assistente já entregou ao longo das semanas.
   - Filtro por status: *Novas*, *Vistas*, *Exploradas*.
   - Busca interna por texto ou tópicos.
2. **Disparador Manual ("Pedir uma Investigação"):**
   - Campo para o usuário enviar uma tarefa espontânea: *"Nexus, pesquise o andamento do projeto X e me avise quando tiver novidades"*.
   - Mostra o card de progresso em tempo real (`Pesquisando fontes...` → `Lendo páginas...` → `Sintetizando...`).
3. **Tópicos & Sensibilidade (Gestão de Preferências):**
   - Lista de tópicos bloqueados com botão de desbloqueio com 1 clique.
   - Seletor de sensibilidade: *Frequente (até 3/dia)* vs. *Moderado (1/dia)* vs. *Apenas Grandes Novidades*.
   - Toggle mestre para ativar ou desativar o assistente proativo a qualquer momento.

---

## 💬 5. Pilar 3: Diálogo Paralelo (Desktop Drawer vs. Mobile)

### O Desafio de Fricção do Usuário
O usuário cogitou um chat separado flutuante estilo WhatsApp/Messenger.
- **Análise de Risco:** Widgets flutuantes tradicionais cobrem elementos vitais (área de digitação, botões de scroll) e no celular quebram completamente com a subida do teclado virtual.
- **A Solução Ideal:**

| Dispositivo | Solução de UX Adotada | Por que funciona sem atrito |
|---|---|---|
| **Desktop** | **Gaveta Lateral Deslizante (Side Drawer)** | Fica recolhida na borda direita. Quando aberta, empurra suavemente ou sobrepõe o chat principal sem quebrar o layout, permitindo tirar dúvidas paralelas com o assistente. |
| **Mobile** | **Transição Nativa via "Me conta aqui"** | Em vez de janelas pequenas esmagadas pelo teclado, o toque em *"Me conta aqui"* cria uma conversa de tela cheia dedicada e limpa, com botão de voltar rápido. |

---

## 🤖 6. Pilar 4: Identidade Visual e Mascote ("Kawaii Tech")

### 6.1 Análise de Mercado
- **OpenAI:** Orbe minimalista abstrato / "Dots". Frio e impessoal.
- **Grok:** Robô geométrico.
- **Claude:** Terracota minimalista editorial.
- **Oportunidade do NexusLocal:** Criar um companheiro acolhedor com **calor humano e expressividade**, mantendo a elegância do glassmorphism.

### 6.2 Conceito: "Nexus Lumi" (ou "Nexus Sparky")
- Um mascote esférico/robótico clean, com olhos luminosos e pequenas microexpressões em SVG puro (sem dependência de imagens pesadas):
  - **Repouso (`idle`):** Olhos amendoados piscando suavemente.
  - **Pesquisando (`researching`):** Óculos de detetive ou lupa girando, olhar concentrado.
  - **Com novidade (`ready`):** Olhos brilhando com estrelinhas (`✦`), acenando com a mãozinha.
  - **Soneca (`sleeping`):** Olhos fechados com `zZz` quando o usuário pausa o assistente.
- **Opção de Escolha nas Configurações:**
  - 🤖 **Mascote Lumi (Kawaii Tech / Expressivo)** — Padrão amigável.
  - ✨ **Nexus Core (Orbe / Ícone Minimalista)** — Para quem prefere visual estritamente corporativo.

---

## 📋 7. Plano de Execução & Tarefas (Fase 7)

### Sprint 7.1 — Sinalização & Descoberta (Sininho + Sidebar)
- [ ] **F7.1.1 (Frontend):** Criar o componente `NotificationBell.tsx` em `frontend/src/components/`.
- [ ] **F7.1.2 (Frontend):** Integrar o `NotificationBell` no header de `ChatWindow.tsx` ao lado de *"Apoiar o NexusLocal"*.
- [ ] **F7.1.3 (Frontend):** Criar o popover suspenso com lista de `pendingInsights`, preview, fontes e ações.
- [ ] **F7.1.4 (Frontend):** Adicionar o item `✦ Assistente Proativo` na `Sidebar.tsx` abaixo de Artefatos, com badge numérico.
- [ ] **F7.1.5 (I18n):** Adicionar todas as strings em `pt-BR.json`, `en-US.json` e `es-ES.json` no namespace `proactive.*`.

### Sprint 7.2 — Hub Dedicado do Assistente
- [ ] **F7.2.1 (Frontend):** Criar a view `ProactiveHubPanel.tsx` acessível via `view === 'proactive'`.
- [ ] **F7.2.2 (Backend/REST):** Criar endpoint `GET /api/proactive/history` para listar os insights históricos do usuário.
- [ ] **F7.2.3 (Frontend):** Implementar abas de Feed Histórico, Gerenciamento de Tópicos e Solicitação Manual.
- [ ] **F7.2.4 (Frontend):** Adicionar rota rápida de disparo manual de pesquisa proativa.

### Sprint 7.3 — Mascote Lumi & Expressões Visuais
- [ ] **F7.3.1 (Design):** Componente SVG vetorial reativo `ProactiveMascot.tsx` com variações de estado (`idle`, `researching`, `ready`, `sleep`).
- [ ] **F7.3.2 (Frontend):** Integrar o mascote nas bolhas do assistente, no popover do sininho e no Hub.
- [ ] **F7.3.3 (Config):** Toggle em `ProactiveSettings.tsx` para escolher entre estilo "Mascote" ou "Orbe Minimalista".

---

## 🛡️ 8. Critérios de Aceite & Invariantes

1. **Zero Fricção:** O sininho e o badge não emitem sons intrusivos nem abrem popups sozinhos; a abertura depende sempre do clique do usuário.
2. **Sincronia em Tempo Real:** Quando o backend envia `proactive_pending` ou `proactive_insight`, o sininho atualiza o número instantaneamente via WebSocket.
3. **Consistência de Estado:** Dispensar um insight no sininho reflete no Hub, no card inicial e no backend (`POST /ack`).
4. **Responsividade Estrita:** No mobile, o sininho aciona um `BottomSheet` ergonômico; a sidebar mantém navegação fluida em gaveta.
5. **Tipagem e Testes:** `npm run build` passa com 0 erros TypeScript e os novos componentes possuem testes unitários cobrindo renderização e contadores.
