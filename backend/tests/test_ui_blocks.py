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


def test_should_offer_ui_sem_falsos_positivos_por_radical():
    # Palavras comuns que contêm os radicais da spec mas não pedem visual
    assert should_offer_ui("compartilhe o link do documento comigo") is False
    assert should_offer_ui("preciso comparecer na reunião amanhã") is False
    assert should_offer_ui("rode as duas tarefas simultaneamente") is False
    assert should_offer_ui("o barraco embarrou com a chuva") is False
    assert should_offer_ui("imprima o cartaz e troque o cartucho") is False
    assert should_offer_ui("qual a diferença entre simulação e simultaneidade?") is True  # 'simulação' vale
    # Formas legítimas continuam disparando
    assert should_offer_ui("faça um comparativo entre as opções") is True
    assert should_offer_ui("simule o financiamento em 36 vezes") is True
    assert should_offer_ui("quais etapas faltam?") is True
    assert should_offer_ui("mostra a foto da placa") is True
    assert should_offer_ui("cálculo do IMC") is True
    assert should_offer_ui("GPT-4o vs Claude") is True
    # Números com palavra de medida colada em outra palavra não contam
    assert should_offer_ui("1, 2 e 3 contratempos no modelito") is False


def test_catalogo_cabe_no_teto_e_tem_as_regras_da_spec():
    from pathlib import Path

    from itertools import combinations
    from backend.ui_blocks.catalog import MODULE_NAMES, compose_catalog

    for combination in combinations(MODULE_NAMES, 3):
        assert len(compose_catalog(combination)) / 4 <= 450
    text = (Path(__file__).resolve().parent.parent / "ui_blocks" / "catalog.txt").read_text(encoding="utf-8")
    text += "\n".join((Path(__file__).resolve().parent.parent / "ui_blocks" / "catalog_modules" / f"{name}.txt").read_text(encoding="utf-8") for name in MODULE_NAMES)
    for frase in (
        "Máximo 6 blocos",
        "info|success|warning|danger",
        "up|down|flat",
        "sem repetir o que a prosa já respondeu",
        "Sem cor",
        "{id_do_campo}",
        "não invente id de modelo",
        "URL de imagem só se for arquivo do app ou host da lista confiável",
        "Não escreva HTML na bolha principal",
        "```nexus-ui",
        "pending|active|done|error",
        "bar|line|compare",
        "text|select|number|range",
    ):
        assert frase in text, f"catálogo sem a linha: {frase}"
    # Sanidade: o exemplo do catálogo é um envelope válido (modelo que copiar acerta),
    # e as menções inline a ```nexus-ui na prosa do catálogo não são tratadas como fence.
    _clean, envelope = extract_ui(text)
    assert envelope is not None and envelope["blocks"][0]["type"] == "progress"
    assert "use SEMPRE o nome de fence ```nexus-ui" in _clean


def test_mencao_inline_a_fence_nao_e_fence():
    text = "Peça ao modelo para usar o fence ```nexus-ui no final, assim: ```nexus-ui {...} ``` e pronto."
    prose, env = extract_ui(text)
    assert env is None
    assert prose == text  # prosa intacta: nada foi engolido

    # Abertura precisa estar no início da linha; indentação de até 3 espaços vale
    indented = '   ```nexus-ui\n{"v":1,"blocks":[{"id":"p","type":"progress","label":"A","value":1,"max":2}]}\n   ```'
    prose, env = extract_ui("Texto.\n\n" + indented)
    assert env is not None and prose == "Texto."

    # Fence aberto em streaming só conta no início da linha
    prose, env = extract_ui("falando de ```nexus-ui no meio da frase")
    assert env is None and prose == "falando de ```nexus-ui no meio da frase"
    prose, env = extract_ui("Texto.\n```nexus-ui\n{\"v\":1,\"blo")
    assert env is None and prose == "Texto."


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


@pytest.mark.asyncio
async def test_recuperacao_ui_blocks_em_conversa():
    import json
    import tempfile
    import os
    import aiosqlite
    import backend.database as dbmod
    from backend.orchestration.persist_turn import save_ui_blocks

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name

    try:
        original_db_path = dbmod.DB_PATH
        dbmod.DB_PATH = temp_db_path
        await dbmod.init_db()

        async with aiosqlite.connect(temp_db_path) as db:
            envelope = {
                "v": 1,
                "blocks": [{"id": "prog1", "type": "progress", "label": "Deploy", "value": 2, "max": 5}]
            }
            await save_ui_blocks(db, "msg_test_123", envelope, source="model")

            async with db.execute(
                "SELECT message_id, payload FROM message_ui_blocks WHERE message_id = ?",
                ("msg_test_123",)
            ) as cur:
                row = await cur.fetchone()
                assert row is not None
                mid, payload_str = row
                parsed = json.loads(payload_str)
                assert parsed["v"] == 1
                assert parsed["blocks"][0]["label"] == "Deploy"

        dbmod.DB_PATH = original_db_path
    finally:
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except OSError:
                pass



# ─── Contrato estrito (alinhado à spec 00-visao-e-spec.md, seção 4) ──────────

_VALID_PROGRESS = {"id": "seo", "type": "progress", "label": "A", "value": 1, "max": 2}


def test_v_diferente_de_1_descarta_envelope_mesmo_com_bloco_valido():
    assert validate_envelope({"v": 2, "blocks": [dict(_VALID_PROGRESS)]}) is None
    # `v` ausente é tolerado
    assert validate_envelope({"blocks": [dict(_VALID_PROGRESS)]}) is not None


def test_chart_kind_invalido_descarta_o_bloco():
    pizza = {
        "v": 1,
        "blocks": [{
            "id": "c", "type": "chart", "kind": "pizza", "x_key": "x",
            "series": [{"key": "y"}], "rows": [{"x": "a", "y": 1}],
        }],
    }
    assert validate_envelope(pizza) is None
    # `kind` ausente assume `bar`
    sem_kind = {"v": 1, "blocks": [{"id": "c", "type": "chart", "x_key": "x", "series": [{"key": "y"}], "rows": [{"x": "a", "y": 1}]}]}
    out = validate_envelope(sem_kind)
    assert out is not None and out["blocks"][0]["kind"] == "bar"


def test_controls_acao_desconhecida_ou_ausente_descarta_o_bloco():
    base = {"id": "k", "type": "controls", "fields": [{"id": "n", "kind": "text", "label": "N"}]}
    assert validate_envelope({"v": 1, "blocks": [dict(base, action={"name": "run_shell", "template": "x"})]}) is None
    assert validate_envelope({"v": 1, "blocks": [dict(base)]}) is None
    ok = validate_envelope({"v": 1, "blocks": [dict(base, action={"name": "send_message", "template": "Nota: {n}"})]})
    assert ok is not None and ok["blocks"][0]["action"]["name"] == "send_message"


def test_controls_corta_em_quatro_fields():
    fields = [{"id": f"f{i}", "kind": "text", "label": "F"} for i in range(6)]
    out = validate_envelope({"v": 1, "blocks": [{"id": "k", "type": "controls", "fields": fields, "action": {"name": "send_message", "template": "ok"}}]})
    assert out is not None
    assert len(out["blocks"][0]["fields"]) == 4


def test_sandbox_initial_height_float_e_limites():
    out = validate_envelope({"v": 1, "blocks": [{"id": "s", "type": "sandbox", "title": "T", "html": "<div>x</div>", "initial_height": 340.0}]})
    assert out is not None and out["blocks"][0]["initial_height"] == 340
    out = validate_envelope({"v": 1, "blocks": [{"id": "s", "type": "sandbox", "title": "T", "html": "<div>x</div>", "initial_height": 9999}]})
    assert out["blocks"][0]["initial_height"] == 300


def test_filtro_de_imagem_usa_parametros_antes_do_ambiente(monkeypatch):
    monkeypatch.delenv("INTELLIGENT_UI_IMAGE_HOSTS", raising=False)
    monkeypatch.delenv("INTELLIGENT_UI_ALLOW_PRIVATE_HTTP", raising=False)
    # Sem env e sem parâmetros: recusa
    assert is_allowed_image_url("https://cdn.exemplo.com/a.jpg") is False
    assert is_allowed_image_url("http://192.168.0.20/foto.jpg") is False
    # Parâmetros explícitos (config do painel) liberam
    assert is_allowed_image_url("https://cdn.exemplo.com/a.jpg", ["cdn.exemplo.com"], False) is True
    assert is_allowed_image_url("http://192.168.0.20/foto.jpg", [], True) is True
    # Parâmetro explícito vazio NÃO cai no env
    monkeypatch.setenv("INTELLIGENT_UI_IMAGE_HOSTS", "cdn.exemplo.com")
    assert is_allowed_image_url("https://cdn.exemplo.com/a.jpg", [], False) is False
    assert is_allowed_image_url("https://cdn.exemplo.com/a.jpg") is True
    # extract_ui repassa os parâmetros
    text = 'Veja.\n\n```nexus-ui\n{"v":1,"blocks":[{"id":"c","type":"card","title":"X","image":{"url":"https://img.casa.lan/a.jpg","alt":"foto"}}]}\n```'
    _, env_default = extract_ui(text)
    _, env_param = extract_ui(text, image_hosts=["img.casa.lan"], allow_private_http=False)
    assert "image" not in env_default["blocks"][0]
    assert env_param["blocks"][0]["image"]["url"] == "https://img.casa.lan/a.jpg"


# ─── Configuração em runtime (painel admin > .env > padrão) ──────────────────

def test_normalize_hosts_limpa_esquema_porta_caminho_e_duplicados():
    from backend.ui_blocks.config import normalize_hosts

    assert normalize_hosts("https://CDN.Exemplo.com:8443/pasta, cdn.exemplo.com, user:pw@img.casa.lan/x?y") == [
        "cdn.exemplo.com",
        "img.casa.lan",
    ]
    assert normalize_hosts(["192.168.0.20", "", "nao vale!", "ok.local"]) == ["192.168.0.20", "ok.local"]
    assert normalize_hosts(None) == []


@pytest.mark.asyncio
async def test_config_env_vale_ate_alguem_salvar_no_painel(monkeypatch):
    import aiosqlite
    from backend import database as dbmod
    from backend.ui_blocks.config import get_intelligent_ui_config, update_intelligent_ui_config

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        temp_db_path = f.name
    original = dbmod.DB_PATH
    try:
        dbmod.DB_PATH = temp_db_path
        await dbmod.init_db()
        async with aiosqlite.connect(temp_db_path) as db:
            # 1) sem linha e sem env → desligado
            monkeypatch.delenv("INTELLIGENT_UI_ENABLED", raising=False)
            monkeypatch.delenv("INTELLIGENT_UI_IMAGE_HOSTS", raising=False)
            monkeypatch.delenv("INTELLIGENT_UI_ALLOW_PRIVATE_HTTP", raising=False)
            cfg = await get_intelligent_ui_config(db)
            assert cfg.enabled is False and cfg.image_hosts == [] and cfg.source == "default"

            # 2) env liga → vale
            monkeypatch.setenv("INTELLIGENT_UI_ENABLED", "true")
            monkeypatch.setenv("INTELLIGENT_UI_IMAGE_HOSTS", "cdn.exemplo.com")
            cfg = await get_intelligent_ui_config(db)
            assert cfg.enabled is True and cfg.image_hosts == ["cdn.exemplo.com"] and cfg.source == "env"

            # 3) painel salva → tabela passa a mandar, mesmo com env dizendo o contrário
            saved = await update_intelligent_ui_config(db, {"enabled": False, "image_hosts": "img.casa.lan"})
            assert saved.enabled is False and saved.image_hosts == ["img.casa.lan"] and saved.source == "db"
            monkeypatch.setenv("INTELLIGENT_UI_ENABLED", "true")
            cfg = await get_intelligent_ui_config(db)
            assert cfg.enabled is False and cfg.source == "db"

            # 4) merge: só o campo enviado muda
            saved = await update_intelligent_ui_config(db, {"allow_private_http": True})
            assert saved.allow_private_http is True and saved.image_hosts == ["img.casa.lan"] and saved.enabled is False
    finally:
        dbmod.DB_PATH = original
        if os.path.exists(temp_db_path):
            try:
                os.remove(temp_db_path)
            except OSError:
                pass


# ─── Telemetria ──────────────────────────────────────────────────────────────

def test_telemetria_motivos_de_descarte():
    from backend.ui_blocks.telemetry import IntelligentUiTelemetry, inspect_fence

    t = IntelligentUiTelemetry()
    ok = '```nexus-ui\n{"v":1,"blocks":[{"id":"p","type":"progress","label":"A","value":1,"max":2},{"id":"x","type":"chart","kind":"radar"}]}\n```'
    # Oferecido, produzido, válido, 1 bloco caiu
    s = t.record_turn(offered=True, text="Oi.\n\n" + ok, envelope=validate_envelope('{"v":1,"blocks":[{"id":"p","type":"progress","label":"A","value":1,"max":2}]}'))
    assert s["produced"] and s["valid"] and s["blocks_in"] == 2 and s["blocks_out"] == 1 and s["blocks_dropped"] == 1
    # Oferecido, sem fence → no_fence
    s = t.record_turn(offered=True, text="Só prosa.", envelope=None)
    assert s["reason"] == "no_fence"
    # Não oferecido e sem fence → caminho normal, não conta como descarte
    t.record_turn(offered=False, text="Só prosa.", envelope=None)
    # JSON quebrado
    s = t.record_turn(offered=True, text="x\n```nexus-ui\n{\"v\":1,\n```", envelope=None)
    assert s["reason"] == "invalid_json"
    # v≠1: JSON ok, envelope rejeitado inteiro
    s = t.record_turn(offered=True, text='x\n```nexus-ui\n{"v":2,"blocks":[{"type":"progress","label":"A","value":1,"max":2}]}\n```', envelope=None)
    assert s["reason"] == "empty_after_validation"  # havia blocos; o validador zerou
    s = t.record_turn(offered=True, text='x\n```nexus-ui\n{"v":1,"blocks":[]}\n```', envelope=None)
    assert s["reason"] == "rejected_envelope"

    snap = t.snapshot()
    assert snap["turns"] == 6 and snap["offered"] == 5 and snap["produced"] == 4 and snap["valid"] == 1
    assert snap["discarded"] == {"no_fence": 1, "invalid_json": 1, "rejected_envelope": 1, "empty_after_validation": 1}
    assert snap["rates"]["valid_given_produced"] == 0.25

    assert inspect_fence("sem nada")["found"] is False
    assert inspect_fence('```chart\n{"kind":"bar","series":[]}\n```')["alt_fence"] is True


# ─── Plano 12 — blocos metric, callout, follow_up; teto 6 e subtetos ──────────

def test_metric_valido_e_limites():
    raw = {
        "v": 1,
        "blocks": [
            {
                "id": "kpis",
                "type": "metric",
                "title": "Este mês",
                "items": [
                    {"label": "Receita", "value": 48200, "unit": "R$", "delta": "+8,1%", "trend": "up", "hint": "vs. mês anterior"},
                    {"label": "Churn", "value": "1,8%", "delta": "-0,3 p.p.", "trend": "down", "good": "down"},
                    {"label": "Texto com unidade", "value": "alto", "unit": "%"},
                    {"label": "Sem valor"},
                    {"label": "NaN", "value": float("nan")},
                    {"label": "Quinto", "value": 5},
                    {"label": "Sexto", "value": 6},
                ],
            }
        ],
    }
    out = validate_envelope(raw)
    assert out is not None
    block = out["blocks"][0]
    assert block["type"] == "metric" and block["title"] == "Este mês"
    labels = [i["label"] for i in block["items"]]
    # "Sem valor" e NaN caem; o teto de 4 corta o sexto
    assert labels == ["Receita", "Churn", "Texto com unidade", "Quinto"]
    assert block["items"][0] == {
        "label": "Receita", "value": 48200, "unit": "R$", "delta": "+8,1%", "trend": "up", "hint": "vs. mês anterior",
    }
    assert block["items"][1]["good"] == "down"
    assert "unit" not in block["items"][2], "unit só acompanha valor numérico"

    assert validate_envelope({"v": 1, "blocks": [{"type": "metric", "items": []}]}) is None
    assert validate_envelope({"v": 1, "blocks": [{"type": "metric", "items": [{"label": "x", "value": True}]}]}) is None


def test_callout_kind_tolerante_e_body_obrigatorio():
    out = validate_envelope({"v": 1, "blocks": [
        {"type": "callout", "kind": "warn", "title": "Atenção", "body": "A Selic usada é a de outubro."},
        {"type": "callout", "kind": "pizza", "body": "Vira info."},
        {"type": "callout", "kind": "error", "body": "Vira danger."},
        {"type": "callout", "kind": "danger", "title": "Sem corpo"},
    ]})
    assert out is not None
    kinds = [(b["kind"], b.get("title")) for b in out["blocks"]]
    assert kinds == [("warning", "Atenção"), ("info", None), ("danger", None)]
    assert len(out["blocks"][0]["body"]) <= 400


def test_follow_up_vai_para_o_fim_e_so_um_por_envelope():
    out = validate_envelope({"v": 1, "blocks": [
        {"type": "follow_up", "items": ["Comparar com 2025", "Mostrar por região", "x", "comparar com 2025", {"label": "Exportar"}, "Quinto item"]},
        {"type": "progress", "label": "A", "value": 1, "max": 2},
        {"type": "follow_up", "items": ["Segundo bloco cai"]},
    ]})
    assert out is not None
    assert [b["type"] for b in out["blocks"]] == ["progress", "follow_up"]
    # "x" é curto demais, a repetição (sem caixa) cai, o objeto com label entra, teto 4
    assert out["blocks"][1]["items"] == ["Comparar com 2025", "Mostrar por região", "Exportar", "Quinto item"]
    assert validate_envelope({"v": 1, "blocks": [{"type": "follow_up", "items": ["ab"]}]}) is None


def test_teto_seis_blocos_com_subtetos():
    chart = {"type": "chart", "kind": "bar", "x_key": "x", "series": [{"key": "y", "label": "Y"}], "rows": [{"x": "a", "y": 1}]}
    sandbox = {"type": "sandbox", "title": "S", "html": "<div></div>"}
    out = validate_envelope({"v": 1, "blocks": [
        dict(chart, id="c1"), dict(chart, id="c2"), dict(chart, id="c3"),
        dict(sandbox, id="s1"), dict(sandbox, id="s2"),
        {"id": "m", "type": "metric", "items": [{"label": "a", "value": 1}]},
        {"id": "setimo", "type": "callout", "body": "fora da janela de 6"},
    ]})
    assert out is not None
    # c3 e s2 passam do subteto; o sétimo bloco nem é olhado
    assert [b["id"] for b in out["blocks"]] == ["c1", "c2", "s1", "m"]


def test_inferencia_de_tipo_dos_blocos_novos():
    out = validate_envelope({"v": 1, "blocks": [
        {"items": ["Primeira sugestão", "Segunda sugestão"]},
        {"items": [{"label": "Receita", "value": 10}]},
        {"kind": "danger", "body": "Cuidado."},
        {"title": "Só título"},
    ]})
    assert out is not None
    assert [b["type"] for b in out["blocks"]] == ["metric", "callout", "card", "follow_up"]
    # Bloco solto (sem envelope) também infere
    assert validate_envelope({"items": ["Uma sugestão válida"]})["blocks"][0]["type"] == "follow_up"


def test_table_valida():
    raw = {
        "v": 1,
        "blocks": [
            {
                "id": "t1",
                "type": "table",
                "title": "Custo por 1M tokens",
                "columns": [
                    {"key": "modelo", "label": "Modelo"},
                    {"key": "entrada", "label": "Entrada (US$)", "kind": "number", "unit": "US$"},
                    {"key": "data", "label": "Data", "kind": "date"},
                ],
                "rows": [
                    {"modelo": "GPT-4o mini", "entrada": 0.15, "data": "2026-10-14"},
                    {"modelo": "Gemini Flash", "entrada": 0.1, "data": "2026-10-13"},
                ],
                "sort": {"key": "entrada", "dir": "asc"},
            }
        ],
    }
    out = validate_envelope(raw)
    assert out is not None
    block = out["blocks"][0]
    assert block["type"] == "table"
    assert block["title"] == "Custo por 1M tokens"
    assert len(block["columns"]) == 3
    assert block["columns"][1]["unit"] == "US$"
    assert len(block["rows"]) == 2
    assert block["rows"][0]["entrada"] == 0.15
    assert block["rows"][0]["data"] == "2026-10-14"
    assert block["sort"] == {"key": "entrada", "dir": "asc"}


def test_table_infere_tipo():
    raw = {
        "columns": [
            {"key": "a", "label": "A"},
            {"key": "b", "label": "B"},
        ],
        "rows": [{"a": "1", "b": "2"}],
    }
    out = validate_envelope(raw)
    assert out is not None
    assert out["blocks"][0]["type"] == "table"


def test_table_limites_e_tolerancias():
    # Menos de 2 colunas válidas -> descartado
    assert validate_envelope({"type": "table", "columns": [{"key": "a"}], "rows": [{"a": 1}]}) is None
    # Rows vazio -> descartado
    assert validate_envelope({"type": "table", "columns": [{"key": "a"}, {"key": "b"}], "rows": []}) is None
    # Trunca em 8 colunas e 50 rows
    cols = [{"key": f"c_{i}", "label": f"Col {i}"} for i in range(12)]
    rows = [{f"c_{i}": f"v_{r}_{i}" for i in range(12)} for r in range(60)]
    out = validate_envelope({"type": "table", "columns": cols, "rows": rows})
    assert out is not None
    assert len(out["blocks"][0]["columns"]) == 8
    assert len(out["blocks"][0]["rows"]) == 50
    # Célula number inválida vira None; date inválida vira None; text vazio vira ""
    raw_types = {
        "type": "table",
        "columns": [
            {"key": "num", "kind": "number"},
            {"key": "dt", "kind": "date"},
            {"key": "txt", "kind": "text"},
        ],
        "rows": [
            {"num": "não é número", "dt": "data-errada", "txt": None},
            {"num": 42, "dt": "2026-10-14", "txt": "olá"},
        ],
        "sort": {"key": "inexistente", "dir": "qualquer"},
    }
    out2 = validate_envelope(raw_types)
    assert out2 is not None
    b = out2["blocks"][0]
    assert b["rows"][0]["num"] is None
    assert b["rows"][0]["dt"] is None
    assert b["rows"][0]["txt"] == ""
    assert b["rows"][1]["num"] == 42
    assert b["rows"][1]["dt"] == "2026-10-14"
    assert "sort" not in b  # sort com chave inexistente é ignorado


def test_chart_pie_valido_e_agrupamento():
    # Pie válido: 1 série, 4 rows
    pie = {
        "type": "chart",
        "kind": "pie",
        "x_key": "categoria",
        "series": [{"key": "valor", "label": "Participação"}],
        "rows": [
            {"categoria": "A", "valor": 40},
            {"categoria": "B", "valor": 30},
            {"categoria": "C", "valor": 20},
            {"categoria": "D", "valor": 10},
        ],
    }
    out = validate_envelope(pie)
    assert out is not None
    assert out["blocks"][0]["kind"] == "pie"
    assert len(out["blocks"][0]["rows"]) == 4

    # Pie com 2+ séries: trunca para a primeira
    pie_multi = dict(pie, series=[{"key": "valor", "label": "V1"}, {"key": "extra", "label": "V2"}])
    out_multi = validate_envelope(pie_multi)
    assert out_multi is not None
    assert len(out_multi["blocks"][0]["series"]) == 1
    assert out_multi["blocks"][0]["series"][0]["key"] == "valor"

    # Pie com menos de 2 rows: descartado
    pie_few = dict(pie, rows=[{"categoria": "A", "valor": 40}])
    assert validate_envelope(pie_few) is None

    # Pie com mais de 8 rows: agrupa no 8º como "Outros"
    ten_rows = [{"categoria": f"Item {i}", "valor": 10} for i in range(10)]
    pie_ten = dict(pie, rows=ten_rows)
    out_ten = validate_envelope(pie_ten)
    assert out_ten is not None
    rows_res = out_ten["blocks"][0]["rows"]
    assert len(rows_res) == 8
    assert rows_res[-1]["categoria"] == "Outros"
    # 3 itens restantes (índices 7, 8, 9) com valor 10 cada -> soma 30
    assert rows_res[-1]["valor"] == 30.0


def test_chart_stacked_unit_e_labels():
    # Compare com stacked: true é mantido
    compare = {
        "type": "chart",
        "kind": "compare",
        "x_key": "mes",
        "stacked": True,
        "unit": "k",
        "x_label": "Mês",
        "y_label": "Usuários",
        "series": [{"key": "s1", "label": "Ativos"}, {"key": "s2", "label": "Novos"}],
        "rows": [{"mes": "Jan", "s1": 10, "s2": 5}],
    }
    out = validate_envelope(compare)
    assert out is not None
    b = out["blocks"][0]
    assert b["stacked"] is True
    assert b["unit"] == "k"
    assert b["x_label"] == "Mês"
    assert b["y_label"] == "Usuários"

    # Bar com stacked: true é ignorado (só compare aceita stacked)
    bar = {
        "type": "chart",
        "kind": "bar",
        "stacked": True,
        "x_key": "x",
        "series": [{"key": "y", "label": "Y"}],
        "rows": [{"x": "a", "y": 1}],
    }
    out_bar = validate_envelope(bar)
    assert out_bar is not None
    assert "stacked" not in out_bar["blocks"][0]


def test_table_gatilhos_should_offer():
    from backend.ui_blocks.should_offer import select_modules, should_offer_ui

    assert should_offer_ui("Mostre uma tabela comparando os modelos")
    assert "table" in select_modules("Mostre uma tabela comparando os modelos")
    assert "table" in select_modules("Veja o ranking dos melhores processadores")
    assert "table" in select_modules("Confira a planilha de gastos")
    assert "chart" in select_modules("Desenhe um gráfico de pizza da distribuição")
    assert "chart" in select_modules("Gráfico de rosca dos custos")


def test_options_valido_single():
    raw = {
        "type": "options",
        "question": "Qual estilo de viagem combina mais com você?",
        "mode": "single",
        "options": [
            {"value": "praia", "label": "Praia e descanso", "description": "Litoral"},
            {"value": "trilha", "label": "Natureza e trilhas"},
            {"value": "cidade", "label": "Cidade e cultura"},
        ],
        "allow_other": True,
        "action": {"name": "send_message", "template": "Prefiro: {choice}"},
    }
    out = validate_envelope(raw)
    assert out is not None
    b = out["blocks"][0]
    assert b["type"] == "options"
    assert b["question"] == "Qual estilo de viagem combina mais com você?"
    assert b["mode"] == "single"
    assert len(b["options"]) == 3
    assert b["options"][0]["value"] == "praia"
    assert b["options"][0]["description"] == "Litoral"
    assert b["allow_other"] is True
    assert b["action"] == {"name": "send_message", "template": "Prefiro: {choice}"}


def test_options_valido_multiple_e_limites():
    raw = {
        "type": "options",
        "question": "Selecione as tecnologias que você domina:",
        "mode": "multiple",
        "options": [{"value": f"tech_{i}", "label": f"Tech {i}"} for i in range(10)],  # Corta em 6
        "action": {"name": "send_message", "template": "Domino: {choice}"},
    }
    out = validate_envelope(raw)
    assert out is not None
    b = out["blocks"][0]
    assert b["mode"] == "multiple"
    assert len(b["options"]) == 6


def test_options_auto_healing():
    raw = {
        "question": "Escolha uma cor:",
        "mode": "invalido",  # Cai para "single"
        "options": [
            {"value": "!!!invalido!!!", "label": "Azul"},  # Auto-heal value
            {"label": "Vermelho"},  # Sem value -> gera opt_2
        ],
        "action": {"name": "send_message", "template": "Cor: {choice}"},
    }
    out = validate_envelope(raw)
    assert out is not None
    b = out["blocks"][0]
    assert b["type"] == "options"
    assert b["mode"] == "single"
    assert b["options"][0]["value"] == "opt_1"
    assert b["options"][1]["value"] == "opt_2"


def test_options_rejeita_invalido():
    # Menos de 2 opções
    assert validate_envelope({
        "type": "options",
        "question": "Pergunta?",
        "options": [{"value": "1", "label": "Um"}],
        "action": {"name": "send_message", "template": "{choice}"},
    }) is None

    # Sem {choice} no template
    assert validate_envelope({
        "type": "options",
        "question": "Pergunta?",
        "options": [{"value": "1", "label": "Um"}, {"value": "2", "label": "Dois"}],
        "action": {"name": "send_message", "template": "Sem placeholder"},
    }) is None

    # Action diferente de send_message
    assert validate_envelope({
        "type": "options",
        "question": "Pergunta?",
        "options": [{"value": "1", "label": "Um"}, {"value": "2", "label": "Dois"}],
        "action": {"name": "set_model", "field": "m"},
    }) is None


def test_options_gatilhos_should_offer():
    from backend.ui_blocks.should_offer import select_modules, should_offer_ui

    assert should_offer_ui("Qual das opções você prefere?")
    assert "options" in select_modules("Qual das opções você prefere?")
    assert "options" in select_modules("Escolha uma alternativa para o projeto")
    assert "options" in select_modules("Participe da enquete sobre o layout")


def test_shared_expressions_in_envelope():
    from backend.ui_blocks.validate import validate_envelope

    # Envelope com controls e metric usando expressão com variáveis de controls
    envelope = {
        "v": 1,
        "blocks": [
            {
                "type": "controls",
                "id": "c1",
                "title": "Simulador",
                "fields": [
                    {"id": "valor", "kind": "number", "default": 1000},
                    {"id": "taxa", "kind": "number", "default": 10},
                ],
                "action": {"name": "send_message", "template": "Calcular {valor}"},
            },
            {
                "type": "metric",
                "id": "m1",
                "items": [
                    {"label": "Total", "value": "={valor} * (1 + {taxa} / 100)", "unit": "R$"},
                    {"label": "Desconhecido", "value": "={nao_existe} + 1"},
                ],
            },
        ],
    }
    validated = validate_envelope(envelope)
    assert validated is not None
    m_block = [b for b in validated["blocks"] if b["type"] == "metric"][0]
    # Expressão válida é preservada com sua unit
    assert m_block["items"][0]["value"] == "={valor} * (1 + {taxa} / 100)"
    assert m_block["items"][0]["unit"] == "R$"
    # Expressão com variável desconhecida vira "—"
    assert m_block["items"][1]["value"] == "—"


def test_duplicate_field_id_across_controls_blocks():
    from backend.ui_blocks.validate import validate_envelope

    envelope = {
        "v": 1,
        "blocks": [
            {
                "type": "controls",
                "id": "c1",
                "title": "Form 1",
                "fields": [{"id": "campo_a", "kind": "number"}],
                "action": {"name": "send_message", "template": "{campo_a}"},
            },
            {
                "type": "controls",
                "id": "c2",
                "title": "Form 2",
                "fields": [{"id": "campo_a", "kind": "number"}],  # Duplicado!
                "action": {"name": "send_message", "template": "{campo_a}"},
            },
        ],
    }
    validated = validate_envelope(envelope)
    assert validated is not None
    # Apenas o primeiro controls passa; o segundo é descartado por duplicate_id
    assert len([b for b in validated["blocks"] if b["type"] == "controls"]) == 1


def test_controls_computed_list_and_cycles():
    from backend.ui_blocks.validate import validate_envelope

    # Lista de computeds encadeada válida
    valid_env = {
        "v": 1,
        "blocks": [
            {
                "type": "controls",
                "fields": [{"id": "preco", "kind": "number"}],
                "computed": [
                    {"id": "subtotal", "template": "Sub: {subtotal}", "formula": "{preco} * 0.9"},
                    {"id": "total", "template": "Total: {total}", "formula": "{subtotal} + 10"},
                ],
                "action": {"name": "send_message", "template": "Resultado: {total}"},
            }
        ],
    }
    res = validate_envelope(valid_env)
    assert res is not None
    assert len(res["blocks"][0]["computed"]) == 2

    # Ciclo de computeds: computed é descartado e send_message com {total} falha
    cycle_env = {
        "v": 1,
        "blocks": [
            {
                "type": "controls",
                "fields": [{"id": "preco", "kind": "number"}],
                "computed": [
                    {"id": "a", "template": "{a}", "formula": "{b} + 1"},
                    {"id": "b", "template": "{b}", "formula": "{a} * 2"},
                ],
                "action": {"name": "send_message", "template": "{a}"},
            }
        ],
    }
    res_cycle = validate_envelope(cycle_env)
    assert res_cycle is None


def test_table_and_chart_expressions():
    from backend.ui_blocks.validate import validate_envelope

    envelope = {
        "v": 1,
        "blocks": [
            {
                "type": "controls",
                "fields": [{"id": "multiplicador", "kind": "number"}],
                "action": {"name": "send_message", "template": "{multiplicador}"},
            },
            {
                "type": "table",
                "columns": [
                    {"key": "item", "label": "Item"},
                    {"key": "valor", "label": "Valor", "kind": "number"},
                ],
                "rows": [
                    {"item": "A", "valor": "={multiplicador} * 10"},
                    {"item": "B", "valor": "={invalido} * 10"},
                ],
            },
            {
                "type": "chart",
                "kind": "bar",
                "x_key": "mes",
                "series": [{"key": "vendas", "label": "Vendas"}],
                "rows": [
                    {"mes": "Jan", "vendas": "={multiplicador} * 5"},
                    {"mes": "Fev", "vendas": "={invalido} + 1"},
                ],
            },
        ],
    }
    validated = validate_envelope(envelope)
    assert validated is not None
    table_b = [b for b in validated["blocks"] if b["type"] == "table"][0]
    assert table_b["rows"][0]["valor"] == "={multiplicador} * 10"
    assert table_b["rows"][1]["valor"] is None

    chart_b = [b for b in validated["blocks"] if b["type"] == "chart"][0]
    assert chart_b["rows"][0]["vendas"] == "={multiplicador} * 5"
    assert chart_b["rows"][1]["vendas"] == 0.0
