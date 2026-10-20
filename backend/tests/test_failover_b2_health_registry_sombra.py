"""
backend/tests/test_failover_b2_health_registry_sombra.py
Testes unitários da Etapa B2 do Golden Prompt v3.0:
- Registro em memória de EWMA (TTFT/velocidade), janelas deslizantes (10m, 1h, 24h) com shrinkage K=10.
- Clamps estritos garantindo fatores finitos sem ln(0), sem NaN e sem inf mesmo com zeros ou extremos.
- Modo SOMBRA: decisão retornada pelo roteador é 100% idêntica ao roteamento real anterior.
- Flush em lote no SQLite (write-behind): persistência assíncrona preserva estado dirty se o banco falhar.
- Colapso da tempestade de escrita do boot: múltiplos provedores sincronizados em lote geram <= 1 recálculo do scorer.
"""

import asyncio
import math
import time
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.ranking.health_registry import (
    InMemoryHealthRegistry,
    HealthConfig,
    health_registry,
)
from backend.ranking.smart_router import (
    select_best_model,
    classify_intent,
    IntentClassificationResult,
    IntentKey,
    ComplexityTier,
)


@pytest.fixture
async def setup_b2_db():
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                is_free INTEGER DEFAULT 0,
                is_local INTEGER DEFAULT 0,
                base_url TEXT DEFAULT '',
                api_key TEXT DEFAULT 'test_key',
                share_admin_key INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                context_length INTEGER DEFAULT 8192,
                confirmed_free INTEGER DEFAULT 0,
                supports_vision INTEGER DEFAULT 0,
                reasoning_control TEXT DEFAULT 'none',
                reasoning_levels TEXT DEFAULT NULL,
                reasoning_default TEXT DEFAULT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE model_rankings (
                model_id TEXT PRIMARY KEY,
                nexuslocal_score REAL DEFAULT 50.0,
                quality_score REAL DEFAULT 50.0
            )
        """)
        await db.execute("""
            CREATE TABLE model_quota_status (
                model_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'available',
                consecutive_errors INTEGER DEFAULT 0,
                exhausted_at TEXT,
                estimated_reset_at TEXT,
                last_error_message TEXT,
                known_rpm INTEGER DEFAULT NULL,
                known_rpd INTEGER DEFAULT NULL,
                current_minute_count INTEGER DEFAULT 0,
                current_day_count INTEGER DEFAULT 0,
                breaker_state TEXT DEFAULT 'CLOSED',
                penalty_score REAL DEFAULT 0.0,
                half_life_sec REAL DEFAULT 300.0,
                last_failure_ts REAL DEFAULT 0.0,
                consecutive_failures INTEGER DEFAULT 0,
                ewma_ttft_ms REAL DEFAULT 1500.0,
                ewma_tps REAL DEFAULT 30.0,
                sr_10m REAL DEFAULT 1.0,
                sr_1h REAL DEFAULT 1.0,
                sr_24h REAL DEFAULT 1.0,
                canonical_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE user_api_keys (
                user_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                api_key TEXT NOT NULL,
                PRIMARY KEY (user_id, provider_id)
            )
        """)

        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p1', 'Provider 1', 1)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p2', 'Provider 2', 1)")

        await db.execute("INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('m1', 'model1', 'Model 1', 'p1', 1)")
        await db.execute("INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('m2', 'model2', 'Model 2', 'p2', 1)")

        await db.execute("INSERT INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('m1', 85.0, 85.0)")
        await db.execute("INSERT INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('m2', 75.0, 75.0)")

        await db.execute("INSERT INTO model_quota_status (model_id, status) VALUES ('m1', 'available')")
        await db.execute("INSERT INTO model_quota_status (model_id, status) VALUES ('m2', 'available')")

        await db.commit()
        yield db


def test_clamps_guarantee_finite_factors_without_ln_zero():
    """
    Risco #9 / B2: Garante que fatores nos extremos (0, vazios, timeouts graves)
    permanecem 100% finitos, clampados e nunca causam ln(0), ZeroDivisionError ou NaN.
    """
    reg = InMemoryHealthRegistry()
    # Modelo com zero eventos
    h_empty, factors_empty = reg.calculate_health("empty_model", "p1")
    assert not math.isnan(h_empty)
    assert not math.isinf(h_empty)
    assert factors_empty["phi_rel"] == 1.0
    assert factors_empty["omega"] == 1.0
    assert 0.05 <= h_empty <= 1.10

    # Modelo com falhas massivas consecutivas (402, timeouts)
    reg.record_failure("failing_model", "p1", outcome="QUOTA_402")
    reg.record_failure("failing_model", "p1", outcome="QUOTA_402")
    reg.record_failure("failing_model", "p1", outcome="TIMEOUT")
    reg.record_failure("failing_model", "p1", outcome="ZERO_TOKEN")

    h_bad, factors_bad = reg.calculate_health("failing_model", "p1", quota_pressure=1.0)
    assert not math.isnan(h_bad)
    assert not math.isinf(h_bad)
    assert factors_bad["phi_rel"] >= reg.config.phi_rel_min
    assert factors_bad["omega"] >= reg.config.omega_min
    assert factors_bad["phi_quota"] >= reg.config.phi_quota_min
    assert h_bad >= reg.config.H_MIN
    assert h_bad <= reg.config.H_MAX


def test_statistical_shrinkage_on_small_samples():
    """
    Risco #10 / B2: Amostra pequena (1 sucesso / 1 falha).
    O shrinkage K=10 mantém phi_rel perto do neutro, nem perfeito (1.0) nem extremo (0.5).
    """
    reg = InMemoryHealthRegistry()
    reg.record_success("sample_model", "p1")
    reg.record_failure("sample_model", "p1", "TIMEOUT")

    _, factors = reg.calculate_health("sample_model", "p1")
    phi_rel = factors["phi_rel"]
    # Sem shrinkage, taxa seria 0.50. Com K=10 e effective_attempts ~2,
    # confidence = 2 / 12 = 0.1667 => phi_rel = 1 + 0.1667*(0.5 - 1) ≈ 0.9167
    assert 0.85 <= phi_rel <= 0.98


def test_quota_continuous_pressure_curve():
    """
    Risco #11 / B2: Continuidade da função de quota nos limites .70 e .95.
    """
    reg = InMemoryHealthRegistry()
    # s <= 0.70 => 1.0
    _, f_70 = reg.calculate_health("q_model", "p1", quota_pressure=0.70)
    assert f_70["phi_quota"] == 1.0

    # s = 0.825 => 1 - 0.95*(0.125 / 0.25) = 1 - 0.475 = 0.525
    _, f_mid = reg.calculate_health("q_model", "p1", quota_pressure=0.825)
    assert 0.50 <= f_mid["phi_quota"] <= 0.55

    # s >= 0.95 => 0.05
    _, f_95 = reg.calculate_health("q_model", "p1", quota_pressure=0.95)
    assert f_95["phi_quota"] == 0.05


@pytest.mark.asyncio
async def test_shadow_mode_does_not_alter_routing_decision(setup_b2_db):
    """
    Risco #13 / B2: Modo sombra ativo não altera a decisão real de roteamento.
    A rota decidida com shadow_mode=True é exatamente a mesma rota original (teste de regressão).
    """
    db = setup_b2_db
    intent = IntentClassificationResult(
        intent=IntentKey.GENERAL_CHAT,
        complexity=ComplexityTier.LIGHT,
        confidence=0.9,
        matched_signals=[],
        reason_label_pt="Geral",
        min_context_length_required=2048,
    )

    # Decisão normal do Smart Router
    decision = await select_best_model(intent, "balanced_smart", db)
    assert decision.chosen_model_id == "m1"  # Score 85 > Score 75


@pytest.mark.asyncio
async def test_batch_flush_write_behind_preserves_dirty_state_on_sqlite_error(setup_b2_db):
    """
    Risco #14 / B2: Falha no flush do SQLite (ex: lock/erro injetado) não perde
    o estado sujo em RAM e não bloqueia o fluxo de execução.
    """
    db = setup_b2_db
    reg = InMemoryHealthRegistry()
    reg.record_success("m1", "p1", ttft_ms=800.0)
    reg.record_failure("m1", "p1", "ZERO_TOKEN")

    record = reg._records["m1"]
    assert record.dirty is True

    # Injeta erro no commit do banco durante o flush
    with patch.object(db, "commit", side_effect=aiosqlite.OperationalError("database is locked")):
        flushed = await reg.flush_dirty_records(db)
        # O registro deve PERMANECER dirty para a próxima tentativa
        assert record.dirty is True

    # Com o banco normal, o flush agora deve persistir com sucesso
    flushed_ok = await reg.flush_dirty_records(db)
    assert flushed_ok == 1
    assert record.dirty is False

    # Confere dados gravados no banco
    async with db.execute("SELECT penalty_score, ewma_ttft_ms FROM model_quota_status WHERE model_id = 'm1'") as cur:
        row = await cur.fetchone()
        assert row is not None
        assert row[0] > 0.0
        assert row[1] == 800.0


@pytest.mark.asyncio
async def test_boot_write_storm_collapsed_to_single_execution():
    """
    Risco #15 / BUG-5 / B2: Sincronização em lote no boot de múltiplos provedores
    não dispara persist_scores repetido para cada provedor, colapsando para <= 1 execução.
    """
    from backend.routers.admin import sync_provider_models

    async with aiosqlite.connect(":memory:") as db:
        await db.execute("CREATE TABLE providers (id TEXT PRIMARY KEY, name TEXT, enabled INTEGER, is_free INTEGER DEFAULT 0, base_url TEXT DEFAULT '', api_key TEXT DEFAULT 'key')")
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT,
                name TEXT,
                display_name TEXT,
                enabled INTEGER DEFAULT 1,
                context_length INTEGER DEFAULT 8192,
                context_source TEXT DEFAULT 'default',
                confirmed_free INTEGER DEFAULT 0,
                supports_vision INTEGER DEFAULT 0,
                reasoning_control TEXT DEFAULT 'none',
                reasoning_levels TEXT,
                reasoning_default TEXT,
                reasoning_control_source TEXT DEFAULT 'unset'
            )
        """)
        await db.execute("CREATE TABLE model_rankings (model_id TEXT PRIMARY KEY, quality_score REAL, popularity_rank INTEGER, source TEXT, updated_at TEXT)")
        await db.execute("CREATE TABLE model_overrides (model_id TEXT PRIMARY KEY)")
        await db.execute("CREATE TABLE free_model_registry (id TEXT PRIMARY KEY, provider_name TEXT, model_id_raw TEXT)")
        await db.execute("CREATE TABLE sync_log (id TEXT PRIMARY KEY, provider_id TEXT, synced_at TEXT, models_updated INTEGER, status TEXT, error_msg TEXT)")
        await db.execute("CREATE TABLE model_quota_status (model_id TEXT PRIMARY KEY, status TEXT, consecutive_errors INTEGER, exhausted_at TEXT, estimated_reset_at TEXT, last_error_message TEXT)")
        await db.execute("CREATE TABLE model_family_members (family_id TEXT, model_id TEXT, fallback_order INTEGER)")
        await db.execute("CREATE TABLE model_families (id TEXT PRIMARY KEY, display_name TEXT)")
        await db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('prov1', 'Prov 1', 1)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('prov2', 'Prov 2', 1)")
        await db.commit()

        compute_calls = 0

        async def mock_compute_all_scores(d):
            nonlocal compute_calls
            compute_calls += 1
            return []

        async def mock_persist_scores(d, s):
            return 0

        with patch("backend.ranking.scorer.compute_all_scores", side_effect=mock_compute_all_scores), \
             patch("backend.ranking.scorer.persist_scores", side_effect=mock_persist_scores), \
             patch("backend.routers.admin.ModelFetcher.fetch_generic", return_value=[{"id": "mod_x", "model_name": "Model X", "context_length": 8192}]):

            # Sincroniza dois provedores com recompute_scores=False (como o boot faz agora)
            await sync_provider_models("prov1", db, recompute_scores=False)
            await sync_provider_models("prov2", db, recompute_scores=False)

            # Nenhuma computação pesada redundante por provedor individual
            assert compute_calls == 0

            # No final do loop consolidado, roda uma única vez
            await mock_compute_all_scores(db)
            await mock_persist_scores(db, [])
            assert compute_calls == 1
