# 🧭 Hub de Documentação: Smart Intent Router (Auto-Roteador Inteligente)
**Multi+ / NexusLocal** · Planejamento Arquitetural e Especificação Técnica

Este diretório contém todo o planejamento, arquitetura, contratos de dados, fluxos de decisão e o checklist operacional para a implementação futura do **Auto-Roteador Inteligente de Modelos**.

---

## 🗂️ Índice de Documentos

1. **[00. Visão Geral, Motivação e Benchmarks](file:///j:/Arquivos%20Osmar/Multi+/melhorias/smart-router/00-visao-geral.md)**
   * Diagnóstico do problema, benchmarking (RouteLLM, OpenRouter Auto, Martian), objetivos de negócio e princípios inegociáveis de design.
2. **[01. Taxonomia de Intenções e Motor de Classificação](file:///j:/Arquivos%20Osmar/Multi+/melhorias/smart-router/01-taxonomia-e-classificador.md)**
   * As 6 classes de intenção, pipeline de inferência em 2 estágios (Heurística Zero-Overhead < 2ms + Classificador Semântico) e regras de extração de sinais.
3. **[02. Arquitetura de Backend e Integração com Failover](file:///j:/Arquivos%20Osmar/Multi+/melhorias/smart-router/02-arquitetura-backend-e-integracao.md)**
   * Desenho do módulo `backend/ranking/smart_router.py`, políticas de roteamento (Econômica, Equilibrada, Máxima Performance) e simbiose perfeita com o motor de `model_rankings` e `failover` de 2 tiers.
4. **[03. Interface do Usuário (UI/UX) e Transparência](file:///j:/Arquivos%20Osmar/Multi+/melhorias/smart-router/03-interface-ui-e-experiencia-usuario.md)**
   * Opção canônica `🎯 Auto` no `ModelSelector.tsx`, pill/badge de rota executada no chat, popover explicativo e painel de preferências em Configurações.
5. **[04. Telemetria, Métricas e Dashboard](file:///j:/Arquivos%20Osmar/Multi+/melhorias/smart-router/04-metricas-telemetria-e-auditoria.md)**
   * Registro analítico no banco (`model_usage_log`), cálculo de taxa de acerto, tokens economizados e gráficos de distribuição por intenção no `UsageDashboard.tsx`.
6. **[05. Roadmap Operacional e Checklist de Subtarefas](file:///j:/Arquivos%20Osmar/Multi+/melhorias/smart-router/05-roadmap-e-subtarefas-checklist.md)**
   * Checklist passo a passo dividido em 5 fases sequenciais para guiar a implementação prática sem retrabalho.
7. **[06. Diagnóstico e Calibração 2026](06-diagnostico-e-calibracao-2026.md)**
   * Por que o Auto escolhia sempre o mesmo modelo, perfil heurístico de capacidades (`model_profile.py`), seleção por *fit*, sticky condicionado, esforço adaptativo e o modo "Testar o roteador".
8. **[07. Rankings de Modelos 2026](07-rankings-de-modelos-2026.md)**
   * Fim do ranking aleatório (`auto-seed`): qualidade determinística (curadoria + heurística do perfil), popularidade OpenRouter casada por nome normalizado, visão por disponibilidade (sem provedores expirados nem modelos de imagem) e sync no boot/24 h.

---

## 🎯 Resumo Executivo em Uma Frase
> *"O usuário simplesmente digita sua mensagem; o NexusLocal analisa a complexidade e intenção em menos de 2 milissegundos e despacha a requisição para a IA mais rápida, eficiente ou profunda disponível, mantendo o Failover de prontidão caso ocorra qualquer instabilidade."*
