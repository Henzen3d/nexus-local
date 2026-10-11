# 🔄 Auto-Switch & Resiliência Dinâmica de Provedores
**NexusLocal / Multi+** · Documentação Arquitetural e Planos de Implementação

---

## 🎯 Visão Executiva

O módulo de **Auto-Switch & Resiliência Dinâmica** transforma o fluxo de conversação do NexusLocal em uma experiência imune a travamentos e livre de atritos. 

Em ambientes que orquestram múltiplos provedores e modelos com cotas gratuitas (*free tier*), é rotineiro encontrar modelos que exigem saldo pago (**HTTP 402**), instâncias em manutenção temporária (**HTTP 400 `model_unavailable`**) ou limites de requisições excedidos (**HTTP 429 / 503**).

Atualmente, qualquer falha além de rate limit interrompe a requisição, exibe um card vermelho de erro e obriga o usuário a abrir o menu de modelos, procurar uma alternativa e redigitar seu prompt. 

Este projeto substitui essa fricção por um **motor contínuo de transbordo (failover) transparente**, **desativação automática de modelos sem saldo**, **cooldown temporário inteligente** e **atualização dinâmica do seletor no frontend**.

---

## 🗺️ Estrutura da Documentação

A especificação completa está distribuída nos seguintes documentos:

| Arquivo | Título | Conteúdo Principal |
| :--- | :--- | :--- |
| [**`00-visao-geral.md`**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/00-visao-geral.md) | **Visão Geral e Diagnóstico Real** | Diagnóstico do teste prático (LLM7.io / Minimax M3), comparação Antes vs. Depois, pilares da solução e impacto na experiência do usuário. |
| [**`01-classificador-erros-e-politica-desativacao.md`**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/01-classificador-erros-e-politica-desativacao.md) | **Classificador de Erros e Ciclo de Vida** | Taxonomia HTTP (402 vs 400 vs 429), regras de desativação permanente vs cooldown reversível, enriquecimento de triggers e persistência no banco. |
| [**`02-arquitetura-backend-e-cascata-failover.md`**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/02-arquitetura-backend-e-cascata-failover.md) | **Arquitetura Backend & Cascata Tier-0** | Loop resiliente em `resolve_request.py`, prioridade do mesmo provedor (Tier 0), integração com `model_quota_status` e eventos WebSocket em tempo real. |
| [**`03-interface-ui-e-experiencia-usuario.md`**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/03-interface-ui-e-experiencia-usuario.md) | **Experiência do Usuário (UI/UX)** | Auto-switch do seletor de modelos, badges sutis de transição na mensagem, estados visuais de saúde no dropdown e eliminação de alertas de pânico. |
| [**`04-ferramenta-diagnostico-saude-provedores.md`**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/04-ferramenta-diagnostico-saude-provedores.md) | **Ferramenta de Diagnóstico de Provedores** | Botão "🔍 Diagnosticar Modelos" no painel admin, scanner concorrente de 1-token (ping leve), auto-pruning de modelos mortos e relatório visual. |
| [**`05-roadmap-e-checklist-implementacao.md`**](file:///j:/Arquivos%20Osmar/Multi+/melhorias/auto-switch/05-roadmap-e-checklist-implementacao.md) | **Roadmap e Checklist de Tarefas** | Plano de execução em 4 ondas (Waves), divisão de tarefas por arquivo, matriz de dependências e critérios formais de aceitação (UAT). |

---

## 🚀 Principais Benefícios Esperados

1. **Zero Abandono de Conversa:** O usuário nunca é bloqueado por erros de cota ou instabilidade de provedores terceiros.
2. **Zero Navegação Frustrante:** Modelos sem crédito pago (402) somem da lista sozinhos, sem necessidade de ir ao painel desmarcar manualmente.
3. **Preservação de Contexto e Intenção:** Se o usuário selecionou o provedor `LLM7.io` ou `Groq`, o sistema prioriza outro modelo funcional daquele mesmo provedor antes de transbordar para outros.
4. **Auto-Alinhamento do Seletor:** Quando um modelo de contingência responde, o seletor do chat sincroniza automaticamente para ele, garantindo que as próximas interações sigam no canal funcional.
