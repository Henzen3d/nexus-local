from backend.fusion.orchestrator import cap_judge_block, judge_timeout_action


def test_cap_judge_block_deixa_texto_curto_intacto():
    assert cap_judge_block("curto") == "curto"


def test_cap_judge_block_corta_em_4000_e_marca():
    texto = "a" * 5000
    saida = cap_judge_block(texto)
    assert saida.startswith("a" * 4000)
    assert saida.endswith("…[truncado para o Juiz]")
    assert len(saida) == 4000 + len("\n…[truncado para o Juiz]")


def test_cap_judge_block_none_vira_vazio():
    assert cap_judge_block(None) == ""


def test_judge_timeout_persiste_se_houver_texto():
    assert judge_timeout_action("  resposta  ") == "persist"
    assert judge_timeout_action("   ") == "error"
    assert judge_timeout_action("") == "error"
