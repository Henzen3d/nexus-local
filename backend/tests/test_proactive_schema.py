"""F2.1.7 — migrações do Assistente Proativo no banco temporário (conftest.py).

``init_db()`` duas vezes sem erro; tabelas, colunas, índices e chaves de
``meta`` presentes; ``proactive_user_settings.enabled`` default 0 (opt-in).
"""
from __future__ import annotations

import uuid

from backend.database import PROACTIVE_META_DEFAULTS, get_db, init_db


async def _columns(db, table: str) -> dict[str, dict]:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    # (cid, name, type, notnull, dflt_value, pk)
    return {r[1]: {"type": r[2], "notnull": r[3], "default": r[4], "pk": r[5]} for r in rows}


async def _indexes(db, table: str) -> set[str]:
    async with db.execute(f"PRAGMA index_list({table})") as cur:
        rows = await cur.fetchall()
    return {r[1] for r in rows}


async def test_init_db_is_idempotent_and_creates_proactive_schema():
    await init_db()
    await init_db()  # segunda passagem não pode falhar nem duplicar nada

    db = await get_db()
    try:
        insights = await _columns(db, "proactive_insights")
        for col in (
            "id", "user_id", "conversation_id", "source_message_id", "delivered_message_id",
            "spawned_conversation_id", "topic", "topic_hash", "entities_json", "category",
            "confidence", "query", "status", "channel", "synthesized_text", "reason_line",
            "sources_json", "follow_ups_json", "language", "emotion", "error_code",
            "detector_model", "synth_model", "latency_detect_ms", "latency_research_ms",
            "latency_synth_ms", "created_at", "ready_at", "delivered_at", "seen_at", "expires_at",
        ):
            assert col in insights, f"coluna ausente em proactive_insights: {col}"
        assert insights["status"]["default"] == "'detected'"

        settings = await _columns(db, "proactive_user_settings")
        assert settings["user_id"]["pk"] == 1
        assert settings["enabled"]["default"] == "0", "opt-in: enabled precisa nascer 0"
        assert settings["sensitivity"]["default"] == "'medium'"
        assert "categories_json" in settings and "quiet_hours_json" in settings
        assert "onboarding_seen_at" in settings
        assert "selected_pet" in settings and "pet_widget_enabled" in settings

        blocklist = await _columns(db, "proactive_topic_blocklist")
        assert {"user_id", "topic_hash", "topic_label", "created_at"} <= set(blocklist)
        assert blocklist["user_id"]["pk"] == 1 and blocklist["topic_hash"]["pk"] == 2

        memories = await _columns(db, "proactive_memories")
        assert {"id", "user_id", "topic_category", "topic_key", "signal_count", "accumulated_context", "status"} <= set(memories)

        bots = await _columns(db, "proactive_bots")
        assert {"id", "user_id", "name", "color_hex", "avatar_shape", "mascot_id", "ambient_enabled"} <= set(bots)

        routines = await _columns(db, "proactive_routines")
        assert {"id", "bot_id", "user_id", "name", "prompt", "timing_type", "timing_value", "is_active"} <= set(routines)

        messages = await _columns(db, "messages")
        assert messages["kind"]["default"] == "'normal'"
        assert "proactive_insight_id" in messages

        conversations = await _columns(db, "conversations")
        assert "origin_insight_id" in conversations

        assert {"idx_proactive_user_status", "idx_proactive_topic_recent", "idx_proactive_conv"} <= (
            await _indexes(db, "proactive_insights")
        )
        assert "idx_messages_kind_proactive" in await _indexes(db, "messages")
        assert "idx_proactive_memories_user_status" in await _indexes(db, "proactive_memories")
        assert "idx_proactive_bots_user" in await _indexes(db, "proactive_bots")
        assert "idx_proactive_routines_next" in await _indexes(db, "proactive_routines")

        async with db.execute("SELECT key, value FROM meta WHERE key LIKE 'proactive_%'") as cur:
            meta = dict(await cur.fetchall())
        for key, value in PROACTIVE_META_DEFAULTS.items():
            assert meta.get(key) == value, f"meta.{key} = {meta.get(key)!r}, esperado {value!r}"
        assert meta["proactive_enabled_global"] == "true"
    finally:
        await db.close()


async def test_meta_defaults_do_not_overwrite_admin_values():
    await init_db()
    db = await get_db()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES ('proactive_max_per_hour_conv', '1')"
        )
        await db.commit()
    finally:
        await db.close()

    await init_db()  # INSERT OR IGNORE: valor do admin preservado
    db = await get_db()
    try:
        async with db.execute("SELECT value FROM meta WHERE key = 'proactive_max_per_hour_conv'") as cur:
            row = await cur.fetchone()
        assert row[0] == "1"
        await db.execute("UPDATE meta SET value = '3' WHERE key = 'proactive_max_per_hour_conv'")
        await db.commit()
    finally:
        await db.close()


async def test_user_settings_row_defaults_to_opt_out_and_messages_kind_normal():
    await init_db()
    db = await get_db()
    try:
        user_id = f"u-{uuid.uuid4()}"
        await db.execute(
            "INSERT INTO users (id, username, password_hash, role) VALUES (?, ?, 'x', 'user')",
            (user_id, user_id),
        )
        await db.execute("INSERT INTO proactive_user_settings (user_id) VALUES (?)", (user_id,))
        conv_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO conversations (id, user_id, title) VALUES (?, ?, 'schema')", (conv_id, user_id)
        )
        msg_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) VALUES (?, ?, 'user', 'oi')",
            (msg_id, conv_id),
        )
        await db.commit()

        async with db.execute(
            "SELECT enabled, sensitivity, categories_json FROM proactive_user_settings WHERE user_id = ?",
            (user_id,),
        ) as cur:
            enabled, sensitivity, categories = await cur.fetchone()
        assert enabled == 0 and sensitivity == "medium"
        assert categories == '["event","news","product","place"]'

        async with db.execute("SELECT kind, proactive_insight_id FROM messages WHERE id = ?", (msg_id,)) as cur:
            kind, insight_id = await cur.fetchone()
        assert kind == "normal" and insight_id is None

        # CHECK de status: valor fora do enum é rejeitado
        import aiosqlite
        import pytest

        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                """INSERT INTO proactive_insights (id, user_id, conversation_id, topic, topic_hash, category, confidence, status)
                   VALUES (?, ?, ?, 't', 'h', 'event', 0.9, 'bogus')""",
                (str(uuid.uuid4()), user_id, conv_id),
            )
    finally:
        await db.close()
