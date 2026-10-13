"""Testes automatizados para os novos provedores gratuitos: OrcaRouter e Bynara."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path
import pytest

os.environ.setdefault("JWT_SECRET", "test-free-providers-secret")
os.environ.setdefault("ORCAROUTER_API_KEY", "sk-orca-test-key")
os.environ.setdefault("BYNARA_API_KEY", "sk-bynara-test-key")

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
async def fresh_db():
    from backend import database as dbmod

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    dbmod.DB_PATH = Path(path)
    await dbmod.init_db()
    yield dbmod
    try:
        if Path(path).exists():
            Path(path).unlink(missing_ok=True)
    except Exception:
        pass


@pytest.mark.asyncio
async def test_orcarouter_and_bynara_registration(fresh_db):
    """Verifica que OrcaRouter e Bynara foram cadastrados como gratuitos com seus modelos confirmados."""
    db = await fresh_db.get_db()
    try:
        # 1. Provedores
        async with db.execute(
            "SELECT id, name, base_url, is_free FROM providers WHERE id IN ('orcarouter', 'bynara')"
        ) as cur:
            providers = {row[0]: row for row in await cur.fetchall()}

        assert "orcarouter" in providers
        assert providers["orcarouter"][1] == "OrcaRouter"
        assert providers["orcarouter"][2] == "https://api.orcarouter.ai/v1"
        assert providers["orcarouter"][3] == 1  # is_free

        assert "bynara" in providers
        assert providers["bynara"][1] == "Bynara"
        assert providers["bynara"][2] == "https://router.bynara.id/v1"
        assert providers["bynara"][3] == 1  # is_free

        # 2. Modelos OrcaRouter
        async with db.execute(
            "SELECT id, name, display_name, confirmed_free FROM models WHERE provider_id = 'orcarouter'"
        ) as cur:
            orca_models = {row[1]: row for row in await cur.fetchall()}

        expected_orca = [
            "orcarouter/free",
            "tencent/hy4-preview-free",
            "tencent/hy3-free",
            "z-ai/glm-5.3-flash-free",
            "deepseek/deepseek-v4-flash-free",
        ]
        for m in expected_orca:
            assert m in orca_models, f"Modelo {m} não encontrado em OrcaRouter"
            assert orca_models[m][3] == 1, f"Modelo {m} deve estar confirmado_free == 1"

        # 3. Modelos Bynara
        async with db.execute(
            "SELECT id, name, display_name, confirmed_free FROM models WHERE provider_id = 'bynara'"
        ) as cur:
            bynara_models = {row[1]: row for row in await cur.fetchall()}

        expected_bynara = [
            "agnes-2.5-flash",
            "laguna-s-2.1",
            "nemotron-3-ultra-free",
            "nemotron-3.5-lightning-free",
        ]
        for m in expected_bynara:
            assert m in bynara_models, f"Modelo {m} não encontrado em Bynara"
            assert bynara_models[m][3] == 1, f"Modelo {m} deve estar confirmado_free == 1"

    finally:
        await db.close()


@pytest.mark.asyncio
async def test_provider_resolution_fallback(fresh_db):
    """Verifica que chamadas sem chave pessoal usam a chave compartilhada de env."""
    from backend.providers.registry import get_provider

    db = await fresh_db.get_db()
    try:
        user_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, 'tester', 'x', 'user')",
            (user_id,),
        )
        await db.commit()

        # Usuário sem chave pessoal obtém provider com a chave configurada no env
        orca = await get_provider("orcarouter", db, user_id=user_id)
        assert orca.api_key == "sk-orca-test-key"
        assert orca.base_url == "https://api.orcarouter.ai/v1"

        bynara = await get_provider("bynara", db, user_id=user_id)
        assert bynara.api_key == "sk-bynara-test-key"
        assert bynara.base_url == "https://router.bynara.id/v1"

    finally:
        await db.close()
