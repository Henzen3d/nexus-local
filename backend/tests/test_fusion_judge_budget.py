from pathlib import Path

from backend.fusion.orchestrator import cap_judge_block, judge_timeout_action


def test_cap_judge_block_deixa_texto_curto_intacto():
    assert cap_judge_block("curto") == "curto"


def test_cap_judge_block_corta_em_4000_e_marca():
    texto = "a" * 5000
    saida = cap_judge_block(texto)
    assert saida.startswith("a" * int(4000 * 0.65))
    assert saida.endswith("a" * (4000 - int(4000 * 0.65) - len("\n…[truncado para o Juiz]")))
    assert saida.count("…[truncado para o Juiz]") == 1
    assert len(saida) == 4000


def test_cap_judge_block_none_vira_vazio():
    assert cap_judge_block(None) == ""


def test_judge_timeout_persiste_se_houver_texto():
    assert judge_timeout_action("  resposta  ") == "persist"
    assert judge_timeout_action("   ") == "error"
    assert judge_timeout_action("") == "error"


def test_join_do_juiz_nao_carrega_resposta_inteira():
    respostas = [
        {"model_id": "a", "response": "x" * 8000, "confidence": None},
        {"model_id": "b", "response": "y" * 100, "confidence": None},
    ]
    blocos = "\n\n".join(
        f"--- RESPOSTA: {r['model_id']} ---\n{cap_judge_block(r['response'])}"
        for r in respostas
    )
    assert "x" * 4001 not in blocos
    assert "yyyy" in blocos
    assert blocos.count("…[truncado para o Juiz]") == 1


def test_orchestrator_aplica_cap_no_join_do_juiz():
    source = Path("backend/fusion/orchestrator.py").read_text(encoding="utf-8")
    assert "cap_judge_block(r['response'])" in source
    assert "judge_timeout_action(full_response)" in source
    assert "max_tokens=256" in source
