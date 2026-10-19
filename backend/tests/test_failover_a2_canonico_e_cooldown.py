"""
backend/tests/test_failover_a2_canonico_e_cooldown.py
Testes unitários da Etapa A2 do Golden Prompt v3.0:
- IDs canônicos normalizados e consistentes.
- Resolução de família Tier 1 para gemini/gemini-2.5-pro e nvidia/nvidia/nemotron-...
- Exclusão de modelos com mesmo canonical_model_id na cascata após 0 tokens.
- Cooldown persistido no SQLite sobrevivendo a restart simulado de conexão.
- Cooldown no escopo canônico quando múltiplos provedores falham com 0 tokens.
"""

import pytest
import aiosqlite
from datetime import datetime, timezone

from backend.ranking.canonical import (
    canonical_model_id,
    extract_family_from_canonical,
    apply_zero_token_cooldown,
)
from backend.ranking.failover import (
    _get_family_for_model,
    resolve_model_with_failover,
    _get_next_best_ranked_model,
)
from backend.ranking.quota import get_quota_status, release_expired_quotas


def test_canonical_model_id_golden_cases():
    """Valida normalização com os IDs reais mapeados no Golden Prompt v3.0."""
    assert canonical_model_id("nvidia/nvidia/nemotron-3-ultra-550b-a55b") == "nemotron-3-ultra-550b-a55b"
    assert canonical_model_id("openrouter/nvidia/nemotron-3-ultra-550b-a55b:free") == "nemotron-3-ultra-550b-a55b"
    assert canonical_model_id("gemini/gemini-2.5-pro") == "gemini-2.5-pro"
    assert canonical_model_id("models/gemini-2.5-pro") == "gemini-2.5-pro"
    assert canonical_model_id("longcat/LongCat-2.5-Preview") == "longcat-2.5-preview"
    assert canonical_model_id("openrouter/google/gemma-4-31b-it:free") == "gemma-4-31b-it"


def test_extract_family_from_canonical():
    """Valida extração de família base a partir de identificadores canônicos."""
    assert extract_family_from_canonical("gemini-2.5-pro") == "gemini"
    assert extract_family_from_canonical("nemotron-3-ultra-550b-a55b") == "nemotron"
    assert extract_family_from_canonical("deepseek-r1-distill-llama-70b") == "deepseek-r1"
    assert extract_family_from_canonical("llama-3.3-70b") == "llama-3.3-70b"
    assert extract_family_from_canonical("longcat-2.5-preview") == "longcat"


@pytest.mark.asyncio
async def test_gemini_and_nemotron_resolve_family_tier1():
    """
    Garante que gemini/gemini-2.5-pro e nvidia/nvidia/nemotron-... resolvem família
    e o Tier 1 passa a ser consultado com sucesso.
    """
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                is_free INTEGER DEFAULT 0,
                base_url TEXT DEFAULT '',
                api_key TEXT DEFAULT 'test_key',
                share_admin_key INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                enabled INTEGER DEFAULT 1,
                confirmed_free INTEGER DEFAULT 0
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
                id TEXT PRIMARY KEY,
                family_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                fallback_order INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE model_rankings (
                model_id TEXT PRIMARY KEY,
                nexuslocal_score REAL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE model_quota_status (
                model_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'available',
                consecutive_errors INTEGER DEFAULT 0,
                exhausted_at TEXT,
                estimated_reset_at TEXT,
                last_error_message TEXT
            )
        """)
        await db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")

        # Insere provedores e famílias
        await db.execute("INSERT INTO providers (id, name) VALUES ('gemini', 'Google Gemini')")
        await db.execute("INSERT INTO providers (id, name) VALUES ('nvidia', 'Nvidia NIM')")
        await db.execute("INSERT INTO model_families (id, display_name) VALUES ('gemini', 'Google Gemini Family')")
        await db.execute("INSERT INTO model_families (id, display_name) VALUES ('nemotron', 'Nvidia Nemotron Family')")

        # Insere modelos da família Gemini
        await db.execute("INSERT INTO models (id, provider_id, name, display_name) VALUES ('gemini/gemini-2.5-pro', 'gemini', 'gemini-2.5-pro', 'Gemini 2.5 Pro')")
        await db.execute("INSERT INTO models (id, provider_id, name, display_name) VALUES ('gemini/gemini-2.5-flash', 'gemini', 'gemini-2.5-flash', 'Gemini 2.5 Flash')")
        await db.execute("INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES ('gemini/gemini-2.5-pro', 95)")
        await db.execute("INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES ('gemini/gemini-2.5-flash', 90)")

        # Insere modelos da família Nemotron
        await db.execute("INSERT INTO models (id, provider_id, name, display_name) VALUES ('nvidia/nvidia/nemotron-3-ultra-550b-a55b', 'nvidia', 'nemotron-ultra', 'Nemotron Ultra')")
        await db.execute("INSERT INTO models (id, provider_id, name, display_name) VALUES ('nvidia/nemotron-70b', 'nvidia', 'nemotron-70b', 'Nemotron 70B')")
        await db.execute("INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES ('nvidia/nvidia/nemotron-3-ultra-550b-a55b', 85)")
        # Insere membros nas famílias model_family_members
        # Gemini cadastrado com gemini/
        await db.execute("INSERT INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('mfm_gemini_1', 'gemini', 'gemini/gemini-2.5-pro', 1)")
        await db.execute("INSERT INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('mfm_gemini_2', 'gemini', 'gemini/gemini-2.5-flash', 2)")

        # Nemotron cadastrado com openrouter/ e :free
        await db.execute("INSERT INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('mfm_nemo_1', 'nemotron', 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free', 1)")
        await db.execute("INSERT INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('mfm_nemo_2', 'nemotron', 'nvidia/nemotron-70b', 2)")
        await db.commit()

        # 1. Verifica resolução de família para gemini/gemini-2.5-pro e models/gemini-2.5-pro
        fam_gemini = await _get_family_for_model("gemini/gemini-2.5-pro", db)
        assert fam_gemini is not None
        assert fam_gemini[0] == "gemini"
        member_ids_gemini = [m[0] for m in fam_gemini[1]]
        assert "gemini/gemini-2.5-flash" in member_ids_gemini

        fam_gemini_alt = await _get_family_for_model("models/gemini-2.5-pro", db)
        assert fam_gemini_alt is not None
        assert fam_gemini_alt[0] == "gemini"

        # 2. Verifica resolução de família para nvidia/nvidia/nemotron-3-ultra-550b-a55b
        fam_nemotron = await _get_family_for_model("nvidia/nvidia/nemotron-3-ultra-550b-a55b", db)
        assert fam_nemotron is not None
        assert fam_nemotron[0] == "nemotron"
        member_ids_nemotron = [m[0] for m in fam_nemotron[1]]
        assert "nvidia/nemotron-70b" in member_ids_nemotron

        # 3. Testa failover Tier 1 do Gemini 2.5 Pro para Gemini 2.5 Flash
        resolved = await resolve_model_with_failover("gemini/gemini-2.5-pro", db, force_skip=True)
        assert resolved.was_failover is True
        assert resolved.family_id == "gemini"
        assert resolved.model_id == "gemini/gemini-2.5-flash"


@pytest.mark.asyncio
async def test_cascade_cross_provider_canonical_exclusion():
    """
    Garante que dois provedores do mesmo modelo canônico com 0 tokens
    não voltam na segunda tentativa dentro da mesma cascata.
    """
    async with aiosqlite.connect(":memory:") as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                share_admin_key INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                enabled INTEGER DEFAULT 1
            )
        """)
        await db.execute("CREATE TABLE model_families (id TEXT PRIMARY KEY, display_name TEXT)")
        await db.execute("CREATE TABLE model_family_members (id TEXT PRIMARY KEY, family_id TEXT, model_id TEXT, fallback_order INTEGER)")
        await db.execute("CREATE TABLE model_rankings (model_id TEXT PRIMARY KEY, nexuslocal_score REAL DEFAULT 0)")
        await db.execute("CREATE TABLE model_quota_status (model_id TEXT PRIMARY KEY, status TEXT, consecutive_errors INTEGER DEFAULT 0, exhausted_at TEXT, last_error_message TEXT, estimated_reset_at TEXT)")
        await db.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")

        await db.execute("INSERT INTO providers (id, name) VALUES ('openrouter', 'OpenRouter')")
        await db.execute("INSERT INTO providers (id, name) VALUES ('nvidia', 'Nvidia')")
        await db.execute("INSERT INTO providers (id, name) VALUES ('groq', 'Groq')")

        m_nemo_openrouter = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
        m_nemo_nvidia = "nvidia/nvidia/nemotron-3-ultra-550b-a55b"
        m_llama_groq = "groq/llama-3.3-70b"

        await db.execute(f"INSERT INTO models (id, provider_id, name, display_name) VALUES ('{m_nemo_openrouter}', 'openrouter', 'nemo-free', 'Nemotron Free')")
        await db.execute(f"INSERT INTO models (id, provider_id, name, display_name) VALUES ('{m_nemo_nvidia}', 'nvidia', 'nemo-nim', 'Nemotron NIM')")
        await db.execute(f"INSERT INTO models (id, provider_id, name, display_name) VALUES ('{m_llama_groq}', 'groq', 'llama-3.3', 'Llama 3.3 70B')")

        # Nemotron NIM tem score maior (98) que Llama (90), mas compartilha canonical com m_nemo_openrouter (que falhou)
        await db.execute(f"INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES ('{m_nemo_openrouter}', 80)")
        await db.execute(f"INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES ('{m_nemo_nvidia}', 98)")
        await db.execute(f"INSERT INTO model_rankings (model_id, nexuslocal_score) VALUES ('{m_llama_groq}', 90)")
        await db.commit()

        # Falha de m_nemo_openrouter: deve pular m_nemo_nvidia e escolher m_llama_groq
        resolved = await resolve_model_with_failover(
            requested_model_id=m_nemo_openrouter,
            db=db,
            force_skip=True,
            exclude_model_ids=[m_nemo_openrouter],
        )
        assert resolved.model_id == m_llama_groq
        assert resolved.model_id != m_nemo_nvidia


@pytest.mark.asyncio
async def test_zero_token_cooldown_survives_restart_and_propagates_canonical(tmp_path):
    """
    Garante que:
    1. O cooldown de 0 tokens é persistido no SQLite e sobrevive a reinício/nova conexão.
    2. Quando 2 provedores do mesmo modelo canônico falham com 0 tokens, o cooldown
       é propagado para todos os provedores variantes no escopo canônico.
    """
    db_file = tmp_path / "test_restart.db"

    # 1. Cria e popula o banco
    async with aiosqlite.connect(str(db_file)) as db:
        await db.execute("""
            CREATE TABLE providers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                share_admin_key INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE models (
                id TEXT PRIMARY KEY,
                provider_id TEXT NOT NULL,
                name TEXT NOT NULL,
                display_name TEXT,
                enabled INTEGER DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE model_quota_status (
                model_id TEXT PRIMARY KEY,
                status TEXT DEFAULT 'available',
                consecutive_errors INTEGER DEFAULT 0,
                exhausted_at TEXT,
                estimated_reset_at TEXT,
                last_error_message TEXT
            )
        """)
        await db.execute("INSERT INTO providers (id, name) VALUES ('openrouter', 'OpenRouter')")
        await db.execute("INSERT INTO providers (id, name) VALUES ('nvidia', 'Nvidia')")
        await db.execute("INSERT INTO providers (id, name) VALUES ('siliconflow', 'SiliconFlow')")

        m1 = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
        m2 = "nvidia/nvidia/nemotron-3-ultra-550b-a55b"
        m3 = "siliconflow/nvidia/nemotron-3-ultra-550b-a55b"

        await db.execute(f"INSERT INTO models (id, provider_id, name) VALUES ('{m1}', 'openrouter', 'n1')")
        await db.execute(f"INSERT INTO models (id, provider_id, name) VALUES ('{m2}', 'nvidia', 'n2')")
        await db.execute(f"INSERT INTO models (id, provider_id, name) VALUES ('{m3}', 'siliconflow', 'n3')")
        await db.commit()

        # Primeiro provedor falha com 0 tokens
        await apply_zero_token_cooldown(m1, db, retry_after=600)

        # Segundo provedor do mesmo modelo canônico também falha com 0 tokens
        await apply_zero_token_cooldown(m2, db, retry_after=600)
        await db.commit()

    # 2. SIMULAÇÃO DE RESTART DO CONTAINER:
    # Abre uma NOVA conexão a partir do arquivo persistido
    async with aiosqlite.connect(str(db_file)) as db_after_restart:
        # m1 e m2 devem estar em cooldown
        q1 = await get_quota_status(m1, db_after_restart)
        q2 = await get_quota_status(m2, db_after_restart)
        assert q1["status"] == "exhausted"
        assert q2["status"] == "exhausted"

        # m3 (SiliconFlow) DEVE ter recebido o cooldown canônico propagado!
        q3 = await get_quota_status(m3, db_after_restart)
        assert q3["status"] == "exhausted"
        assert "Canonical cooldown" in q3["last_error_message"]
