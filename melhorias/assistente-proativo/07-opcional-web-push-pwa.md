# 🔔 Fase 6 (opcional, pós-MVP) — Web Push no PWA

**Objetivo:** alcançar o usuário **com o app fechado** (celular no bolso, computador em outra tarefa) por notificação nativa, respeitando horário silencioso e sem substituir o modelo de entrega do MVP — o push é só mais um *ponteiro* para a mensagem persistida.
**Estimativa:** 8 h · **Dependências:** F3 (fila `pending`), F4 (settings/quiet hours) · **Decisão:** fica para a próxima fase, após o MVP rodar bem.

> Limitações conhecidas: no iOS, Web Push só funciona com o PWA **instalado na tela inicial** (iOS ≥ 16.4) e a permissão precisa ser pedida a partir de um gesto do usuário. No Android/desktop funciona em Chrome/Edge/Firefox.

---

## Tarefa F6.1 — Infra de push (backend)

- [ ] **F6.1.1** Gerar par VAPID (`py-vapid`/`pywebpush`); variáveis `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (`mailto:`) no `.env.example`. Adicionar `pywebpush` pinado em `backend/requirements.txt`.
- [ ] **F6.1.2** Tabela `push_subscriptions(id, user_id REFERENCES users ON DELETE CASCADE, endpoint UNIQUE, p256dh, auth, user_agent, created_at, last_success_at, failures INTEGER DEFAULT 0)` (migração incremental).
- [ ] **F6.1.3** Rotas (`get_current_user`): `GET /api/push/vapid-public-key`, `POST /api/push/subscribe`, `DELETE /api/push/subscribe` (por endpoint), `POST /api/push/test` (envia uma notificação de teste ao próprio usuário).
- [ ] **F6.1.4** `backend/proactive/push.py::send_push(user_id, payload)`: envia para todas as subscriptions do usuário; `410 Gone`/`404` ⇒ remove a subscription; falhas consecutivas ≥ 5 ⇒ remove; payload mínimo `{title, body, url, insight_id}` (sem conteúdo sensível — o texto completo fica no app).
- [ ] **F6.1.5** Integração em `delivery.decide()`: quando o canal for `pending` **e** o usuário estiver `offline` há ≥ 10 min **e** fora do horário silencioso **e** `settings.push_enabled` ⇒ `send_push` (1 push por insight; agrupar se houver > 1 pendente em 15 min: "2 novidades esperando você").
- [ ] **F6.1.6** Nunca enviar push para insights `news` com menos de 48 h de validade restante? (Não — notícia é justamente o caso urgente.) Regra: respeitar `expires_at`; se faltar < 2 h para expirar, não enviar.

**Arquivos:** `backend/routers/push.py`, `backend/proactive/push.py`, `backend/proactive/delivery.py`, `backend/database.py`, `backend/requirements.txt`, `.env.example`

---

## Tarefa F6.2 — Service worker e permissão (frontend)

- [ ] **F6.2.1** Migrar o `vite-plugin-pwa` de `generateSW` para `injectManifest` (precisamos de código próprio no SW) mantendo o precache atual e `navigateFallbackDenylist` (`/api/`, `/attachments/`, `/ws`).
- [ ] **F6.2.2** `frontend/src/sw.ts`: handlers `push` (mostra `showNotification` com `data.url`) e `notificationclick` (foca uma aba existente do app ou abre `url`; a URL leva à conversa de origem com `?insight=<id>` para o cliente fazer `ack seen`).
- [ ] **F6.2.3** `hooks/usePushSubscription.ts`: verifica suporte, pede permissão **somente** a partir de um clique ("Ativar notificações" nas settings do assistente proativo), registra `pushManager.subscribe({userVisibleOnly:true, applicationServerKey})`, envia ao backend; re-sincroniza no boot se a subscription mudou; remove ao desligar.
- [ ] **F6.2.4** Settings: toggle "Notificações nativas" + horário silencioso (já previsto em F4) + botão "Enviar teste".
- [ ] **F6.2.5** Banner contextual (não modal) na primeira vez que um insight ficou pendente por > 1 h sem ser visto: "Quer que eu te avise no celular da próxima vez?" — no máximo 1 vez.
- [ ] **F6.2.6** i18n: `proactive.push.*` (título, descrição, permissão negada, teste enviado, horário silencioso).

**Arquivos:** `frontend/vite.config.ts`, `frontend/src/sw.ts`, `hooks/usePushSubscription.ts`, `components/ProactiveSettings.tsx`, `i18n/locales/*.json`

---

## Tarefa F6.3 — Testes e aceite

- [ ] **F6.3.1** Backend: `send_push` com cliente fake — remove subscription em 410; agrupa múltiplos pendentes; respeita quiet hours (timezone do usuário via `client_timezone_offset` já enviado pelo chat) e `expires_at`.
- [ ] **F6.3.2** Autorização: subscriptions só do próprio usuário; `POST /push/test` só para si.
- [ ] **F6.3.3** Teste manual: Android (Chrome, PWA instalado), desktop (Chrome/Firefox), iOS instalado — registrar resultado por plataforma no README da pasta.
- [ ] **F6.3.4** Aceite: notificação chega com o app fechado em ≤ 30 s após o insight ficar pronto (fora do horário silencioso); clicar abre a conversa certa e marca `seen`; desligar o toggle remove a subscription no servidor.
