"""test_system_prompt_temporal.py — Testes de ancoragem temporal e instrução anti-corte do system prompt.

Valida:
1. Injeção dinâmica da data atual, dia da semana, mês e ano no system prompt base.
2. Diretriz explícita anti-alucinação de corte de conhecimento (prevenção de taxar o ano corrente como futuro ou hipotético).
3. Propagação da data atual em resolve_project_context com suporte a fuso horário do cliente.
"""

from __future__ import annotations

import datetime
import pytest
from unittest.mock import AsyncMock

from backend.orchestration.build_context import (
    BASE_SYSTEM_PROMPT,
    BASE_SYSTEM_PROMPT_TEMPLATE,
    format_base_system_prompt,
    get_current_temporal_context,
    resolve_project_context,
)


def test_get_current_temporal_context_fixed_date():
    """Valida a formatação correta de dia da semana, dia, mês por extenso e ano."""
    # 20 de Outubro de 2026 é Terça-feira (weekday 1)
    fixed_dt = datetime.datetime(2026, 10, 20, 14, 30, 0)
    date_str, year_str = get_current_temporal_context(fixed_dt)
    assert date_str == "Terça-feira, 20 de Outubro de 2026"
    assert year_str == "2026"


def test_get_current_temporal_context_default_now():
    """Valida execução padrão sem parâmetro now."""
    date_str, year_str = get_current_temporal_context()
    now = datetime.datetime.now()
    assert str(now.year) == year_str
    assert year_str in date_str


def test_format_base_system_prompt_contains_temporal_grounding():
    """Garante que a seção CONTEXTO TEMPORAL e a regra anti-alucinação estão presentes."""
    fixed_dt = datetime.datetime(2026, 6, 15, 10, 0, 0)
    prompt = format_base_system_prompt(
        active_model="Qwen 2.5 72B",
        active_provider="Groq",
        now=fixed_dt,
    )

    assert "CONTEXTO TEMPORAL" in prompt
    assert "Data atual do sistema: Segunda-feira, 15 de Junho de 2026 (Ano: 2026)." in prompt
    assert "Quaisquer menções a \"hoje\", \"este ano\", \"atualmente\" ou \"recente\" referem-se estritamente ao ano de 2026." in prompt
    assert "Seu conhecimento pré-treinado possui uma data de corte no passado." in prompt
    assert "Eventos, fatos e datas referentes a 2026 pertencem à realidade presente e NÃO devem ser considerados \"conteúdo futuro\", \"simulado\" ou \"hipotético\"." in prompt
    assert "IDENTIDADE E TRANSPARÊNCIA" in prompt
    assert "Qwen 2.5 72B" in prompt
    assert "via Groq" in prompt


@pytest.mark.asyncio
async def test_resolve_project_context_injects_temporal_grounding():
    """Valida se resolve_project_context propaga a data fornecida via now no prompt final."""
    from unittest.mock import MagicMock

    class AsyncContextManagerMock:
        def __init__(self, return_val):
            self.return_val = return_val

        async def __aenter__(self):
            return self.return_val

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    cur_conv = AsyncMock()
    cur_conv.fetchone = AsyncMock(return_value=None)

    cur_model = AsyncMock()
    cur_model.fetchone = AsyncMock(return_value=("Llama 3.3 70B", "Groq"))

    def execute_side_effect(query, params=None):
        if "FROM conversations" in query:
            return AsyncContextManagerMock(cur_conv)
        elif "FROM models" in query:
            return AsyncContextManagerMock(cur_model)
        return AsyncContextManagerMock(cur_conv)

    db_mock = MagicMock()
    db_mock.execute.side_effect = execute_side_effect
    db_mock.commit = AsyncMock()

    fixed_dt = datetime.datetime(2026, 10, 20, 15, 0, 0)
    proj_id, system_instruction = await resolve_project_context(
        db=db_mock,
        ws=AsyncMock(),
        conversation_id="conv-123",
        request_project_id=None,
        user={"id": "usr-1"},
        model_id="llama-3.3-70b",
        provider_id="groq",
        user_message="Quem são os candidatos?",
        history=[],
        project_context_debug=False,
        base_system=BASE_SYSTEM_PROMPT,
        user_mem_text="",
        now=fixed_dt,
    )

    assert proj_id is None
    assert "CONTEXTO TEMPORAL" in system_instruction
    assert "Data atual do sistema: Terça-feira, 20 de Outubro de 2026 (Ano: 2026)." in system_instruction
    assert "Ano: 2026" in system_instruction
    assert "Llama 3.3 70B" in system_instruction
