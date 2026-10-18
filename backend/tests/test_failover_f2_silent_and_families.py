import pytest
from datetime import datetime, timezone
import aiosqlite

from backend.database import init_db, get_db
from backend.ranking.failover import (
    canonical_model_id,
    _get_family_for_model,
    _get_next_best_ranked_model,
    resolve_model_with_failover,
)
from backend.ranking.quota import mark_model_exhausted, get_quota_status


def test_canonical_model_id_normalization():
    assert canonical_model_id("openrouter/nvidia/nemotron-3-ultra-550b-a55b:free") == "nemotron-3-ultra-550b-a55b"
    assert canonical_model_id("nvidia/nvidia/nemotron-3-ultra-550b-a55b") == "nemotron-3-ultra-550b-a55b"
    assert canonical_model_id("gemini/gemini-2.5-pro") == "gemini-2.5-pro"
    assert canonical_model_id("models/gemini-2.5-pro") == "gemini-2.5-pro"
    assert canonical_model_id("openrouter/google/gemma-4-31b-it:free") == "gemma-4-31b-it"


@pytest.mark.asyncio
async def test_family_matching_tier1_with_prefixes():
    """(c) match de família no Tier 1 com prefixos gemini/ e nvidia/nvidia/ + :free."""
    await init_db()
    db = await get_db()
    try:
        # Cadastrar provedores com share_admin_key=1 para permitir uso
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('gemini', 'Gemini', 'https://api.gemini', 1, 1)")
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('openrouter', 'OpenRouter', 'https://api.openrouter', 1, 1)")
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('nvidia', 'Nvidia', 'https://api.nvidia', 1, 1)")

        # Cadastrar modelos
        await db.execute("INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('gemini/gemini-2.5-pro', 'gemini', 'gemini-2.5-pro', 'Gemini 2.5 Pro', 1)")
        await db.execute("INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('gemini/gemini-3.8-flash', 'gemini', 'gemini-3.8-flash', 'Gemini 3.8 Flash', 1)")
        await db.execute("INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('openrouter/nvidia/nemotron-3-ultra-550b-a55b:free', 'openrouter', 'nemotron:free', 'Nemotron Free', 1)")
        await db.execute("INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('nvidia/nemotron-70b', 'nvidia', 'nemotron-70b', 'Nemotron 70B', 1)")

        # Cadastrar famílias
        await db.execute("INSERT OR REPLACE INTO model_families (id, display_name) VALUES ('gemini', 'Google Gemini Family')")
        await db.execute("INSERT OR REPLACE INTO model_families (id, display_name) VALUES ('nemotron', 'Nvidia Nemotron Family')")

        # Membros da família gemini
        await db.execute("INSERT OR REPLACE INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('m_gemini_1', 'gemini', 'gemini/gemini-2.5-pro', 1)")
        await db.execute("INSERT OR REPLACE INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('m_gemini_2', 'gemini', 'gemini/gemini-3.8-flash', 2)")

        # Membros da família nemotron (cadastrado com openrouter/ e :free)
        await db.execute("INSERT OR REPLACE INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('m_nemo_1', 'nemotron', 'openrouter/nvidia/nemotron-3-ultra-550b-a55b:free', 1)")
        await db.execute("INSERT OR REPLACE INTO model_family_members (id, family_id, model_id, fallback_order) VALUES ('m_nemo_2', 'nemotron', 'nvidia/nemotron-70b', 2)")

        await db.commit()

        # Match 1: gemini/gemini-2.5-pro
        fam_gemini = await _get_family_for_model("gemini/gemini-2.5-pro", db)
        assert fam_gemini is not None
        assert fam_gemini[0] == "gemini"

        # Match 2: nvidia/nvidia/nemotron-3-ultra-550b-a55b reconhece a família nemotron por canonical match
        fam_nemo = await _get_family_for_model("nvidia/nvidia/nemotron-3-ultra-550b-a55b", db)
        assert fam_nemo is not None
        assert fam_nemo[0] == "nemotron"

        # Teste de failover Tier 1 do Gemini 2.5 Pro para Gemini 3.8 Flash
        resolved = await resolve_model_with_failover("gemini/gemini-2.5-pro", db, force_skip=True)
        assert resolved.was_failover is True
        assert resolved.model_id == "gemini/gemini-3.8-flash"
        assert resolved.family_id == "gemini"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_cross_provider_exclusion_after_zero_tokens():
    """(a) exclusão cross-provider após 0 tokens."""
    await init_db()
    db = await get_db()
    try:
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('openrouter', 'OpenRouter', 'https://api.openrouter', 1, 1)")
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('nvidia', 'Nvidia', 'https://api.nvidia', 1, 1)")
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('groq', 'Groq', 'https://api.groq', 1, 1)")

        # Dois providers para o mesmo modelo base nemotron-3-ultra-550b-a55b
        m_failed = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
        m_same_canon = "nvidia/nvidia/nemotron-3-ultra-550b-a55b"
        m_different = "groq/llama-3.3-70b"

        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{m_failed}', 'openrouter', 'nemo-free', 'Nemotron Free', 1)")
        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{m_same_canon}', 'nvidia', 'nemo-nvidia', 'Nemotron Nvidia', 1)")
        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{m_different}', 'groq', 'llama-3.3', 'Llama 3.3 70B', 1)")

        # Rankings: m_same_canon tem score 95, m_different tem score 90
        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{m_failed}', 80)")
        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{m_same_canon}', 95)")
        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{m_different}', 90)")
        await db.commit()

        # m_failed falhou na cascata (está em exclude_model_ids)
        # Tier 2 deve pular m_same_canon (mesmo com score maior) e escolher m_different!
        resolved = await resolve_model_with_failover(
            requested_model_id=m_failed,
            db=db,
            force_skip=True,
            exclude_model_ids=[m_failed],
        )
        assert resolved.model_id == m_different
        assert resolved.model_id != m_same_canon
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_cooldown_between_requests_after_zero_tokens():
    """(b) cooldown entre requisições após 0 tokens."""
    await init_db()
    db = await get_db()
    try:
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('openrouter', 'OpenRouter', 'https://api.openrouter', 1, 1)")
        await db.execute("INSERT OR REPLACE INTO providers (id, name, base_url, enabled, share_admin_key) VALUES ('groq', 'Groq', 'https://api.groq', 1, 1)")

        model_zero = "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free"
        model_backup = "groq/llama-3.3-70b"

        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{model_zero}', 'openrouter', 'nemo-free', 'Nemotron Free', 1)")
        await db.execute(f"INSERT OR REPLACE INTO models (id, provider_id, name, display_name, enabled) VALUES ('{model_backup}', 'groq', 'llama-3.3', 'Llama 3.3 70B', 1)")

        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{model_zero}', 95)")
        await db.execute(f"INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score) VALUES ('{model_backup}', 90)")
        await db.commit()

        # Simula 0 tokens gerados: aplica cooldown temporário
        await mark_model_exhausted(
            model_zero,
            db,
            retry_after=600,
            error_msg="Silent failure: 0 tokens returned",
        )

        # Verifica status de cota do modelo
        quota = await get_quota_status(model_zero, db)
        assert quota["status"] == "exhausted"
        assert "Silent failure" in quota["last_error_message"]

        # Nova requisição subsequente solicitando model_zero sem force_skip:
        # Não pode usar model_zero (pois está esgotado), caindo em failover para model_backup
        resolved = await resolve_model_with_failover(
            requested_model_id=model_zero,
            db=db,
        )
        assert resolved.was_failover is True
        assert resolved.model_id == model_backup

        # No ranking geral Tier 2 diretamente:
        next_model = await _get_next_best_ranked_model(db=db, exclude_model_ids=[], exclude_family_ids=[])
        assert next_model is not None
        assert next_model[0] == model_backup
    finally:
        await db.close()
