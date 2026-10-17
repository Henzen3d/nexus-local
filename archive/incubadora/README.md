# Incubadora — Módulos Arquivados

Esta pasta contém módulos que foram descontinuados da UI ativa do NexusLocal, mas mantidos para referência, treinamento futuro e possível reacoplamento.

## Estrutura

```
archive/incubadora/
  README.md                      # Este arquivo
  mascote/                       # Módulo Mascote (Jax)
  assistente-proativo/           # Módulo Assistente Proativo
  multi-agentes/                 # Módulo Multi-Agentes & Sandbox
```

## Módulo: Mascote (Jax)

### Arquivos
- `NexusPetWidget.tsx` — Widget flutuante roxo no canto inferior direito
- `PetAvatar.tsx` — Avatar animado do mascote
- `PetSpeechBalloon.tsx` — Balão de fala do mascote
- `PetConfetti.tsx` — Efeito confetti
- `PetSettingsModal.tsx` — Modal de configurações do pet
- `mascotProfiles.ts` — Perfis de mascotes (lumi, etc.)
- `petAnimations.css` — Animações CSS dos mascotes

### Estado usado (useStore.ts)
- `proactiveSettings.pet_widget_enabled`
- `proactiveSettings.selected_pet`
- `proactiveSettings.persona_style`

### Endpoints de backend
- `/api/proactive/settings` (GET/PUT) — configurações do usuário
- WS `proactive_pending` — insights em tempo real

### Como reacoplar
1. Copiar arquivos de volta para `frontend/src/components/mascot/`
2. Re-adicionar import em `frontend/src/App.tsx`
3. Re-adicionar estado `proactiveSettings` no useStore.ts se necessário

---

## Módulo: Assistente Proativo

### Arquivos
- `ProactiveBubble.tsx` — Bolha de mensagem proativa no chat (inclui ProactiveResearching)
- `ProactiveCompanionModal.tsx` — Modal de companion para insights
- `ProactiveDashboardSection.tsx` — Seção de dashboard de uso proativo
- `ProactiveHubPanel.tsx` — Painel principal do hub proativo
- `ProactiveMascot.tsx` — Ícone do mascote proativo (usado no NotificationBell)
- `ProactiveOnboarding.tsx` — Onboarding do assistente proativo
- `ProactiveSettings.tsx` — Configurações do usuário
- `ProactiveWelcomeCard.tsx` — Card de boas-vindas na tela inicial
- `ProactiveAdminSettings.tsx` — Configurações admin
- `presenceState.ts` — Utilitário de estado de presença
- `proactivePending.ts` — Utilitário de fila de pendentes

### Estado usado (useStore.ts)
- `proactiveSettings` — configurações do usuário
- `pendingInsights` — fila de insights pendentes
- `proactiveStatus` — status de pesquisa em andamento
- `proactiveCompanionOpen` — modal do companion aberto/fechado
- `proactiveCompanionInsight` — insight ativo no companion
- `proactiveCompanionMessages` — histórico do companion
- `openProactiveCompanion()` — abre modal companion
- `closeProactiveCompanion()` — fecha modal
- `sendProactiveCompanionMessage()` — envia mensagem ao companion
- `loadProactiveSettings()` — carrega configurações
- `updateProactiveSettings()` — atualiza configurações
- `markProactiveOnboardingSeen()` — marca onboarding como visto
- `openPendingInsight()` — abre insight pendente
- `dismissPendingInsight()` — descarta insight pendente
- `expandProactiveInsight()` — expande insight (new_chat / continue)
- `pauseProactive()` — pausa o assistente

### Endpoints de backend
- `GET /api/proactive/pending` — insights pendentes
- `GET /api/proactive/settings` — configurações
- `PUT /api/proactive/settings` — atualizar configurações
- `POST /api/proactive/ack` — ack de insight
- `POST /api/proactive/companion` — chat com companion
- `GET /api/proactive/admin-config` — config admin
- `GET /api/proactive/admin-stats` — stats admin
- WS `proactive_pending` —推送 em tempo real

### Como reacoplar
1. Copiar arquivos de volta para `frontend/src/components/`
2. Re-adicionar imports nos componentes que os consomem
3. Re-adicionar campos no useStore.ts
4. Remover `archive/**/*` do exclude no `frontend/tsconfig.json`

---

## Módulo: Multi-Agentes & Sandbox

### Arquivos
- `AgentWorkspace.tsx` — Workspace principal de agentes
- `BotRosterList.tsx` — Lista de bots/agentes
- `ComputerActionBlock.tsx` — Bloco de ação do computador (sandbox)
- `CreateBotModal.tsx` — Modal de criação de bot
- `CreateRoutineModal.tsx` — Modal de criação de rotina

### Estado usado (useStore.ts)
- `view === 'agents'` — navegação para aba de agentes

### Endpoints de backend
- `GET /api/agents` — lista de agentes
- `POST /api/agents` — criar agente
- `DELETE /api/agents/:id` — deletar agente
- `GET /api/routines` — lista de rotinas
- `POST /api/routines` — criar rotina
- `POST /api/sandbox/run` — executar ação no sandbox

### Como reacoplar
1. Copiar arquivos de volta para `frontend/src/components/agents/`
2. Re-adicionar import de `AgentWorkspace` em `frontend/src/App.tsx`
3. Re-adicionar item de navegação "Multi-Agentes" em `frontend/src/components/Sidebar.tsx`
4. Re-adicionar `view === 'agents'` no type de view do useStore.ts

---

## Notas de Build

A pasta `archive/` está excluída do type-check e do bundle Vite via:
- `frontend/tsconfig.json`: `"exclude": ["src/**/*.test.ts", "../../archive/**/*"]`
- Vite não compila arquivos fora de `frontend/src/` naturalmente

Para reacoplar qualquer módulo, mova os arquivos de volta para `frontend/src/` e remova as linhas do tsconfig exclude se necessário.
