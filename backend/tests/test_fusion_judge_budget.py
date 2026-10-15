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
async def test_timeout_com_texto_parcial_persiste_e_envia_fusion_status():
    """Runtime:timeout do juiz com texto já emitido envia fusion_status e salva no DB."""
    from backend.ranking.failover import ResolvedModel
    from unittest.mock import patch, AsyncMock, MagicMock
    import os

    sent = []

    class FakeWS:
        async def send_json(self, obj):
            sent.append(obj)

    async def slow_stream(**kwargs):
        for token in ["RES", "POST", "A"]:
            await asyncio.sleep(0.02)
            yield token

    async def slow_stream_wrapper(**kwargs):
        async for t in slow_stream(**kwargs):
            yield t

    fake_provider = MagicMock()
    fake_provider.stream_chat = slow_stream_wrapper

    resolved = MagicMock()
    resolved.model_id = "judge-slow"
    resolved.provider_id = "fake"
    resolved.was_failover = False
    resolved.original_model_id = None

    with patch("backend.fusion.orchestrator.get_provider") as mock_get_provider, \
         patch("backend.fusion.orchestrator.get_model_name", return_value=AsyncMock(return_value="slow")), \
         patch("backend.fusion.orchestrator.TIMEOUT_JUIZ", 0.05), \
         patch("backend.fusion.orchestrator._precisa_refinar", return_value=False), \
         patch("backend.fusion.orchestrator._refinar_pergunta", return_value=AsyncMock(return_value="Oi")), \
         patch("backend.ranking.failover.resolve_model_with_failover", return_value=AsyncMock(return_value=resolved)), \
         patch("backend.fusion.orchestrator.check_and_deactivate_model", return_value=AsyncMock(return_value=None)), \
         patch("backend.fusion.orchestrator.detect_artifacts", return_value=(None, [])), \
         patch("backend.fusion.orchestrator.save_artifact"), \
         patch("backend.web_search.get_web_search_config", return_value=AsyncMock(return_value={"enabled": False})), \
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

        class FakeDB:
            def execute(self, sql, *args, **kwargs):
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
            force_grounding=False,
            web_search_already_done=False,
        )

    types = [m.get("type") for m in sent]
    assert "stream_start" in types, f"tipos enviados: {types}"
    status_msgs = [m for m in sent if m.get("type") == "fusion_status"]
    # 3 statuses: running (proposer), done (proposer), timeout (juiz)
    assert len(status_msgs) >= 2, f"esperado >=2 fusion_status, recebeu: {types}"
    timeout_msg = [m for m in status_msgs if "parcial salva" in m.get("message", "").lower()]
    assert len(timeout_msg) == 1, f"deveria haver 1 timeout fusion_status; received: {types}"
    assert "0.05" in timeout_msg[0]["message"], f"TIMEOUT_JUIZ não interpolado: {timeout_msg[0]['message']}"

    err_msgs = [m for m in sent if m.get("type") == "error"]
    assert len(err_msgs) == 0, f"não deveria haver error quando há texto parcial; recebeu: {types}"


