from fastapi import APIRouter, HTTPException, Depends
import httpx
import re
import uuid
from backend.database import get_db
from backend.models import ProviderUpdate, ModelToggle, ModelUpdate, FreeRegistryConfigUpdate
from backend.providers.model_fetcher import ModelFetcher
from backend.auth import get_current_user
from backend.free_registry.sync import sync_free_registry

router = APIRouter(prefix="/api/admin", tags=["admin"])


def derive_display_name(model_id: str) -> str:
    # Remove provider prefix if it exists in the model ID (e.g., "meta-llama/Llama-3...")
    parts = model_id.split("/")
    name = parts[-1]
    
    # Replace dashes/underscores with spaces
    name = name.replace("-", " ").replace("_", " ")
    
    # Title Case words
    words = name.split()
    # Keep acronyms uppercase, capitalize others
    formatted_words = []
    for w in words:
        if w.lower() in ["ai", "r1", "v3", "v4", "gpt", "nim", "qwen", "gemini", "llama", "coder"]:
            formatted_words.append(w.upper())
        else:
            formatted_words.append(w.capitalize())
            
    return " ".join(formatted_words)


async def sync_provider_models(provider_id: str, db, custom_api_key: str = None) -> dict:
    async with db.execute(
        "SELECT base_url, api_key, enabled FROM providers WHERE id = ?", (provider_id,)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        return {"updated": 0, "skipped": 0, "errors": [f"Provider {provider_id} nao encontrado"]}
    base_url, global_api_key, enabled = row
    
    api_key = custom_api_key if custom_api_key else global_api_key
    if not api_key and provider_id != "ollama":
        return {"updated": 0, "skipped": 0, "errors": ["Chave de API nao configurada"]}

    # 1. Fetch models from provider
    models_fetched = []
    error_msg = None
    try:
        if provider_id == "groq":
            models_fetched = await ModelFetcher.fetch_groq(api_key)
        elif provider_id == "openrouter":
            models_fetched = await ModelFetcher.fetch_openrouter(api_key)
        elif provider_id == "gemini":
            models_fetched = await ModelFetcher.fetch_gemini(api_key)
        elif provider_id == "cerebras":
            models_fetched = await ModelFetcher.fetch_cerebras(api_key)
        elif provider_id == "sambanova":
            models_fetched = await ModelFetcher.fetch_sambanova(api_key)
        elif provider_id == "cloudflare":
            account_id = "{account_id}"
            match = re.search(r"/accounts/([^/]+)/ai", base_url)
            if match and match.group(1) != "{account_id}":
                account_id = match.group(1)
            else:
                raise Exception("Cloudflare Account ID nao configurado na URL base")
            models_fetched = await ModelFetcher.fetch_cloudflare(account_id, api_key)
        elif provider_id == "ollama":
            models_fetched = await ModelFetcher.fetch_ollama(base_url, api_key)
        else:
            # generic openai compat provider
            models_fetched = await ModelFetcher.fetch_generic(base_url, api_key)
    except Exception as e:
        error_msg = str(e)

    # 2. Write to sync_log
    log_id = str(uuid.uuid4())
    status_str = "error" if error_msg else "ok"
    
    if error_msg:
        await db.execute(
            """INSERT INTO sync_log (id, provider_id, synced_at, models_updated, status, error_msg)
               VALUES (?, ?, datetime('now'), 0, ?, ?)""",
            (log_id, provider_id, status_str, error_msg)
        )
        await db.commit()
        return {"updated": 0, "skipped": 0, "errors": [error_msg]}

    # 3. Update database models
    updated_count = 0
    skipped_count = 0
    synced_ids = []

    # Load context registry for fallback values
    registry_models = {}
    try:
        from pathlib import Path
        import json
        registry_path = Path(__file__).parent.parent / "data" / "context_registry.json"
        if registry_path.exists():
            with open(registry_path, "r", encoding="utf-8") as f:
                registry_data = json.load(f)
                registry_models = registry_data.get("models", {})
    except Exception as e:
        print(f"Error loading context registry during sync: {e}")

    for item in models_fetched:
        model_name = item["model_name"]
        context_length = item["context_length"]
        
        # Override with registry context if it contains a larger value
        reg_ctx = None
        if model_name in registry_models:
            reg_ctx = registry_models[model_name].get("context_length")
        elif model_name.split('/')[-1] in registry_models:
            reg_ctx = registry_models[model_name.split('/')[-1]].get("context_length")
        else:
            # Fallback heuristics for common model name patterns
            name_lower = model_name.lower()
            if "deepseek" in name_lower:
                if any(x in name_lower for x in ["r1", "v3", "v4"]):
                    reg_ctx = 131072
                else:
                    reg_ctx = 64000
            elif "qwen" in name_lower:
                if any(x in name_lower for x in ["qwen3", "qwen2.5"]):
                    reg_ctx = 131072
                else:
                    reg_ctx = 32768
            elif "llama-3" in name_lower or "llama-4" in name_lower:
                reg_ctx = 131072
            
        if reg_ctx and reg_ctx > context_length:
            context_length = reg_ctx
            
        db_model_id = f"{provider_id}/{model_name}"
        synced_ids.append(db_model_id)

        # Check if the model is overridden
        async with db.execute("SELECT 1 FROM model_overrides WHERE model_id = ?", (db_model_id,)) as cur:
            is_overridden = await cur.fetchone() is not None

        if is_overridden:
            skipped_count += 1
            continue

        # Get existing model details to see if context changed
        async with db.execute("SELECT context_length, context_source, enabled, confirmed_free FROM models WHERE id = ?", (db_model_id,)) as cur:
            existing = await cur.fetchone()

        if existing:
            old_ctx, old_source, old_enabled, old_confirmed_free = existing
            if old_ctx != context_length or old_source != 'api':
                await db.execute(
                    "UPDATE models SET context_length = ?, context_source = 'api' WHERE id = ?",
                    (context_length, db_model_id)
                )
                updated_count += 1
            else:
                skipped_count += 1
        else:
            # Insert new model!
            display_name = derive_display_name(model_name)
            await db.execute(
                """INSERT INTO models (id, provider_id, name, display_name, context_length, context_source, enabled, confirmed_free)
                   VALUES (?, ?, ?, ?, ?, 'api', 0, 0)""",
                (db_model_id, provider_id, model_name, display_name, context_length)
            )
            updated_count += 1

    # Disables models that are NOT returned by the API (excluding overridden ones)
    if synced_ids:
        placeholders = ",".join("?" for _ in synced_ids)
        await db.execute(
            f"""UPDATE models 
               SET enabled = 0 
               WHERE provider_id = ? 
                 AND id NOT IN ({placeholders}) 
                 AND id NOT IN (SELECT model_id FROM model_overrides)""",
            [provider_id] + synced_ids,
        )

    # Record sync log success
    await db.execute(
        """INSERT INTO sync_log (id, provider_id, synced_at, models_updated, status)
           VALUES (?, ?, datetime('now'), ?, ?)""",
        (log_id, provider_id, updated_count, status_str)
    )
    # Update last sync time in meta table
    import datetime as _dt
    await db.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        (f"last_sync_{provider_id}", _dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    )

    # Auto-seed model_rankings for missing models
    import random
    from backend.ranking.scorer import compute_all_scores, persist_scores
    async with db.execute("SELECT id FROM models WHERE id NOT IN (SELECT model_id FROM model_rankings)") as cur:
        missing_models = await cur.fetchall()
    
    if missing_models:
        for (m_id,) in missing_models:
            q_score = random.uniform(60, 99)
            p_rank = random.randint(1, 100)
            await db.execute(
                "INSERT INTO model_rankings (model_id, quality_score, popularity_rank, source) VALUES (?, ?, ?, 'auto-seed')",
                (m_id, q_score, p_rank)
            )
        # Recalculate scores
        scored_models = await compute_all_scores(db)
        await persist_scores(db, scored_models)

    # Executa o matching do registry para auto-habilitar modelos recém-sincronizados que sejam confirmados como free
    from backend.free_registry.matcher import match_registry_to_models
    await match_registry_to_models(db)

    await db.commit()
    return {"updated": updated_count, "skipped": skipped_count, "errors": []}



@router.get("/providers")
async def list_providers(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute(
            """SELECT p.id, p.name, p.base_url, k.api_key IS NOT NULL as has_key, p.enabled, p.is_free,
                      COALESCE(k.api_key, p.api_key) as active_key
               FROM providers p
               LEFT JOIN user_api_keys k ON k.provider_id = p.id AND k.user_id = ?
               WHERE p.id != 'free_registry'
               ORDER BY p.name""",
            (current_user["id"],),
        ) as cur:
            providers = await cur.fetchall()

        result = []
        for p in providers:
            pid = p[0]
            active_key = p[6] or ""
            
            # Mask API Key
            masked_key = ""
            if active_key:
                if len(active_key) <= 8:
                    masked_key = "***"
                else:
                    masked_key = f"{active_key[:6]}...{active_key[-4:]}"

            async with db.execute(
                "SELECT id, display_name, enabled, context_length, context_source, confirmed_free FROM models WHERE provider_id = ? ORDER BY display_name",
                (pid,),
            ) as cur:
                models = await cur.fetchall()
            result.append({
                "id": pid,
                "name": p[1],
                "base_url": p[2],
                "has_key": bool(p[3]),
                "enabled": bool(p[4]),
                "is_free": bool(p[5]),
                "masked_key": masked_key,
                "models": [
                    {
                        "id": m[0], 
                        "display_name": m[1], 
                        "enabled": bool(m[2]), 
                        "context_length": m[3],
                        "context_source": m[4],
                        "confirmed_free": bool(m[5])
                    }
                    for m in models
                ],
            })
        return result
    finally:
        await db.close()


@router.get("/models")
async def list_all_models(current_user: dict = Depends(get_current_user)):
    """Returns only enabled models from enabled providers (for chat selector).
    Includes ranking data (nexuslocal_score, popularity_rank, quality_score) and quota_status.
    """
    db = await get_db()
    try:
        # Pega a config de hide_unconfirmed
        async with db.execute("SELECT value FROM meta WHERE key = 'free_registry_hide_unconfirmed'") as cur:
            row = await cur.fetchone()
            hide_unconfirmed = row[0] == "true" if row else True

        async with db.execute(
            """SELECT m.id, m.display_name, m.context_length,
                      p.id as provider_id, p.name as provider_name,
                      r.nexuslocal_score, r.popularity_rank, r.quality_score,
                      COALESCE(q.status, 'available') as quota_status,
                      COALESCE((SELECT COUNT(*) FROM model_usage_log WHERE model_id = m.id), 0) as internal_usage_count,
                      q.known_rpm, q.known_rpd, q.current_minute_count, q.current_day_count,
                      m.confirmed_free, p.is_free
               FROM models m
               JOIN providers p ON p.id = m.provider_id
               LEFT JOIN user_api_keys k ON k.provider_id = p.id AND k.user_id = ?
               LEFT JOIN model_rankings r ON r.model_id = m.id
               LEFT JOIN model_quota_status q ON q.model_id = m.id
               WHERE m.enabled = 1 AND p.enabled = 1 AND (
                   (k.api_key IS NOT NULL AND k.api_key != '') OR 
                   (p.api_key IS NOT NULL AND p.api_key != '') OR 
                   p.id = 'ollama'
               )
               ORDER BY COALESCE(r.nexuslocal_score, -1) DESC, p.name, m.display_name""",
            (current_user["id"],),
        ) as cur:
            rows = await cur.fetchall()
            
        result = []
        for r in rows:
            confirmed_free = bool(r[14])
            is_free_provider = bool(r[15])
            
            # Se for um provedor free e hide_unconfirmed estiver ativo, filtra os não confirmados
            if hide_unconfirmed and is_free_provider and not confirmed_free:
                continue
                
            result.append({
                "id": r[0], "display_name": r[1], "context_length": r[2],
                "provider_id": r[3], "provider_name": r[4],
                "nexuslocal_score": r[5],
                "popularity_rank": r[6],
                "quality_score": r[7],
                "quota_status": r[8],
                "internal_usage_count": r[9],
                "known_rpm": r[10],
                "known_rpd": r[11],
                "current_minute_count": r[12],
                "current_day_count": r[13],
            })
        return result
    finally:
        await db.close()



@router.patch("/providers/{provider_id}")
async def update_provider(provider_id: str, body: ProviderUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        should_sync = False
        if body.base_url is not None:
            await db.execute(
                "UPDATE providers SET base_url = ? WHERE id = ?",
                (body.base_url, provider_id),
            )
        if body.api_key is not None:
            # Insere ou atualiza na tabela user_api_keys
            await db.execute(
                """INSERT INTO user_api_keys (user_id, provider_id, api_key)
                   VALUES (?, ?, ?)
                   ON CONFLICT(user_id, provider_id) DO UPDATE SET api_key = excluded.api_key""",
                (current_user["id"], provider_id, body.api_key.strip()),
            )
            should_sync = True
        if body.enabled is not None:
            await db.execute(
                "UPDATE providers SET enabled = ? WHERE id = ?",
                (1 if body.enabled else 0, provider_id),
            )
        await db.commit()

        if should_sync and body.api_key is not None:
            await sync_provider_models(provider_id, db, custom_api_key=body.api_key.strip())
        return {"ok": True}
    finally:
        await db.close()


@router.patch("/models/{model_id:path}")
async def toggle_model(model_id: str, body: ModelUpdate):
    db = await get_db()
    try:
        if body.enabled is not None:
            await db.execute(
                "UPDATE models SET enabled = ? WHERE id = ?",
                (1 if body.enabled else 0, model_id),
            )
        if body.context_length is not None:
            await db.execute(
                """INSERT INTO model_overrides (model_id, context_length)
                   VALUES (?, ?)
                   ON CONFLICT(model_id) DO UPDATE SET context_length=excluded.context_length, set_at=datetime('now')""",
                (model_id, body.context_length),
            )
            await db.execute(
                "UPDATE models SET context_length = ?, context_source = 'user' WHERE id = ?",
                (body.context_length, model_id),
            )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@router.post("/models/{model_id:path}/confirm-free")
async def confirm_model_free(model_id: str):
    db = await get_db()
    try:
        # Update models table
        await db.execute(
            "UPDATE models SET confirmed_free = 1 WHERE id = ?",
            (model_id,)
        )
        # Update or insert into model_quota_status
        await db.execute(
            """INSERT INTO model_quota_status (model_id, registry_source, confirmed_free) 
               VALUES (?, 'manual', 1)
               ON CONFLICT(model_id) DO UPDATE SET registry_source = 'manual', confirmed_free = 1""",
            (model_id,)
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()


@router.post("/providers/{provider_id}/models/toggle")
async def toggle_all_provider_models(provider_id: str, body: ModelToggle):
    db = await get_db()
    try:
        await db.execute(
            "UPDATE models SET enabled = ? WHERE provider_id = ?",
            (1 if body.enabled else 0, provider_id),
        )
        await db.commit()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await db.close()


@router.post("/providers/sync")
async def sync_all_providers(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        # Pega todos os providers ativos
        async with db.execute(
            "SELECT id FROM providers WHERE enabled = 1"
        ) as cur:
            providers = await cur.fetchall()
            
        for p in providers:
            pid = p[0]
            # Tenta ler a chave do usuário para esse provider
            async with db.execute(
                "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = ?",
                (current_user["id"], pid),
            ) as key_cur:
                key_row = await key_cur.fetchone()
            
            api_key = key_row[0] if key_row else None
            if api_key:
                await sync_provider_models(pid, db, custom_api_key=api_key)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await db.close()


@router.post("/providers/{provider_id}/sync")
async def sync_provider(provider_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = ?",
            (current_user["id"], provider_id),
        ) as cur:
            row = await cur.fetchone()
        
        api_key = row[0] if row else None
        await sync_provider_models(provider_id, db, custom_api_key=api_key)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await db.close()


@router.post("/providers/{provider_id}/sync-models")
async def sync_models_endpoint(provider_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute(
            "SELECT api_key FROM user_api_keys WHERE user_id = ? AND provider_id = ?",
            (current_user["id"], provider_id),
        ) as cur:
            row = await cur.fetchone()
            
        api_key = row[0] if row else None
        res = await sync_provider_models(provider_id, db, custom_api_key=api_key)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await db.close()


@router.get("/free-registry/config")
async def get_free_registry_config(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        # Padrões se não existirem
        config = {
            "last_updated": None,
            "threshold": 85,
            "hide_unconfirmed": True
        }
        async with db.execute("SELECT key, value FROM meta WHERE key IN ('free_registry_last_updated', 'free_registry_threshold', 'free_registry_hide_unconfirmed')") as cur:
            rows = await cur.fetchall()
            for r in rows:
                if r[0] == "free_registry_last_updated":
                    config["last_updated"] = r[1]
                elif r[0] == "free_registry_threshold":
                    config["threshold"] = int(r[1])
                elif r[0] == "free_registry_hide_unconfirmed":
                    config["hide_unconfirmed"] = r[1] == "true"
        return config
    finally:
        await db.close()

@router.patch("/free-registry/config")
async def update_free_registry_config(body: FreeRegistryConfigUpdate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        if body.threshold is not None:
            await db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('free_registry_threshold', ?)",
                (str(body.threshold),)
            )
        if body.hide_unconfirmed is not None:
            await db.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES ('free_registry_hide_unconfirmed', ?)",
                ("true" if body.hide_unconfirmed else "false",)
            )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()

@router.post("/free-registry/sync")
async def trigger_free_registry_sync(current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        res = await sync_free_registry(db)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        await db.close()

# ── Gerenciamento de Usuários (Apenas Admin) ──────────────────────────
@router.get("/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
        
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, username, email, phone, role, created_at FROM users ORDER BY username"
        ) as cur:
            rows = await cur.fetchall()
        return [
            {
                "id": r[0],
                "username": r[1],
                "email": r[2],
                "phone": r[3],
                "role": r[4],
                "created_at": r[5]
            }
            for r in rows
        ]
    finally:
        await db.close()


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores.")
        
    if current_user["id"] == user_id:
        raise HTTPException(status_code=400, detail="Você não pode excluir a sua própria conta de administrador.")

    db = await get_db()
    try:
        # Verifica se o usuário existe
        async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        # Deleta o usuário (conversas e chaves são deletadas via ON DELETE CASCADE no SQLite)
        await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
