# 🤖 Assistente Proativo — Hub de Documentação

Transformar o Nexus de chat reativo em assistente que percebe **interesse genuíno** (emoção + assunto concreto), pesquisa em segundo plano e volta com um resumo curto, com fontes — **no momento certo**, inclusive quando o usuário saiu e voltou.

## Índice (leia nesta ordem)

| # | Documento | O que contém |
|---|---|---|
| 0 | [`00-visao-geral-v2.md`](./00-visao-geral-v2.md) | Visão ajustada ao código real, decisões de produto, o que reaproveitar, correções ao plano original, fases e critérios de sucesso |
| 1 | [`01-decisao-entrega-e-presenca.md`](./01-decisao-entrega-e-presenca.md) | **A decisão que estava em aberto:** toast × bolha × cartão de retorno × push; máquina de estados de presença; regras de frescor; contratos WS/REST; cenário "saiu para almoçar" passo a passo |
| 2 | [`02-fase-1-spike-detector.md`](./02-fase-1-spike-detector.md) | F1 — porteiro léxico + classificador LLM + dataset gold + métricas (go/no-go) |
| 3 | [`03-fase-2-nucleo-pipeline.md`](./03-fase-2-nucleo-pipeline.md) | F2 — migrações, limites, pesquisa, síntese, entrega inline/toast, bolha, integração no chat |
| 4 | [`04-fase-3-presenca-fila-retorno.md`](./04-fase-3-presenca-fila-retorno.md) | F3 — presença, fila `pending`, cartão "Enquanto você esteve fora", "Me conta aqui" iniciando chat novo, expiração |
| 5 | [`05-fase-4-controles-e-admin.md`](./05-fase-4-controles-e-admin.md) | F4 — opt-in e onboarding, settings do usuário, blocklist, painel admin, logs anonimizados, kill-switch |
| 6 | [`06-fase-5-qualidade-e-rollout.md`](./06-fase-5-qualidade-e-rollout.md) | F5 — suíte completa, housekeeping, observabilidade, documentação, rollout gradual com a família |
| 7 | [`07-opcional-web-push-pwa.md`](./07-opcional-web-push-pwa.md) | F6 (pós-MVP) — notificação nativa com o app fechado |
| ✔ | [`ROADMAP-CHECKLIST.md`](./ROADMAP-CHECKLIST.md) | Todas as tarefas e subtarefas em checkboxes, com IDs, estimativas e critérios de aceite |

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
| Fase | Status |
|---|---|
| F1 Spike do detector | ⏳ não iniciada |
| F2 Núcleo do pipeline | ⏸️ aguardando F1 |
| F3 Presença, fila e retorno | ⏸️ |
| F4 Controles e admin | ⏸️ |
| F5 Qualidade e rollout | ⏸️ |
| F6 Web Push (opcional) | 🔮 pós-MVP |

**Estimativa:** ~38 h para o MVP (F1–F5); ~46 h com F6.
