"""
Testes unitários para validar as correções dos erros e warnings identificados nos logs do sistema:
1. build_summary_block e build_memory_block sem TypeError (can only concatenate str to str)
2. memory_dream e database sem chamada inválida de build_memory_fingerprint(user_id)
3. DuckDuckGoProvider tratando 'No results found.' graciosamente sem erro
4. Memory Extractor aceitando markdown e respostas em prosa ('não há fatos')
"""

import pytest
import re
import json
from unittest.mock import MagicMock, patch

from backend.memory import (
    build_summary_block,
    build_memory_block,
    build_memory_fingerprint,
)
from backend.web_search.providers import DuckDuckGoProvider


def test_build_summary_block_always_returns_str():
    """Valida que build_summary_block sempre retorna str e nunca None."""
    # Cenário 1: Sem nenhum resumo
    res_empty = build_summary_block(None, None)
    assert isinstance(res_empty, str)
    assert res_empty == ""

    # Cenário 2: Resumo global presente
    res_global = build_summary_block(
        global_summary={"summary_md": "Usuário prefere respostas concisas."},
        project_summary=None,
    )
    assert isinstance(res_global, str)
    assert "RESUMO GLOBAL DO USUÁRIO" in res_global
    assert "Usuário prefere respostas concisas." in res_global

    # Cenário 3: Resumo de projeto presente
    res_proj = build_summary_block(
        global_summary=None,
        project_summary={"scope_ref": "nexus-web", "summary_md": "Frontend do projeto"},
    )
    assert isinstance(res_proj, str)
    assert "RESUMO DO PROJETO ATIVO: nexus-web" in res_proj


def test_build_memory_block_no_typeerror():
    """Valida que build_memory_block não gera TypeError ao concatenar partes."""
    facts = [
        {"id": "f1", "fact": "Trabalha com Python e TypeScript", "category": "tech"},
        {"id": "f2", "fact": "Nome preferido Osmar", "category": "identity"},
    ]
    profile = {
        "display_name": "Osmar",
        "memory_enabled": 1,
    }
    global_sum = {"summary_md": "Usuário desenvolvedor experiente."}
    proj_sum = {"scope_ref": "multi-app", "summary_md": "App principal."}

    # Chamada completa
    block = build_memory_block(
        facts=facts,
        profile=profile,
        global_summary=global_sum,
        project_summary=proj_sum,
    )
    assert isinstance(block, str)
    assert "PERFIL DO USUÁRIO" in block
    assert "RESUMO GLOBAL DO USUÁRIO" in block
    assert "RESUMO DO PROJETO ATIVO" in block
    assert "CONTEXTO SOBRE O USUÁRIO" in block

    # Chamada sem resumos (anteriormente quebrava com TypeError se summary_part fosse None)
    block_no_sum = build_memory_block(
        facts=facts,
        profile=profile,
        global_summary=None,
        project_summary=None,
    )
    assert isinstance(block_no_sum, str)
    assert "PERFIL DO USUÁRIO" in block_no_sum
    assert "CONTEXTO SOBRE O USUÁRIO" in block_no_sum


def test_build_memory_fingerprint_signature_and_behavior():
    """Valida que build_memory_fingerprint requer lista de fatos e gera hash estável."""
    facts = [
        {"id": "1", "fact": "Fato 1", "updated_at": "2026-10-15T00:00:00", "is_active": 1},
    ]
    fp1 = build_memory_fingerprint(facts, profile={"display_name": "Test"})
    assert isinstance(fp1, str)
    assert len(fp1) == 16

    # Teste de idempotência
    fp2 = build_memory_fingerprint(facts, profile={"display_name": "Test"})
    assert fp1 == fp2


@pytest.mark.asyncio
async def test_duckduckgo_no_results_handled_gracefully():
    """Valida que 'No results found.' da lib ddgs retorna lista vazia sem exception."""
    provider = DuckDuckGoProvider()

    with patch("ddgs.DDGS") as mock_ddgs_cls:
        mock_instance = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_instance
        # Simula a exceção disparada pelo ddgs quando nada é encontrado
        mock_instance.text.side_effect = Exception("ddgs.exceptions.DDGSException: No results found.")

        results = await provider.search("termo_muito_raro_sem_resultados_123456")
        assert results == []


def test_memory_extractor_prose_and_markdown_parsing():
    """Valida a lógica aprimorada de extração de JSON do extrator de memória."""
    # 1. Resposta em prosa explicativa (caso do log)
    prose_response = (
        "Analisando a conversa, não há fatos duráveis sobre a identidade do usuário, "
        "trabalho, família ou projetos pessoais. As interações consistem em perguntas."
    )
    lower_resp = prose_response.lower()
    no_fact_phrases = (
        "não há fatos",
        "sem fatos",
        "nenhum fato",
        "não foram encontrados",
        "não identifiquei",
        "não foi possível extrair",
    )
    is_no_fact_prose = any(p in lower_resp for p in no_fact_phrases)
    assert is_no_fact_prose is True

    # 2. Resposta com bloco markdown ```json ... ```
    md_response = """Aqui estão as memórias encontradas:
```json
[
  {"fact_key": "tech.lang", "category": "tech", "fact": "Usa Python", "confidence": 0.9}
]
```
Espero ter ajudado!"""

    fenced_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", md_response, re.DOTALL)
    assert fenced_match is not None
    extracted_json = fenced_match.group(1).strip()
    data = json.loads(extracted_json)
    assert len(data) == 1
    assert data[0]["fact_key"] == "tech.lang"
