import aiosqlite
import json
import os
from pathlib import Path

from backend.logging_config import get_logger

logger = get_logger(__name__)

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
    share_admin_key INTEGER DEFAULT 0,  -- 1 = admin compartilha esta chave com outros usuários
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
CREATE INDEX IF NOT EXISTS idx_conversations_user_updated ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_user_favorite ON conversations(user_id, is_favorite, favorited_at DESC) WHERE is_favorite = 1;

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    model_id        TEXT,
    provider        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

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
CREATE INDEX IF NOT EXISTS idx_artifacts_conv ON artifacts(conv_id);

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
    user_id        TEXT,
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

CREATE TABLE IF NOT EXISTS user_memory (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,
    fact        TEXT NOT NULL,
    source_conv_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    confidence  REAL DEFAULT 1.0,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_user_memory_user ON user_memory(user_id);

-- =========================================================
-- PROJECTS MODULE (persistent context workspaces + RAG)
-- =========================================================

CREATE TABLE IF NOT EXISTS projects (
    id                   TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name                 TEXT NOT NULL,
    description          TEXT DEFAULT '',
    instructions         TEXT DEFAULT '',
    model_default        TEXT,
    is_favorite          INTEGER DEFAULT 0,
    archived             INTEGER DEFAULT 0,
    retrieval_top_k      INTEGER DEFAULT 6,
    retrieval_threshold  REAL DEFAULT 0.42,
    created_at           TEXT DEFAULT (datetime('now')),
    updated_at           TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id, updated_at);

CREATE TABLE IF NOT EXISTS project_files (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    mime_type       TEXT,
    raw_path        TEXT,
    extracted_text  TEXT,
    size_bytes      INTEGER DEFAULT 0,
    index_status    TEXT DEFAULT 'pending',  -- pending | indexing | ready | error
    index_error     TEXT,
    indexed_at      TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files(project_id);

CREATE TABLE IF NOT EXISTS file_chunks (
    id               TEXT PRIMARY KEY,
    project_file_id  TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
    chunk_text       TEXT NOT NULL,
    chunk_index      INTEGER NOT NULL,
    embedding        BLOB
);
CREATE INDEX IF NOT EXISTS idx_file_chunks_file ON file_chunks(project_file_id);

CREATE TABLE IF NOT EXISTS chat_chunks (
    id               TEXT PRIMARY KEY,
    chat_session_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chunk_text       TEXT NOT NULL,
    role             TEXT DEFAULT 'turn',
    embedding        BLOB,
    created_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_chat_chunks_project ON chat_chunks(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chat_chunks_session ON chat_chunks(chat_session_id);

CREATE TABLE IF NOT EXISTS project_memory (
    id                   TEXT PRIMARY KEY,
    project_id           TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    summary_text         TEXT DEFAULT '',
    last_synthesized_at  TEXT,
    source_chat_ids      TEXT DEFAULT '[]'
);

-- Schema reserved for a future release (no pipeline yet — decision #3)
CREATE TABLE IF NOT EXISTS global_memory (
    id                   TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    summary_text         TEXT DEFAULT '',
    last_synthesized_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_global_memory_user ON global_memory(user_id);
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
        "is_free": 1,
        "models": [
            ("longcat/longcat-2.0", "LongCat-2.0", "LongCat 2.0", 1000000),
        ],
    },
    {
        "id": "freetheai",
        "name": "FreeTheAI",
        "base_url": "https://api.freetheai.xyz/v1",
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
    {
        "id": "zenmux",
        "name": "ZenMux",
        "base_url": "https://zenmux.ai/api/v1",
        "api_key": "free",
        "is_free": 1,
        "models": [
            ("zenmux/grok-4.5-free", "x-ai/grok-4.5-free", "Grok 4.5 Free", 131072),
            ("zenmux/step-3.7-flash-free", "stepfun/step-3.7-flash-free", "Step 3.7 Flash Free", 131072),
            ("zenmux/glm-4.7-flash-free", "z-ai/glm-4.7-flash-free", "GLM 4.7 Flash Free", 131072),
            ("zenmux/glm-4.6v-flash-free", "z-ai/glm-4.6v-flash-free", "GLM 4.6v Flash Free", 131072),
        ],
    },
]


async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA foreign_keys = ON")
    await db.commit()
    return db


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
            logger.error("Error migrating Ollama base_url:", exc_info=e)

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

        # Per-provider admin key sharing (individualize share_admin_keys)
        try:
            await db.execute("SELECT share_admin_key FROM providers LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute(
                "ALTER TABLE providers ADD COLUMN share_admin_key INTEGER DEFAULT 0"
            )
            await db.commit()
            # Seed from global meta: if global share was on, enable all providers
            try:
                async with db.execute(
                    "SELECT value FROM meta WHERE key = 'share_admin_keys'"
                ) as cur:
                    row = await cur.fetchone()
                if row and row[0] == "true":
                    await db.execute("UPDATE providers SET share_admin_key = 1")
                    await db.commit()
            except Exception as e:
                logger.info("[database migration] share_admin_key seed: %s", e)

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

        # Incremental migration check for web_search_log.user_id
        try:
            await db.execute("SELECT user_id FROM web_search_log LIMIT 1")
        except aiosqlite.OperationalError:
            await db.execute("ALTER TABLE web_search_log ADD COLUMN user_id TEXT")
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
            logger.error("[database migration] erro ao migrar prompt do juiz:", exc_info=e)

        # Load context registry
        registry_path = Path(__file__).parent / "data" / "context_registry.json"
        registry_data = {}
        if registry_path.exists():
            try:
                with open(registry_path, "r", encoding="utf-8") as f:
                    registry_data = json.load(f)
            except Exception as e:
                logger.error("Error loading context registry:", exc_info=e)

        registry_models = registry_data.get("models", {})

        for prov in DEFAULT_PROVIDERS:
            # Resolve api_key from env var (e.g. SILICONFLOW_API_KEY) or leave empty
            env_key_name = f"{prov['id'].upper().replace('-', '_')}_API_KEY"
            resolved_api_key = os.getenv(env_key_name, "")
            # Resolve Cloudflare account_id placeholder in base_url from env
            resolved_base_url = prov["base_url"]
            if "{account_id}" in resolved_base_url:
                cf_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
                if cf_account_id:
                    resolved_base_url = resolved_base_url.replace("{account_id}", cf_account_id)
            await db.execute(
                """INSERT INTO providers (id, name, base_url, api_key, is_free) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name, is_free=excluded.is_free""",
                (prov["id"], prov["name"], resolved_base_url, resolved_api_key, prov["is_free"]),
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

        # Default share_admin_keys setting
        await db.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('share_admin_keys', 'false')"
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
            logger.error("Error initializing vision relay config:", exc_info=e)

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
            logger.error("Error initializing web search config:", exc_info=e)

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
            logger.error("Error updating vision models:", exc_info=e)

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

        # Incremental migration check for user_memory
        try:
            await db.execute("SELECT id FROM user_memory LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_memory (
                        id             TEXT PRIMARY KEY,
                        user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        category       TEXT NOT NULL,
                        fact           TEXT NOT NULL,
                        fact_key       TEXT,
                        is_active      INTEGER DEFAULT 1,
                        is_pinned      INTEGER DEFAULT 0,
                        source_conv_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                        confidence     REAL DEFAULT 1.0,
                        created_at     TEXT DEFAULT (datetime('now')),
                        updated_at     TEXT DEFAULT (datetime('now'))
                    )
                    """
                )
                await db.execute("CREATE INDEX IF NOT EXISTS idx_user_memory_user ON user_memory(user_id)")
                await db.execute("CREATE INDEX IF NOT EXISTS idx_user_memory_key ON user_memory(user_id, fact_key) WHERE is_active = 1")
                await db.commit()
            except Exception as e:
                logger.error("[database migration] erro ao migrar user_memory:", exc_info=e)

        # Incremental migration: add fact_key and is_active columns if missing
        for col_name, col_def in [
            ("fact_key", "TEXT"),
            ("is_active", "INTEGER DEFAULT 1"),
            ("is_pinned", "INTEGER DEFAULT 0"),
        ]:
            try:
                await db.execute(f"SELECT {col_name} FROM user_memory LIMIT 1")
            except aiosqlite.OperationalError:
                try:
                    await db.execute(f"ALTER TABLE user_memory ADD COLUMN {col_name} {col_def}")
                    await db.commit()
                except Exception as e:
                    logger.error("[database migration] erro ao adicionar coluna %s em user_memory:", col_name, exc_info=e)

        # Phase A+: user_profiles (server-side profile + memory_enabled)
        try:
            await db.execute("SELECT user_id FROM user_profiles LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_profiles (
                        user_id              TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        display_name         TEXT DEFAULT '',
                        full_name            TEXT DEFAULT '',
                        occupation           TEXT DEFAULT '',
                        custom_instructions  TEXT DEFAULT '',
                        memory_enabled       INTEGER DEFAULT 1,
                        updated_at           TEXT DEFAULT (datetime('now'))
                    )
                    """
                )
                await db.commit()
            except Exception as e:
                logger.error("[database migration] erro ao criar user_profiles:", exc_info=e)

        # Phase C2: rolling summaries (global / project / conversation)
        try:
            await db.execute("SELECT id FROM user_memory_summaries LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute(
                    """
                    CREATE TABLE IF NOT EXISTS user_memory_summaries (
                        id          TEXT PRIMARY KEY,
                        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        scope       TEXT NOT NULL CHECK(scope IN ('global', 'project', 'conversation')),
                        scope_ref   TEXT DEFAULT '',
                        summary_md  TEXT NOT NULL,
                        updated_at  TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, scope, scope_ref)
                    )
                    """
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_memory_summaries_user ON user_memory_summaries(user_id, scope)"
                )
                await db.commit()
            except Exception as e:
                logger.error("[database migration] erro ao criar user_memory_summaries:", exc_info=e)

        # Phase C2: optional project tag on conversations
        try:
            await db.execute("SELECT project_tag FROM conversations LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute("ALTER TABLE conversations ADD COLUMN project_tag TEXT DEFAULT NULL")
                await db.commit()
            except Exception as e:
                logger.error("[database migration] erro ao adicionar project_tag:", exc_info=e)

        # M4: last successful memory extraction timestamp per conversation
        try:
            await db.execute("SELECT memory_extracted_at FROM conversations LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute(
                    "ALTER TABLE conversations ADD COLUMN memory_extracted_at TEXT DEFAULT NULL"
                )
                await db.commit()
            except Exception as e:
                logger.error("[database migration] erro ao adicionar memory_extracted_at:", exc_info=e)

        # Optional: embeddings on memory facts (semantic recall)
        try:
            await db.execute("SELECT embedding FROM user_memory LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute("ALTER TABLE user_memory ADD COLUMN embedding BLOB")
                await db.commit()
            except Exception as e:
                logger.error("[database migration] erro ao adicionar embedding em user_memory:", exc_info=e)

        # Projects module tables (idempotent CREATE IF NOT EXISTS via SCHEMA above + safety)
        try:
            await db.execute("SELECT id FROM projects LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS projects (
                        id                   TEXT PRIMARY KEY,
                        user_id              TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        name                 TEXT NOT NULL,
                        description          TEXT DEFAULT '',
                        instructions         TEXT DEFAULT '',
                        model_default        TEXT,
                        is_favorite          INTEGER DEFAULT 0,
                        archived             INTEGER DEFAULT 0,
                        retrieval_top_k      INTEGER DEFAULT 6,
                        retrieval_threshold  REAL DEFAULT 0.42,
                        created_at           TEXT DEFAULT (datetime('now')),
                        updated_at           TEXT DEFAULT (datetime('now'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id, updated_at);
                    CREATE TABLE IF NOT EXISTS project_files (
                        id              TEXT PRIMARY KEY,
                        project_id      TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        filename        TEXT NOT NULL,
                        mime_type       TEXT,
                        raw_path        TEXT,
                        extracted_text  TEXT,
                        size_bytes      INTEGER DEFAULT 0,
                        index_status    TEXT DEFAULT 'pending',
                        index_error     TEXT,
                        indexed_at      TEXT,
                        created_at      TEXT DEFAULT (datetime('now'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_project_files_project ON project_files(project_id);
                    CREATE TABLE IF NOT EXISTS file_chunks (
                        id               TEXT PRIMARY KEY,
                        project_file_id  TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
                        chunk_text       TEXT NOT NULL,
                        chunk_index      INTEGER NOT NULL,
                        embedding        BLOB
                    );
                    CREATE INDEX IF NOT EXISTS idx_file_chunks_file ON file_chunks(project_file_id);
                    CREATE TABLE IF NOT EXISTS chat_chunks (
                        id               TEXT PRIMARY KEY,
                        chat_session_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                        project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                        chunk_text       TEXT NOT NULL,
                        role             TEXT DEFAULT 'turn',
                        embedding        BLOB,
                        created_at       TEXT DEFAULT (datetime('now'))
                    );
                    CREATE INDEX IF NOT EXISTS idx_chat_chunks_project ON chat_chunks(project_id, created_at);
                    CREATE INDEX IF NOT EXISTS idx_chat_chunks_session ON chat_chunks(chat_session_id);
                    CREATE TABLE IF NOT EXISTS project_memory (
                        id                   TEXT PRIMARY KEY,
                        project_id           TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
                        summary_text         TEXT DEFAULT '',
                        last_synthesized_at  TEXT,
                        source_chat_ids      TEXT DEFAULT '[]'
                    );
                    CREATE TABLE IF NOT EXISTS global_memory (
                        id                   TEXT PRIMARY KEY,
                        user_id              TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        summary_text         TEXT DEFAULT '',
                        last_synthesized_at  TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_global_memory_user ON global_memory(user_id);
                    """
                )
                await db.commit()
                logger.info("[OK] Projects tables: created")
            except Exception as e:
                logger.error("[database migration] erro ao criar tabelas de projects:", exc_info=e)

        # conversations.project_id (nullable) — chat avulso when NULL
        try:
            await db.execute("SELECT project_id FROM conversations LIMIT 1")
        except aiosqlite.OperationalError:
            try:
                await db.execute(
                    "ALTER TABLE conversations ADD COLUMN project_id TEXT REFERENCES projects(id) ON DELETE SET NULL"
                )
                await db.execute(
                    "CREATE INDEX IF NOT EXISTS idx_conversations_project ON conversations(project_id)"
                )
                await db.commit()
                logger.info("[OK] conversations.project_id: added")
            except Exception as e:
                logger.error("[database migration] erro ao adicionar project_id em conversations:", exc_info=e)

        logger.error("[OK] Ranking & Failover tables: initialized")


MEMORY_CATEGORIES = ('professional', 'personal', 'project', 'preference', 'identity', 'tech')

# Max chars (~tokens x4) to inject into system prompt from memory block
MEMORY_INJECT_MAX_CHARS = 4000

# Max number of facts to fetch for injection (top-K by confidence + recency)
MEMORY_INJECT_LIMIT = 30


async def get_user_memory(user_id: str, limit: int = MEMORY_INJECT_LIMIT, active_only: bool = False) -> list[dict]:
    """Returns up to `limit` active memory facts ordered by confidence desc, updated_at desc."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        where = "user_id = ? AND is_active = 1" if active_only else "user_id = ?"
        async with db.execute(
            f"""SELECT id, category, fact, fact_key, source_conv_id, confidence, is_pinned, is_active, updated_at
                FROM user_memory
                WHERE {where}
                ORDER BY is_pinned DESC, confidence DESC, updated_at DESC
                LIMIT ?""",
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


def _try_embed_fact(text: str):
    """Optional embedding via cache manager embedder (fastembed)."""
    try:
        from backend.cache.manager import _embed_text
        return _embed_text(text or "")
    except Exception:
        return None


async def add_memory_fact(
    user_id: str,
    category: str,
    fact: str,
    fact_key: str = None,
    source_conv_id: str = None,
    confidence: float = 1.0,
) -> str:
    """Upserts a memory fact. If fact_key matches an existing active fact, updates it in-place."""
    import uuid
    emb = _try_embed_fact(fact)
    async with aiosqlite.connect(DB_PATH) as db:
        # 1. Try to match by fact_key (stable key = definitive identity of a fact)
        if fact_key:
            async with db.execute(
                "SELECT id FROM user_memory WHERE user_id = ? AND fact_key = ? AND is_active = 1",
                (user_id, fact_key),
            ) as cur:
                existing = await cur.fetchone()
            if existing:
                if emb is not None:
                    await db.execute(
                        """UPDATE user_memory
                           SET fact = ?, category = ?, confidence = MAX(confidence, ?),
                               source_conv_id = ?, embedding = ?, updated_at = datetime('now')
                           WHERE id = ?""",
                        (fact, category, confidence, source_conv_id, emb, existing[0]),
                    )
                else:
                    await db.execute(
                        """UPDATE user_memory
                           SET fact = ?, category = ?, confidence = MAX(confidence, ?),
                               source_conv_id = ?, updated_at = datetime('now')
                           WHERE id = ?""",
                        (fact, category, confidence, source_conv_id, existing[0]),
                    )
                await db.commit()
                return existing[0]

        # 2. Fallback: avoid exact text duplicates
        async with db.execute(
            "SELECT id FROM user_memory WHERE user_id = ? AND fact = ? AND is_active = 1",
            (user_id, fact),
        ) as cur:
            dup = await cur.fetchone()
        if dup:
            if fact_key or emb is not None:
                if emb is not None and fact_key:
                    await db.execute(
                        "UPDATE user_memory SET fact_key = ?, embedding = ?, updated_at = datetime('now') WHERE id = ?",
                        (fact_key, emb, dup[0]),
                    )
                elif emb is not None:
                    await db.execute(
                        "UPDATE user_memory SET embedding = ?, updated_at = datetime('now') WHERE id = ?",
                        (emb, dup[0]),
                    )
                else:
                    await db.execute(
                        "UPDATE user_memory SET fact_key = ?, updated_at = datetime('now') WHERE id = ?",
                        (fact_key, dup[0]),
                    )
                await db.commit()
            return dup[0]

        # 3. Insert new fact — respect cap of 200 active facts per user
        async with db.execute(
            "SELECT COUNT(*) FROM user_memory WHERE user_id = ? AND is_active = 1", (user_id,)
        ) as cur:
            (count,) = await cur.fetchone()
        if count >= 200:
            # Archive the oldest, lowest-confidence non-pinned fact to make room
            await db.execute(
                """UPDATE user_memory SET is_active = 0 WHERE id = (
                    SELECT id FROM user_memory
                    WHERE user_id = ? AND is_active = 1 AND is_pinned = 0
                    ORDER BY confidence ASC, updated_at ASC LIMIT 1
                )""",
                (user_id,),
            )

        fact_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO user_memory
               (id, user_id, category, fact, fact_key, source_conv_id, confidence, is_active, embedding)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)""",
            (fact_id, user_id, category, fact, fact_key, source_conv_id, confidence, emb),
        )
        await db.commit()
        return fact_id


async def set_memory_fact_pinned(user_id: str, fact_id: str, pinned: bool) -> bool:
    """Pin/unpin a fact belonging to user. Returns True if updated."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM user_memory WHERE id = ? AND user_id = ?",
            (fact_id, user_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return False
        await db.execute(
            "UPDATE user_memory SET is_pinned = ?, updated_at = datetime('now') WHERE id = ?",
            (1 if pinned else 0, fact_id),
        )
        await db.commit()
        return True


async def get_relevant_memory(
    user_id: str,
    query_text: str,
    limit: int = MEMORY_INJECT_LIMIT,
) -> list[dict]:
    """
    Semantic recall: pinned facts first, then top-K by embedding similarity to query.
    Falls back to confidence order if embedder unavailable.
    """
    import asyncio

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # embedding column may be missing on very old DBs mid-migration
        try:
            async with db.execute(
                """SELECT id, category, fact, fact_key, source_conv_id, confidence,
                          is_pinned, is_active, updated_at, embedding
                   FROM user_memory
                   WHERE user_id = ? AND is_active = 1""",
                (user_id,),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]
        except Exception:
            async with db.execute(
                """SELECT id, category, fact, fact_key, source_conv_id, confidence,
                          is_pinned, is_active, updated_at
                   FROM user_memory
                   WHERE user_id = ? AND is_active = 1""",
                (user_id,),
            ) as cur:
                rows = [dict(r) for r in await cur.fetchall()]

    if not rows:
        return []

    pinned = [r for r in rows if r.get("is_pinned")]
    unpinned = [r for r in rows if not r.get("is_pinned")]

    # Embed query (optional fastembed)
    query_blob = None
    _embed_text = _blob_to_embedding = _cosine_similarity = None
    _HAS_NUMPY = False
    try:
        from backend.cache.manager import (
            _embed_text as _et,
            _blob_to_embedding as _b2e,
            _cosine_similarity as _cos,
            _HAS_NUMPY as _hn,
        )
        _embed_text, _blob_to_embedding, _cosine_similarity, _HAS_NUMPY = _et, _b2e, _cos, _hn
    except Exception:
        pass

    if query_text and _HAS_NUMPY and _embed_text:
        loop = asyncio.get_event_loop()
        try:
            query_blob = await loop.run_in_executor(None, _embed_text, query_text[:2000])
        except Exception:
            query_blob = None

    if query_blob is not None and unpinned and _blob_to_embedding and _cosine_similarity:
        qvec = _blob_to_embedding(query_blob)
        scored = []
        for r in unpinned:
            emb = r.get("embedding")
            if emb:
                try:
                    sim = _cosine_similarity(qvec, _blob_to_embedding(emb))
                except Exception:
                    sim = 0.0
            else:
                # keyword soft score
                qt = query_text.lower()
                ft = (r.get("fact") or "").lower()
                sim = 0.15 if any(w in ft for w in qt.split() if len(w) > 3) else 0.0
            conf = float(r.get("confidence") or 0.5)
            scored.append((0.7 * sim + 0.3 * conf, r))
        scored.sort(key=lambda x: x[0], reverse=True)
        ranked = [r for _, r in scored]
    else:
        ranked = sorted(
            unpinned,
            key=lambda r: (float(r.get("confidence") or 0), r.get("updated_at") or ""),
            reverse=True,
        )

    # Merge: all pinned + ranked unpinned, cap limit
    seen = set()
    result = []
    for r in pinned + ranked:
        rid = r.get("id")
        if rid in seen:
            continue
        seen.add(rid)
        # strip heavy blob from response
        r = {k: v for k, v in r.items() if k != "embedding"}
        result.append(r)
        if len(result) >= limit:
            break
    return result


async def deactivate_memory_by_key(user_id: str, fact_key: str) -> None:
    """Soft-deletes a memory fact by fact_key (action: forget from the extractor)."""
    if not fact_key:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_memory SET is_active = 0, updated_at = datetime('now') WHERE user_id = ? AND fact_key = ?",
            (user_id, fact_key),
        )
        await db.commit()


async def delete_memory_fact(fact_id: str, user_id: str = None) -> bool:
    """Hard-delete a single fact by ID. If user_id is provided, only deletes
    if the fact belongs to that user (prevents IDOR). Returns True if deleted."""
    async with aiosqlite.connect(DB_PATH) as db:
        if user_id is not None:
            async with db.execute(
                "SELECT id FROM user_memory WHERE id = ? AND user_id = ?",
                (fact_id, user_id),
            ) as cur:
                if not await cur.fetchone():
                    return False
        await db.execute("DELETE FROM user_memory WHERE id = ?", (fact_id,))
        await db.commit()
        return True


async def clear_all_memory_summaries(user_id: str) -> int:
    """Hard-deletes all rolling summaries (global + project) for a user."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "DELETE FROM user_memory_summaries WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        return cur.rowcount if cur.rowcount is not None else 0


async def clear_all_memory(user_id: str) -> None:
    """
    Esquecer tudo: soft-delete de todos os fatos ativos + apaga resumos rolling
    (global e por projeto). Perfil manual (nome/instruções) é preservado.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE user_memory SET is_active = 0, updated_at = datetime('now') WHERE user_id = ? AND is_active = 1",
            (user_id,),
        )
        await db.execute(
            "DELETE FROM user_memory_summaries WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def get_memory_stats(user_id: str) -> dict:
    """Local metrics for memory dashboard (Phase D)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM user_memory WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ) as cur:
            (active_facts,) = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(*) FROM user_memory WHERE user_id = ? AND (is_active = 0 OR is_active IS NULL)",
            (user_id,),
        ) as cur:
            (inactive_facts,) = await cur.fetchone()
        async with db.execute(
            """SELECT category, COUNT(*) FROM user_memory
               WHERE user_id = ? AND is_active = 1
               GROUP BY category""",
            (user_id,),
        ) as cur:
            by_category = {row[0]: row[1] for row in await cur.fetchall()}
        async with db.execute(
            "SELECT COUNT(*) FROM user_memory_summaries WHERE user_id = ?",
            (user_id,),
        ) as cur:
            (summaries_count,) = await cur.fetchone()
        async with db.execute(
            "SELECT MAX(updated_at) FROM user_memory WHERE user_id = ? AND is_active = 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            last_fact_update = row[0] if row else None
        async with db.execute(
            "SELECT value FROM meta WHERE key = ?",
            (f"memory_extractions_total_{user_id}",),
        ) as cur:
            row = await cur.fetchone()
            extractions_total = int(row[0]) if row and str(row[0]).isdigit() else 0
        async with db.execute(
            "SELECT value FROM meta WHERE key = ?",
            (f"memory_extractions_day_{user_id}",),
        ) as cur:
            row = await cur.fetchone()
            day_raw = row[0] if row else None
        extractions_today = 0
        extractions_day_date = None
        if day_raw and "|" in day_raw:
            extractions_day_date, count_s = day_raw.split("|", 1)
            try:
                extractions_today = int(count_s)
            except ValueError:
                extractions_today = 0
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if extractions_day_date != today:
            extractions_today = 0

    return {
        "active_facts": active_facts or 0,
        "inactive_facts": inactive_facts or 0,
        "by_category": by_category,
        "summaries_count": summaries_count or 0,
        "last_fact_update": last_fact_update,
        "extractions_total": extractions_total,
        "extractions_today": extractions_today,
    }


async def increment_memory_extraction_stats(user_id: str) -> None:
    """Bump extraction counters after a successful background extract."""
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_key = f"memory_extractions_total_{user_id}"
    day_key = f"memory_extractions_day_{user_id}"
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT value FROM meta WHERE key = ?", (total_key,)) as cur:
            row = await cur.fetchone()
        total = int(row[0]) + 1 if row and str(row[0]).isdigit() else 1
        await db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (total_key, str(total)),
        )
        async with db.execute("SELECT value FROM meta WHERE key = ?", (day_key,)) as cur:
            row = await cur.fetchone()
        day_count = 1
        if row and row[0] and "|" in row[0]:
            d, c = row[0].split("|", 1)
            if d == today:
                try:
                    day_count = int(c) + 1
                except ValueError:
                    day_count = 1
        await db.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (day_key, f"{today}|{day_count}"),
        )
        await db.commit()


async def get_user_profile(user_id: str) -> dict:
    """Returns server-side profile or empty defaults."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT user_id, display_name, full_name, occupation,
                      custom_instructions, memory_enabled, updated_at
               FROM user_profiles WHERE user_id = ?""",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {
                "user_id": user_id,
                "display_name": "",
                "full_name": "",
                "occupation": "",
                "custom_instructions": "",
                "memory_enabled": 1,
                "updated_at": None,
            }
        return dict(row)


async def get_memory_summary(user_id: str, scope: str = "global", scope_ref: str = "") -> dict | None:
    """Returns one summary row or None."""
    scope_ref = scope_ref or ""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT id, user_id, scope, scope_ref, summary_md, updated_at
               FROM user_memory_summaries
               WHERE user_id = ? AND scope = ? AND scope_ref = ?""",
            (user_id, scope, scope_ref),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def list_memory_summaries(user_id: str, scope: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if scope:
            async with db.execute(
                """SELECT id, user_id, scope, scope_ref, summary_md, updated_at
                   FROM user_memory_summaries
                   WHERE user_id = ? AND scope = ?
                   ORDER BY updated_at DESC""",
                (user_id, scope),
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]
        async with db.execute(
            """SELECT id, user_id, scope, scope_ref, summary_md, updated_at
               FROM user_memory_summaries
               WHERE user_id = ?
               ORDER BY scope, updated_at DESC""",
            (user_id,),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]


async def upsert_memory_summary(
    user_id: str,
    scope: str,
    summary_md: str,
    scope_ref: str = "",
) -> dict:
    """Insert or replace a rolling summary for user/scope."""
    import uuid

    scope_ref = scope_ref or ""
    summary_md = (summary_md or "").strip()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """SELECT id FROM user_memory_summaries
               WHERE user_id = ? AND scope = ? AND scope_ref = ?""",
            (user_id, scope, scope_ref),
        ) as cur:
            existing = await cur.fetchone()
        if existing:
            await db.execute(
                """UPDATE user_memory_summaries
                   SET summary_md = ?, updated_at = datetime('now')
                   WHERE id = ?""",
                (summary_md, existing[0]),
            )
            await db.commit()
            sid = existing[0]
        else:
            sid = str(uuid.uuid4())
            await db.execute(
                """INSERT INTO user_memory_summaries
                   (id, user_id, scope, scope_ref, summary_md, updated_at)
                   VALUES (?, ?, ?, ?, ?, datetime('now'))""",
                (sid, user_id, scope, scope_ref, summary_md),
            )
            await db.commit()
    return await get_memory_summary(user_id, scope, scope_ref) or {
        "id": sid,
        "user_id": user_id,
        "scope": scope,
        "scope_ref": scope_ref,
        "summary_md": summary_md,
    }


async def delete_memory_summary(user_id: str, scope: str, scope_ref: str = "") -> None:
    scope_ref = scope_ref or ""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """DELETE FROM user_memory_summaries
               WHERE user_id = ? AND scope = ? AND scope_ref = ?""",
            (user_id, scope, scope_ref),
        )
        await db.commit()


async def delete_orphaned_memory_summaries(user_id: str, keep_project_refs: set[str] | None = None) -> int:
    """
    Remove project summaries whose scope_ref is not in keep_project_refs.
    If keep_project_refs is empty/None, deletes all project-scoped summaries.
    Global summary is left alone (caller handles empty global).
    """
    keep = { (r or "").strip().lower() for r in (keep_project_refs or set()) if (r or "").strip() }
    async with aiosqlite.connect(DB_PATH) as db:
        if not keep:
            cur = await db.execute(
                "DELETE FROM user_memory_summaries WHERE user_id = ? AND scope = 'project'",
                (user_id,),
            )
        else:
            # Delete project summaries not in keep list
            async with db.execute(
                "SELECT id, scope_ref FROM user_memory_summaries WHERE user_id = ? AND scope = 'project'",
                (user_id,),
            ) as cur:
                rows = await cur.fetchall()
            to_delete = [r[0] for r in rows if (r[1] or "").strip().lower() not in keep]
            if not to_delete:
                return 0
            placeholders = ",".join("?" * len(to_delete))
            cur = await db.execute(
                f"DELETE FROM user_memory_summaries WHERE id IN ({placeholders})",
                to_delete,
            )
        await db.commit()
        return cur.rowcount if cur.rowcount is not None else 0


async def get_conversation_project_tag(conversation_id: str) -> str | None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT project_tag FROM conversations WHERE id = ?",
            (conversation_id,),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return None
        tag = row[0]
        return tag.strip() if tag and str(tag).strip() else None


async def set_conversation_project_tag(conversation_id: str, project_tag: str | None) -> None:
    tag = (project_tag or "").strip() or None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE conversations SET project_tag = ?, updated_at = datetime('now') WHERE id = ?",
            (tag, conversation_id),
        )
        await db.commit()


async def mark_conversation_memory_extracted(conversation_id: str) -> None:
    """Stamp conversation after a successful (or attempted) memory extraction pass."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE conversations SET memory_extracted_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        await db.commit()


# M4: idle extraction defaults (minutes / days / batch size)
MEMORY_IDLE_MINUTES = 120          # conversation quiet for 2h
MEMORY_IDLE_MAX_AGE_DAYS = 7       # ignore chats older than a week
MEMORY_IDLE_BATCH = 8              # max conversations per job tick
MEMORY_IDLE_MIN_MESSAGES = 2       # need at least user+assistant


async def list_idle_conversations_for_memory(
    idle_minutes: int = MEMORY_IDLE_MINUTES,
    max_age_days: int = MEMORY_IDLE_MAX_AGE_DAYS,
    limit: int = MEMORY_IDLE_BATCH,
    min_messages: int = MEMORY_IDLE_MIN_MESSAGES,
) -> list[dict]:
    """
    Conversations that:
      - have enough messages
      - have been idle for `idle_minutes` (no new activity)
      - are not older than `max_age_days`
      - have never been extracted OR have new activity since last extraction
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # SQLite datetime('now') is UTC when using datetime('now')
        async with db.execute(
            f"""
            SELECT c.id AS conversation_id,
                   c.user_id AS user_id,
                   c.model_id AS model_id,
                   c.provider_id AS provider_id,
                   c.updated_at AS updated_at,
                   c.memory_extracted_at AS memory_extracted_at,
                   COUNT(m.id) AS message_count
            FROM conversations c
            INNER JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id IS NOT NULL
              AND datetime(c.updated_at) <= datetime('now', ?)
              AND datetime(c.updated_at) >= datetime('now', ?)
              AND (
                    c.memory_extracted_at IS NULL
                 OR datetime(c.memory_extracted_at) < datetime(c.updated_at)
              )
            GROUP BY c.id
            HAVING COUNT(m.id) >= ?
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (
                f"-{int(idle_minutes)} minutes",
                f"-{int(max_age_days)} days",
                int(min_messages),
                int(limit),
            ),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def upsert_user_profile(
    user_id: str,
    display_name: str | None = None,
    full_name: str | None = None,
    occupation: str | None = None,
    custom_instructions: str | None = None,
    memory_enabled: int | None = None,
) -> dict:
    """Creates or updates user profile fields (only provided keys are changed)."""
    current = await get_user_profile(user_id)
    new_display = display_name if display_name is not None else current.get("display_name") or ""
    new_full = full_name if full_name is not None else current.get("full_name") or ""
    new_occ = occupation if occupation is not None else current.get("occupation") or ""
    new_instr = custom_instructions if custom_instructions is not None else current.get("custom_instructions") or ""
    new_mem = memory_enabled if memory_enabled is not None else int(current.get("memory_enabled", 1) or 1)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_profiles
               (user_id, display_name, full_name, occupation, custom_instructions, memory_enabled, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
               ON CONFLICT(user_id) DO UPDATE SET
                 display_name = excluded.display_name,
                 full_name = excluded.full_name,
                 occupation = excluded.occupation,
                 custom_instructions = excluded.custom_instructions,
                 memory_enabled = excluded.memory_enabled,
                 updated_at = datetime('now')""",
            (user_id, new_display, new_full, new_occ, new_instr, int(new_mem)),
        )
        await db.commit()
    return await get_user_profile(user_id)


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
        "model_not_found",
        # Cloudflare Workers AI: Function UUID not found
        "function '",
        "404 page not found",
    ]
    
    if any(trigger in error_lower for trigger in deactivate_triggers):
        try:
            should_close = False
            if db is None:
                db = await get_db()
                should_close = True
            
            await db.execute("UPDATE models SET enabled = 0 WHERE id = ?", (model_id,))
            await db.commit()
            logger.error("🚫 Model '%s' automatically disabled due to billing/subscription error:", model_id, exc_info=error_msg)
            
            if should_close:
                await db.close()
            return True
        except Exception as e:
            logger.error("Error auto-disabling model '%s':", model_id, exc_info=e)
    return False

