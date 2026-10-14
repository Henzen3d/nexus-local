# 📁 Hub de Melhorias, Planos e Documentação — Multi+ (NexusLocal)

Esta pasta centraliza todas as iniciativas de evolução, planos de arquitetura, documentações de auditoria e arquivos de melhoria do **Multi+**, mantendo a raiz do projeto limpa, organizada e focada no código-fonte.

---

## 🗂️ Estrutura de Diretórios

```
melhorias/
├── intelligent-ui/             # Interface inteligente: JSON de blocos, UI fica no Multi+ já aberto
│   ├── README.md
│   ├── 00-visao-e-spec.md
│   ├── 01-plano-fundacao.md
│   ├── 02-plano-indicadores.md
│   ├── 03-plano-cartoes-imagens.md
│   ├── 04-plano-graficos.md
│   ├── 05-plano-controles.md
│   ├── 06-criterios-aceite.md
│   ├── 07-chatkit-referencia.md
│   ├── 08-open-intelligent-ui-referencia.md
│   ├── 09-plano-sandbox-e-exportacao.md
│   ├── 10-referencias-answerui-openui-openwebui.md
│   ├── 11-plano-camada-visual.md
│   ├── 12-plano-paridade-intelligent-ui.md
│   ├── 13-plano-cenas-2d-3d.md
│   └── referencias-codigo/     # Módulos prontos (sandbox, tokens, exportação, cena, JSON parcial)
│
├── assistente-proativo/        # 🤖 Assistente Proativo (Detecção de emoção/entidades + pesquisa background)
│   ├── README.md               # Hub e índice (comece aqui)
│   ├── 00-visao-geral-v2.md    # Visão ajustada ao código, decisões de produto, fases
│   ├── 01-decisao-entrega-e-presenca.md # Toast × bolha × cartão de retorno × push; presença; contratos
│   ├── 02-fase-1-spike-detector.md
│   ├── resultados-spike-f1.md  # Resultados do spike F1: métricas do porteiro, comandos do classificador, go/no-go
│   ├── 03-fase-2-nucleo-pipeline.md
│   ├── 04-fase-3-presenca-fila-retorno.md
│   ├── 05-fase-4-controles-e-admin.md
│   ├── 06-fase-5-qualidade-e-rollout.md
│   ├── 07-opcional-web-push-pwa.md
│   ├── ROADMAP-CHECKLIST.md    # Tarefas e subtarefas com IDs e critérios de aceite
│   ├── assistente-proativo-plano.md      # (histórico) plano original de 2026-10-07
│   ├── brainstorm-assistente-proativo.md # (histórico)
│   └── design-assistente-proativo.md     # (histórico)
│
├── dream-memory/               # 🌙 Consolidação Noturna de Memória ("Dream Memory" - Kimi/Claude Code/Mem0)
│   ├── 00-visao-geral.md       # Diagnóstico, decisão e arquitetura geral
│   ├── 01-fase-esquema-e-historico.md
│   ├── 02-fase-motor-de-consolidacao.md
│   ├── 03-fase-gatilho-e-orquestracao.md
│   ├── 04-fase-interface-e-auditoria-ui.md
│   └── 05-fase-testes-e-criterios-aceite.md
│
├── smart-router/               # 🧭 Auto-Roteador Inteligente de Modelos (Smart Intent Router)
│   ├── README.md               # Hub e índice geral de navegação
│   ├── 00-visao-geral.md       # Diagnóstico, problema e benchmark
│   ├── 01-taxonomia-e-classificador.md # Taxonomia das 6 classes e motor < 2ms
│   ├── 02-arquitetura-backend-e-integracao.md # Políticas, matriz e integração com failover
│   ├── 03-interface-ui-e-experiencia-usuario.md # Opção 'Auto', badges e transparência
│   ├── 04-metricas-telemetria-e-auditoria.md # KPIs, logs e cards de dashboard
│   └── 05-roadmap-e-subtarefas-checklist.md # Checklist de execução em 5 fases
│
├── esforco-reasoning/          # 🎚️ Seletor de esforço gated por modelo (plano, sem código)
│   ├── README.md
│   ├── 00-visao-e-diagnostico.md
│   ├── 01-taxonomia-de-controles.md
│   ├── 02-backend-catalogo-e-payload.md
│   ├── 03-interface-cockpit.md
│   └── 04-roadmap-subtarefas.md
│
├── novas-5-melhorias-ux/       # 🚀 As 5 Próximas Frentes de Melhoria UX/UI (Benchmarks 2026)
│   ├── README.md               # Visão geral comparada (Claude, ChatGPT, DeepSeek, MiMo, Manus, MiniMax)
│   ├── ROADMAP-CHECKLIST.md    # Checklist operacional consolidado de execução
│   ├── 01-composer-action-pills.md
│   ├── 02-slash-commands-shortcuts.md
│   ├── 03-reasoning-thought-stream.md
│   ├── 04-bento-starter-cards.md
│   └── 05-sidebar-pins-temporal.md
│
├── system-prompt/              # 🧠 System Prompt & Harness: Composição, anti-injeção, perfis e resiliência
│   ├── README.md               # Hub e visão geral do harness
│   ├── 01-novo-system-prompt-base.md
│   ├── 02-composicao-projetos-e-fontes-rag.md
│   ├── 03-privacidade-e-filtragem-de-memoria.md
│   ├── 04-perfis-por-familia-de-modelos.md
│   ├── 05-harness-resiliencia-latencia-e-cache.md
│   └── 06-suite-de-testes-e-regressao.md
│
├── historico-planos/           # 📜 Planos de fases anteriores, auditorias e especificações consolidadas
│   ├── AUDIT-REPORT.md
│   ├── Audit-changes-history.mb
│   ├── BADGE-plan.md
│   ├── context-plan.md
│   ├── FABLE5.md
│   ├── free-api.md
│   ├── gap_analysis.md
│   ├── melhorias-UX-UI.md
│   ├── MELHORIAS_FUSION.md
│   ├── micropolimento.md
│   ├── mudancas.md
│   ├── MYTHOS.md
│   ├── PLANO_SIDEBAR_CONVERSAS_ARTEFATOS.md
│   ├── PLAN_FIX_RAG_PROJETOS.md
│   ├── Plan-attachments.md
│   ├── Plan-free-registry-quota.md
│   ├── Plan-otimizacao-fusion.md
│   ├── Plan-performance-audit.md
│   ├── Plan-projects.md
│   ├── Plan-web-search.md
│   ├── plan-melhorias-ux-ui.md
│   ├── plan-micropolimento-fase5.md
│   ├── plan-ranking-failover-modelos.md
│   ├── plan-ranking-failover.md
│   ├── plan_coffee.md
│   ├── plan_inter.md
│   └── plan_memory.md
│
└── amostras-e-testes/          # 🧪 Arquivos de amostra, laudos de teste, screenshots e scripts avulsos
    ├── _fable5_migration_test.py
    ├── check_db.py
    ├── antigo-config.html
    ├── Discurso.html
    ├── discurso-v2.html
    ├── NexusLocal.html
    ├── NexusLocal-Configurações.png
    ├── test-empty-state-dark.png
    ├── test-login-onboarding.png
    ├── Multi+.rar
    ├── vistoria.html
    ├── vistoria-final.html
    ├── vistoria_sem_marca_dagua.html
    ├── vistoria.pdf
    ├── Laudo de Vistoria #001932.pdf
    └── Laudo_de_Vistoria_001932.pdf
```

---

## Intelligent UI

Spec e planos em [`intelligent-ui/`](intelligent-ui/README.md). **Implementado** (Fases 1–7; auditoria de 2026-10-14 com pendências anotadas nos planos). A IA manda dados. O React atual desenha. A flag nasce desligada e, desde as correções de 2026-10-14, desliga o recurso inteiro (catálogo, extração, persistência, render); liga-se pelo painel admin (Ferramentas → Interface Inteligente) ou por `INTELLIGENT_UI_ENABLED`. Pendências restantes em `intelligent-ui/06-criterios-aceite.md`. Em 2026-10-14 a camada visual dos cartões foi unificada (plano 11) e ficaram planejados, de forma aditiva, a paridade com o Intelligent UI do ChatGPT (plano 12: `metric`, `table`, `callout`, `options`, `follow_up`, estado compartilhado, render progressivo, laço de correção) e as cenas 2D/3D (plano 13), com base nos repositórios AnswerUI, OpenUI e Open WebUI (leitura no plano 10).

## New Chat Input (Redesign Benchmark Claude 2026)

Documentação e planos detalhados em [`new-chat-input/`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/new-chat-input/README.md):
- Input em linha única no chat ativo (~44px)
- Migração da seleção de modelos para a linha de rodapé com disclaimer
- Ações dinâmicas à direita: Voz ➔ Enter
- Menu integrado no botão `+` (anexos, enhance de prompt, busca web)
- Balão unificado de modelos e provedores com toggle de Auto-Roteamento Inteligente e filtro por provedor

## Esforço de raciocínio

Plano em [`esforco-reasoning/`](esforco-reasoning/README.md). Não implementado. Seletor só aparece quando o modelo aceita dial de esforço. Reasoning exibido no chat e temperatura do Smart Router ficam de fora. Checklist em 6 fases, ainda aberto.

## Image gen

Docs em [`image-gen/`](image-gen/README.md). Não implementado. Pedido de imagem raster sai do modelo de chat e vai para Cloudflare Workers AI em background. A imagem volta no mesmo chat.

## System Prompt & Harness Architecture

Documentação completa e planos em [`system-prompt/`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/system-prompt/README.md):
- **Prompt Base Afirmativo (~290 tokens):** Identidade neutra, honestidade estrita, ausência de emojis e regras claras de código.
- **Composição em Camadas:** Substituição eliminada em projetos; injeção modular que preserva regras base e prefix caching.
- **Defesa Anti-Prompt Injection (`<fonte>`):** Encapsulamento de dados externos (RAG, anexos, busca web) em tags semânticas não executáveis.
- **Governança de Privacidade:** Minimização de PII; dados sensíveis (família, nascimento) retidos sob demanda para provedores externos.
- **Perfis por Família de Modelos:** Ajustes cirúrgicos para modelos de raciocínio, compactos e coders.
- **Resiliência e Desempenho:** TTFT timeout (8s), parser de nome de arquivo em artefatos, coalescência de WebSocket e isolamento de cache.


## 🚀 Frentes Ativas de Desenvolvimento

Para acompanhar e executar as próximas melhorias de UX/UI, consulte a pasta [`novas-5-melhorias-ux/`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/):

1. **[01. Composer com Action Pills & Modos](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/01-composer-action-pills.md)** — Raciocínio, Fusion, Web Search e Enhancer integrados diretamente no rodapé da caixa de prompt.
2. **[02. Slash Commands (`/`) e Navegação por Teclado](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/02-slash-commands-shortcuts.md)** — Comandos instantâneos no input e paleta global `Ctrl+K`.
3. **[03. Accordion de Raciocínio (*Thought Stream*) & Timeline Fusion](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/03-reasoning-thought-stream.md)** — Pensamento colapsável com cronômetro em tempo real (estilo DeepSeek-R1) e status do Fusion.
4. **[04. Bento Starter Cards no Empty State](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/04-bento-starter-cards.md)** — Grade interativa de cartões com ações prontas inspirada no Manus e Xiaomi MiMo.
5. **[05. Sidebar Modular com Fixados e Agrupamento Temporal](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/05-sidebar-pins-temporal.md)** — Top dock com atalhos, seção destacada de Fixados e separação cronológica (Hoje, Ontem, 7d, 30d).

Acompanhe a evolução de cada item através do [`ROADMAP-CHECKLIST.md`](file:///j:/Arquivos%20Osmar/Multi+/melhorias/novas-5-melhorias-ux/ROADMAP-CHECKLIST.md).
