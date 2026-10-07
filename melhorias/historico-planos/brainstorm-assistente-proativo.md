# Assistente Proativo — Brainstorm Nexus Local

## Visão
Transformar o Multi de chat reativo para assistente proativo que detecta interesse na conversa e pesquisa automaticamente.

## Gatilho
Quando o usuário demonstra emoção/interesse genuíno na conversa (não só mencionar entidade).

Exemplo: "vi que Gabriel e Shirley vão tocar em Blumenau, tô muito animado!" → IA pesquisa shows, data, local.

## Pipeline

1. **Detector** — analisa mensagem do usuário, decide se há interesse suficiente
2. **Executor** — busca em múltiplas fontes (web search, browser se necessário)
3. **Síntese** — transforma resultados em linguagem natural
4. **Entrega** — mensagem na mesma janela ou notificação

## Componentes

### A. Módulo de Detecção
- Análise de tom emocional da mensagem
- Identificação de entidades nomeadas
- Heurística: emoção + entidade = interesse

### B. Módulo de Pesquisa
- Web search (Brave/DuckDuckGo)
- Browser (Playwright) para sites que bloqueiam APIs
- Cache de resultados

### C. Módulo de Entrega
- Mensagem automática na mesma conversa
- Notificação se em outra janela
- Opção de aprofundar

## Uso Inicial
Pesquisa de eventos, notícias, curiosidades sobre tópicos que o usuário demonstra interesse.
