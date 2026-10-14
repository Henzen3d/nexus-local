# 🕒 Fase 3 — Presença, Fila de Pendentes e Entrega no Retorno

**Objetivo:** cobrir o cenário central ("saiu para almoçar e voltou"): detectar ausência, **não disparar nada no vazio**, perceber o retorno e entregar no lugar certo — inclusive **iniciando um chat novo** quando o usuário pedir "Me conta aqui".
**Estimativa:** 10 h · **Dependências:** F2 · **Bloqueia:** F4 (parcialmente), F5.

**Entregáveis**
- `backend/proactive/presence.py`, `delivery.py` completo, `GET /pending`, `POST /insights/{id}/expand`, evento `proactive_pending`
- Frontend: `hooks/usePresence.ts`, `hooks/useProactive.ts`, `components/ProactiveWelcomeCard.tsx`, "veio de: «conversa»" na bolha, expiração

---

## Tarefa F3.1 — Presença no servidor (`presence.py`)

- [ ] **F3.1.1** `PresenceState(user_id, sockets: dict[ws_id, SocketPresence(state, conversation_id, view, last_seen_at)])`; `effective_state(user)` = melhor estado entre sockets (`active > idle > hidden`), `offline` se nenhum socket.
- [ ] **F3.1.2** `update(user_id, ws, state, conversation_id, view)`; `touch(user_id, ws)` em cada ping/pong (renova `last_seen_at`); `remove(user_id, ws)` no `finally` do WS (junto de `unregister_socket`).
- [ ] **F3.1.3** Timeout de segurança: socket sem `touch` há > 2 × intervalo de ping ⇒ tratado como `hidden` (caso o cliente tenha congelado sem fechar o socket).
- [ ] **F3.1.4** Callbacks de transição: `on_return(user_id, ws, conversation_id, view)` disparado quando `idle|hidden|offline → active` ou quando um socket novo conecta — chama `delivery.flush_pending(user_id, ws, context)`.
- [ ] **F3.1.5** Métricas simples para o dashboard admin: usuários `active` agora, transições/hora (opcional).
- [ ] **F3.1.6** Testes unitários da máquina de presença (multi-socket, timeout, transições).

**Arquivos:** `backend/proactive/presence.py`, `backend/routers/chat.py` (hook em ping/pong/`presence`/`finally`)

---

## Tarefa F3.2 — Fila `pending` e entrega no retorno (`delivery.py` completo)

- [ ] **F3.2.1** `decide(insight, presence) -> Channel`: implementar a máquina de estados de `01-decisao-entrega-e-presenca.md` §2.2 (`inline` / `toast` / `pending`).
- [ ] **F3.2.2** `pending`: manter `status='ready'`, `channel=NULL`, **sem** mensagem persistida; aplicar `max_pending=3` (expira o mais antigo).
- [ ] **F3.2.3** `flush_pending(user_id, ws, context)` no retorno: expira vencidos (`expires_at < now`), carrega `ready` restantes (≤ 3) e decide por item conforme `context.view`/`conversation_id`:
  - abriu a **conversa de origem** ⇒ persistir mensagem com prefixo de retorno (`i18n`: "Enquanto você estava fora, pesquisei…"), `channel='pending_inline'`, enviar `proactive_insight{channel_hint:'inline'}`;
  - está na **tela inicial / chat novo** ⇒ enviar `proactive_pending{insights:[…]}` (o cartão decide), `channel` continua `NULL` até o usuário agir;
  - está em **outra conversa/tela** ⇒ `proactive_pending` + o cliente mostra toast + badge.
- [ ] **F3.2.4** `GET /api/proactive/pending`: mesmo conteúdo do `flush` para o boot do app (login/refresh), com expiração aplicada.
- [ ] **F3.2.5** Mudança de conversa do usuário enquanto há pendentes para ela ⇒ `on_return` com `conversation_id` ⇒ item correspondente vira `pending_inline` na hora de abrir (a bolha aparece no fim do histórico com o prefixo de retorno).
- [ ] **F3.2.6** `ack` estendido: `seen` (viewport/cartão aberto), `dismissed` (cartão), `blocked` (também grava blocklist). Dispensar no cartão **não** apaga o insight: `status='dismissed'`, some das listas.
- [ ] **F3.2.7** Job de expiração/limpeza: `run_proactive_housekeeping_job()` em `main.py` (a cada 15 min): expira vencidos, falha `researching` travados > 5 min (`failed:stuck`), apaga insights terminais com > 30 dias.

**Arquivos:** `backend/proactive/delivery.py`, `backend/routers/proactive.py`, `backend/main.py`

---

## Tarefa F3.3 — "Me conta aqui": iniciar a conversa a partir do insight

- [ ] **F3.3.1** `POST /api/proactive/insights/{id}/expand {mode: "same" | "new_chat"}` (dono apenas):
  - `same` ⇒ cria mensagem **do usuário** "Me conta mais sobre {topic}" na conversa de origem? **Não** — para não escrever em nome do usuário, `same` apenas devolve `{conversation_id, prefill: follow_ups[0]}` e o cliente preenche o input; o envio é do usuário.
  - `new_chat` ⇒ cria `conversations(title=topic truncado, origin_insight_id, model_id/provider_id = os da conversa de origem)`, persiste a 1ª mensagem **do assistente** (`kind='proactive'`, prefixo de chat novo com `«título da origem»`), atualiza `insights.spawned_conversation_id`, `status='delivered'`, `channel='new_chat'`, e devolve `{conversation_id, message_id}`.
- [ ] **F3.3.2** Prefixo de chat novo inclui referência estruturada: `insight.origin = {conversation_id, title}` no payload para o frontend renderizar "veio de: «título»" como link (abre a conversa de origem).
- [ ] **F3.3.3** O turno seguinte nessa conversa funciona normalmente (`load_history` enxerga a mensagem do assistente; `ensure_conversation` encontra a conversa do usuário — ownership já validado pela auditoria).
- [ ] **F3.3.4** `GET /api/conversations` devolve `origin_insight_id` para a sidebar poder mostrar o ícone ✦ na conversa gerada (opcional).

**Arquivos:** `backend/routers/proactive.py`, `backend/routers/conversations.py`

---

## Tarefa F3.4 — Frontend: presença

- [ ] **F3.4.1** `hooks/usePresence.ts`: combina `visibilitychange`, `focus/blur`, `online`, atividade (pointerdown/keydown/scroll/touchstart, throttle 10 s) e timer de idle (5 min); estado derivado `active|idle|hidden`; emite `presence` pelo WS com debounce 2 s **e** imediatamente em transições para `active` (é o gatilho de "voltou"). Inclui `conversation_id` e `view` do store.
- [ ] **F3.4.2** Emitir `presence` também logo após o `ready` do WS (reconexão) e ao trocar `activeConversationId`/`view`.
- [ ] **F3.4.3** Guarda de digitação: expor `lastTypingAt` no store (`MessageInput` atualiza) para o `handleProactiveInsight` respeitar os 3 s.
- [ ] **F3.4.4** Testes de hook (vitest/RTL se existir no projeto; senão teste manual documentado em F5).

**Arquivos:** `frontend/src/hooks/usePresence.ts`, `hooks/useChat.ts`, `store/useStore.ts`, `components/MessageInput.tsx`

---

## Tarefa F3.5 — Frontend: cartão de retorno e fluxo "Me conta aqui"

- [ ] **F3.5.1** `hooks/useProactive.ts`: no boot (token presente) chama `api.getProactivePending()`; trata `proactive_pending` do WS; mantém `pendingInsights` no store (≤ 3); remove item ao `ack`/`expand`; aplica expiração local (`expires_at`).
- [ ] **F3.5.2** `components/ProactiveWelcomeCard.tsx`: renderizado no bloco `isEmpty` do `ChatWindow.tsx`, abaixo da saudação (`getRandomGreeting`); título "Enquanto você esteve fora…" (ou "Tenho uma novidade" se o item for recente < 10 min); até 3 itens com `✦ topic · tempo relativo`; ações por item: **Abrir conversa** (navega para a origem ⇒ bolha com prefixo de retorno), **Me conta aqui** (`expand new_chat` ⇒ abre a conversa nova), **Dispensar** (`ack dismissed`). Estilo com tokens CSS existentes (cards do welcome), **sem Tailwind**.
- [ ] **F3.5.3** Em outra conversa/tela: `proactive_pending` ⇒ toast com ação "Ver" (abre a conversa de origem) + badge ✦; não empilhar mais de 1 toast de proatividade por vez (agrupar: "2 novidades enquanto você esteve fora").
- [ ] **F3.5.4** `ProactiveBubble`: mostrar o link "veio de: «título»" quando `insight.origin` existir; prefixo já vem do servidor.
- [ ] **F3.5.5** Acessibilidade: cartão com `role="region"` e `aria-label`; botões ≥ 44 px no mobile; foco visível.
- [ ] **F3.5.6** i18n: `proactive.cardTitleAway`, `proactive.cardTitleFresh`, `proactive.cardItem`, `proactive.openConversation`, `proactive.tellMeHere`, `proactive.dismiss`, `proactive.cameFrom`, `proactive.toastGrouped` (pt-BR, en-US, es-ES + demais).
- [ ] **F3.5.7** `npm run build` 0 erros.

**Arquivos:** `frontend/src/hooks/useProactive.ts`, `components/ProactiveWelcomeCard.tsx`, `components/ChatWindow.tsx`, `components/ProactiveBubble.tsx`, `api/client.ts`, `store/useStore.ts`, `i18n/locales/*.json`, `index.css`

---

## Tarefa F3.6 — Testes da fase

- [ ] **F3.6.1** Presença: `hidden` ⇒ insight fica `ready` sem mensagem; `active` na origem ⇒ mensagem com prefixo de retorno; `active` na tela inicial ⇒ `proactive_pending` sem mensagem.
- [ ] **F3.6.2** Expiração: insight `event` com `expires_at` no passado nunca é entregue no retorno; `housekeeping` marca `expired`.
- [ ] **F3.6.3** `max_pending=3`: o 4º expira o mais antigo.
- [ ] **F3.6.4** `expand new_chat`: cria conversa do dono com `origin_insight_id`, 1ª mensagem do assistente, `spawned_conversation_id` preenchido; outro usuário ⇒ 404.
- [ ] **F3.6.5** Integração WS (`TestClient`): conectar ⇒ receber `ready` e, se houver pendentes, `proactive_pending`; enviar `presence{state:'active', conversation_id: origem}` ⇒ receber `proactive_insight{channel_hint:'inline'}` uma única vez (idempotência em reconexão).
- [ ] **F3.6.6** Multi-aba: dois sockets do mesmo usuário recebem o mesmo `message_id`; nenhuma duplicata no banco.

---

## Critérios de aceite da fase
- [ ] Com a aba oculta/fechada, **nada** é enviado; ao voltar, a entrega acontece em ≤ 2 s pelo canal correto.
- [ ] Cenário completo de `01-decisao-entrega-e-presenca.md` §4 reproduzido manualmente (vídeo/curto no PR).
- [ ] "Me conta aqui" cria o chat novo com a referência à conversa de origem e a conversa segue normalmente.
- [ ] Insights vencidos jamais aparecem; máximo de 3 pendentes.
- [ ] Suíte verde; build 0 erros; i18n completa.
