"""Testes da política de janela de contexto — item 04."""

from pathlib import Path

from backend.orchestration.context_window import (
    history_after_trim_failure,
    resolve_context_length,
)


def test_nome_nao_entra_na_funcao_api_8192_fica_8192():
    assert resolve_context_length(8192) == 8192


def test_registry_velho_nao_sobe_o_valor_da_api():
    assert resolve_context_length(8192, registry_ctx=131072, verified_at="2026-07-15") == 8192


def test_registry_recente_pode_subir():
    assert resolve_context_length(8192, registry_ctx=32768, verified_at="2026-10") == 32768


def test_api_ausente_cai_no_default():
    assert resolve_context_length(None) == 8192
    assert resolve_context_length(0) == 8192


def test_falha_de_poda_guarda_as_ultimas_12():
    history = [{"i": i} for i in range(20)]
    kept = history_after_trim_failure(history)
    assert len(kept) == 12
    assert kept[0]["i"] == 8
    assert kept[-1]["i"] == 19


def test_falha_de_poda_com_lista_curta_nao_inventa():
    history = [{"i": 1}]
    assert history_after_trim_failure(history) == [{"i": 1}]


def test_admin_nao_infla_llama_por_nome():
    source = Path("backend/routers/admin.py").read_text(encoding="utf-8")
    assert 'elif "llama-3" in name_lower or "llama-4" in name_lower:' not in source
    assert "resolve_context_length" in source


def test_chat_nao_manda_historico_inteiro_se_a_poda_falha():
    source = Path("backend/routers/chat.py").read_text(encoding="utf-8")
    assert "history_after_trim_failure" in source
    assert '"history_trimmed"' in source
