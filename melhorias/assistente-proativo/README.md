# 🤖 Assistente Proativo — Hub de Documentação

Transformar o Nexus de chat reativo em assistente que percebe **interesse genuíno** (emoção + assunto concreto), pesquisa em segundo plano e volta com um resumo curto, com fontes — **no momento certo**, inclusive quando o usuário saiu e voltou.

## Índice (leia nesta ordem)

| # | Documento | O que contém |
|---|---|---|
| 0 | [`00-visao-geral-v2.md`](./00-visao-geral-v2.md) | Visão ajustada ao código real, decisões de produto, o que reaproveitar, correções ao plano original, fases e critérios de sucesso |
| 1 | [`01-decisao-entrega-e-presenca.md`](./01-decisao-entrega-e-presenca.md) | **A decisão que estava em aberto:** toast × bolha × cartão de retorno × push; máquina de estados de presença; regras de frescor; contratos WS/REST; cenário "saiu para almoçar" passo a passo |
| 2 | [`02-fase-1-spike-detector.md`](./02-fase-1-spike-detector.md) | F1 — porteiro léxico + classificador LLM + dataset gold + métricas (go/no-go) |
| 2b | [`resultados-spike-f1.md`](./resultados-spike-f1.md) | Resultados do spike F1: entregáveis, métricas medidas do porteiro, comandos para medir o classificador, decisão go/no-go |
| 3 | [`03-fase-2-nucleo-pipeline.md`](./03-fase-2-nucleo-pipeline.md) | F2 — migrações, limites, pesquisa, síntese, entrega inline/toast, bolha, integração no chat |
| 4 | [`04-fase-3-presenca-fila-retorno.md`](./04-fase-3-presenca-fila-retorno.md) | F3 — presença, fila `pending`, cartão "Enquanto você esteve fora", "Me conta aqui" iniciando chat novo, expiração |
| 5 | [`05-fase-4-controles-e-admin.md`](./05-fase-4-controles-e-admin.md) | F4 — opt-in e onboarding, settings do usuário, blocklist, painel admin, logs anonimizados, kill-switch |
| 6 | [`06-fase-5-qualidade-e-rollout.md`](./06-fase-5-qualidade-e-rollout.md) | F5 — suíte completa, housekeeping, observabilidade, documentação, rollout gradual com a família |
| 7 | [`07-opcional-web-push-pwa.md`](./07-opcional-web-push-pwa.md) | F6 (pós-MVP) — notificação nativa com o app fechado |
| ✔ | [`ROADMAP-CHECKLIST.md`](./ROADMAP-CHECKLIST.md) | Todas as tarefas e subtarefas em checkboxes, com IDs, estimativas, critérios de aceite e **notas de implementação por fase** |
| 📖 | [`../../docs/guia-assistente-proativo.md`](../../docs/guia-assistente-proativo.md) | Guia de 1 página para a família (pt-BR): o que é, como ligar/desligar, como bloquear um assunto, privacidade |
| 🔐 | [`../../docs/auditoria-sistema.md`](../../docs/auditoria-sistema.md) | Auditoria de segurança que definiu o padrão dos testes de IDOR/SSRF reaproveitado aqui |

### Documentos originais (mantidos como histórico)
- [`brainstorm-assistente-proativo.md`](./brainstorm-assistente-proativo.md) — ideia inicial
- [`design-assistente-proativo.md`](./design-assistente-proativo.md) — design doc de 2026-10-07
- [`assistente-proativo-plano.md`](./assistente-proativo-plano.md) — plano de 6 fases/14 h (substituído pela v2 acima)

## Decisões fechadas na v2
- **Opt-in** por usuário nas configurações (onboarding na primeira vez).
- **Entrega híbrida guiada por presença**: a fonte da verdade é uma mensagem persistida na conversa de origem (`messages.kind='proactive'`); toast, badge e cartão de retorno são ponteiros. Com o usuário ausente, **nada é disparado** — o insight espera e aparece quando ele volta.
- **"Me conta aqui"** abre um chat novo iniciado pelo assistente, **referenciando a conversa de origem**.
- **Web Push** fica para a fase seguinte ao MVP.
- **Sem Playwright**; **pessoas privadas nunca são pesquisadas**; limites: 3/h/conversa, 10/dia, 24 h por tópico, máx. 3 pendentes.

## Estado das fases

| Fase | Status | Entregue em |
|---|---|---|
| F1 Spike do detector | ✅ porteiro **GO** (83,3 % negativos rejeitados / 0 % positivos perdidos); classificador fail-closed com thresholds 0,8/0,7/0,6 ([`resultados-spike-f1.md`](./resultados-spike-f1.md)) | PR #4 |
| F2 Núcleo do pipeline | ✅ migrações, limites, pesquisa + leitura de 2 páginas, síntese ≤ 600 caracteres, bolha `kind='proactive'`, toast | PR #5 |
| F3 Presença, fila e retorno | ✅ presença por socket (máx. entre abas), fila `pending`, cartão de retorno, "Me conta aqui" em chat novo, expiração/housekeeping | PR #6 |
| F4 Controles e admin | ✅ opt-in + onboarding, settings, blocklist com desfazer, painel admin, logs anonimizados, kill-switch | PR #7 |
| F5 Qualidade e rollout | ✅ código: fakes compartilhados, regressão de segurança, carga leve, recuperação no boot, logs estruturados, cards + alarme no dashboard, flag de onboarding, docs · ⏳ **semana de teste com a família** (F5.4.2–F5.4.4, F5.5.3) é operacional e fica com o admin | PR F5 |
| F6 Web Push (opcional) | 🔮 pós-MVP | — |

### Como operar (resumo)
1. **Deploy**: `docker compose build backend frontend && docker compose up -d` — migrações rodam no boot; sobe com `enabled_global=true` e **ninguém** ativado (opt-in).
2. **Semana 1**: só o admin liga em *Configurações → Assistente proativo*; acompanhe no *Dashboard de uso* (insights/dia, taxa «saber mais», bloqueio, p95, tokens) e nos logs anonimizados.
3. **Semana 2**: ligue **"Liberar onboarding para novos usuários"** no bloco admin (meta `proactive_onboarding_enabled`) — o convite passa a aparecer para quem tem ≥ 3 conversas e ainda não ativou.
4. **Manter ligado se**: 0 relatos de pesquisa sobre pessoa privada · ≤ 1 relato de spam · ≥ 1 «saber mais» por usuário ativo/semana · `failed` < 20 % (o painel mostra um alarme quando passa de 50 % em 24 h).
5. **Reverter**: kill-switch global no painel (sem deploy) — cancela pipelines e expira pendentes. Rollback de código não exige migração reversa (as colunas novas são ignoradas pela versão anterior).

**Variáveis de ambiente** (`PROACTIVE_*`, todas opcionais — o valor salvo em `meta` pelo painel tem precedência): ver bloco em [`.env.example`](../../.env.example). Regras do módulo para quem for mexer no código: seção 3 do [`AGENTS.md`](../../AGENTS.md).

**Estimativa original:** ~38 h para o MVP (F1–F5); ~46 h com F6.
