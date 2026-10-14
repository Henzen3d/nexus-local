"""Seleção determinística, orçamento e telemetria do catálogo modular."""
import pytest
from backend.ui_blocks.catalog import build_catalog, compose_catalog
from backend.ui_blocks.should_offer import select_modules
from backend.ui_blocks.telemetry import IntelligentUiTelemetry


@pytest.mark.parametrize('text,modules', [
    ('compare custos', ('chart', 'follow_up')),
    ('resumo de indicadores KPI', ('metric', 'follow_up')),
    ('roteiro passo a passo', ('progress', 'follow_up')),
    ('calcule parcelas', ('controls', 'follow_up')),
    ('atenção ao risco', ('callout', 'follow_up')),
    ('foto do produto', ('card', 'follow_up')),
    ('animação 3d interativa', ('sandbox', 'follow_up')),
    ('10, 20 e 30 tokens de custo', ('chart', 'follow_up')),
    ('bom dia', ()),
    ('compartilhe comparecer simultaneamente cartaz barraco', ()),
    ('1, 2 e 3 contratempos no modelito', ()),
])
def test_modules(text, modules):
    catalog, selected = build_catalog(text)
    assert selected == modules == select_modules(text)
    assert bool(catalog) == bool(modules)
    assert len(catalog) / 4 <= 450


def test_priority_and_supported_contracts():
    text, modules = build_catalog('foto gráfico indicador cálculo aviso animação etapas')
    assert modules == ('chart', 'metric', 'follow_up')
    assert 'controls:' not in text
    assert 'table:' not in text and 'options:' not in text and 'round(' not in text
    # Quando pedido tabela, o módulo table: entra no catálogo
    t_text, t_mods = build_catalog('tabela comparativa de vendas')
    assert 'table' in t_mods
    assert 'table:' in t_text
    # Quando pedido opções, o módulo options: entra no catálogo
    o_text, o_mods = build_catalog('qual das opções você prefere')
    assert 'options' in o_mods
    assert 'options:' in o_text
    with pytest.raises(ValueError):
        compose_catalog(('unknown',))


def test_module_counters_are_per_turn_and_independent_of_offer():
    telemetry = IntelligentUiTelemetry()
    envelope = {'v': 1, 'blocks': [{'type': 'metric'}, {'type': 'metric'}]}
    telemetry.record_turn(offered=True, modules=('chart', 'follow_up'), text='', envelope=envelope)
    telemetry.record_turn(offered=False, modules=(), text='', envelope=envelope)
    snapshot = telemetry.snapshot()
    assert snapshot['modules_offered'] == {'chart': 1, 'follow_up': 1}
    assert snapshot['modules_produced'] == {'metric': 2}
    assert snapshot['block_types'] == {'metric': 4}
    telemetry.reset()
    assert telemetry.snapshot()['modules_offered'] == {}
