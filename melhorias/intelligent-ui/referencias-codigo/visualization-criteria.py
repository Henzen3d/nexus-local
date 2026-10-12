"""
OpenIntelligentUI (CopilotKit) — Visualization Router Criteria (Referência Conceitual)
Fonte: CopilotKit/OpenIntelligentUI (apps/agent/src/visualization_router.py)

NOTA DE IMPLEMENTAÇÃO NO MULTI+:
Estes critérios servem como taxonomia de referência teórica.
No Multi+ / Nexus Local, NÃO utilizamos LLM router externo nem estes tipos literais
(como scatter_plot ou animated_route). O sistema utiliza o classificador heurístico
determinístico e enxuto de 400 tokens (backend/ui_blocks/should_offer.py) especificado
na Seção 8 de 00-visao-e-spec.md, mapeando exclusivamente para os 5 blocos do contrato
nexus-ui/1: progress, card, chart (bar/line/compare), controls e sandbox.
"""

VISUALIZATION_CRITERIA = {
    "text": (
        "Fatos diretos, prosa, redação, código, conversa cotidiana ou pedidos de esclarecimento. "
        "Nenhum visual necessário."
    ),
    "table": (
        "Tabela básica: valores exatos, registros ou comparação simples lado a lado. "
        "Sem interação customizada."
    ),
    "bar_chart": (
        "Comparar grandezas ou ranquear categorias com um gráfico de barras."
    ),
    "line_chart": (
        "Mostrar tendências, séries temporais ou evolução de dados contínuos com um gráfico de linhas."
    ),
    "scatter_plot": (
        "Mostrar correlação e dispersão entre duas variáveis numéricas."
    ),
    "distribution": (
        "Mostrar distribuição de observações numéricas com histograma ou box plot."
    ),
    "part_to_whole": (
        "Mostrar proporções de um total significativo (poucas fatias / categorias)."
    ),
    "flowchart": (
        "Explicar etapas, fluxos lógicos, processos de decisão, ramificações ou dependências."
    ),
    "static_diagram": (
        "Explicar estrutura espacial, topologia ou relações onde interação agrega pouco valor."
    ),
    "interactive_diagram": (
        "Explicar um mecanismo ou modelo dinâmico onde o usuário ganha entendimento ao alterar controles e variáveis."
    ),
    "calculator": (
        "Calcular resultados dinâmicos a partir de entradas ajustáveis do usuário com fórmulas e unidades (ex: divisão de conta, simulador de juros, conversor)."
    ),
    "animated_route": (
        "Itinerários de viagem ou percursos sequenciais com paradas numeradas e cartões vinculados."
    ),
}

ROUTER_SYSTEM_INSTRUCTION = """
Selecione o formato de apresentação mais eficiente para a mensagem do usuário:
- Escolha 'text' quando o visual não agregar valor ou faltarem dados essenciais.
- Escolha componentes nativos (table, card, progress, chart) para dados tabulares, listas ou séries temporais diretas.
- Escolha ferramentas interativas (calculator, interactive_diagram) apenas quando sliders, entradas e recálculo imediato facilitarem a compreensão.
""".strip()
