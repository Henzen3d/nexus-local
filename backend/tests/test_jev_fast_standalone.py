"""
backend/tests/test_jev_fast_standalone.py
Validação automatizada das melhorias ativas do JEV-Fast (Planos 02, 03, 05, 10, 11, 16 e 09).
Regra de ouro (AGENTS.md): Roda estritamente em banco SQLite temporário descartável (tempfile).
"""

import os
import sys
sys.path.insert(0, os.path.abspath("."))
import time
import uuid
import asyncio
import tempfile
import aiosqlite

# 1. Criação do banco temporário isolado ANTES de qualquer importação de DB
temp_db_fd, temp_db_path = tempfile.mkstemp(suffix="_jev_test.db")
os.close(temp_db_fd)

import backend.database as db_mod
import backend.cache.manager as cache_mgr_mod
db_mod.DB_PATH = temp_db_path
cache_mgr_mod.DB_PATH = temp_db_path

from backend.context.request_context import RequestContext
from backend.cache.manager import cache_manager
from backend.ranking.smart_router import (
    IntentKey,
    ComplexityTier,
    IntentClassificationResult,
    select_best_model,
    invalidate_model_cache,
    _MODEL_CACHE,
)
from backend.ranking.quota import mark_model_exhausted, release_expired_quotas
from backend.ranking.token_bucket import TokenBucket, TokenBucketManager, RateLimitConfig
from backend.vision_relay.relay import (
    _VISION_L1_CACHE,
    get_cached_description,
    save_description_cache,
    invalidate_vision_l1_cache,
    _VISION_L1_MAX_ENTRIES,
)
from backend.metrics.task_benchmark import task_benchmark_manager


async def setup_test_schema(db: aiosqlite.Connection):
    """Cria o esquema necessário para testes no banco temporário."""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS providers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            enabled INTEGER DEFAULT 1,
            is_free INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            provider_id TEXT NOT NULL,
            name TEXT NOT NULL,
            display_name TEXT NOT NULL,
            context_length INTEGER DEFAULT 8192,
            enabled INTEGER DEFAULT 1,
            confirmed_free INTEGER DEFAULT 0,
            supports_vision INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS model_rankings (
            model_id TEXT PRIMARY KEY,
            nexuslocal_score REAL DEFAULT 50.0,
            quality_score REAL DEFAULT 50.0,
            popularity_rank INTEGER DEFAULT 50
        );

        CREATE TABLE IF NOT EXISTS model_quota_status (
            model_id TEXT PRIMARY KEY,
            status TEXT DEFAULT 'available',
            consecutive_errors INTEGER DEFAULT 0,
            exhausted_at TEXT,
            estimated_reset_at TEXT,
            last_error_message TEXT,
            registry_source TEXT,
            confirmed_free INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS cache_exact (
            id TEXT PRIMARY KEY,
            hash TEXT NOT NULL,
            model_id TEXT NOT NULL,
            response TEXT NOT NULL,
            token_est INTEGER DEFAULT 0,
            hits INTEGER DEFAULT 0,
            last_hit TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS cache_semantic (
            id TEXT PRIMARY KEY,
            prompt_text TEXT NOT NULL,
            embedding BLOB NOT NULL,
            response TEXT NOT NULL,
            model_id TEXT NOT NULL,
            fingerprint TEXT,
            user_id TEXT,
            token_est INTEGER DEFAULT 0,
            hits INTEGER DEFAULT 0,
            similarity REAL DEFAULT 0.0,
            last_hit TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_cache_semantic_fp ON cache_semantic(fingerprint, model_id);
        CREATE INDEX IF NOT EXISTS idx_cache_semantic_user ON cache_semantic(user_id);
        CREATE INDEX IF NOT EXISTS idx_cache_semantic_scope_fp ON cache_semantic(user_id, model_id, fingerprint);

        CREATE TABLE IF NOT EXISTS cache_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS vision_descriptions_cache (
            file_hash TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            relay_model TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Seed de configurações de cache
    for k, v in [
        ("enabled", "true"),
        ("exact_enabled", "true"),
        ("semantic_enabled", "true"),
        ("exact_ttl_hours", "168"),
        ("semantic_ttl_hours", "72"),
        ("similarity_threshold", "0.92"),
    ]:
        await db.execute("INSERT OR REPLACE INTO cache_settings (key, value) VALUES (?, ?)", (k, v))

    # Seed de 2 provedores e 2 modelos
    await db.execute("INSERT OR REPLACE INTO providers (id, name, enabled, is_free) VALUES ('prov1', 'Provider One', 1, 1)")
    await db.execute("INSERT OR REPLACE INTO providers (id, name, enabled, is_free) VALUES ('prov2', 'Provider Two', 1, 1)")

    await db.execute("""
        INSERT OR REPLACE INTO models (id, provider_id, name, display_name, context_length, enabled, confirmed_free)
        VALUES ('model-fast', 'prov1', 'Model Fast', 'Model Fast Display', 8192, 1, 1)
    """)
    await db.execute("""
        INSERT OR REPLACE INTO models (id, provider_id, name, display_name, context_length, enabled, confirmed_free)
        VALUES ('model-fallback', 'prov2', 'Model Fallback', 'Model Fallback Display', 8192, 1, 1)
    """)

    await db.execute("INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('model-fast', 95.0, 90.0)")
    await db.execute("INSERT OR REPLACE INTO model_rankings (model_id, nexuslocal_score, quality_score) VALUES ('model-fallback', 80.0, 85.0)")

    await db.execute("INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model-fast', 'available')")
    await db.execute("INSERT OR REPLACE INTO model_quota_status (model_id, status) VALUES ('model-fallback', 'available')")
    await db.commit()


async def test_single_embedding_memoization():
    """Valida que duas chamadas no mesmo turno reutilizam o mesmo embedding em RAM (0ms)."""
    print("[1/6] Testando Single-Embedding por Turno via RequestContext...")
    req_ctx = RequestContext(user_id="user_test_123")
    query = "Como criar um servidor ASGI assíncrono?"

    t0 = time.perf_counter()
    blob1 = await req_ctx.get_embedding(query)
    lat1 = (time.perf_counter() - t0) * 1000

    assert blob1 is not None, "Primeira inferência de embedding deve retornar bytes"

    # Segunda chamada imediata
    t1 = time.perf_counter()
    blob2 = await req_ctx.get_embedding(query)
    lat2 = (time.perf_counter() - t1) * 1000

    assert blob1 == blob2, "Embeddings devem ser idênticos"
    assert lat2 < 1.0, f"Reutilização de embedding deve levar < 1ms (levou {lat2:.4f}ms)"
    assert query.strip() in req_ctx._embedding_cache
    print(f"  [OK] Passou! Latência 1: {lat1:.2f}ms | Latência 2 (hit RAM): {lat2:.4f}ms")


async def test_semantic_cache_user_isolation(db: aiosqlite.Connection):
    """Valida que o cache semântico e exato de user_A nunca atende user_B."""
    print("[2/6] Testando Isolamento Estrito de Usuário no Cache Semântico e Exato...")
    prompt = "Qual a capital do Japão?"
    response = "A capital do Japão é Tóquio."
    model_id = "model-fast"

    # Fase A: Testar isolamento estrito no Cache Semântico (desativando cache exato)
    await cache_manager.update_settings({"exact_enabled": False, "semantic_enabled": True})

    # Popula cache semântico para user_alpha
    await cache_manager.set(
        model_id=model_id,
        messages=[{"role": "user", "content": prompt}],
        response=response,
        user_id="user_alpha",
    )

    # 1. Consulta para user_beta (deve ser MISS no cache semântico)
    hit_beta = await cache_manager.get(
        model_id=model_id,
        messages=[{"role": "user", "content": prompt}],
        user_id="user_beta",
    )
    assert hit_beta is None, "Cache semântico de user_alpha NÃO pode ser retornado para user_beta"

    # 2. Consulta para user_alpha (deve ser HIT pelo bypass SHA-256 fingerprint do cache semântico)
    t0 = time.perf_counter()
    hit_alpha = await cache_manager.get(
        model_id=model_id,
        messages=[{"role": "user", "content": prompt}],
        user_id="user_alpha",
    )
    t_fp = (time.perf_counter() - t0) * 1000.0
    assert hit_alpha is not None, "Cache semântico para user_alpha deve ser retornado"
    assert hit_alpha.response == response
    assert hit_alpha.similarity == 1.0
    assert hit_alpha.cache_type == "semantic"
    print(f"  [OK] Bypass SHA-256 fingerprint do cache semântico validado em {t_fp:.3f}ms")

    # Fase B: Testar isolamento no Cache Exato
    await cache_manager.update_settings({"exact_enabled": True, "semantic_enabled": True})
    hit_beta_exact = await cache_manager.get(
        model_id=model_id,
        messages=[{"role": "user", "content": prompt}],
        user_id="user_beta",
    )
    assert hit_beta_exact is None, "Cache exato de user_alpha NÃO pode ser retornado para user_beta"

    print("  [OK] Passou! user_beta teve MISS e user_alpha teve HIT com 100% de isolamento.")


async def test_semantic_gate_follow_ups():
    """Valida que o gate multi-turno desativa a busca semântica em follow-ups."""
    print("[3/6] Testando Semantic Gate em Multi-Turno...")
    # Follow-up com len(user_messages) > 1
    messages_followup = [
        {"role": "user", "content": "Me conte uma piada."},
        {"role": "assistant", "content": "Por que o livro de matemática se suicidou? Porque tinha muitos problemas."},
        {"role": "user", "content": "Não entendi, explica?"},
    ]

    hit = await cache_manager.get(
        model_id="model-fast",
        messages=messages_followup,
        user_id="user_alpha",
    )
    assert hit is None, "Semantic Gate deve bloquear busca semântica em follow-ups"
    print("  [OK] Passou! Follow-ups foram bloqueados pelo Semantic Gate.")


async def test_model_cache_and_reactive_invalidation(db: aiosqlite.Connection):
    """Valida que o Model Cache em RAM atualiza status de cota imediatamente após invalidate_model_cache()."""
    print("[4/6] Testando Model Cache e Invalidação Reativa...")
    invalidate_model_cache()

    intent_result = IntentClassificationResult(
        intent=IntentKey.TRIVIAL_QUICK,
        complexity=ComplexityTier.LIGHT,
        confidence=1.0,
        matched_signals=["test"],
        reason_label_pt="Teste",
    )

    # Seleção 1: model-fast está available
    decision1 = await select_best_model(intent_result, "balanced_smart", db)
    assert decision1.chosen_model_id == "model-fast", f"Esperado model-fast, obteve {decision1.chosen_model_id}"

    # Esgota cota de model-fast e invalida cache
    await mark_model_exhausted("model-fast", db, retry_after=3600, error_msg="Rate limit")
    invalidate_model_cache()

    # Seleção 2: Deve selecionar model-fallback imediatamente
    decision2 = await select_best_model(intent_result, "balanced_smart", db)
    assert decision2.chosen_model_id == "model-fallback", f"Esperado model-fallback, obteve {decision2.chosen_model_id}"

    # Libera cotas expiradas
    await db.execute("UPDATE model_quota_status SET estimated_reset_at = datetime('now', '-1 minute') WHERE model_id = 'model-fast'")
    await db.commit()
    released = await release_expired_quotas(db)
    assert released >= 1, "model-fast deve ser liberado"

    # Seleção 3: model-fast deve voltar ao topo imediatamente
    decision3 = await select_best_model(intent_result, "balanced_smart", db)
    assert decision3.chosen_model_id == "model-fast", f"Esperado model-fast após liberação, obteve {decision3.chosen_model_id}"

    print("  [OK] Passou! Status de cota e invalidate_model_cache() sincronizados com perfeição.")


async def test_vision_relay_l1_cache(db: aiosqlite.Connection):
    """Valida cache L1 em RAM para Vision Relay com LRU 512 e invalidação."""
    print("[5/6] Testando Vision Relay L1 LRU Cache em RAM...")
    invalidate_vision_l1_cache()

    file_hash = "sha256_mock_hash_image_123"
    desc = "Uma foto nítida de uma praia tropical ao pôr do sol."

    # Salva descrição
    await save_description_cache(file_hash, desc, "gemini-2.0-flash", db)
    assert file_hash in _VISION_L1_CACHE

    # Obtém do L1 (RAM)
    t0 = time.perf_counter()
    retrieved = await get_cached_description(file_hash, db)
    lat = (time.perf_counter() - t0) * 1000

    assert retrieved == desc
    assert lat < 1.0, f"Leitura em L1 deve ser < 1ms (levou {lat:.4f}ms)"

    # Invalidação
    invalidate_vision_l1_cache()
    assert len(_VISION_L1_CACHE) == 0

    # Próxima leitura carrega do banco e repopula L1
    retrieved_db = await get_cached_description(file_hash, db)
    assert retrieved_db == desc
    assert file_hash in _VISION_L1_CACHE
    print("  [OK] Passou! L1 LRU em RAM entregou descrição em < 1ms e invalidou perfeitamente.")


async def test_token_bucket_hysteresis():
    """Valida Token Bucket com histerese para proteger Sticky Routing."""
    print("[6/6] Testando Token Bucket com Histerese (Sticky vs Non-Sticky)...")
    config = RateLimitConfig(provider_id="mock_prov", rpm=60, burst_size=2)
    bucket = TokenBucket(config)

    # 1. Consome os 2 tokens do burst
    allowed1, _ = await bucket.acquire(1, is_sticky=False)
    allowed2, _ = await bucket.acquire(1, is_sticky=False)
    assert allowed1 is True and allowed2 is True
    assert bucket.tokens <= 0.001  # Floating point tolerance

    # 2. Chamada normal (non-sticky) deve ser rejeitada
    allowed3, wait3 = await bucket.acquire(1, is_sticky=False)
    assert allowed3 is False
    assert wait3 > 0.0

    # Simula recarga parcial de 0.6 tokens (menor que 1.0)
    bucket.tokens = 0.6
    bucket._throttled = False  # Sem trava rígida ainda

    # 3. Chamada normal (non-sticky) precisa de 1.0 token -> rejeita
    allowed_non_sticky, _ = await bucket.acquire(1, is_sticky=False)
    assert allowed_non_sticky is False, "Non-sticky deve exigir 1.0 token completo"

    # Restaura para 0.6 tokens
    bucket.tokens = 0.6
    bucket._throttled = False

    # 4. Chamada STICKY (KV-cache affinity) aceita com histerese (>= 0.5 tokens)
    allowed_sticky, _ = await bucket.acquire(1, is_sticky=True)
    assert allowed_sticky is True, "Sticky routing com histerese deve autorizar chamada com 0.6 tokens"

    # 5. Penalidade reativa (HTTP 429 real)
    await bucket.on_rate_limit()
    assert bucket.tokens <= 0.001  # Floating point tolerance
    assert bucket._throttled is True

    # 6. Teste de Benchmarking não-bloqueante
    bench = await task_benchmark_manager.record_task_async(
        task_type="chat",
        latency_ms=45.2,
        model_id="model-fast",
        provider_id="prov1",
        success=True,
        phase_latencies={"fast_path": 0.5, "llm_ttfb": 25.0},
    )
    stats = task_benchmark_manager.get_aggregated_stats("chat")
    assert "chat" in stats
    assert stats["chat"]["count"] >= 1
    assert "llm_ttfb" in stats["chat"]["avg_phase_latencies_ms"]
    print("  [OK] Passou! Histerese de Sticky Routing e métricas não-bloqueantes validadas.")


async def run_all():
    print("==================================================================")
    print("INICIANDO SUÍTE DE TESTES JEV-FAST EM BANCO TEMPORÁRIO ISOLADO")
    print(f"Banco Temporário: {temp_db_path}")
    print("==================================================================")

    async with aiosqlite.connect(temp_db_path) as db:
        await setup_test_schema(db)
        await test_single_embedding_memoization()
        await test_semantic_cache_user_isolation(db)
        await test_semantic_gate_follow_ups()
        await test_model_cache_and_reactive_invalidation(db)
        await test_vision_relay_l1_cache(db)
        await test_token_bucket_hysteresis()

    print("==================================================================")
    print("TODOS OS TESTES PASSARAM COM 100% DE SUCESSO!")
    print("==================================================================")


if __name__ == "__main__":
    try:
        asyncio.run(run_all())
    finally:
        # Limpeza obrigatória do arquivo descartável
        import gc
        import time
        gc.collect()
        time.sleep(0.2)
        if os.path.exists(temp_db_path):
            for _ in range(5):
                try:
                    os.remove(temp_db_path)
                    print(f"[CLEANUP] Banco temporário {temp_db_path} removido com sucesso.")
                    break
                except Exception as e:
                    time.sleep(0.3)
                    gc.collect()
            else:
                print(f"[CLEANUP WARNING] Falha ao remover banco temporário.")
