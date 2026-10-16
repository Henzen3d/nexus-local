"""backend/tools/tool_definitions.py — Schemas de ferramentas (function calling) e handler unificado.
Compatível com OpenAI, Anthropic, Gemini e provedores compatíveis com JSON Schema.
"""
from __future__ import annotations

from typing import Any, Optional
import aiosqlite

from backend.tools.base import ToolResult
from backend.tools.dispatcher import dispatch_tool


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Obtém condições meteorológicas atuais e previsão do tempo para uma cidade ou coordenadas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "Nome da cidade e estado/país (ex: 'São Paulo', 'Rio de Janeiro, BR', 'Lisboa')",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Número de dias para a previsão (1 a 7)",
                        "default": 3,
                    },
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_currency",
            "description": "Consulta cotações e conversão entre moedas mundiais e criptomoedas em tempo real.",
            "parameters": {
                "type": "object",
                "properties": {
                    "from": {
                        "type": "string",
                        "description": "Código da moeda de origem (ex: 'USD', 'EUR', 'BRL', 'GBP', 'BTC')",
                    },
                    "to": {
                        "type": "string",
                        "description": "Código da moeda de destino (ex: 'BRL', 'USD', 'EUR')",
                        "default": "BRL",
                    },
                    "amount": {
                        "type": "number",
                        "description": "Valor monetário a converter",
                        "default": 1.0,
                    },
                },
                "required": ["from"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_brasil",
            "description": "Consulta dados oficiais brasileiros: CEP (endereço completo), CNPJ (dados cadastrais de empresas), DDD (cidades atendidas) e feriados nacionais.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["cep", "cnpj", "ddd", "feriados"],
                        "description": "Tipo de consulta",
                    },
                    "value": {
                        "type": "string",
                        "description": "Valor a ser consultado (número do CEP, CNPJ ou código DDD)",
                    },
                    "year": {
                        "type": "integer",
                        "description": "Ano para consulta de feriados (ex: 2026)",
                    },
                },
                "required": ["type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wikipedia",
            "description": "Busca artigos, biografias, fatos históricos e definições conceituais na Wikipedia para reduzir alucinação.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Termo de busca, pessoa, evento ou conceito",
                    },
                    "lang": {
                        "type": "string",
                        "description": "Idioma da Wikipedia (ex: 'pt', 'en', 'es')",
                        "default": "pt",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Busca manchetes e notícias de última hora sobre tecnologia, economia, mundo ou tópicos específicos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tópico de notícias ou palavra-chave",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Quantidade máxima de notícias a retornar (1 a 10)",
                        "default": 3,
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate_text",
            "description": "Traduz trechos de texto entre dezenas de idiomas com qualidade neural.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Texto a ser traduzido",
                    },
                    "source": {
                        "type": "string",
                        "description": "Código do idioma de origem (ex: 'auto', 'en', 'pt', 'es')",
                        "default": "auto",
                    },
                    "target": {
                        "type": "string",
                        "description": "Código do idioma de destino (ex: 'pt', 'en', 'es')",
                        "default": "pt",
                    },
                },
                "required": ["text", "target"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Executa com segurança código fonte em Python, JavaScript, Java, C++, Go, Rust, etc., em ambiente sandbox isolado.",
            "parameters": {
                "type": "object",
                "properties": {
                    "language": {
                        "type": "string",
                        "description": "Linguagem de programação (ex: 'python', 'javascript', 'cpp', 'rust', 'go')",
                    },
                    "code": {
                        "type": "string",
                        "description": "Código fonte a ser compilado e executado",
                    },
                    "stdin": {
                        "type": "string",
                        "description": "Entrada padrão (stdin) opcional",
                        "default": "",
                    },
                },
                "required": ["language", "code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "render_diagram",
            "description": "Renderiza diagramas de arquitetura (Mermaid, PlantUML, D2, Graphviz) ou gráficos de dados em SVG limpo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["mermaid", "plantuml", "d2", "graphviz", "chart"],
                        "description": "Tipo de diagrama ou gráfico",
                    },
                    "source": {
                        "type": "string",
                        "description": "Código-fonte da especificação do diagrama ou JSON do Chart.js",
                    },
                },
                "required": ["type", "source"],
            },
        },
    },
]


TOOL_NAME_TO_FAMILY = {
    "get_weather": "weather",
    "get_currency": "currency",
    "lookup_brasil": "brasil",
    "search_wikipedia": "knowledge",
    "get_news": "news",
    "translate_text": "translation",
    "execute_code": "code_exec",
    "render_diagram": "diagrams",
}


async def handle_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: str,
    db: aiosqlite.Connection,
) -> ToolResult:
    """Executa a chamada de ferramenta originada pelo function calling do modelo."""
    family = TOOL_NAME_TO_FAMILY.get(tool_name)
    if not family:
        return ToolResult(
            family="unknown",
            provider="unknown",
            success=False,
            error=f"Ferramenta desconhecida: '{tool_name}'",
        )

    return await dispatch_tool(
        family=family,
        params=arguments,
        user_id=user_id,
        db=db,
    )
