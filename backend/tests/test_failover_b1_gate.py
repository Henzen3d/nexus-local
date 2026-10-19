"""
backend/tests/test_failover_b1_gate.py
Testes unitários da Etapa B1 do Golden Prompt v3.0:
- Gate de elegibilidade explícito e limpo (Seção 6.1).
- Risco #8: Candidato com maior base_score, mas em quarentena/cooldown/OPEN, nunca é selecionado.
- Cooldown no escopo do canonical_model_id barra variantes de outros provedores no gate.
- Saturação de quota >= 0.95 bloqueia candidatos (exceto probe canary).
- Semáforo de admissão cheio (concorrência) bloqueia novos roteamentos para o modelo/provedor.
"""

from datetime import datetime, timedelta, timezone
import pytest
import aiosqlite

from backend.ranking.eligibility import (
    check_candidate_eligibility,
    is_candidate_eligible_in_memory,
    EligibilityResult,
)
from backend.ranking.failover import (
    resolve_model_with_failover,
    _get_next_best_ranked_model,
)
from backend.ranking.admission import admission_controller
from backend.ranking.token_bucket import token_bucket_manager
from backend.ranking.smart_router import rank_candidates, IntentClassificationResult, IntentKey, ComplexityTier


@pytest.fixture
async def setup_b1_db():
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
            CREATE TABLE model_families (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE model_family_members (
                family_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                fallback_order INTEGER DEFAULT 1,
                PRIMARY KEY (family_id, model_id)
            )
        """)
        await db.execute("""
            CREATE TABLE model_quota_status (
                model_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                consecutive_errors INTEGER DEFAULT 0,
                exhausted_at TEXT,
                estimated_reset_at TEXT,
                last_error_message TEXT,
                known_rpm INTEGER DEFAULT NULL,
                known_rpd INTEGER DEFAULT NULL,
                current_minute_count INTEGER DEFAULT 0,
                current_day_count INTEGER DEFAULT 0
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

        # Provedor 1 e Provedor 2
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p1', 'Provider 1', 1)")
        await db.execute("INSERT INTO providers (id, name, enabled) VALUES ('p2', 'Provider 2', 1)")

        await db.execute("INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user_b1', 'p1', 'sk-1')")
        await db.execute("INSERT INTO user_api_keys (user_id, provider_id, api_key) VALUES ('user_b1', 'p2', 'sk-2')")

        await db.commit()
        admission_controller.reset()
        yield db
        admission_controller.reset()


@pytest.mark.asyncio
async def test_gate_rejects_highest_score_model_in_quarantine_or_open(setup_b1_db):
    """
    Risco #8: Candidato com maior base_score (99.0) em quarentena/OPEN
    NUNCA é selecionado; o gate duro filtra e escolhe o modelo elegível (score 70.0).
    """
    db = setup_b1_db
    # Modelo A: Score 99.0, mas breaker 'open' / quarentena
    await db.execute(
        "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('model_a', 'model_a', 'Model A', 'p1', 1)"
    )
    await db.execute(
        "INSERT INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('model_a', 99.0, 99.0)"
    )
    await db.execute(
        "INSERT INTO model_quota_status (model_id, status, last_error_message) VALUES ('model_a', 'open', 'Circuit breaker open')"
    )

    # Modelo B: Score 70.0, status 'available'
    await db.execute(
        "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('model_b', 'model_b', 'Model B', 'p2', 1)"
    )
    await db.execute(
        "INSERT INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('model_b', 70.0, 70.0)"
    )
    await db.execute(
        "INSERT INTO model_quota_status (model_id, status) VALUES ('model_b', 'available')"
    )
    await db.commit()

    # Consulta direta ao gate
    elig_a = await check_candidate_eligibility("model_a", "p1", db)
    assert not elig_a.eligible
    assert "circuit_breaker" in elig_a.reason

    elig_b = await check_candidate_eligibility("model_b", "p2", db)
    assert elig_b.eligible

    # No Tier 2 do failover, Model A com score 99 NUNCA deve ser selecionado; Model B deve ser o escolhido
    next_best = await _get_next_best_ranked_model(db, exclude_model_ids=[], exclude_family_ids=[], user_id="user_b1")
    assert next_best is not None
    mid, pid, dname = next_best
    assert mid == "model_b", f"Esperava model_b, mas foi selecionado: {mid}"


@pytest.mark.asyncio
async def test_gate_rejects_canonical_cooldown_cross_provider(setup_b1_db):
    """
    Valida que cooldown ativo em um provedor bloqueia o mesmo modelo canônico em outro provedor no gate.
    """
    db = setup_b1_db
    # openrouter/nemotron em cooldown após 0 tokens
    now = datetime.now(timezone.utc)
    future = (now + timedelta(minutes=10)).isoformat()

    await db.execute(
        "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('openrouter/nemotron-mini', 'nemotron-mini', 'Nemotron OpenRouter', 'p1', 1)"
    )
    await db.execute(
        "INSERT INTO model_quota_status (model_id, status, estimated_reset_at) VALUES ('openrouter/nemotron-mini', 'cooldown', ?)",
        (future,)
    )

    # nvidia/nemotron no p2 tem score alto
    await db.execute(
        "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('nvidia/nemotron-mini', 'nemotron-mini', 'Nemotron Nvidia', 'p2', 1)"
    )
    await db.execute(
        "INSERT INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('nvidia/nemotron-mini', 95.0, 95.0)"
    )
    await db.commit()

    # Testando o gate para a variante da nvidia
    elig = await check_candidate_eligibility("nvidia/nemotron-mini", "p2", db)
    assert not elig.eligible
    assert "canonical_cooldown_active" in elig.reason


@pytest.mark.asyncio
async def test_gate_quota_saturation_and_canary_exemption(setup_b1_db):
    """
    Saturação >= 0.95 bloqueia chamadas regulares, mas is_canary_probe=True tem isenção controlada.
    """
    db = setup_b1_db
    await db.execute(
        "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('model_saturated', 'm_sat', 'Sat Model', 'p1', 1)"
    )
    await db.execute("""
        INSERT INTO model_quota_status (model_id, status, known_rpm, current_minute_count)
        VALUES ('model_saturated', 'available', 100, 96)
    """)
    await db.commit()

    # Chamada regular: saturada (96% >= 95%)
    elig_regular = await check_candidate_eligibility("model_saturated", "p1", db, is_canary_probe=False)
    assert not elig_regular.eligible
    assert elig_regular.reason == "quota_saturated_rpm"

    # Probe canary: isenção concedida
    elig_canary = await check_candidate_eligibility("model_saturated", "p1", db, is_canary_probe=True)
    assert elig_canary.eligible


@pytest.mark.asyncio
async def test_gate_admission_concurrency_semaphore(setup_b1_db):
    """
    Semáforo de concorrência in-flight bloqueia quando limite por modelo ou provedor é atingido.
    """
    db = setup_b1_db
    await db.execute(
        "INSERT INTO models (id, name, display_name, provider_id, enabled) VALUES ('model_busy', 'm_busy', 'Busy Model', 'p1', 1)"
    )
    await db.commit()

    admission_controller.max_per_model = 2

    assert admission_controller.acquire("model_busy", "p1") is True
    assert admission_controller.acquire("model_busy", "p1") is True
    # Terceiro deve falhar
    assert admission_controller.acquire("model_busy", "p1") is False

    elig = await check_candidate_eligibility("model_busy", "p1", db)
    assert not elig.eligible
    assert elig.reason == "admission_concurrency_saturated"

    # Libera uma requisição
    admission_controller.release("model_busy", "p1")
    elig_after = await check_candidate_eligibility("model_busy", "p1", db)
    assert elig_after.eligible


def test_smart_router_in_memory_eligibility_filter():
    """
    Garante que o rank_candidates descarta modelos em quarentena/open/cooldown antes de pontuar.
    """
    intent = IntentClassificationResult(
        intent=IntentKey.GENERAL_CHAT,
        complexity=ComplexityTier.LIGHT,
        confidence=0.9,
        matched_signals=[],
        reason_label_pt="Chat",
        min_context_length_required=2048,
    )

    models_data = [
        {
            "id": "model_quarantined",
            "provider_id": "p1",
            "name": "model_quarantined",
            "display_name": "Quarantined Model",
            "context_length": 8192,
            "quota_status": "quarantine",
            "quality_score": 98.0,
            "nexuslocal_score": 98.0,
            "is_free": 1,
            "supports_vision": 0,
            "reasoning_control": "none",
        },
        {
            "id": "model_healthy",
            "provider_id": "p2",
            "name": "model_healthy",
            "display_name": "Healthy Model",
            "context_length": 8192,
            "quota_status": "available",
            "quality_score": 75.0,
            "nexuslocal_score": 75.0,
            "is_free": 1,
            "supports_vision": 0,
            "reasoning_control": "none",
        },
    ]

    ranked = rank_candidates(models_data, intent, "balanced_smart")
    assert len(ranked) >= 1
    # O modelo em quarentena não pode ter sido rankeado como #1
    assert ranked[0]["model"]["id"] == "model_healthy"
