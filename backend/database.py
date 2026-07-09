import aiosqlite
import json
from pathlib import Path

DB_PATH = Path(__file__).parent / "nexuslocal.db"

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS providers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    api_key     TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    is_free     INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS models (
    id             TEXT PRIMARY KEY,
    provider_id    TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    context_length INTEGER DEFAULT 8192,
    context_source TEXT DEFAULT 'default',
    enabled        INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         TEXT UNIQUE,
    phone         TEXT,
    role          TEXT DEFAULT 'user',
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_api_keys (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    api_key     TEXT NOT NULL,
    PRIMARY KEY (user_id, provider_id)
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT DEFAULT 'Nova conversa',
    model_id    TEXT,
    provider_id TEXT,
    is_favorite INTEGER DEFAULT 0,
    favorited_at TEXT DEFAULT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    model_id        TEXT,
    provider        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS cache_exact (
    id          TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    response    TEXT NOT NULL,
    token_est   INTEGER DEFAULT 0,
    hits        INTEGER DEFAULT 0,
    last_hit    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cache_exact_hash ON cache_exact(hash, model_id);

CREATE TABLE IF NOT EXISTS cache_semantic (
    id          TEXT PRIMARY KEY,
    prompt_text TEXT NOT NULL,
    embedding   BLOB NOT NULL,
    response    TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    token_est   INTEGER DEFAULT 0,
    hits        INTEGER DEFAULT 0,
    similarity  REAL DEFAULT 0.0,
    last_hit    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_cache_semantic_model ON cache_semantic(model_id);

CREATE TABLE IF NOT EXISTS cache_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_log (
    id              TEXT PRIMARY KEY,
    provider_id     TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    synced_at       TEXT DEFAULT (datetime('now')),
    models_updated  INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'ok',
    error_msg       TEXT
);

CREATE TABLE IF NOT EXISTS model_overrides (
    model_id        TEXT PRIMARY KEY,
    context_length  INTEGER NOT NULL,
    set_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS enhancer_config (
    id                      INTEGER PRIMARY KEY DEFAULT 1,
    enhancer_provider_id    TEXT,
    enhancer_model_id       TEXT,
    enhancer_enabled        INTEGER DEFAULT 1,
    enhancer_system_prompt  TEXT
);

CREATE TABLE IF NOT EXISTS fusion_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    judge_provider_id   TEXT NOT NULL,
    judge_model_id      TEXT NOT NULL,
    judge_system_prompt TEXT,
    enabled             INTEGER DEFAULT 1,
    grounding_enabled   INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS fusion_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    position    INTEGER DEFAULT 0,
    UNIQUE(provider_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id                TEXT PRIMARY KEY,
    conv_id           TEXT NOT NULL,
    msg_id            TEXT,
    type              TEXT NOT NULL,
    title             TEXT NOT NULL DEFAULT 'Artifact',
    content           TEXT NOT NULL,
    version           INTEGER DEFAULT 1,
    artifact_group_id TEXT,           -- agrupa todas as versões do mesmo artifact lógico
    visibility        TEXT DEFAULT 'Privado',
    view_count        INTEGER DEFAULT 0,
    thumbnail         TEXT DEFAULT NULL,
    created_at        TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (conv_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (msg_id) REFERENCES messages(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS attachments (
    id              TEXT PRIMARY KEY,
    message_id      TEXT REFERENCES messages(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT NOT NULL,
    file_type       TEXT NOT NULL,        -- 'document' | 'image'
    size_bytes      INTEGER NOT NULL,
    file_hash       TEXT NOT NULL,
    extracted_text  TEXT,                 -- NULL for images
    storage_path    TEXT NOT NULL,        -- relative to storage/attachments
    thumbnail_path  TEXT,                 -- only for images
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_attachments_message ON attachments(message_id);

CREATE TABLE IF NOT EXISTS vision_relay_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    relay_provider_id   TEXT,
    relay_model_id      TEXT,
    relay_system_prompt TEXT DEFAULT 'Você é um sistema de descrição de imagens. Descreva a imagem em detalhes objetivos e completos: objetos, pessoas, texto visível (transcreva literalmente), cores, contexto da cena, e qualquer informação relevante. Seja exaustivo mas direto. Não faça julgamentos de valor. Não adicione introduções como "esta imagem mostra". Vá direto à descrição.',
    enabled             INTEGER DEFAULT 1,
    cache_descriptions  INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS vision_descriptions_cache (
    file_hash    TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    relay_model  TEXT NOT NULL,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS web_search_config (
    id                    INTEGER PRIMARY KEY DEFAULT 1,
    enabled               INTEGER DEFAULT 1,
    search_provider       TEXT DEFAULT 'duckduckgo',
    api_key               TEXT DEFAULT '',
    max_results           INTEGER DEFAULT 5,
    heuristic_enabled     INTEGER DEFAULT 0,
    heuristic_sensitivity TEXT DEFAULT 'medium',
    injection_template    TEXT DEFAULT 'Resultados de busca para "{query}":\n\n{results}\n\n--- Use essas informações para responder a pergunta do usuário.'
);

CREATE TABLE IF NOT EXISTS web_search_log (
    id             TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id     TEXT,
    query          TEXT NOT NULL,
    trigger_type   TEXT NOT NULL,
    results_count  INTEGER,
    created_at     TEXT DEFAULT (datetime('now'))
);

-- =========================================================
-- RANKING & FAILOVER TABLES (Fase 1)
-- =========================================================

CREATE TABLE IF NOT EXISTS model_families (
    id            TEXT PRIMARY KEY,       -- 'deepseek-r1', 'llama-3.3-70b'
    display_name  TEXT NOT NULL,          -- 'DeepSeek R1'
    description   TEXT
);

CREATE TABLE IF NOT EXISTS model_family_members (
    id              TEXT PRIMARY KEY,
    family_id       TEXT NOT NULL REFERENCES model_families(id) ON DELETE CASCADE,
    model_id        TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    fallback_order  INTEGER NOT NULL,     -- 1 = prioridade, 2 = primeiro fallback, etc.
    UNIQUE(family_id, model_id)
);
CREATE INDEX IF NOT EXISTS idx_family_members_family ON model_family_members(family_id, fallback_order);

CREATE TABLE IF NOT EXISTS model_rankings (
    model_id           TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    quality_score      REAL DEFAULT 0,    -- normalizado 0-100, de llm-stats / curadoria
    popularity_rank    INTEGER,           -- posição no OpenRouter Rankings (1 = mais popular)
    nexuslocal_score   REAL DEFAULT 0,    -- combinado (calculado por scorer.py)
    source             TEXT DEFAULT 'manual',  -- 'manual' | 'openrouter' | 'llm-stats' | 'hybrid'
    updated_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_quota_status (
    model_id            TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    status              TEXT DEFAULT 'available',  -- 'available' | 'degraded' | 'exhausted'
    consecutive_errors  INTEGER DEFAULT 0,
    exhausted_at        TEXT,
    estimated_reset_at  TEXT,             -- estimativa de quando volta (Retry-After ou heurística)
    last_error_message  TEXT
);

CREATE TABLE IF NOT EXISTS model_usage_log (
    id                     TEXT PRIMARY KEY,
    model_id               TEXT NOT NULL,
    provider_id            TEXT NOT NULL,
    conversation_id        TEXT,
    user_id                TEXT,          -- rastreia por usuário (JWT já implementado)
    tokens_est             INTEGER DEFAULT 0,
    was_fallback           INTEGER DEFAULT 0,  -- 1 se foi failover automático
    fallback_from_model_id TEXT,
    fallback_reason        TEXT,          -- 'rate_limit' | 'error' | 'manual'
    created_at             TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_usage_model ON model_usage_log(model_id, created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user  ON model_usage_log(user_id, created_at);

CREATE TABLE IF NOT EXISTS free_model_registry (
    id              TEXT PRIMARY KEY,
    source          TEXT NOT NULL,            -- 'mnfst' | 'cheahjs' | 'manual'
    provider_name   TEXT NOT NULL,             -- nome como aparece na fonte (ex: "Groq")
    model_id_raw    TEXT NOT NULL,             -- id como aparece na fonte (ex: "llama-3.3-70b-versatile")
    context_raw     TEXT,                      -- string bruta, ex: "131K"
    max_output_raw  TEXT,
    modality        TEXT,
    rate_limit_raw  TEXT,                      -- string bruta, ex: "30 RPM, 14,400 RPD"
    rpm             INTEGER,                   -- parseado
    rpd             INTEGER,                   -- parseado
    tpm             INTEGER,
    tpd             INTEGER,
    rps             INTEGER,
    parse_confidence TEXT DEFAULT 'high',       -- 'high' | 'low' | 'unparseable'
    base_url        TEXT,
    last_synced_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_registry_provider ON free_model_registry(provider_name, model_id_raw);
"""

DEFAULT_PROVIDERS = [
    {
        "id": "groq",
        "name": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "is_free": 1,
        "models": [
            ("groq/llama-3.3-70b", "llama-3.3-70b-versatile", "Llama 3.3 70B", 128000),
            ("groq/llama-3.1-8b", "llama-3.1-8b-instant", "Llama 3.1 8B (Fast)", 128000),
            ("groq/gemma2-9b", "gemma2-9b-it", "Gemma 2 9B", 8192),
            ("groq/mixtral-8x7b", "mixtral-8x7b-32768", "Mixtral 8x7B", 32768),
        ],
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "is_free": 1,
        "models": [
            ("openrouter/llama-3.3-70b", "meta-llama/llama-3.3-70b-instruct:free", "Llama 3.3 70B", 131072),
            ("openrouter/qwen2.5-72b", "qwen/qwen-2.5-72b-instruct:free", "Qwen 2.5 72B", 32768),
            ("openrouter/deepseek-r1", "deepseek/deepseek-r1:free", "DeepSeek R1", 65536),
            ("openrouter/gemma3-27b", "google/gemma-3-27b-it:free", "Gemma 3 27B", 131072),
            ("openrouter/mistral-7b", "mistralai/mistral-7b-instruct:free", "Mistral 7B", 32768),
        ],
    },
    {
        "id": "gemini",
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "is_free": 1,
        "models": [
            ("gemini/flash-2.0", "gemini-2.0-flash", "Gemini 2.0 Flash", 1048576),
            ("gemini/flash-1.5", "gemini-1.5-flash", "Gemini 1.5 Flash", 1048576),
            ("gemini/flash-2.0-lite", "gemini-2.0-flash-lite", "Gemini 2.0 Flash Lite", 1048576),
        ],
    },
    {
        "id": "cerebras",
        "name": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "is_free": 1,
        "models": [
            ("cerebras/llama-3.3-70b", "llama-3.3-70b", "Llama 3.3 70B (Ultra Fast)", 131072),
            ("cerebras/llama-3.1-8b", "llama3.1-8b", "Llama 3.1 8B (Ultra Fast)", 131072),
        ],
    },
    {
        "id": "zai",
        "name": "z.ai",
        "base_url": "https://api.z.ai/v1",
        "is_free": 1,
        "models": [
            ("zai/z-coder", "z-coder", "z-coder", 128000),
            ("zai/z-chat", "z-chat", "z-chat", 128000),
        ],
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "base_url": "https://ollama.com/v1",
        "is_free": 1,
        "models": [
            ("ollama/llama3", "llama3", "Llama 3 (Ollama)", 8192),
            ("ollama/mistral", "mistral", "Mistral (Ollama)", 32768),
            ("ollama/qwen2.5", "qwen2.5", "Qwen 2.5 (Ollama)", 32768),
        ],
    },
    {
        "id": "huggingface",
        "name": "Hugging Face",
        "base_url": "https://router.huggingface.co/v1",
        "is_free": 1,
        "models": [
            ("huggingface/llama-3.3-70b", "meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B (HuggingFace)", 128000),
            ("huggingface/qwen-2.5-coder", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B (HuggingFace)", 131072),
        ],
    },
    {
        "id": "cloudflare",
        "name": "Cloudflare",
        "base_url": "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1",
        "is_free": 1,
        "models": [
            ("cloudflare/llama-3.3-70b-fast", "@cf/meta/llama-3.3-70b-instruct-fp8-fast", "Llama 3.3 70B FP8 (Fast)", 131072),
            ("cloudflare/llama-3.1-8b-fast", "@cf/meta/llama-3.1-8b-instruct-fast", "Llama 3.1 8B (Fast)", 128000),
            ("cloudflare/llama-3.1-8b-awq", "@cf/meta/llama-3.1-8b-instruct-awq", "Llama 3.1 8B AWQ", 128000),
            ("cloudflare/llama-3.1-8b-fp8", "@cf/meta/llama-3.1-8b-instruct-fp8", "Llama 3.1 8B FP8", 128000),
            ("cloudflare/llama-3.1-70b", "@cf/meta/llama-3.1-70b-instruct", "Llama 3.1 70B", 131072),
            ("cloudflare/qwen-2.5-coder-32b", "@cf/qwen/qwen2.5-coder-32b-instruct", "Qwen 2.5 Coder 32B (Cloudflare)", 32768),
            ("cloudflare/deepseek-r1-distill-qwen-32b", "@cf/deepseek-ai/deepseek-r1-distill-qwen-32b", "DeepSeek R1 Distill Qwen 32B", 131072),
            ("cloudflare/qwq-32b", "@cf/qwen/qwq-32b", "QwQ 32B (Reasoning)", 32768),
            ("cloudflare/qwen3-30b-a3b-fp8", "@cf/qwen/qwen3-30b-a3b-fp8", "Qwen3 30B FP8", 32768),
            ("cloudflare/llama-3.2-1b", "@cf/meta/llama-3.2-1b-instruct", "Llama 3.2 1B", 131072),
            ("cloudflare/llama-3.2-3b", "@cf/meta/llama-3.2-3b-instruct", "Llama 3.2 3B", 131072),
            ("cloudflare/llama-3.2-11b-vision", "@cf/meta/llama-3.2-11b-vision-instruct", "Llama 3.2 11B Vision", 131072),
            ("cloudflare/llama-4-scout-17b-16e", "@cf/meta/llama-4-scout-17b-16e-instruct", "Llama 4 Scout 17B", 131072),
            ("cloudflare/gemma-3-12b", "@cf/google/gemma-3-12b-it", "Gemma 3 12B", 131072),
            ("cloudflare/gemma-4-26b-a4b", "@cf/google/gemma-4-26b-a4b-it", "Gemma 4 26B", 256000),
            ("cloudflare/kimi-k2.7-code", "@cf/moonshotai/kimi-k2.7-code", "Kimi K2.7 Code", 262144),
            ("cloudflare/kimi-k2.6", "@cf/moonshotai/kimi-k2.6", "Kimi K2.6", 262144),
            ("cloudflare/kimi-k2.5", "@cf/moonshotai/kimi-k2.5", "Kimi K2.5", 256000),
            ("cloudflare/glm-4.7-flash", "@cf/zai-org/glm-4.7-flash", "GLM 4.7 Flash", 131072),
            ("cloudflare/glm-5.2", "@cf/zai-org/glm-5.2", "GLM 5.2", 262144),
            ("cloudflare/gpt-oss-120b", "@cf/openai/gpt-oss-120b", "GPT OSS 120B", 131072),
            ("cloudflare/gpt-oss-20b", "@cf/openai/gpt-oss-20b", "GPT OSS 20B", 128000),
            ("cloudflare/nemotron-3-120b-a12b", "@cf/nvidia/nemotron-3-120b-a12b", "Nemotron 3 120B", 256000),
            ("cloudflare/mistral-small-3.1-24b", "@cf/mistralai/mistral-small-3.1-24b-instruct", "Mistral Small 3.1 24B", 131072),
            ("cloudflare/granite-4.0-h-micro", "@cf/ibm-granite/granite-4.0-h-micro", "Granite 4.0 H-Micro", 131072),
            ("cloudflare/gemma-sea-lion-v4-27b", "@cf/aisingapore/gemma-sea-lion-v4-27b-it", "Gemma Sea Lion v4 27B", 128000),
            ("cloudflare/meta-llama-3-8b-hf", "@hf/meta-llama/meta-llama-3-8b-instruct", "Llama 3 8B (HF)", 8192),
            ("cloudflare/mistral-7b-v0.2-hf", "@hf/mistral/mistral-7b-instruct-v0.2", "Mistral 7B v0.2 (HF)", 32768),
            ("cloudflare/gemma-7b-hf", "@hf/google/gemma-7b-it", "Gemma 7B (HF)", 8192),
            ("cloudflare/hermes-2-pro-mistral-7b-hf", "@hf/nousresearch/hermes-2-pro-mistral-7b", "Hermes 2 Pro Mistral 7B (HF)", 32768),
            ("cloudflare/phi-2", "@cf/microsoft/phi-2", "Phi-2 (Cloudflare)", 2048),
            ("cloudflare/sqlcoder-7b-2", "@cf/defog/sqlcoder-7b-2", "SQLCoder 7B", 10000),
            ("cloudflare/llama-2-7b-chat-fp16", "@cf/meta/llama-2-7b-chat-fp16", "Llama 2 7B Chat (FP16)", 4096),
            ("cloudflare/llama-2-7b-chat-int8", "@cf/meta/llama-2-7b-chat-int8", "Llama 2 7B Chat (INT8)", 4096),
            ("cloudflare/mistral-7b-instruct-v0.1", "@cf/mistral/mistral-7b-instruct-v0.1", "Mistral 7B v0.1", 8192),
            ("cloudflare/llama-3-8b", "@cf/meta/llama-3-8b-instruct", "Llama 3 8B (Cloudflare)", 8192),
            ("cloudflare/llama-3-8b-awq", "@cf/meta/llama-3-8b-instruct-awq", "Llama 3 8B AWQ (Cloudflare)", 8192),
            ("cloudflare/llama-3.1-8b", "@cf/meta/llama-3.1-8b-instruct", "Llama 3.1 8B (Cloudflare)", 128000),
        ],
    },
    {
        "id": "nvidia",
        "name": "NVIDIA NIM",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "is_free": 1,
        "models": [
            ("nvidia/llama-3.1-405b", "meta/llama-3.1-405b-instruct", "Llama 3.1 405B", 131072),
            ("nvidia/mistral-nemo", "nv-mistralai/mistral-nemo-12b-instruct", "Mistral Nemo 12B", 128000),
            ("nvidia/nemotron-70b", "nvidia/llama-3.1-nemotron-70b-instruct", "Nemotron 70B", 131072),
        ],
    },
    {
        "id": "sambanova",
        "name": "SambaNova",
        "base_url": "https://api.sambanova.ai/v1",
        "is_free": 1,
        "models": [
            ("sambanova/llama-3.3-70b", "Meta-Llama-3.3-70B-Instruct", "Llama 3.3 70B", 131072),
            ("sambanova/llama-3.2-1b", "Meta-Llama-3.2-1B-Instruct", "Llama 3.2 1B (Fast)", 16384),
        ],
    },
    {
        "id": "siliconflow",
        "name": "SiliconFlow",
        "base_url": "https://api.siliconflow.com/v1",
        "api_key": "sk-zixgmlzccyngmdjigkioevizaftoxwlobcwgthcuoidryjvi",
        "is_free": 1,
        "models": [
            ("siliconflow/deepseek-r1", "deepseek-ai/DeepSeek-R1", "DeepSeek R1", 131072),
            ("siliconflow/deepseek-v3", "deepseek-ai/DeepSeek-V3", "DeepSeek V3", 131072),
            ("siliconflow/qwen-2.5-72b", "Qwen/Qwen2.5-72B-Instruct", "Qwen 2.5 72B", 131072),
            ("siliconflow/qwen-2.5-coder-32b", "Qwen/Qwen2.5-Coder-32B-Instruct", "Qwen 2.5 Coder 32B", 131072),
            ("siliconflow/llama-3.3-70b", "meta-llama/Llama-3.3-70B-Instruct", "Llama 3.3 70B", 131072),
        ],
    },
    {
        "id": "longcat",
        "name": "LongCat",
        "base_url": "https://api.longcat.chat/openai/v1",
        "api_key": "ak_2QQ4X24FL3Dg1mO3VR0Qu8ic0jt51",
        "is_free": 1,
        "models": [
            ("longcat/longcat-2.0", "LongCat-2.0", "LongCat 2.0", 1000000),
        ],
    },
    {
        "id": "freetheai",
        "name": "FreeTheAI",
        "base_url": "https://api.freetheai.xyz/v1",
        "api_key": "sta_528389e5fbf49959aa7c4dfdd932088fdc93ea0df2ef70e8",
        "is_free": 1,
        "models": [
            ("freetheai/gpt-4o-mini", "gpt-4o-mini", "GPT-4o Mini", 128000),
            ("freetheai/claude-3-5-sonnet", "claude-3-5-sonnet", "Claude 3.5 Sonnet", 200000),
            ("freetheai/deepseek-r1", "deepseek-r1", "DeepSeek R1", 131072),
        ],
    },
    {
        "id": "llm7",
        "name": "LLM7.io",
        "base_url": "https://api.llm7.io/v1",
        "api_key": "LqQQJpUz2WzOs1CTwulyBruKUhyolo4qhWYovhgyhDORjC76aYLFiw77wBfDHtme/QmI/z34+la0pb9hmc+K3210cCXPB6Al8n4nKRRIBakEnELjdSrUaF7526wWS+ii1tl6TQAndak9Y1Y=",
        "is_free": 1,
        "models": [
            ("llm7/gpt-5.5", "gpt-5.5", "GPT-5.5", 1050000),
            ("llm7/gpt-5.4-mini", "gpt-5.4-mini", "GPT-5.4 Mini", 400000),
            ("llm7/deepseek-v4-flash", "deepseek-v4-flash", "DeepSeek V4 Flash", 1000000),
            ("llm7/claude-sonnet-5", "claude-sonnet-5", "Claude Sonnet 5", 1000000),
            ("llm7/codestral-latest", "codestral-latest", "Codestral Latest", 32000),
        ],
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "is_free": 0,
        "models": [
            ("deepseek/deepseek-chat", "deepseek-chat", "DeepSeek V3", 64000),
            ("deepseek/deepseek-reasoner", "deepseek-reasoner", "DeepSeek R1", 64000),
        ],
    },
    {
        "id": "qwen",
        "name": "Qwen",
        "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "is_free": 0,
        "models": [
            ("qwen/qwen-plus", "qwen-plus", "Qwen Plus", 131072),
            ("qwen/qwen-turbo", "qwen-turbo", "Qwen Turbo", 131072),
            ("qwen/qwen-max", "qwen-max", "Qwen Max", 30720),
        ],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "is_free": 0,
        "models": [
            ("openai/gpt-4o", "gpt-4o", "GPT-4o", 128000),
            ("openai/gpt-4o-mini", "gpt-4o-mini", "GPT-4o Mini", 128000),
        ],
    },
    {
        "id": "together",
        "name": "Together AI",
        "base_url": "https://api.together.xyz/v1",
        "is_free": 0,
        "models": [
            ("together/llama-3-70b", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo", "Llama 3.1 70B (Together)", 131072),
            ("together/llama-3-8b", "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo", "Llama 3.1 8B (Together)", 131072),
        ],
    },
    {
        "id": "mistral",
        "name": "Mistral AI",
        "base_url": "https://api.mistral.ai/v1",
        "is_free": 0,
        "models": [
            ("mistral/mistral-large", "mistral-large-latest", "Mistral Large", 128000),
            ("mistral/codestral", "codestral-latest", "Codestral", 32768),
        ],
    },
    {
        "id": "cohere",
        "name": "Cohere",
        "base_url": "https://api.cohere.com/v1",
        "is_free": 0,
        "models": [
            ("cohere/command-r-plus", "command-r-plus", "Command R+", 128000),
            ("cohere/command-r", "command-r", "Command R", 128000),
        ],
    },
]


async def get_db():
    return await aiosqlite.connect(DB_PATH)


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()

        # Migrate old Ollama default base_url if it is still pointing to api.z.ai or localhost:11434
        try:
            await db.execute(
                "UPDATE providers SET base_url = 'https://ollama.com/v1' WHERE id = 'ollama' AND (base_url = 'https://api.z.ai/v1' OR base_url = 'http://localhost:11434')"
            )
            await db.commit()
        except Exception as e:
            print(f"Error migrating Ollama base_url: {e}")

        # Incremental migration check for messages.provider
        try:
            await db.execute("SELECT provider FROM messages LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE messages ADD COLUMN provider TEXT")
            await db.commit()

        # Incremental migration check for context_source
        try:
            await db.execute("SELECT context_source FROM models LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE models ADD COLUMN context_source TEXT DEFAULT 'default'")
            await db.commit()

        # Incremental migration check for conversations.user_id
        try:
            await db.execute("SELECT user_id FROM conversations LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE CASCADE")
            await db.commit()

        # Incremental migration checks for users columns (email, phone, role)
        for col, col_type in [("email", "TEXT"), ("phone", "TEXT"), ("role", "TEXT DEFAULT 'user'")]:
            try:
                await db.execute(f"SELECT {col} FROM users LIMIT 1")
            except aiosqlite.OperationalError:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                await db.commit()

        # Garante que pelo menos um admin exista se houver usuários cadastrados
        async with db.execute("SELECT COUNT(id) FROM users WHERE role = 'admin'") as cur:
            row = await cur.fetchone()
            admin_count = row[0] if row else 0

        if admin_count == 0:
            async with db.execute("SELECT id FROM users ORDER BY created_at ASC LIMIT 1") as cur:
                user_row = await cur.fetchone()
            if user_row:
                await db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_row[0],))
                await db.commit()

        # Incremental migration check for artifact_group_id
        try:
            await db.execute("SELECT artifact_group_id FROM artifacts LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE artifacts ADD COLUMN artifact_group_id TEXT")
            # Retroativamente atribui group_id único a cada artifact existente
            # (cada um vira seu próprio grupo, pois não conseguimos inferir agrupamentos passados)
            import uuid as _uuid
            async with db.execute("SELECT id FROM artifacts WHERE artifact_group_id IS NULL") as _cur:
                rows = await _cur.fetchall()
            for (aid,) in rows:
                await db.execute(
                    "UPDATE artifacts SET artifact_group_id = ? WHERE id = ?",
                    (str(_uuid.uuid4()), aid)
                )
            await db.commit()
            # Cria o índice agora que a coluna existe
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_artifacts_group ON artifacts(artifact_group_id)"
            )
            await db.commit()

        # Incremental migration checks for conversations is_favorite and favorited_at
        try:
            await db.execute("SELECT is_favorite FROM conversations LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE conversations ADD COLUMN is_favorite INTEGER DEFAULT 0")
            await db.commit()

        try:
            await db.execute("SELECT favorited_at FROM conversations LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE conversations ADD COLUMN favorited_at TEXT DEFAULT NULL")
            await db.commit()

        # Incremental migration checks for artifacts columns (visibility, view_count, thumbnail)
        for col, col_type in [("visibility", "TEXT DEFAULT 'Privado'"), ("view_count", "INTEGER DEFAULT 0"), ("thumbnail", "TEXT DEFAULT NULL")]:
            try:
                await db.execute(f"SELECT {col} FROM artifacts LIMIT 1")
            except aiosqlite.OperationalError:
                await db.execute(f"ALTER TABLE artifacts ADD COLUMN {col} {col_type}")
                await db.commit()

        # Incremental migration check for models.supports_vision
        try:
            await db.execute("SELECT supports_vision FROM models LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE models ADD COLUMN supports_vision INTEGER DEFAULT 0")
            await db.commit()

        # Incremental migration check for messages.relay_used / relay_model
        try:
            await db.execute("SELECT relay_used FROM messages LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE messages ADD COLUMN relay_used INTEGER DEFAULT 0")
            await db.execute("ALTER TABLE messages ADD COLUMN relay_model TEXT")
            await db.commit()

        # Incremental migration check for messages.web_search_used / web_search_query / web_search_sources
        try:
            await db.execute("SELECT web_search_used FROM messages LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE messages ADD COLUMN web_search_used INTEGER DEFAULT 0")
            await db.execute("ALTER TABLE messages ADD COLUMN web_search_query TEXT")
            await db.execute("ALTER TABLE messages ADD COLUMN web_search_sources TEXT")
            await db.commit()

        # Incremental migration check for fusion_config.grounding_enabled
        try:
            await db.execute("SELECT grounding_enabled FROM fusion_config LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE fusion_config ADD COLUMN grounding_enabled INTEGER DEFAULT 1")
            await db.commit()

        # Migração do prompt do juiz antigo para NULL (ativando o fallback do novo prompt completo)
        try:
            old_prompt_prefix = "Você é o Agente Juiz e Consolidador do NexusLocal.\n\nAbaixo estão as respostas de diferentes%"
            await db.execute(
                "UPDATE fusion_config SET judge_system_prompt = NULL WHERE judge_system_prompt LIKE ?",
                (old_prompt_prefix,)
            )
            await db.commit()
        except Exception as e:
            print(f"[database migration] erro ao migrar prompt do juiz: {e}")

        # Load context registry
        registry_path = Path(__file__).parent / "data" / "context_registry.json"
        registry_data = {}
        if registry_path.exists():
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry_data = json.load(f)
            except Exception as e:
                print(f"Error loading context registry: {e}")

        registry_models = registry_data.get("models", {})

        for prov in DEFAULT_PROVIDERS:
            # Avoid overwriting user's custom base_url on conflict
            await db.execute(
                """INSERT INTO providers (id, name, base_url, api_key, is_free) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, is_free=excluded.is_free""",
                (prov["id"], prov["name"], prov["base_url"], prov.get("api_key", ""), prov["is_free"]),
            )
            for model_id, model_name, display_name, ctx in prov["models"]:
                reg_info = registry_models.get(model_name)
                final_ctx = reg_info["context_length"] if reg_info else ctx
                final_source = 'registry' if reg_info else 'default'

                await db.execute(
                    """INSERT INTO models (id, provider_id, name, display_name, context_length, context_source)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET 
                           name=excluded.name, 
                           display_name=excluded.display_name,
                           context_length=CASE WHEN models.id IN (SELECT model_id FROM model_overrides) THEN models.context_length ELSE excluded.context_length END,
                           context_source=CASE WHEN models.id IN (SELECT model_id FROM model_overrides) THEN 'user' ELSE excluded.context_source END""",
                    (model_id, prov["id"], model_name, display_name, final_ctx, final_source),
                )
        await db.commit()

        # Compare and apply static registry version updates to existing models in database
        registry_version = registry_data.get("version", "unknown")
        db_version = None
        try:
            async with db.execute("SELECT value FROM meta WHERE key = 'registry_version'") as cur:
                row = await cur.fetchone()
                if row:
                    db_version = row[0]
        except Exception:
            pass

        if db_version != registry_version:
            for name, info in registry_models.items():
                await db.execute(
                    """UPDATE models 
                       SET context_length = ?, context_source = 'registry'
                       WHERE name = ? AND id NOT IN (SELECT model_id FROM model_overrides)""",
                    (info["context_length"], name)
                )
            await db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('registry_version', ?)",
                (registry_version,)
            )
            await db.commit()

        # Default cache settings
        defaults = {
            "enabled": "true",
            "exact_enabled": "true",
            "semantic_enabled": "true",
            "exact_ttl_hours": "168",
            "semantic_ttl_hours": "72",
            "similarity_threshold": "0.92",
        }
        for k, v in defaults.items():
            await db.execute(
                "INSERT OR IGNORE INTO cache_settings (key, value) VALUES (?, ?)", (k, v)
            )
        await db.commit()

        # Default vision relay configuration
        try:
            async with db.execute("SELECT COUNT(*) FROM vision_relay_config") as cur:
                row = await cur.fetchone()
                count = row[0] if row else 0
            if count == 0:
                await db.execute(
                    """INSERT INTO vision_relay_config (relay_provider_id, relay_model_id, enabled, cache_descriptions)
                       VALUES ('gemini', 'gemini/flash-2.0', 1, 1)"""
                )
                await db.commit()
        except Exception as e:
            print(f"Error initializing vision relay config: {e}")

        # Default web search configuration
        try:
            async with db.execute("SELECT COUNT(*) FROM web_search_config") as cur:
                row = await cur.fetchone()
                count = row[0] if row else 0
            if count == 0:
                await db.execute(
                    """INSERT INTO web_search_config (id, enabled, search_provider, api_key, max_results, heuristic_enabled, heuristic_sensitivity)
                       VALUES (1, 1, 'duckduckgo', '', 5, 0, 'medium')"""
                )
                await db.commit()
        except Exception as e:
            print(f"Error initializing web search config: {e}")

        # Update supports_vision for vision-capable models
        try:
            # Update known models and anything with 'vision' or 'vl' in name/id
            await db.execute(
                """UPDATE models SET supports_vision = 1 
                   WHERE id LIKE '%vision%' 
                      OR id LIKE '%vl%' 
                      OR id LIKE '%gpt-4o%' 
                      OR id LIKE '%gemini/flash%' 
                      OR name LIKE '%vision%' 
                      OR name LIKE '%vl%' 
                      OR name LIKE '%gpt-4o%' 
                      OR name LIKE '%gemini%'"""
            )
            await db.commit()
        except Exception as e:
            print(f"Error updating vision models: {e}")

        # ── Migração incremental: tabelas de ranking & failover ──────────────
        # model_families — garante coluna 'description' (tabela pode já existir sem ela)
        try:
            await db.execute("SELECT description FROM model_families LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute("ALTER TABLE model_families ADD COLUMN description TEXT")
                await db.commit()
            except Exception:
                pass  # tabela nova criada pelo SCHEMA, nada a migrar

        # model_quota_status — garante coluna 'consecutive_errors'
        try:
            await db.execute("SELECT consecutive_errors FROM model_quota_status LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute("ALTER TABLE model_quota_status ADD COLUMN consecutive_errors INTEGER DEFAULT 0")
                await db.commit()
            except Exception:
                pass

        # model_usage_log — garante colunas de failover
        for col, col_type in [
            ("was_fallback", "INTEGER DEFAULT 0"),
            ("fallback_from_model_id", "TEXT"),
            ("fallback_reason", "TEXT"),
            ("tokens_est", "INTEGER DEFAULT 0"),
        ]:
            try:
                await db.execute(f"SELECT {col} FROM model_usage_log LIMIT 1")
            except aiosqlite.OperationalError:
                try:
                    await db.execute(f"ALTER TABLE model_usage_log ADD COLUMN {col} {col_type}")
                    await db.commit()
                except Exception:
                    pass

        # model_quota_status — colunas do registry de cotas free
        for col, col_type in [
            ("known_rpm", "INTEGER"),
            ("known_rpd", "INTEGER"),
            ("known_tpm", "INTEGER"),
            ("known_tpd", "INTEGER"),
            ("current_minute_count", "INTEGER DEFAULT 0"),
            ("current_day_count", "INTEGER DEFAULT 0"),
            ("minute_window_reset", "TEXT"),
            ("day_window_reset", "TEXT"),
            ("confirmed_free", "INTEGER DEFAULT 0"),
            ("registry_source", "TEXT"),
        ]:
            try:
                await db.execute(f"SELECT {col} FROM model_quota_status LIMIT 1")
            except aiosqlite.OperationalError:
                try:
                    await db.execute(f"ALTER TABLE model_quota_status ADD COLUMN {col} {col_type}")
                    await db.commit()
                except Exception:
                    pass

        # models — coluna confirmed_free
        try:
            await db.execute("SELECT confirmed_free FROM models LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute("ALTER TABLE models ADD COLUMN confirmed_free INTEGER DEFAULT 0")
                await db.commit()
            except Exception:
                pass

        print("[OK] Ranking & Failover tables: initialized")


async def check_and_deactivate_model(model_id: str, error_msg: str, db=None) -> bool:
    """
    Checks if the error indicates a subscription, upgrade, quota, or billing issue,
    and automatically disables the model in the database.
    Returns True if the model was deactivated, False otherwise.
    """
    if not model_id:
        return False
        
    error_lower = error_msg.lower()
    deactivate_triggers = [
        "requires a subscription",
        "upgrade for access",
        "ollama.com/upgrade",
        "billing_limit_reached",
        "credit balance is too low",
        "insufficient_quota",
        "insufficient quota",
        "credit limit",
        "billing limit",
        "payment required",
        "invalid_model",
        "invalid model",
        "model not found",
        "not_found",
        "not found",
        "model_not_found"
    ]
    
    if any(trigger in error_lower for trigger in deactivate_triggers):
        try:
            should_close = False
            if db is None:
                db = await get_db()
                should_close = True
            
            await db.execute("UPDATE models SET enabled = 0 WHERE id = ?", (model_id,))
            await db.commit()
            print(f"🚫 Model '{model_id}' automatically disabled due to billing/subscription error: {error_msg}")
            
            if should_close:
                await db.close()
            return True
        except Exception as e:
            print(f"Error auto-disabling model '{model_id}': {e}")
    return False

