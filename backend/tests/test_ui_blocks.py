"""Testes para o módulo ui_blocks (validador, extrator, heurístico e tabela isolada)."""

from __future__ import annotations

import os
import tempfile
import pytest

from backend.ui_blocks.validate import validate_envelope, is_allowed_image_url
from backend.ui_blocks.extract import extract_ui
from backend.ui_blocks.should_offer import should_offer_ui


# ─── Validador de Envelope ────────────────────────────────────────────────────

def test_rejeita_versao_errada():
    assert validate_envelope('{"v":2,"blocks":[]}') is None


def test_rejeita_json_invalido():
    assert validate_envelope('{"v":1, "incompleto":') is None


def test_rejeita_acima_do_limite_tamanho():
    huge = '{"v":1,"blocks":[{"id":"a","type":"progress","label":"' + ("x" * 16500) + '"}]}'
    assert validate_envelope(huge) is None


def test_progress_valido():
    raw = '{"v":1,"blocks":[{"id":"seo","type":"progress","label":"Auditoria SEO","value":7,"max":10}]}'
    out = validate_envelope(raw)
    assert out is not None
    assert out["blocks"][0]["value"] == 7
    assert out["blocks"][0]["max"] == 10


def test_bloco_ruim_nao_derruba_o_bom():
    raw = '{"v":1,"blocks":[{"id":"ok","type":"progress","label":"A","value":1,"max":2},{"id":"ruim","type":"chart","kind":"pizza"}]}'
    out = validate_envelope(raw)
    assert out is not None
    assert [b["id"] for b in out["blocks"]] == ["ok"]


def test_card_e_filtro_imagem(monkeypatch):
    monkeypatch.setenv("INTELLIGENT_UI_IMAGE_HOSTS", "trusted.cdn.com")
    monkeypatch.setenv("INTELLIGENT_UI_ALLOW_PRIVATE_HTTP", "false")

    # URL relativa permitida
    raw_local = '{"v":1,"blocks":[{"id":"c1","type":"card","title":"Local","image":{"url":"/attachments/pic.png","alt":"Foto"}}]}'
    out = validate_envelope(raw_local)
    assert out is not None
    assert "image" in out["blocks"][0]

    # Host externo não confiável -> imagem removida, cartão mantido
    raw_unsafe = '{"v":1,"blocks":[{"id":"c2","type":"card","title":"Remoto","image":{"url":"https://evil.com/pic.png","alt":"Foto"}}]}'
    out_unsafe = validate_envelope(raw_unsafe)
    assert out_unsafe is not None
    assert "image" not in out_unsafe["blocks"][0]
    assert out_unsafe["blocks"][0]["title"] == "Remoto"

    # Host em INTELLIGENT_UI_IMAGE_HOSTS permitido
    raw_trusted = '{"v":1,"blocks":[{"id":"c3","type":"card","title":"Trusted","image":{"url":"https://trusted.cdn.com/pic.png","alt":"Foto"}}]}'
    out_trusted = validate_envelope(raw_trusted)
    assert out_trusted is not None
    assert "image" in out_trusted["blocks"][0]


def test_chart_bar_line_compare():
    # Bar válido
    bar_raw = {
        "v": 1,
        "blocks": [{
            "id": "ch1",
            "type": "chart",
            "title": "Custos",
            "kind": "bar",
            "x_key": "modelo",
            "series": [{"key": "usd", "label": "USD"}],
            "rows": [{"modelo": "A", "usd": 0.05}],
        }]
    }
    assert validate_envelope(bar_raw) is not None

    # Bar com 2 séries -> inválido para kind bar
    bar_invalid = {
        "v": 1,
        "blocks": [{
            "id": "ch1",
            "type": "chart",
            "title": "Custos",
            "kind": "bar",
            "x_key": "modelo",
            "series": [{"key": "usd"}, {"key": "brl"}],
            "rows": [{"modelo": "A", "usd": 0.05, "brl": 0.25}],
        }]
    }
    assert validate_envelope(bar_invalid) is None


def test_controls_send_message_e_set_model():
    raw_controls = {
        "v": 1,
        "blocks": [{
            "id": "ctrl1",
            "type": "controls",
            "title": "Executar",
            "submit_label": "Rodar",
            "fields": [
                {"id": "agente", "kind": "select", "options": [{"value": "seo", "label": "SEO"}, {"value": "code", "label": "Code"}]},
                {"id": "qtd", "kind": "range", "min": 1, "max": 10, "default": 5}
            ],
            "action": {
                "name": "send_message",
                "template": "Executar {agente} com qtd {qtd}"
            }
        }]
    }
    out = validate_envelope(raw_controls)
    assert out is not None
    assert out["blocks"][0]["action"]["name"] == "send_message"

    # Placeholder desconhecido no template descarta o bloco
    bad_template = dict(raw_controls)
    bad_template["blocks"] = [{
        "id": "ctrl2",
        "type": "controls",
        "title": "Executar",
        "submit_label": "Rodar",
        "fields": [{"id": "agente", "kind": "text"}],
        "action": {"name": "send_message", "template": "Executar {desconhecido}"}
    }]
    assert validate_envelope(bad_template) is None


def test_sandbox_valido():
    raw_sb = {
        "v": 1,
        "blocks": [{
            "id": "sb1",
            "type": "sandbox",
            "title": "Calculadora",
            "initial_height": 350,
            "html": "<div id='app'>calc</div>",
            "css": "#app { color: red; }",
            "js": "console.log(1);",
            "standalone_download": True
        }]
    }
    out = validate_envelope(raw_sb)
    assert out is not None
    assert out["blocks"][0]["initial_height"] == 350


# ─── Extrator de Fence ────────────────────────────────────────────────────────

def test_tira_fence_e_deixa_prosa():
    text = "Sete de dez já foram.\n\n```nexus-ui\n{\"v\":1,\"blocks\":[{\"id\":\"seo\",\"type\":\"progress\",\"label\":\"Auditoria SEO\",\"value\":7,\"max\":10}]}\n```"
    prose, env = extract_ui(text)
    assert "Sete de dez" in prose
    assert "nexus-ui" not in prose
    assert env is not None
    assert env["blocks"][0]["id"] == "seo"


def test_fence_aberto_nao_grava_json():
    prose, env = extract_ui("texto explicativo\n```nexus-ui\n{\"v\":1")
    assert env is None
    assert "nexus-ui" not in prose
    assert "texto explicativo" in prose


def test_multiplos_fences_usa_apenas_o_ultimo():
    text = (
        "Primeiro parágrafo.\n\n"
        "```nexus-ui\n{\"v\":1,\"blocks\":[{\"id\":\"p1\",\"type\":\"progress\",\"label\":\"Antigo\",\"value\":1,\"max\":2}]}\n```\n\n"
        "Segundo parágrafo.\n\n"
        "```nexus-ui\n{\"v\":1,\"blocks\":[{\"id\":\"p2\",\"type\":\"progress\",\"label\":\"Novo\",\"value\":2,\"max\":2}]}\n```"
    )
    prose, env = extract_ui(text)
    assert "Primeiro parágrafo" in prose
    assert "Segundo parágrafo" in prose
    assert "nexus-ui" not in prose
    assert env is not None
    assert env["blocks"][0]["id"] == "p2"


# ─── Heurístico de Oferta ────────────────────────────────────────────────────

def test_should_offer_ui_triggers():
    assert should_offer_ui("compare os custos dos modelos") is True
    assert should_offer_ui("mostre um gráfico de barras") is True
    assert should_offer_ui("qual o progresso das tarefas?") is True
    assert should_offer_ui("calcule a divisão da conta de 150 reais") is True
    assert should_offer_ui("bom dia, como você está?") is False
    assert should_offer_ui("me explique o conceito de recursão") is False

    # 3+ números e palavra-chave
    assert should_offer_ui("temos 10, 20 e 30 tokens com custo variável") is True
    assert should_offer_ui("10, 20 e 30 gatos correram") is False


# ─── Isolamento de Banco de Dados para Tabela Nova ───────────────────────────

@pytest.mark.asyncio
async def test_tabela_message_ui_blocks_isolada():
    """Valida que a tabela é criada e opera sem tocar no banco de produção."""
    import aiosqlite
    from backend import database as dbmod

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        # Inicializa o banco temporário
        original_db_path = dbmod.DB_PATH
        dbmod.DB_PATH = temp_db_path

        await dbmod.init_db()

        async with aiosqlite.connect(temp_db_path) as db:
            # Verifica se a tabela message_ui_blocks existe
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='message_ui_blocks'"
            )
            row = await cursor.fetchone()
            assert row is not None, "A tabela message_ui_blocks deve ser criada no init_db"

        dbmod.DB_PATH = original_db_path
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except OSError:
                pass
