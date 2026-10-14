"""
Testes do ranking de modelos determinístico (Configurações → Rankings de Modelos).

Cobre:
- normalização de nomes entre provedores e casamento de popularidade (OpenRouter);
- qualidade determinística (curadoria > heurística do perfil), nunca aleatória;
- migração das linhas legadas 'auto-seed' (aleatórias) e semeadura de modelos novos;
- sync completo com fonte OpenRouter simulada (sem rede);
- GET /api/ranking: provedor real, filtro de disponibilidade, exclusão de não-chat.

Usa SEMPRE um banco SQLite temporário (conftest + tmp_path) — nunca o nexuslocal.db real.
"""
from __future__ import annotations

import statistics
from pathlib import Path

import aiosqlite
import pytest

from backend import database as dbmod
from backend.ranking.model_profile import profile_model
from backend.ranking.scorer import (
    POPULARITY_NEUTRAL,
    build_ranking_overview,
    calculate_nexuslocal_score,
    normalize_popularity,
)
from backend.ranking.sources import (
    SOURCE_CURATED,
    SOURCE_HEURISTIC,
    SOURCE_LEGACY_RANDOM,
    StaticRegistrySource,
    build_popularity_index,
    match_popularity,
    normalize_model_key,
    resolve_quality,
)
from backend.ranking.sync import (
    migrate_legacy_rankings,
    seed_missing_rankings,
    sync_rankings,
)

# ── Catálogo de teste: (provider, name, enabled, reasoning_control, supports_vision) ──
CATALOG = [
    ("groq", "llama-3.3-70b-versatile", 1, "none", 0),
    ("groq", "llama-3.1-8b-instant", 1, "none", 0),
    ("groq", "openai/gpt-oss-120b", 1, "openai_effort", 0),
    ("cerebras", "llama3.1-8b", 1, "none", 0),
    ("cerebras", "gpt-oss-120b", 1, "none", 0),
    ("gemini", "gemini-2.5-pro", 1, "gemini_thinking", 1),
    ("gemini", "gemini-2.5-flash-lite", 1, "gemini_thinking", 1),
    ("gemini", "gemma-3-27b-it", 1, "none", 1),
    ("openrouter", "deepseek/deepseek-r1:free", 1, "always_on", 0),
    ("openrouter", "moonshotai/kimi-k2:free", 1, "none", 0),
    ("openrouter", "openai/gpt-5.2", 1, "openai_effort", 1),
    ("openrouter", "meta-llama/llama-3.2-3b-instruct:free", 1, "none", 0),
    ("openrouter", "agnes/agnes-image-2.1-flash", 1, "none", 0),   # não-chat (imagem)
    ("openrouter", "openai/text-embedding-3-small", 1, "none", 0),  # não-chat (embedding)
    ("cloudflare", "@cf/meta/llama-3.1-8b-instruct-fp8", 1, "none", 0),
    ("cloudflare", "@cf/qwen/qwen2.5-coder-32b-instruct", 1, "none", 0),
    ("zenmux", "google/gemini-3.8-flash", 1, "none", 1),           # provedor desabilitado (assinatura expirou)
    ("zenmux", "nex-agi/nex-n2-pro", 1, "none", 0),
    ("qwen", "qwen3.5-plus", 1, "none", 0),                          # provedor habilitado, mas sem chave
    ("ollama", "gemma3:4b", 1, "none", 1),
    ("ollama", "llama3.2:1b", 0, "none", 0),                         # modelo desabilitado
]

# provider_id → (nome, enabled, is_free, is_local, api_key global)
PROVIDERS = {
    "groq": ("Groq", 1, 1, 0, "gsk_global"),
    "cerebras": ("Cerebras", 1, 1, 0, "csk_global"),
    "gemini": ("Google Gemini", 1, 1, 0, "AIza_global"),
    "openrouter": ("OpenRouter", 1, 1, 0, "sk-or-global"),
    "cloudflare": ("Cloudflare", 1, 1, 0, "cf_global"),
    "zenmux": ("ZenMux", 0, 0, 0, "zm_expired"),
    "qwen": ("Qwen (Alibaba)", 1, 0, 0, ""),
    "ollama": ("Ollama", 1, 0, 1, ""),
}

USER_ID = "rank-user-1"


def _mid(pid: str, name: str) -> str:
    return f"{pid}/{name}"


# Fixture OpenRouter (ordem = popularidade), simulando /api/v1/models?sort=most-popular
OPENROUTER_FIXTURE = [
    "google/gemini-2.5-flash", "anthropic/claude-sonnet-4.5", "openai/gpt-5.2", "deepseek/deepseek-chat-v3.1",
    "google/gemini-2.5-pro", "deepseek/deepseek-r1:free", "deepseek/deepseek-r1", "moonshotai/kimi-k2",
    "meta-llama/llama-3.3-70b-instruct", "openai/gpt-oss-120b", "qwen/qwen2.5-coder-32b-instruct",
    "meta-llama/llama-3.1-8b-instruct", "google/gemma-3-27b-it", "google/gemini-2.5-flash-lite",
    "meta-llama/llama-3.2-3b-instruct:free", "moonshotai/kimi-k2:free",
]


class _FakeOpenRouter:
    def __init__(self, ids=None):
        self.ids = OPENROUTER_FIXTURE if ids is None else ids
        self.calls = 0

    async def fetch_popularity_ranks(self):
        self.calls += 1
        return {mid: i + 1 for i, mid in enumerate(self.ids)}


@pytest.fixture
async def rank_db(monkeypatch, tmp_path: Path):
    """Banco temporário exclusivo com catálogo, provedores e chave pessoal do usuário."""
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "rankings.db", raising=True)
    await dbmod.init_db()
    db = await aiosqlite.connect(dbmod.DB_PATH)
    try:
        await db.execute("DELETE FROM model_rankings")
        await db.execute("DELETE FROM model_quota_status")
        await db.execute("DELETE FROM model_usage_log")
        await db.execute("DELETE FROM models")
        await db.execute("UPDATE providers SET enabled = 0")
        for pid, (pname, enabled, is_free, is_local, key) in PROVIDERS.items():
            await db.execute(
                "INSERT INTO providers (id, name, base_url, api_key, enabled, is_free, is_local) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, api_key = excluded.api_key, enabled = excluded.enabled, "
                "is_free = excluded.is_free, is_local = excluded.is_local",
                (pid, pname, f"https://{pid}.example/v1", key, enabled, is_free, is_local),
            )
        for pid, name, enabled, rc, vis in CATALOG:
            await db.execute(
                "INSERT INTO models (id, provider_id, name, display_name, context_length, confirmed_free, enabled, "
                "supports_vision, reasoning_control) VALUES (?, ?, ?, ?, 32768, 1, ?, ?, ?)",
                (_mid(pid, name), pid, name, name, enabled, vis, rc),
            )
        await db.execute(
            "INSERT OR IGNORE INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
            (USER_ID, "rank-user"),
        )
        # Chave pessoal só para o OpenRouter (os demais free usam a chave global).
        await db.execute(
            "INSERT OR REPLACE INTO user_api_keys (user_id, provider_id, api_key) VALUES (?, 'openrouter', 'sk-or-user')",
            (USER_ID,),
        )
        await db.execute(
            "INSERT INTO meta (key, value) VALUES ('free_registry_hide_unconfirmed', 'true') "
            "ON CONFLICT(key) DO UPDATE SET value = 'true'"
        )
        await db.commit()
        yield db
    finally:
        await db.close()


# ── Normalização e casamento de nomes ────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("@cf/meta/llama-3.1-8b-instruct-fp8", "llama-3.1-8b"),
        ("llama3.1:8b", "llama-3.1-8b"),
        ("meta-llama/llama-3.1-8b-instruct", "llama-3.1-8b"),
        ("llama-3.1-8b-instant", "llama-3.1-8b"),
        ("Meta-Llama-3.3-70B-Instruct", "llama-3.3-70b"),
        ("llama-3.3-70b-versatile", "llama-3.3-70b"),
        ("moonshotai/kimi-k2-instruct-0905", "kimi-k-2"),
        ("moonshotai/kimi-k2:free", "kimi-k-2"),
        ("gemini-2.5-flash-lite-preview-06-17", "gemini-2.5-flash-lite"),
        ("openai/gpt-oss-120b:free", "gpt-oss-120b"),
        ("gpt-4o-2024-11-20", "gpt-4o"),
        ("mistral-large-2512", "mistral-large"),
        ("gemma3:27b", "gemma-3-27b"),
        ("google/gemma-3-27b-it", "gemma-3-27b"),
        ("@cf/qwen/qwen2.5-coder-32b-instruct", "qwen-2.5-coder-32b"),
        ("", ""),
        (None, ""),
    ],
)
def test_normalize_model_key_converges_across_providers(raw, expected):
    assert normalize_model_key(raw) == expected


def test_popularity_index_and_fuzzy_match():
    ranks = {mid: i + 1 for i, mid in enumerate(OPENROUTER_FIXTURE)}
    index = build_popularity_index(ranks)

    # Variantes (:free) colapsam na melhor posição
    assert index["deepseek-r-1"] == 6
    assert index["kimi-k-2"] == 8
    # Casamento exato entre provedores diferentes
    assert match_popularity(normalize_model_key("llama-3.3-70b-versatile"), index) == 9
    assert match_popularity(normalize_model_key("Meta-Llama-3.3-70B-Instruct"), index) == 9
    assert match_popularity(normalize_model_key("gpt-oss-120b"), index) == 10
    assert match_popularity(normalize_model_key("@cf/meta/llama-3.1-8b-instruct-fp8"), index) == 12
    # Encurtamento progressivo do nome (sufixos de build)
    assert match_popularity(normalize_model_key("gemini-2.5-flash-lite-preview-06-17"), index) == 14
    # Nunca casa família inteira sem versão
    assert match_popularity(normalize_model_key("llama"), index) is None
    assert match_popularity(normalize_model_key("agnes/agnes-image-2.1-flash"), index) is None
    assert match_popularity("", index) is None


def test_normalize_popularity_is_monotonic_and_bounded():
    values = [normalize_popularity(r) for r in (1, 2, 5, 10, 50, 100, 299, 300, 1000)]
    assert values[0] == 100.0
    assert all(a >= b for a, b in zip(values, values[1:]))
    assert values[-1] == 0.0 and values[-2] == 0.0
    assert normalize_popularity(None) == POPULARITY_NEUTRAL
    # Um modelo listado numa posição intermediária fica perto do neutro — nem premiado, nem punido
    assert 20 < normalize_popularity(60) < POPULARITY_NEUTRAL + 10
    # Fórmula completa continua usando a normalização
    bd = calculate_nexuslocal_score(80.0, None, 0)
    assert bd["popularity_normalized"] == POPULARITY_NEUTRAL
    assert bd["nexuslocal_score"] == pytest.approx(80 * 0.5 + POPULARITY_NEUTRAL * 0.3, abs=1e-6)


# ── Qualidade determinística ─────────────────────────────────────────────────

def test_resolve_quality_prefers_curated_exact_match_then_heuristic():
    curated = StaticRegistrySource().load_index()
    assert curated, "curadoria local deve existir"
    q, src = resolve_quality("openrouter/deepseek/deepseek-r1:free", "deepseek/deepseek-r1:free", "openrouter", "always_on", 0, curated)
    assert src == SOURCE_CURATED and q == curated["deepseek-r-1"]["quality_score"]
    # Distill NÃO herda a curadoria do R1 (correspondência exata)
    q2, src2 = resolve_quality("groq/deepseek-r1-distill-llama-70b", "deepseek-r1-distill-llama-70b", "groq", None, 0, curated)
    assert src2 == SOURCE_HEURISTIC
    assert q2 == profile_model("groq/deepseek-r1-distill-llama-70b", "deepseek-r1-distill-llama-70b", "groq", None, 0).baseline_quality
    assert q2 < q
    # Sem curadoria → heurística do perfil (mesma base do roteador)
    q3, src3 = resolve_quality("gemini/gemini-2.5-pro", "gemini-2.5-pro", "gemini", "gemini_thinking", 1, {})
    assert src3 == SOURCE_HEURISTIC and q3 == profile_model("gemini/gemini-2.5-pro", "gemini-2.5-pro", "gemini", "gemini_thinking", 1).baseline_quality


def test_curated_json_is_on_the_same_scale_as_the_router_heuristic():
    """A curadoria local não pode voltar a inflar famílias antigas (ex.: R1 = 98 > Kimi K2.7 = 92)."""
    curated = StaticRegistrySource().load_index()
    for key, val in curated.items():
        q = float(val["quality_score"])
        assert 40 <= q <= 95, key
    assert float(curated["deepseek-r-1"]["quality_score"]) <= 92
    assert float(curated["llama-3.1-8b"]["quality_score"]) < float(curated["llama-3.3-70b"]["quality_score"])


# ── Semeadura e migração ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_missing_rankings_is_deterministic_and_never_random(rank_db):
    db = rank_db
    n1 = await seed_missing_rankings(db)
    await db.commit()
    assert n1 == len(CATALOG)
    async with db.execute("SELECT model_id, quality_score, popularity_rank, source FROM model_rankings ORDER BY model_id") as cur:
        first = await cur.fetchall()
    assert all(r[2] is None for r in first), "semeadura não inventa popularidade"
    assert set(r[3] for r in first) <= {SOURCE_CURATED, SOURCE_HEURISTIC}
    # Segunda chamada: nada a fazer e valores idênticos (determinismo)
    assert await seed_missing_rankings(db) == 0
    await db.execute("DELETE FROM model_rankings")
    await seed_missing_rankings(db)
    await db.commit()
    async with db.execute("SELECT model_id, quality_score, popularity_rank, source FROM model_rankings ORDER BY model_id") as cur:
        second = await cur.fetchall()
    assert first == second
    by_id = {r[0]: r[1] for r in first}
    assert by_id[_mid("gemini", "gemini-2.5-pro")] > by_id[_mid("groq", "llama-3.3-70b-versatile")] > by_id[_mid("groq", "llama-3.1-8b-instant")]
    # Não-chat (imagem/embedding) nunca lidera o seletor nem o failover
    assert by_id[_mid("openrouter", "agnes/agnes-image-2.1-flash")] <= 25
    assert by_id[_mid("openrouter", "openai/text-embedding-3-small")] <= 25
    assert by_id[_mid("openrouter", "openai/gpt-5.2")] >= 90
    assert by_id[_mid("openrouter", "meta-llama/llama-3.2-3b-instruct:free")] <= 60


@pytest.mark.asyncio
async def test_migrate_legacy_random_rows(rank_db):
    db = rank_db
    # Simula o legado: linhas 'auto-seed' aleatórias + uma 'hybrid' da curadoria 2024-25 (R1 = 98)
    legacy = [
        (_mid("groq", "llama-3.1-8b-instant"), 98.7, 2, SOURCE_LEGACY_RANDOM),
        (_mid("openrouter", "agnes/agnes-image-2.1-flash"), 97.9, 3, SOURCE_LEGACY_RANDOM),
        (_mid("openrouter", "deepseek/deepseek-r1:free"), 98.0, 1, "hybrid"),
    ]
    for mid, q, p, src in legacy:
        await db.execute(
            "INSERT INTO model_rankings (model_id, quality_score, popularity_rank, nexuslocal_score, source) VALUES (?, ?, ?, 77.0, ?)",
            (mid, q, p, src),
        )
    await db.commit()

    changed = await migrate_legacy_rankings(db)
    assert changed == len(CATALOG)  # 3 migrados + os demais semeados

    async with db.execute("SELECT COUNT(*) FROM model_rankings WHERE source IN ('auto-seed', 'hybrid', 'manual')") as cur:
        assert (await cur.fetchone())[0] == 0
    async with db.execute("SELECT quality_score, popularity_rank, nexuslocal_score FROM model_rankings WHERE model_id = ?",
                          (_mid("groq", "llama-3.1-8b-instant"),)) as cur:
        q, p, score = await cur.fetchone()
    assert q == profile_model(_mid("groq", "llama-3.1-8b-instant"), "llama-3.1-8b-instant", "groq", "none", 0).baseline_quality
    assert p is None and score > 0
    async with db.execute("SELECT quality_score FROM model_rankings WHERE model_id = ?", (_mid("openrouter", "deepseek/deepseek-r1:free"),)) as cur:
        assert (await cur.fetchone())[0] <= 92  # rebaseado para a escala atual
    # Idempotente
    assert await migrate_legacy_rankings(db) == 0


@pytest.mark.asyncio
async def test_init_db_migrates_legacy_rows(monkeypatch, tmp_path: Path):
    """A migração roda dentro de init_db() (bloco incremental) e não quebra o boot."""
    monkeypatch.setattr(dbmod, "DB_PATH", tmp_path / "boot.db", raising=True)
    await dbmod.init_db()
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO providers (id, name, base_url, api_key, enabled, is_free) VALUES ('groq', 'Groq', 'https://g/v1', 'k', 1, 1)"
        )
        await db.execute(
            "INSERT INTO models (id, provider_id, name, display_name, enabled) VALUES ('groq/llama-3.3-70b-versatile', 'groq', 'llama-3.3-70b-versatile', 'Llama 3.3 70B', 1)"
        )
        await db.execute(
            "INSERT INTO model_rankings (model_id, quality_score, popularity_rank, source) VALUES ('groq/llama-3.3-70b-versatile', 61.2, 77, 'auto-seed')"
        )
        await db.commit()
    await dbmod.init_db()  # segundo boot = upgrade
    async with aiosqlite.connect(dbmod.DB_PATH) as db:
        async with db.execute("SELECT quality_score, popularity_rank, source FROM model_rankings WHERE model_id = 'groq/llama-3.3-70b-versatile'") as cur:
            q, p, src = await cur.fetchone()
    assert src in (SOURCE_CURATED, SOURCE_HEURISTIC) and p is None and q == 80.0


# ── Sync completo (OpenRouter simulado) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_rankings_spreads_scores_and_matches_popularity(rank_db):
    db = rank_db
    fake = _FakeOpenRouter()
    res = await sync_rankings(db=db, fetch_popularity=True, openrouter_source=fake)
    assert res["status"] == "success", res
    assert fake.calls == 1
    assert res["models"] == len(CATALOG)
    assert res["popularity_refreshed"] is True
    assert res["matched_popularity"] >= 10

    async with db.execute("SELECT model_id, quality_score, popularity_rank, nexuslocal_score, source FROM model_rankings") as cur:
        rows = await cur.fetchall()
    by_id = {r[0]: r for r in rows}
    # Popularidade casada entre provedores
    assert by_id[_mid("groq", "llama-3.3-70b-versatile")][2] == 9
    assert by_id[_mid("cerebras", "gpt-oss-120b")][2] == 10
    assert by_id[_mid("cloudflare", "@cf/meta/llama-3.1-8b-instruct-fp8")][2] == 12
    assert by_id[_mid("openrouter", "deepseek/deepseek-r1:free")][2] == 6
    assert by_id[_mid("zenmux", "nex-agi/nex-n2-pro")][2] is None
    # Scores com dispersão real (antes: todos ~77-78)
    chat_scores = [
        r[3] for r in rows
        if profile_model(r[0], r[0].split("/", 1)[1], r[0].split("/", 1)[0]).is_chat_capable
    ]
    assert max(chat_scores) - min(chat_scores) >= 20
    assert statistics.pstdev(chat_scores) >= 5
    # Forte > fraco
    assert by_id[_mid("openrouter", "openai/gpt-5.2")][3] > by_id[_mid("groq", "llama-3.1-8b-instant")][3]
    assert by_id[_mid("gemini", "gemini-2.5-pro")][3] > by_id[_mid("openrouter", "meta-llama/llama-3.2-3b-instruct:free")][3]

    # Segunda execução sem rede preserva a popularidade conhecida
    res2 = await sync_rankings(db=db, fetch_popularity=True, openrouter_source=_FakeOpenRouter(ids=[]))
    assert res2["status"] == "success" and res2["popularity_refreshed"] is False
    async with db.execute("SELECT popularity_rank FROM model_rankings WHERE model_id = ?", (_mid("groq", "llama-3.3-70b-versatile"),)) as cur:
        assert (await cur.fetchone())[0] == 9


# ── Visão do endpoint ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ranking_overview_hides_unusable_and_non_chat_models(rank_db):
    db = rank_db
    await sync_rankings(db=db, fetch_popularity=True, openrouter_source=_FakeOpenRouter())

    available = await build_ranking_overview(db, USER_ID, "available")
    ids = [m.model_id for m in available]
    # Não-chat nunca aparece
    assert _mid("openrouter", "agnes/agnes-image-2.1-flash") not in ids
    assert _mid("openrouter", "openai/text-embedding-3-small") not in ids
    # Provedor desabilitado (assinatura expirada), sem chave e modelo desabilitado ficam fora
    assert not any(i.startswith("zenmux/") for i in ids)
    assert not any(i.startswith("qwen/") for i in ids)
    assert _mid("ollama", "llama3.2:1b") not in ids
    # Utilizáveis: free com chave global, chave pessoal (openrouter) e ollama local
    assert _mid("groq", "llama-3.3-70b-versatile") in ids
    assert _mid("openrouter", "openai/gpt-5.2") in ids
    assert _mid("ollama", "gemma3:4b") in ids
    assert all(m.available for m in available)
    # Provedor real (nunca 'Local / Outro') e tags do perfil
    top = available[0]
    assert top.provider_name and top.provider_name != "Local / Outro"
    assert top.display_name and top.size_label and top.tags
    by_id = {m.model_id: m for m in available}
    assert by_id[_mid("ollama", "gemma3:4b")].provider_name == "Ollama" and by_id[_mid("ollama", "gemma3:4b")].is_local
    assert "reasoning:dial" in by_id[_mid("gemini", "gemini-2.5-pro")].tags
    assert "coder" in by_id[_mid("cloudflare", "@cf/qwen/qwen2.5-coder-32b-instruct")].tags
    # Ordenado por score decrescente
    scores = [m.nexuslocal_score for m in available]
    assert scores == sorted(scores, reverse=True)

    everything = await build_ranking_overview(db, USER_ID, "all")
    all_ids = {m.model_id: m for m in everything}
    assert len(everything) > len(available)
    assert all_ids[_mid("zenmux", "nex-agi/nex-n2-pro")].unavailable_reason == "provider_disabled"
    assert all_ids[_mid("qwen", "qwen3.5-plus")].unavailable_reason == "missing_key"
    assert all_ids[_mid("ollama", "llama3.2:1b")].unavailable_reason == "model_disabled"
    assert _mid("openrouter", "agnes/agnes-image-2.1-flash") not in all_ids


@pytest.mark.asyncio
async def test_ranking_overview_ignores_legacy_random_rows_without_migration(rank_db):
    """Mesmo antes da migração, a visão nunca usa a qualidade aleatória legada."""
    db = rank_db
    mid = _mid("groq", "llama-3.1-8b-instant")
    await db.execute(
        "INSERT INTO model_rankings (model_id, quality_score, popularity_rank, source) VALUES (?, 98.9, 2, 'auto-seed')", (mid,)
    )
    await db.commit()
    rows = {m.model_id: m for m in await build_ranking_overview(db, USER_ID, "all")}
    assert rows[mid].quality_score == profile_model(mid, "llama-3.1-8b-instant", "groq", "none", 0).baseline_quality
    assert rows[mid].popularity_rank is None and rows[mid].source == SOURCE_HEURISTIC


@pytest.mark.asyncio
async def test_ranking_endpoint_scope_and_admin_sync(rank_db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.auth import get_current_user, require_admin
    from backend.routers.ranking import router as ranking_router
    import backend.ranking.sync as sync_mod

    await sync_rankings(db=rank_db, fetch_popularity=True, openrouter_source=_FakeOpenRouter())

    app = FastAPI()
    app.include_router(ranking_router)
    user = {"id": USER_ID, "username": "rank-user", "role": "admin"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_admin] = lambda: user
    client = TestClient(app)

    res = client.get("/api/ranking")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body and all(item["available"] for item in body)
    assert not any(item["model_id"].startswith("zenmux/") for item in body)
    assert {"display_name", "provider_name", "tags", "size_label", "source"} <= set(body[0].keys())

    res_all = client.get("/api/ranking", params={"scope": "all"})
    assert res_all.status_code == 200
    assert len(res_all.json()) > len(body)
    assert client.get("/api/ranking", params={"scope": "bogus"}).status_code == 422

    # POST /api/ranking/sync usa a fonte real por padrão → injeta a simulada
    monkeypatch.setattr(sync_mod, "OpenRouterRankingSource", lambda *a, **k: _FakeOpenRouter())
    res_sync = client.post("/api/ranking/sync")
    assert res_sync.status_code == 200, res_sync.text
    assert res_sync.json()["status"] == "success"
