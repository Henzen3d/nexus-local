# 📣 Decisão de Entrega e Presença — como e quando o assistente fala

**Pergunta que este documento responde:** o retorno do assistente deve ser um toast? Uma mensagem? E se o usuário saiu para almoçar e volta depois — como o assistente percebe que ele está de volta e "puxa" a conversa?

---

## 1. Opções avaliadas

| # | Opção | Como funciona | Prós | Contras | Veredito |
|---|---|---|---|---|---|
| A | **Toast / snackbar** | balão no canto que some em segundos (`App.tsx::Toast`) | zero fricção; já existe | efêmero (quem saiu perde); 1 slot só; não cabe conteúdo; não "conversa" | só como **aviso** |
| B | **Bolha inline na conversa de origem** | mensagem do assistente com visual próprio (`kind='proactive'`) | fica no histórico; o modelo "lembra" dela no turno seguinte ("quer saber mais?"); é literalmente uma conversa | quem está em outra tela nunca descobre | **fonte da verdade** |
| C | **Cartão "enquanto você esteve fora"** na tela inicial / chat novo | lista de 1–3 novidades no empty-state do `ChatWindow` | é o instante exato em que a pessoa volta e está receptiva; não interrompe; permite **disparar a conversa** num chat novo | só aparece se abrir a tela inicial (por isso combina com badge + toast) | **canal principal de retorno** |
| D | Centro de notificações (sininho + bandeja) | ícone com contador na barra | persistente, multi-item | mais UI para manter; peso desnecessário para uma família | não no MVP (badge na sidebar cobre) |
| E | **Web Push (PWA)** | notificação do sistema com app fechado | único canal que alcança quem fechou o app | VAPID, subscriptions, permissão, iOS irregular | **F6 opcional** |
| F | Abrir a conversa automaticamente | o app navega sozinho | — | sequestra o que a pessoa fazia; parece bug | **rejeitada** |

**Por que não "só toast":** o toast atual é um único slot, some em segundos e não carrega conteúdo — o oposto do que o cenário "voltou da refeição" exige (persistência, descoberta no momento do retorno e capacidade de virar conversa). Ele continua útil como *aviso* quando a pessoa está ativa em outra tela.

---

## 2. Modelo adotado: entrega híbrida guiada por presença

**Princípio:** o insight vira **uma mensagem persistida na conversa onde o interesse surgiu** (`messages.kind='proactive'`). Toast, badge, cartão e push são apenas *ponteiros* para essa mensagem. Assim nada se perde e o canal muda conforme onde a pessoa está.

### 2.1 Estados de presença (por usuário, mantidos em `backend/proactive/presence.py`)

| Estado | Como é detectado | Observação |
|---|---|---|
| `active` | evento WS `presence{state:"active"}` (pointer/teclado/scroll nos últimos 5 min **e** aba visível) | inclui `active_conversation_id` e `view` (`chat`, `admin`, `projects`…) |
| `idle` | aba visível, sem interação há ≥ 5 min | tratado como ausente para fins de entrega |
| `hidden` | `document.visibilityState === 'hidden'` ou `blur` da janela | ausente |
| `offline` | nenhum socket aberto para o usuário | ausente |

Transições relevantes: **`idle|hidden|offline → active` = "voltou"**. Também conta como "voltou": reconexão do WS, boot do app (login/refresh) e abertura de uma conversa.

### 2.2 Máquina de estados de entrega

```
                              insight READY
                                   │
            ┌──────────────────────┼───────────────────────────┐
            ▼                      ▼                           ▼
   ACTIVE na conversa      ACTIVE em outra              AUSENTE (idle / hidden /
   de origem               conversa ou tela             offline)
            │                      │                           │
            ▼                      ▼                           ▼
   bolha "ao vivo" na      toast com ação               fila `pending`
   conversa — só quando    "✦ Pesquisei sobre X"        (nada é disparado)
   não há streaming e      [Ver] (8 s) + badge ✦                │
   não há digitação        na conversa (sidebar)         ao VOLTAR (transição
   há ≥ 3 s                                              para active / reconexão /
                                                         boot / abrir conversa)
                                                                │
                                   ┌────────────────────────────┼─────────────────────┐
                                   ▼                            ▼                     ▼
                           abre a conversa              abre a tela inicial      está em outra
                           de origem                    ou um chat novo          conversa
                                   │                            │                     │
                           bolha já está lá;            cartão "Enquanto você    toast + badge
                           prefixo muda para            esteve fora…"
                           "Enquanto você estava        [Abrir conversa]
                           fora, pesquisei…"            [Me conta aqui] ──► a IA inicia o chat
                                                        [Dispensar]          novo (1ª msg dela)
                                                                             com link "veio de:
                                                                             <conversa origem>"
```

### 2.3 Regras de bom senso (invariantes)

1. **Nunca interromper.** Sem entrega durante streaming (`isStreaming`) ou digitação (debounce 3 s após o último keypress). Se o usuário manda uma mensagem enquanto há insight pronto e não entregue, ele é entregue **depois** da resposta normal daquele turno (`delivery.flush_after_turn`).
2. **Frescor.** `expires_at` por categoria: evento → até a data do evento (máx. 7 dias); notícia → 48 h; produto/lugar/curiosidade → 7 dias. Expirou antes de ser visto → `status='expired'`, descarte silencioso. **Nunca** entregar "o show foi ontem".
3. **Sem pilha.** Máx. **3 pendentes** por usuário; ao criar o 4º, o mais antigo expira. Nada de "você tem 14 novidades".
4. **Prefixo contextual.** O texto sintetizado é único; o *prefixo* muda na entrega: ao vivo → "Fiquei curioso e pesquisei…"; no retorno → "Enquanto você estava fora, pesquisei…"; em chat novo → "Oi! Na nossa conversa *«título»* você pareceu animado com X, então fui pesquisar…".
5. **Transparência.** Toda bolha mostra: motivo ("você pareceu animado com X"), fontes (`SourceShelf`) e três ações: **Quero saber mais** · **Não quero sobre isso** · **Pausar assistente proativo**.
6. **Horário silencioso** (22h–8h, configurável) só afeta Web Push (F6). Inline/cartão não têm hora: só aparecem quando a pessoa já está no app.
7. **Um canal por vez.** Se a bolha foi entregue ao vivo, não há toast; se houve toast, o badge some ao abrir a conversa; o cartão de retorno só lista itens com `status='ready'` ainda não vistos.
8. **Idempotência.** `delivered_message_id` garante que reconexões ou múltiplas abas não dupliquem a mensagem; `seen` é marcado quando a bolha entra na viewport (`IntersectionObserver`) ou o cartão é aberto.

### 2.4 Multi-aba / multi-dispositivo

- A presença do usuário é o **máximo** entre seus sockets (uma aba ativa basta para `active`).
- O WS envia `proactive_insight` para **todos** os sockets do usuário (`notify_user_sockets` já faz isso); cada aba decide o canal pela própria tela. A persistência evita duplicidade: a bolha é a mesma `message_id` em todas.

---

## 3. Contratos

### 3.1 WebSocket — cliente → servidor
```json
{ "type": "presence", "state": "active|idle|hidden", "conversation_id": "uuid|null", "view": "chat|admin|projects|library|artifacts" }
```
Emitido com debounce de 2 s nas transições; a cada ping (já existente) o servidor renova `last_seen_at`. Socket fechado ⇒ `offline`.

### 3.2 WebSocket — servidor → cliente
```json
{ "type": "proactive_status",  "conversation_id": "uuid", "stage": "researching|synthesizing" }
{ "type": "proactive_insight", "insight": { "id": "...", "conversation_id": "...", "message_id": "...", "topic": "...",
    "category": "event|news|product|place", "text": "...", "sources": [{"title": "...", "url": "...", "domain": "..."}],
    "follow_ups": ["..."], "expires_at": "ISO", "created_at": "ISO" }, "channel_hint": "inline|toast|pending" }
{ "type": "proactive_pending", "insights": [ /* mesmo shape, status ready, ≤3 */ ] }
```
`proactive_pending` é enviado na (re)conexão do socket quando houver pendências — complementa `GET /api/proactive/pending` usado no boot.

### 3.3 REST
| Método | Rota | Quem | Função |
|---|---|---|---|
| GET | `/api/proactive/pending` | usuário | lista insights `ready` não vistos (≤ 3), já expirando o que venceu |
| POST | `/api/proactive/insights/{id}/ack` `{action: seen|dismissed|blocked}` | dono | marca estado; `blocked` também grava `proactive_topic_blocklist` |
| POST | `/api/proactive/insights/{id}/expand` `{mode: "same"|"new_chat"}` | dono | `same`: cria turno "Me conta mais sobre…" na conversa de origem; `new_chat`: cria conversa com `origin_insight_id`, 1ª mensagem do assistente e devolve `conversation_id` |
| GET/PUT | `/api/proactive/settings` | usuário | `enabled, sensitivity, categories, quiet_hours, onboarding_seen_at` |
| GET/PUT | `/api/proactive/admin-config` | admin | kill-switch global, modelos do detector/síntese, caps, TTLs |
| GET | `/api/proactive/logs?limit=` | admin | log anonimizado (tópico, categoria, confiança, latências, status) |

### 3.4 Textos-base da IA (pt-BR; i18n gera os demais)
- **Ao vivo:** "Fiquei curioso com *{topic}* e fui pesquisar: {resumo}. {gancho}"
- **No retorno (mesma conversa):** "Enquanto você estava fora, pesquisei sobre *{topic}*: {resumo}. {gancho}"
- **Chat novo:** "Oi! Na nossa conversa *«{titulo_origem}»* você pareceu animado com *{topic}*, então fui pesquisar: {resumo}. {gancho}"
- **Motivo (linha pequena na bolha):** "Pesquisei porque você pareceu {emoção} com {topic}."
- **Cartão de retorno (título):** "Enquanto você esteve fora…" · **(item):** "✦ Pesquisei sobre {topic} · {há N min / ontem}"

---

## 4. Como o cenário "saiu para almoçar" roda, passo a passo

1. 12:03 — usuário escreve a mensagem animada; o turno normal responde. `schedule_proactive_check()` agenda a verificação.
2. 12:03 — porteiro aprova; classificador devolve `interest=0.86, category=event, topic="show Gabriel e Shirley — Balneário Camboriú"`.
3. 12:04 — pesquisa + leitura de 2 páginas + síntese → `status='ready'`, `expires_at=2026-11-15T23:59`.
4. 12:04 — `delivery.decide()`: presença do usuário é `hidden` desde 12:03:40 (fechou a aba/trocou de app) → fica `pending`. **Nada é enviado.**
5. 12:55 — usuário reabre o app. Boot chama `GET /api/proactive/pending` (e o WS, ao conectar, envia `proactive_pending`).
6. Ele cai na **tela inicial** → `ProactiveWelcomeCard` aparece sob a saudação. Clica em **Me conta aqui**.
7. `POST /insights/{id}/expand {mode:"new_chat"}` cria a conversa (título "Show Gabriel e Shirley — BC", `origin_insight_id`), grava a 1ª mensagem do assistente (`kind='proactive'`, prefixo de chat novo, link "veio de: «conversa de origem»") e devolve o `conversation_id`; o frontend abre a conversa e a bolha já está lá. O usuário responde normalmente — o modelo tem a bolha no histórico.
8. Se em vez disso ele tivesse aberto a conversa de origem: a bolha já estaria lá com o prefixo "Enquanto você estava fora…" e o badge ✦ sumiria ao entrar na viewport (`ack seen`).

---

## 5. Decisões explicitamente adiadas

- Web Push (app fechado) — `07-opcional-web-push-pwa.md`.
- Centro de notificações — só se o volume crescer além de 3 pendentes por usuário.
- Entrega por voz no modo de conversa por voz — depende do TTS; avaliar após o MVP.
