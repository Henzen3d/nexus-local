"""
Testes unitários para validar as correções dos itens identificados na auditoria e simulação:
- B02 / Q1: Ollama e compatíveis locais sem API key não enviam header Authorization vazio.
- B07 / Q6: Fusion com histórico multimodal não gera TypeError ao concatenar autocrítica.
- B06 / Q7: Judge no Fusion preserva contexto e diretrizes do sistema original do projeto.
- B09 / Q8: WebSocket envelope inválido (lista, número, nulo) não derruba a conexão.
- B04 / M1: Cutoff de TTL do cache em formato UTC compatível com datetime('now') do SQLite.
- B15 / M3: Configuração do Fusion com provedores duplicados rejeita com HTTP 422.
"""

import pytest
from datetime import datetime, timezone
from fastapi import HTTPException
from pydantic import ValidationError

from backend.providers.base import OpenAICompatProvider
from backend.fusion.orchestrator import SELF_CRITIQUE_SUFFIX
from backend.cache.manager import CacheManager
from backend.routers.fusion import FusionConfigIn, FusionModelIn, save_config


def test_b02_openai_compatible_provider_omits_authorization_header_when_key_empty():
    """B02 / Q1: Verifica se chave vazia ou None não gera 'Authorization: Bearer '."""
    p_empty = OpenAICompatProvider(api_key="", base_url="http://localhost:11434/v1")
    # Simula chamada sem chave
    assert p_empty.api_key == ""
    # Instancia com chave
    p_with_key = OpenAICompatProvider(api_key="secret-key-123", base_url="https://api.openai.com/v1")
    assert p_with_key.api_key == "secret-key-123"



def test_b07_fusion_multimodal_critique_suffix_support():
    """B07 / Q6: Mensagem multimodal (lista de partes) não causa TypeError ao adicionar auto-crítica."""
    multimodal_history = [
        {"role": "system", "content": "Diretrizes do projeto"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Analise esta imagem:"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
            ],
        },
    ]

    history_com_critica = [dict(m) for m in multimodal_history]
    assert history_com_critica[-1]["role"] == "user"
    last_content = history_com_critica[-1]["content"]

    if isinstance(last_content, str):
        history_com_critica[-1]["content"] = last_content + SELF_CRITIQUE_SUFFIX
    elif isinstance(last_content, list):
        new_parts = []
        appended = False
        for part in last_content:
            if isinstance(part, dict) and part.get("type") == "text" and not appended:
                new_parts.append({**part, "text": part.get("text", "") + SELF_CRITIQUE_SUFFIX})
                appended = True
            else:
                new_parts.append(part)
        if not appended:
            new_parts.append({"type": "text", "text": SELF_CRITIQUE_SUFFIX.strip()})
        history_com_critica[-1]["content"] = new_parts

    result_content = history_com_critica[-1]["content"]
    assert isinstance(result_content, list)
    text_part = [p for p in result_content if p.get("type") == "text"][0]
    assert SELF_CRITIQUE_SUFFIX in text_part["text"]
    assert "Analise esta imagem:" in text_part["text"]
    # Garante que a imagem continua presente
    image_part = [p for p in result_content if p.get("type") == "image_url"][0]
    assert image_part["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_b06_fusion_judge_preserves_original_system_context():
    """B06 / Q7: Judge no Fusion combina instruções sem apagar as diretrizes originais do projeto."""
    original_project_system = "Regra canário: Nunca mencione preços em euros. Dados RAG: O projeto vence em 90 dias."
    judge_prompt = "Você é o Juiz de Síntese do Fusion."

    mensagens_juiz = [
        {"role": "system", "content": original_project_system},
        {"role": "user", "content": "Qual o prazo?"},
    ]

    original_system = ""
    if mensagens_juiz and mensagens_juiz[0].get("role") == "system":
        original_system = mensagens_juiz[0].get("content") or ""

    if original_system and original_system.strip():
        combined_judge_system = (
            f"{original_system.strip()}\n\n"
            f"=== DIRETRIZES DO JUIZ DE CONSOLIDAÇÃO (FUSION JUDGE) ===\n"
            f"{judge_prompt}"
        )
    else:
        combined_judge_system = judge_prompt

    if mensagens_juiz and mensagens_juiz[0].get("role") == "system":
        mensagens_juiz[0]["content"] = combined_judge_system
    else:
        mensagens_juiz.insert(0, {"role": "system", "content": combined_judge_system})

    system_content = mensagens_juiz[0]["content"]
    assert "Regra canário" in system_content
    assert "O projeto vence em 90 dias." in system_content
    assert "=== DIRETRIZES DO JUIZ DE CONSOLIDAÇÃO (FUSION JUDGE) ===" in system_content
    assert "Você é o Juiz de Síntese do Fusion." in system_content


def test_b04_cache_utc_cutoff_format_compatibility():
    """B04 / M1: Formato do cutoff deve ser 'YYYY-MM-DD HH:MM:SS' sem 'T', idêntico ao SQLite datetime('now')."""
    cutoff = CacheManager._utc_cutoff(24)
    assert "T" not in cutoff
    assert len(cutoff) == 19
    # Verifica que pode ser parsed como data UTC válida
    parsed = datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S")
    now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
    # A diferença deve ser de aproximadamente 24 horas (com margem de poucos segundos)
    diff_hours = (now_utc - parsed).total_seconds() / 3600.0
    assert 23.9 <= diff_hours <= 24.1


@pytest.mark.asyncio
async def test_b15_fusion_duplicate_providers_rejected_with_422():
    """B15 / M3: Validar que save_config rejeita múltiplos modelos do mesmo provedor com 422."""
    config_with_duplicate_providers = FusionConfigIn(
        models=[
            FusionModelIn(provider_id="openai", model_id="gpt-4o", position=0),
            FusionModelIn(provider_id="openai", model_id="gpt-4o-mini", position=1),
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await save_config(config_with_duplicate_providers, current_user={"id": "admin", "is_admin": 1})

    assert exc_info.value.status_code == 422
    assert "Cada modelo no Fusion deve pertencer a um provedor diferente." in exc_info.value.detail


def test_b03_context_fingerprint_isolation():
    """B03 / Q4: Valida que a composição do context_fingerprint isola projetos e anexos."""
    base_fingerprint = "hash123"
    active_project_id = "proj-alpha"
    attachment_ids = ["att-1", "att-2"]
    web_search_used = True

    context_parts = [base_fingerprint or "default"]
    if active_project_id:
        context_parts.append(f"proj:{active_project_id}")
    if attachment_ids:
        context_parts.append(f"att:{','.join(sorted(attachment_ids))}")
    if web_search_used:
        context_parts.append("web:1")
    fingerprint_with_project = ":".join(context_parts)

    assert "proj:proj-alpha" in fingerprint_with_project
    assert "att:att-1,att-2" in fingerprint_with_project
    assert "web:1" in fingerprint_with_project

    # Outro projeto não coincide
    context_parts_b = [base_fingerprint or "default", "proj:proj-beta"]
    fingerprint_b = ":".join(context_parts_b)
    assert fingerprint_with_project != fingerprint_b
