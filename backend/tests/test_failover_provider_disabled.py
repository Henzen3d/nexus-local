"""
backend/tests/test_failover_provider_disabled.py
Validação estrita da cascata de failover e auto-router com provedores desabilitados.
Garante que modelos de provedores com enabled = 0 NUNCA sejam selecionados nem causem crash no chat.
"""
import pytest
import aiosqlite
from unittest.mock import AsyncMock, patch

from backend.database import DB_PATH, init_db
from backend.ranking.failover import (
    resolve_model_with_failover,
    _get_family_for_model,
    _get_next_best_ranked_model,
    NoAvailableModelError,
)
from backend.ranking.smart_router import (
    classify_intent,
    select_best_model,
    invalidate_model_cache,
)


@pytest.fixture
async def setup_failover_db():
    await init_db()
    async with aiosqlite.connect(DB_PATH) as db:
        # Cria provedor ativo e provedor desativado (simulando qwen desativado no painel)
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) VALUES ('prov_active', 'Active Provider', 'http://active', 1, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) VALUES ('prov_disabled', 'Disabled Provider', 'http://disabled', 0, 0)"
        )

        # Insere modelos
        # Modelo 1: Primário ativo (mas que vamos simular esgotamento)
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_primary', 'primary', 'Model Primary', 'prov_active', 1, 16384)"
        )
        # Modelo 2: Irmão da mesma família, mas cujo provedor foi desabilitado
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_fam_disabled', 'fam_disabled', 'Model Family Disabled', 'prov_disabled', 1, 16384)"
        )
        # Modelo 3: Irmão da mesma família com provedor ativo
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_fam_active', 'fam_active', 'Model Family Active', 'prov_active', 1, 16384)"
        )
        # Modelo 4: Modelo fora da família com score alto, mas provedor desabilitado (tipo Qwen)
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_high_score_disabled', 'qwen-max', 'Qwen Max', 'prov_disabled', 1, 16384)"
        )
        # Modelo 5: Modelo fora da família com score médio e provedor ativo
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_tier2_active', 'tier2_active', 'Tier 2 Active', 'prov_active', 1, 16384)"
        )

        # Rankings
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('model_primary', 95.0, 95.0, 1)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('model_high_score_disabled', 99.0, 99.0, 0)"  # Score altíssimo, mas provedor desativado!
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('model_tier2_active', 85.0, 85.0, 2)"
        )

        # Família
        await db.execute("INSERT OR REPLACE INTO model_families (id, display_name) VALUES ('test_fam', 'Test Family')")
        await db.execute(
            "INSERT OR REPLACE INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam', 'model_primary', 1)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam', 'model_fam_disabled', 2)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_family_members (family_id, model_id, fallback_order) VALUES ('test_fam', 'model_fam_active', 3)"
        )

        await db.commit()
    yield DB_PATH


@pytest.mark.asyncio
async def test_failover_skips_disabled_provider_in_family(setup_failover_db):
    """Tier 1: Modelo primário esgotado, irmão subsequente tem provedor desabilitado -> pula e pega o irmão com provedor ativo."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Marca primário como esgotado
        await db.execute(
            "INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model_primary', 'exhausted')"
        )
        await db.commit()

        # Resolução com failover
        resolved = await resolve_model_with_failover("model_primary", db)
        assert resolved.was_failover is True
        # Deve ter pulado 'model_fam_disabled' (porque prov_disabled tem enabled = 0) e escolhido 'model_fam_active'
        assert resolved.model_id == "model_fam_active"
        assert resolved.provider_id == "prov_active"


@pytest.mark.asyncio
async def test_failover_tier2_ignores_high_score_disabled_provider(setup_failover_db):
    """Tier 2: Todos da família esgotados. O modelo com maior score global tem provedor desativado -> deve ser ignorado."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Marca todos os membros da família como esgotados
        await db.execute(
            "INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model_primary', 'exhausted')"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model_fam_active', 'exhausted')"
        )
        await db.commit()

        resolved = await resolve_model_with_failover("model_primary", db)
        assert resolved.was_failover is True
        # Apesar de 'model_high_score_disabled' ter score 99.0 contra 85.0 de 'model_tier2_active',
        # o provedor dele está desativado (enabled = 0), então Tier 2 escolhe 'model_tier2_active'.
        assert resolved.model_id == "model_tier2_active"
        assert resolved.provider_id == "prov_active"


@pytest.mark.asyncio
async def test_resolve_directly_requested_disabled_provider_triggers_failover(setup_failover_db):
    """Se o usuário ou frontend requisitar diretamente um modelo cujo provedor foi desativado, o failover desvia imediatamente."""
    async with aiosqlite.connect(DB_PATH) as db:
        resolved = await resolve_model_with_failover("model_high_score_disabled", db, failover_enabled=True)
        assert resolved.was_failover is True
        assert resolved.model_id == "model_tier2_active"
        assert resolved.provider_id == "prov_active"


@pytest.mark.asyncio
async def test_smart_router_filters_disabled_providers_in_real_time(setup_failover_db):
    """Smart router exclui imediatamente modelos de provedores desativados mesmo com cache de modelos."""
    invalidate_model_cache()
    async with aiosqlite.connect(DB_PATH) as db:
        intent = classify_intent("escreva uma redação sobre o futuro")
        decision1 = await select_best_model(intent, "balanced_smart", db)
        assert decision1.provider_id != "prov_disabled"

        # Agora desativa o provedor que foi escolhido
        chosen_provider = decision1.provider_id
        await db.execute("UPDATE providers SET enabled = 0 WHERE id = ?", (chosen_provider,))
        await db.commit()

        # Sem chamar invalidate_model_cache() manualmente — a filtragem em tempo real deve ignorar o provedor agora desabilitado
        decision2 = await select_best_model(intent, "balanced_smart", db)
        assert decision2.provider_id != chosen_provider
        assert decision2.provider_id != "prov_disabled"


@pytest.mark.asyncio
async def test_stream_from_llm_recovers_from_disabled_provider_value_error(setup_failover_db):
    """Garante que stream_from_llm não aborte ao encontrar ValueError('Provider disabled'), fazendo failover para o próximo."""
    from backend.orchestration.resolve_request import stream_from_llm

    mock_ws = AsyncMock()
    sent_messages = []
    async def capture_send(msg):
        sent_messages.append(msg)
    mock_ws.send_json.side_effect = capture_send

    class FakeProvider:
        async def stream_chat(self, **kwargs):
            yield "Resposta de contingência gerada com sucesso."

    async with aiosqlite.connect(DB_PATH) as db:
        # Mock get_provider para falhar na primeira chamada com prov_disabled e ter sucesso na segunda
        original_get_provider = None
        from backend.providers import registry
        real_get_provider = registry.get_provider

        calls = []
        async def mock_get_provider(pid, database, user_id=None):
            calls.append(pid)
            if pid == "prov_disabled":
                raise ValueError("Provider 'prov_disabled' is disabled.")
            return FakeProvider()

        with patch("backend.orchestration.resolve_request.get_provider", side_effect=mock_get_provider):
            res = await stream_from_llm(
                ws=mock_ws,
                db=db,
                conversation_id="conv-123",
                user_id="user-123",
                model_id="model_high_score_disabled",
                provider_id="prov_disabled",
                history=[{"role": "user", "content": "Olá"}],
            )

            assert res is not None
            full_response, resolved_mid, resolved_pid = res
            assert "Resposta de contingência" in full_response
            assert resolved_pid != "prov_disabled"
            # O websocket não deve ter recebido mensagem fatal de erro
            error_msgs = [m for m in sent_messages if m.get("type") == "error"]
            assert len(error_msgs) == 0


@pytest.mark.asyncio
async def test_qwen_model_from_active_provider_allowed_while_qwen_provider_disabled(setup_failover_db):
    """Garante que modelos da família Qwen providos por provedores ativos participem normalmente,
    mas modelos do provedor 'qwen' (desabilitado) sejam estritamente bloqueados."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Provedor qwen nativo (desativado nas configurações)
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) "
            "VALUES ('qwen', 'Qwen Cloud', 'https://dashscope.aliyuncs.com', 0, 0)"
        )
        # Provedor cloudflare (ativo) servindo um modelo qwen
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) "
            "VALUES ('cloudflare', 'Cloudflare Workers AI', 'https://api.cloudflare.com', 1, 1)"
        )

        # Modelo 1: Qwen servido pelo provedor Qwen (desativado)
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('qwen/qwen3.5-plus', 'qwen3.5-plus', 'Qwen 3.5 Plus', 'qwen', 1, 32768)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('qwen/qwen3.5-plus', 99.5, 99.5, 1)"
        )

        # Modelo 2: Qwen servido pelo provedor Cloudflare (ativo)
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('cloudflare/qwen-2.5-coder-32b', 'qwen-2.5-coder-32b', 'Qwen 2.5 Coder 32B', 'cloudflare', 1, 32768)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('cloudflare/qwen-2.5-coder-32b', 92.0, 92.0, 2)"
        )
        await db.commit()

        # 1. Se requisitar diretamente o modelo do provedor desativado (qwen/qwen3.5-plus)
        res_direct = await resolve_model_with_failover("qwen/qwen3.5-plus", db, failover_enabled=True)
        assert res_direct.was_failover is True
        assert res_direct.provider_id != "qwen"
        assert res_direct.model_id != "qwen/qwen3.5-plus"

        # 2. Se requisitar o modelo Qwen servido pelo Cloudflare (ativo)
        res_cf = await resolve_model_with_failover("cloudflare/qwen-2.5-coder-32b", db, failover_enabled=True)
        assert res_cf.was_failover is False
        assert res_cf.model_id == "cloudflare/qwen-2.5-coder-32b"
        assert res_cf.provider_id == "cloudflare"

        # 3. Em failover Tier 2 quando outros estão esgotados, o modelo Qwen do Cloudflare PODE ser o destino
        await db.execute("INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model_primary', 'exhausted')")
        await db.execute("INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model_tier2_active', 'exhausted')")
        await db.commit()

        res_fallback = await resolve_model_with_failover("model_primary", db, failover_enabled=True)
        assert res_fallback.was_failover is True
        # Não pode ter sido o qwen nativo desativado (mesmo com score 99.5)
        assert res_fallback.provider_id != "qwen"
        assert res_fallback.model_id != "qwen/qwen3.5-plus"


@pytest.mark.asyncio
async def test_failover_skips_paid_provider_without_key_when_user_id_passed(setup_failover_db):
    """Garante que provedores pagos sem chave configurada para o usuário sejam ignorados no failover."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Provedor pago ativo, mas usuário não tem chave
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) "
            "VALUES ('prov_paid_nokey', 'Paid No Key', 'https://paid', 1, 0)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_paid_nokey', 'paid-nokey', 'Paid No Key', 'prov_paid_nokey', 1, 16384)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('model_paid_nokey', 98.0, 98.0, 1)"
        )

        # Provedor gratuito ativo (com chave ou local)
        await db.execute(
            "INSERT OR REPLACE INTO providers (id, name, base_url, enabled, is_free) "
            "VALUES ('prov_free_key', 'Free Provider', 'https://free', 1, 1)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO models (id, name, display_name, provider_id, enabled, context_length) "
            "VALUES ('model_free_key', 'free-key', 'Free Key Model', 'prov_free_key', 1, 16384)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score, popularity_rank) "
            "VALUES ('model_free_key', 80.0, 80.0, 5)"
        )

        # Marca primário como esgotado
        await db.execute("INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model_primary', 'exhausted')")
        await db.commit()

        # Resolução passando user_id (usuário não tem chave para prov_paid_nokey)
        resolved = await resolve_model_with_failover("model_primary", db, user_id="user_without_keys")
        assert resolved.was_failover is True
        # Deve ter ignorado model_paid_nokey (faltando chave) e prov_disabled (desativado)
        assert resolved.provider_id != "prov_paid_nokey"
        assert resolved.provider_id != "prov_disabled"


@pytest.mark.asyncio
async def test_suggest_families_excludes_disabled_providers(setup_failover_db):
    """Garante que a rota suggest_families nunca liste modelos pertencentes a provedores desativados."""
    from backend.routers.families import suggest_family_groupings
    suggestions = await suggest_family_groupings(current_user={"id": "admin", "role": "admin"})
    
    for sugg in suggestions:
        matched = sugg.get("matched_models", [])
        for m in matched:
            assert not m["id"].startswith("prov_disabled/")
            assert "Qwen Max" not in m["display_name"]


@pytest.mark.asyncio
async def test_dashboard_quotas_excludes_disabled_providers(setup_failover_db):
    """Garante que a rota /dashboard/quotas não liste modelos de provedores desativados como esgotados."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Marca modelo do provedor desativado como esgotado
        await db.execute(
            "INSERT OR REPLACE INTO model_quota_status (model_id, status, consecutive_errors, last_error_message) "
            "VALUES ('model_high_score_disabled', 'exhausted', 5, 'Rate limit 429')"
        )
        await db.commit()

    from backend.routers.dashboard import get_quota_status
    quotas = await get_quota_status(current_user={"id": "admin", "role": "admin"})
    
    # Não deve incluir model_high_score_disabled porque prov_disabled está desativado (enabled = 0)
    for q in quotas:
        assert q["model_id"] != "model_high_score_disabled"
        assert q["provider_id"] != "prov_disabled"



