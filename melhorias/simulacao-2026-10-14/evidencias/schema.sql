CREATE INDEX idx_artifacts_conv ON artifacts(conv_id);

CREATE INDEX idx_attachments_message ON attachments(message_id);

CREATE INDEX idx_attachments_user_unsent ON attachments(user_id) WHERE message_id IS NULL;

CREATE INDEX idx_cache_exact_hash ON cache_exact(hash, model_id);

CREATE INDEX idx_cache_semantic_fp ON cache_semantic(fingerprint, model_id);

CREATE INDEX idx_cache_semantic_model ON cache_semantic(model_id);

CREATE INDEX idx_cache_semantic_scope_fp ON cache_semantic(user_id, model_id, fingerprint);

CREATE INDEX idx_cache_semantic_user ON cache_semantic(user_id);

CREATE INDEX idx_chat_chunks_project ON chat_chunks(project_id, created_at);

CREATE INDEX idx_chat_chunks_session ON chat_chunks(chat_session_id);

CREATE INDEX idx_conversations_project ON conversations(project_id);

CREATE INDEX idx_conversations_user_favorite ON conversations(user_id, is_favorite, favorited_at DESC) WHERE is_favorite = 1;

CREATE INDEX idx_conversations_user_updated ON conversations(user_id, updated_at DESC);

CREATE INDEX idx_dream_logs_user ON dream_logs(user_id, created_at DESC);

CREATE INDEX idx_family_members_family ON model_family_members(family_id, fallback_order);

CREATE INDEX idx_file_chunks_file ON file_chunks(project_file_id);

CREATE INDEX idx_global_memory_user ON global_memory(user_id);

CREATE INDEX idx_image_tasks_att ON image_gen_tasks(attachment_id);

CREATE INDEX idx_image_tasks_status ON image_gen_tasks(status, created_at);

CREATE INDEX idx_image_tasks_user_day ON image_gen_tasks(user_id, created_at);

CREATE INDEX idx_memory_summaries_user ON user_memory_summaries(user_id, scope);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

CREATE INDEX idx_messages_kind_proactive ON messages(conversation_id) WHERE kind = 'proactive';

CREATE INDEX idx_models_reasoning_control ON models(reasoning_control);

CREATE INDEX idx_proactive_conv ON proactive_insights(conversation_id, created_at DESC);

CREATE INDEX idx_proactive_topic_recent ON proactive_insights(user_id, topic_hash, created_at DESC);

CREATE INDEX idx_proactive_user_status ON proactive_insights(user_id, status, created_at DESC);

CREATE INDEX idx_project_files_project ON project_files(project_id);

CREATE INDEX idx_projects_user ON projects(user_id, updated_at);

CREATE INDEX idx_registry_provider ON free_model_registry(provider_name, model_id_raw);

CREATE INDEX idx_snapshots_user ON memory_snapshots(user_id, created_at DESC);

CREATE INDEX idx_usage_auto ON model_usage_log(was_auto_routed, route_intent);

CREATE INDEX idx_usage_model ON model_usage_log(model_id, created_at);

CREATE INDEX idx_usage_user  ON model_usage_log(user_id, created_at);

CREATE INDEX idx_user_memory_key ON user_memory(user_id, fact_key) WHERE is_active = 1;

CREATE INDEX idx_user_memory_user ON user_memory(user_id);

CREATE TABLE artifacts (
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

CREATE TABLE attachments (
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
, user_id TEXT);

CREATE TABLE cache_exact (
    id          TEXT PRIMARY KEY,
    hash        TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    response    TEXT NOT NULL,
    token_est   INTEGER DEFAULT 0,
    hits        INTEGER DEFAULT 0,
    last_hit    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE cache_semantic (
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
, fingerprint TEXT, user_id TEXT);

CREATE TABLE cache_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE chat_chunks (
    id               TEXT PRIMARY KEY,
    chat_session_id  TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    project_id       TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    chunk_text       TEXT NOT NULL,
    role             TEXT DEFAULT 'turn',
    embedding        BLOB,
    created_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT DEFAULT 'Nova conversa',
    model_id    TEXT,
    provider_id TEXT,
    is_favorite INTEGER DEFAULT 0,
    favorited_at TEXT DEFAULT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
, project_tag TEXT DEFAULT NULL, memory_extracted_at TEXT DEFAULT NULL, project_id TEXT REFERENCES projects(id) ON DELETE SET NULL, origin_insight_id TEXT);

CREATE TABLE dream_logs (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    snapshot_id        TEXT REFERENCES memory_snapshots(id) ON DELETE SET NULL,
    provider_id        TEXT NOT NULL,
    model_id           TEXT NOT NULL,
    facts_before       INTEGER NOT NULL,
    facts_after        INTEGER NOT NULL,
    facts_merged       INTEGER NOT NULL,
    facts_superseded   INTEGER NOT NULL,
    facts_created      INTEGER NOT NULL,
    facts_total_active INTEGER NOT NULL,
    duration_ms        INTEGER NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending',
    summary_notes      TEXT,
    error_message      TEXT,
    interrupted_fixed  INTEGER DEFAULT 0,
    created_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE enhancer_config (
    id                      INTEGER PRIMARY KEY DEFAULT 1,
    enhancer_provider_id    TEXT,
    enhancer_model_id       TEXT,
    enhancer_enabled        INTEGER DEFAULT 1,
    enhancer_system_prompt  TEXT
);

CREATE TABLE file_chunks (
    id               TEXT PRIMARY KEY,
    project_file_id  TEXT NOT NULL REFERENCES project_files(id) ON DELETE CASCADE,
    chunk_text       TEXT NOT NULL,
    chunk_index      INTEGER NOT NULL,
    embedding        BLOB
);

CREATE TABLE free_model_registry (
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

CREATE TABLE fusion_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    judge_provider_id   TEXT NOT NULL,
    judge_model_id      TEXT NOT NULL,
    judge_system_prompt TEXT,
    enabled             INTEGER DEFAULT 1,
    grounding_enabled   INTEGER DEFAULT 1
);

CREATE TABLE fusion_models (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id TEXT NOT NULL,
    model_id    TEXT NOT NULL,
    position    INTEGER DEFAULT 0,
    UNIQUE(provider_id)
);

CREATE TABLE global_memory (
    id                   TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    summary_text         TEXT DEFAULT '',
    last_synthesized_at  TEXT
);

CREATE TABLE image_gen_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    enabled             INTEGER DEFAULT 0,
    auto_detect         INTEGER DEFAULT 1,
    provider_id         TEXT,
    model_id            TEXT,
    steps               INTEGER DEFAULT 4,
    width               INTEGER DEFAULT 1024,
    height              INTEGER DEFAULT 1024,
    daily_cap_per_user  INTEGER DEFAULT 20
);

CREATE TABLE image_gen_tasks (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL,
    user_id          TEXT NOT NULL,
    message_id       TEXT NOT NULL,
    prompt           TEXT NOT NULL,
    status           TEXT NOT NULL,
    model_id         TEXT,
    error_message    TEXT,
    created_at       TEXT DEFAULT (datetime('now')),
    started_at       TEXT,
    completed_at     TEXT,
    attachment_id    TEXT
);

CREATE TABLE image_models (
    id            TEXT PRIMARY KEY,
    provider_id   TEXT NOT NULL,
    name          TEXT NOT NULL,
    display_name  TEXT NOT NULL,
    notes         TEXT,
    enabled       INTEGER DEFAULT 1
);

CREATE TABLE memory_snapshots (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trigger_type   TEXT NOT NULL,
    facts_count    INTEGER NOT NULL,
    snapshot_json  TEXT NOT NULL,
    snapshot_hash  TEXT NOT NULL,
    is_compressed  INTEGER DEFAULT 0,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE message_ui_blocks (
                    message_id TEXT PRIMARY KEY REFERENCES messages(id) ON DELETE CASCADE,
                    payload    TEXT NOT NULL,
                    source     TEXT NOT NULL CHECK(source IN ('host', 'model')),
                    created_at TEXT DEFAULT (datetime('now'))
                );

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK(role IN ('user','assistant','system')),
    content         TEXT NOT NULL,
    model_id        TEXT,
    provider        TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
, relay_used INTEGER DEFAULT 0, relay_model TEXT, web_search_used INTEGER DEFAULT 0, web_search_query TEXT, web_search_sources TEXT, process_steps TEXT, kind TEXT DEFAULT 'normal', proactive_insight_id TEXT);

CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE model_families (
    id            TEXT PRIMARY KEY,       -- 'deepseek-r1', 'llama-3.3-70b'
    display_name  TEXT NOT NULL,          -- 'DeepSeek R1'
    description   TEXT
);

CREATE TABLE model_family_members (
    id              TEXT PRIMARY KEY,
    family_id       TEXT NOT NULL REFERENCES model_families(id) ON DELETE CASCADE,
    model_id        TEXT NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    fallback_order  INTEGER NOT NULL,     -- 1 = prioridade, 2 = primeiro fallback, etc.
    UNIQUE(family_id, model_id)
);

CREATE TABLE model_overrides (
    model_id        TEXT PRIMARY KEY,
    context_length  INTEGER NOT NULL,
    set_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE model_quota_status (
    model_id            TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    status              TEXT DEFAULT 'available',  -- 'available' | 'degraded' | 'exhausted'
    consecutive_errors  INTEGER DEFAULT 0,
    exhausted_at        TEXT,
    estimated_reset_at  TEXT,             -- estimativa de quando volta (Retry-After ou heurística)
    last_error_message  TEXT
, known_rpm INTEGER, known_rpd INTEGER, known_tpm INTEGER, known_tpd INTEGER, current_minute_count INTEGER DEFAULT 0, current_day_count INTEGER DEFAULT 0, minute_window_reset TEXT, day_window_reset TEXT, confirmed_free INTEGER DEFAULT 0, registry_source TEXT);

CREATE TABLE model_rankings (
    model_id           TEXT PRIMARY KEY REFERENCES models(id) ON DELETE CASCADE,
    quality_score      REAL DEFAULT 0,    -- normalizado 0-100, de llm-stats / curadoria
    popularity_rank    INTEGER,           -- posição no OpenRouter Rankings (1 = mais popular)
    nexuslocal_score   REAL DEFAULT 0,    -- combinado (calculado por scorer.py)
    source             TEXT DEFAULT 'manual',  -- 'manual' | 'openrouter' | 'llm-stats' | 'hybrid'
    updated_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE model_usage_log (
    id                     TEXT PRIMARY KEY,
    model_id               TEXT NOT NULL,
    provider_id            TEXT NOT NULL,
    conversation_id        TEXT,
    user_id                TEXT,          -- rastreia por usuário (JWT já implementado)
    tokens_est             INTEGER DEFAULT 0,
    was_fallback           INTEGER DEFAULT 0,  -- 1 se foi failover automático
    fallback_from_model_id TEXT,
    fallback_reason        TEXT,          -- 'rate_limit' | 'error' | 'manual'
    was_auto_routed        INTEGER DEFAULT 0,  -- 1 se foi roteado automaticamente
    route_intent           TEXT,               -- 'code_engineering', 'trivial_quick', etc.
    route_confidence       REAL,               -- 0.0 a 1.0
    route_latency_ms       REAL,               -- Latência do classificador (< 2.0ms)
    route_policy           TEXT,               -- 'economical_free', 'balanced_smart', 'max_performance'
    created_at             TEXT DEFAULT (datetime('now'))
);

CREATE TABLE models (
    id             TEXT PRIMARY KEY,
    provider_id    TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    context_length INTEGER DEFAULT 8192,
    context_source TEXT DEFAULT 'default',
    confirmed_free INTEGER DEFAULT 0,
    enabled        INTEGER DEFAULT 1
, supports_vision INTEGER DEFAULT 0, reasoning_control TEXT DEFAULT 'none', reasoning_levels TEXT, reasoning_default TEXT, reasoning_control_source TEXT DEFAULT 'unset');

CREATE TABLE proactive_insights (
                    id                      TEXT PRIMARY KEY,
                    user_id                 TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    conversation_id         TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    source_message_id       TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    delivered_message_id    TEXT REFERENCES messages(id) ON DELETE SET NULL,
                    spawned_conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
                    topic                   TEXT NOT NULL,
                    topic_hash              TEXT NOT NULL,
                    entities_json           TEXT NOT NULL DEFAULT '[]',
                    category                TEXT NOT NULL,
                    confidence              REAL NOT NULL,
                    query                   TEXT,
                    status                  TEXT NOT NULL DEFAULT 'detected'
                        CHECK(status IN ('detected','researching','ready','delivered','seen',
                                         'dismissed','blocked','expired','failed')),
                    channel                 TEXT,
                    synthesized_text        TEXT,
                    reason_line             TEXT,
                    sources_json            TEXT,
                    follow_ups_json         TEXT,
                    language                TEXT,
                    emotion                 TEXT,
                    error_code              TEXT,
                    detector_model          TEXT,
                    synth_model             TEXT,
                    latency_detect_ms       INTEGER,
                    latency_research_ms     INTEGER,
                    latency_synth_ms        INTEGER,
                    created_at              TEXT DEFAULT (datetime('now')),
                    ready_at                TEXT,
                    delivered_at            TEXT,
                    seen_at                 TEXT,
                    expires_at              TEXT
                , know_more_at TEXT, tokens_in INTEGER, tokens_out INTEGER);

CREATE TABLE proactive_topic_blocklist (
                    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    topic_hash  TEXT NOT NULL,
                    topic_label TEXT,
                    created_at  TEXT DEFAULT (datetime('now')),
                    PRIMARY KEY (user_id, topic_hash)
                );

CREATE TABLE proactive_user_settings (
                    user_id            TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                    enabled            INTEGER DEFAULT 0,
                    sensitivity        TEXT DEFAULT 'medium',
                    categories_json    TEXT DEFAULT '["event","news","product","place"]',
                    quiet_hours_json   TEXT,
                    onboarding_seen_at TEXT,
                    updated_at         TEXT DEFAULT (datetime('now'))
                );

CREATE TABLE project_files (
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

CREATE TABLE project_memory (
    id                   TEXT PRIMARY KEY,
    project_id           TEXT NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    summary_text         TEXT DEFAULT '',
    last_synthesized_at  TEXT,
    source_chat_ids      TEXT DEFAULT '[]'
);

CREATE TABLE projects (
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

CREATE TABLE providers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    base_url    TEXT NOT NULL,
    api_key     TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    is_free     INTEGER DEFAULT 0,
    is_local    INTEGER DEFAULT 0,
    share_admin_key INTEGER DEFAULT 0,  -- 1 = admin compartilha esta chave com outros usuários
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE sqlite_sequence(name,seq);

CREATE TABLE sync_log (
    id              TEXT PRIMARY KEY,
    provider_id     TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    synced_at       TEXT DEFAULT (datetime('now')),
    models_updated  INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'ok',
    error_msg       TEXT
);

CREATE TABLE user_api_keys (
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider_id TEXT NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    api_key     TEXT NOT NULL, account_id TEXT,
    PRIMARY KEY (user_id, provider_id)
);

CREATE TABLE user_memory (
    id             TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category       TEXT NOT NULL,
    fact           TEXT NOT NULL,
    fact_key       TEXT,
    is_active      INTEGER DEFAULT 1,
    is_pinned      INTEGER DEFAULT 0,
    status         TEXT DEFAULT 'active' CHECK(status IN ('active', 'merged', 'superseded', 'archived')),
    superseded_by_id TEXT REFERENCES user_memory(id) ON DELETE SET NULL,
    source_dream_id TEXT REFERENCES dream_logs(id) ON DELETE SET NULL,
    consolidated_at TEXT DEFAULT NULL,
    version        INTEGER DEFAULT 1,
    source_conv_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    confidence     REAL DEFAULT 1.0,
    embedding      BLOB,
    created_at     TEXT DEFAULT (datetime('now')),
    updated_at     TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE user_memory_fts USING fts5(
    fact,
    category,
    tokenize='unicode61 remove_diacritics 1',
    content='user_memory',
    content_rowid='rowid'
);

CREATE TABLE 'user_memory_fts_config'(k PRIMARY KEY, v) WITHOUT ROWID;

CREATE TABLE 'user_memory_fts_data'(id INTEGER PRIMARY KEY, block BLOB);

CREATE TABLE 'user_memory_fts_docsize'(id INTEGER PRIMARY KEY, sz BLOB);

CREATE TABLE 'user_memory_fts_idx'(segid, term, pgno, PRIMARY KEY(segid, term)) WITHOUT ROWID;

CREATE TABLE user_memory_summaries (
                        id          TEXT PRIMARY KEY,
                        user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        scope       TEXT NOT NULL CHECK(scope IN ('global', 'project', 'conversation')),
                        scope_ref   TEXT DEFAULT '',
                        summary_md  TEXT NOT NULL,
                        updated_at  TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, scope, scope_ref)
                    );

CREATE TABLE user_profiles (
                        user_id              TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                        display_name         TEXT DEFAULT '',
                        full_name            TEXT DEFAULT '',
                        occupation           TEXT DEFAULT '',
                        custom_instructions  TEXT DEFAULT '',
                        memory_enabled       INTEGER DEFAULT 1,
                        updated_at           TEXT DEFAULT (datetime('now'))
                    );

CREATE TABLE users (
    id            TEXT PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    email         TEXT UNIQUE,
    phone         TEXT,
    role          TEXT DEFAULT 'user',
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE vision_descriptions_cache (
    file_hash    TEXT PRIMARY KEY,
    description  TEXT NOT NULL,
    relay_model  TEXT NOT NULL,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE vision_relay_config (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    relay_provider_id   TEXT,
    relay_model_id      TEXT,
    relay_system_prompt TEXT DEFAULT 'Você é um sistema de descrição de imagens. Descreva a imagem em detalhes objetivos e completos: objetos, pessoas, texto visível (transcreva literalmente), cores, contexto da cena, e qualquer informação relevante. Seja exaustivo mas direto. Não faça julgamentos de valor. Não adicione introduções como "esta imagem mostra". Vá direto à descrição.',
    enabled             INTEGER DEFAULT 1,
    cache_descriptions  INTEGER DEFAULT 1
);

CREATE TABLE web_search_config (
    id                    INTEGER PRIMARY KEY DEFAULT 1,
    enabled               INTEGER DEFAULT 1,
    search_provider       TEXT DEFAULT 'duckduckgo',
    api_key               TEXT DEFAULT '',
    max_results           INTEGER DEFAULT 5,
    heuristic_enabled     INTEGER DEFAULT 0,
    heuristic_sensitivity TEXT DEFAULT 'medium',
    injection_template    TEXT DEFAULT 'Resultados de busca para "{query}":

{results}

--- Use essas informações para responder a pergunta do usuário.'
);

CREATE TABLE web_search_log (
    id             TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    message_id     TEXT,
    query          TEXT NOT NULL,
    trigger_type   TEXT NOT NULL,
    results_count  INTEGER,
    user_id        TEXT,
    created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TRIGGER user_memory_fts_ai AFTER INSERT ON user_memory BEGIN
    INSERT INTO user_memory_fts(rowid, fact, category) VALUES (new.rowid, new.fact, new.category);
END;

CREATE TRIGGER user_memory_fts_del AFTER DELETE ON user_memory BEGIN
    DELETE FROM user_memory_fts WHERE rowid=old.rowid;
END;

CREATE TRIGGER user_memory_fts_du AFTER UPDATE ON user_memory BEGIN
    UPDATE user_memory_fts SET fact=new.fact, category=new.category WHERE rowid=old.rowid;
END;