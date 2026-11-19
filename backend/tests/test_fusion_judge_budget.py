from pathlib import Path
import asyncio
import sqlite3
import tempfile
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
import aiosqlite

from backend.fusion.orchestrator import cap_judge_block, judge_timeout_action, executar_fusion


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


@pytest.mark.asyncio
@pytest.mark.parametrize("with_grounding", [False, True])
async def test_fusion_terminal_preserves_partial_or_grounded_sources(with_grounding):
    """Valida o timeout parcial e o sucesso com fontes reunidas pelo Fusion."""
    sent = []
    provider_calls = []

    class FakeWS:
        async def send_json(self, obj):
            sent.append(obj)

    stream_calls = 0
    async def slow_stream_wrapper(**kwargs):
        nonlocal stream_calls
        stream_calls += 1
        provider_calls.append(kwargs)
        if stream_calls == 1:
            yield "PROPOSTA"
            return
        yield "PARCIAL"
        if not with_grounding:
            await asyncio.Event().wait()

    fake_provider = MagicMock()
    fake_provider.stream_chat = slow_stream_wrapper

    resolved = MagicMock()
    resolved.model_id = "judge-slow"
    resolved.provider_id = "fake"
    resolved.was_failover = False
    resolved.original_model_id = None

    with patch("backend.fusion.orchestrator.get_provider") as mock_get_provider, \
         patch("backend.fusion.orchestrator.get_model_name", return_value="slow"), \
         patch("backend.fusion.orchestrator.TIMEOUT_JUIZ", 2 if with_grounding else 0.05), \
         patch("backend.fusion.orchestrator._precisa_refinar", return_value=False), \
         patch("backend.fusion.orchestrator._refinar_pergunta", return_value="Oi"), \
         patch("backend.ranking.failover.resolve_model_with_failover", return_value=resolved), \
         patch("backend.fusion.orchestrator.check_and_deactivate_model", return_value=None), \
         patch("backend.fusion.orchestrator.detect_artifacts", return_value=(None, [])), \
         patch("backend.fusion.orchestrator.save_artifact"), \
         patch("backend.web_search.get_web_search_config", return_value={"enabled": with_grounding}), \
         patch("backend.fusion.orchestrator._detectar_claims_verificaveis", return_value=["consulta A", "consulta B"]), \
         patch("backend.fusion.orchestrator._buscar_web", side_effect=[
             [{"title": "Primeira fonte", "url": "https://example.com/A"}],
             [{"title": "Segunda fonte", "url": "https://example.com/B"}],
         ]), \
         patch("backend.orchestration.persist_turn.save_web_search_metadata", new_callable=AsyncMock) as web_metadata, \
         patch("backend.fusion.orchestrator.get_db") as mock_get_db:
        # get_provider returns the real fake_provider (not wrapped in another coroutine)
        async def _get_provider(*a, **kw):
            return fake_provider
        mock_get_provider.side_effect = _get_provider
        # get_db returns a fake that satisfies the DB queries the orchestrator makes
        class FakeCursor:
            def __init__(self, rows):
                self._rows = rows
                self._idx = 0
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def fetchone(self):
                if self._idx < len(self._rows):
                    r = self._rows[self._idx]
                    self._idx += 1
                    return r
                return None
            async def fetchall(self):
                return self._rows[:]

        class FakeExecute:
            def __init__(self, sql, *args, **kwargs):
                if "fusion_models" in sql:
                    self._cursor = FakeCursor([("fake", "fake", "judge-slow", 0)])
                elif "fusion_config" in sql:
                    self._cursor = FakeCursor([("fake", "judge-slow", "Você é o juiz.", 0)])
                else:
                    self._cursor = FakeCursor([])
            def __await__(self):
                return self._cursor.__aenter__().__await__()
            async def __aenter__(self):
                return await self
            async def __aexit__(self, *a):
                pass

        writes = []
        class FakeDB:
            def execute(self, sql, *args, **kwargs):
                writes.append((sql, args))
                return FakeExecute(sql, *args, **kwargs)
            async def commit(self):
                pass
            async def close(self):
                pass
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass

        mock_get_db.return_value = FakeDB()

        await executar_fusion(
            prompt="Oi",
            history=[{"role": "user", "content": "Oi"}],
            websocket=FakeWS(),
            conversation_id="conv-timeout",
            user_id="user-1",
            force_grounding=with_grounding,
            web_search_already_done=False,
            user_msg_id="synthetic-user-message" if with_grounding else None,
            turn_id="turn-fusion-timeout",
        )

    types = [m.get("type") for m in sent]
    assert "stream_start" in types, f"tipos enviados: {types}"
    status_msgs = [m for m in sent if m.get("type") == "fusion_status"]
    assert len(status_msgs) >= 2, f"esperado >=2 fusion_status, recebeu: {types}"
    terminal = [m for m in sent if m.get("type") == "stream_end"]
    assert len(terminal) == 1
    assert terminal[0]["turn_id"] == "turn-fusion-timeout"
    if with_grounding:
        assert terminal[0]["outcome"] == "success"
        assert terminal[0]["web_search_used"] is True
        assert terminal[0]["source_count"] == 2
        expected = [(1, "https://example.com/A"), (2, "https://example.com/B")]
        assert [(s["index"], s["url"]) for s in terminal[0]["web_search_sources"]] == expected
        assert web_metadata.await_args.args[4] == terminal[0]["web_search_sources"]
        judge_input = str(provider_calls[-1]["messages"])
        assert "[1] Primeira fonte" in judge_input
        assert "[2] Segunda fonte" in judge_input
        return
    assert terminal[0]["outcome"] == "timeout"
    assert terminal[0]["reason"] == "judge_partial_timeout"
    assert "0.05" in terminal[0]["message"]
    assert any("INSERT INTO messages" in sql and "PARCIAL" in args[0] for sql, args in writes)

    err_msgs = [m for m in sent if m.get("type") == "error"]
    assert len(err_msgs) == 0, f"não deveria haver error quando há texto parcial; recebeu: {types}"


