"""Badge de failover: stream_end deve identificar o modelo que RESpondeu (pós-failover),
não o modelo solicitado que falhou.

Correção: o payload stream_end ganhou was_fallback + final_model_id +
final_model_name + final_provider_id (via build_final_model_metadata).
O frontend usa final_* no ModelBadge da resposta; o fallback segue valendo
para mensagens antigas sem os campos.
"""
import aiosqlite
import pytest

from backend.orchestration.resolve_request import build_final_model_metadata


@pytest.fixture
async def models_db(tmp_path):
    db_path = tmp_path / "failover_badge.db"
    db = await aiosqlite.connect(str(db_path))
    await db.executescript(
        """
        CREATE TABLE models (
            id TEXT PRIMARY KEY,
            name TEXT,
            display_name TEXT,
            provider_id TEXT
        );
        INSERT INTO models (id, name, display_name, provider_id) VALUES
            ('prov_a/main-model', 'main_model', 'Main Model', 'prov_a'),
            ('prov_b/fallback-model', 'fallback_model', 'Fallback Model', 'prov_b'),
            ('prov_c/no-display', 'no_display', NULL, 'prov_c');
        """
    )
    await db.commit()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_metadata_flags_failover(models_db):
    meta = await build_final_model_metadata(
        models_db,
        requested_model_id="prov_a/main-model",
        resolved_model_id="prov_b/fallback-model",
        resolved_provider_id="prov_b",
    )
    assert meta["was_fallback"] is True
    assert meta["final_model_id"] == "prov_b/fallback-model"
    # O badge deve mostrar o nome legível do modelo que respondeu
    assert meta["final_model_name"] == "Fallback Model"
    assert meta["final_provider_id"] == "prov_b"


@pytest.mark.asyncio
async def test_metadata_no_failover_when_same_model(models_db):
    meta = await build_final_model_metadata(
        models_db,
        requested_model_id="prov_a/main-model",
        resolved_model_id="prov_a/main-model",
        resolved_provider_id="prov_a",
    )
    assert meta["was_fallback"] is False
    assert meta["final_model_id"] == "prov_a/main-model"
    assert meta["final_model_name"] == "Main Model"
    assert meta["final_provider_id"] == "prov_a"


@pytest.mark.asyncio
async def test_metadata_unknown_model_falls_back_to_id(models_db):
    """Modelo inexistente no catálogo: nunca quebrar o turno — usa o id como nome."""
    meta = await build_final_model_metadata(
        models_db,
        requested_model_id="prov_a/main-model",
        resolved_model_id="prov_x/ghost-model",
        resolved_provider_id="prov_x",
    )
    assert meta["was_fallback"] is True
    assert meta["final_model_id"] == "prov_x/ghost-model"
    assert meta["final_model_name"] == "prov_x/ghost-model"


@pytest.mark.asyncio
async def test_metadata_name_fallback_when_display_name_null(models_db):
    meta = await build_final_model_metadata(
        models_db,
        requested_model_id="prov_a/main-model",
        resolved_model_id="prov_c/no-display",
        resolved_provider_id="prov_c",
    )
    assert meta["final_model_name"] == "no_display"
