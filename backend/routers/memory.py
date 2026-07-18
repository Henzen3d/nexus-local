import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

from backend.auth import get_current_user
from backend.database import (
    get_db,
    get_user_memory,
    delete_memory_fact,
    clear_all_memory,
    get_user_profile,
    upsert_user_profile,
    get_memory_summary,
    list_memory_summaries,
    upsert_memory_summary,
    get_memory_stats,
    add_memory_fact,
    set_memory_fact_pinned,
    MEMORY_CATEGORIES,
)
from backend.memory import (
    build_memory_block,
    build_memory_fingerprint,
    refresh_memory_summaries,
    parse_external_memory_export,
    EXTERNAL_MEMORY_EXPORT_PROMPT,
)

from backend.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = None
    full_name: Optional[str] = None
    occupation: Optional[str] = None
    custom_instructions: Optional[str] = None
    memory_enabled: Optional[bool] = None


class ExtractorConfigIn(BaseModel):
    memory_extractor_provider_id: Optional[str] = None
    memory_extractor_model_id: Optional[str] = None
    memory_extractor_enabled: Optional[bool] = None
    memory_llm_summaries_enabled: Optional[bool] = None


class MemoryImportIn(BaseModel):
    """Phase D: import bundle (facts + optional profile + summaries)."""
    mode: Optional[str] = "merge"  # merge | replace
    profile: Optional[dict] = None
    facts: Optional[list] = None
    summaries: Optional[list] = None


class MemoryImportTextIn(BaseModel):
    """Import free-text export from Claude / ChatGPT / Gemini / etc."""
    text: str
    mode: Optional[str] = "merge"  # merge | replace
    merge_instructions_into_profile: Optional[bool] = True


class PinUpdate(BaseModel):
    pinned: bool


async def _meta_get(db, key: str) -> Optional[str]:
    async with db.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
        return row[0] if row else None


async def _meta_set(db, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def _get_extractor_config() -> dict:
    db = await get_db()
    try:
        provider = await _meta_get(db, "memory_extractor_provider_id")
        model = await _meta_get(db, "memory_extractor_model_id")
        enabled_raw = await _meta_get(db, "memory_extractor_enabled")
        enabled = True if enabled_raw is None else enabled_raw not in ("0", "false", "False", "no", "off")

        # Resolve which source the waterfall would use (for UI feedback)
        source = "chat_fallback"
        if provider and model:
            source = "memory_extractor"
        else:
            async with db.execute(
                "SELECT enhancer_provider_id, enhancer_model_id FROM enhancer_config WHERE id = 1"
            ) as cur:
                row = await cur.fetchone()
            if row and row[0] and row[1]:
                source = "enhancer"

        llm_sum_raw = await _meta_get(db, "memory_llm_summaries_enabled")
        llm_summaries = True if llm_sum_raw is None else llm_sum_raw not in ("0", "false", "False", "no", "off")

        return {
            "memory_extractor_provider_id": provider,
            "memory_extractor_model_id": model,
            "memory_extractor_enabled": enabled,
            "memory_llm_summaries_enabled": llm_summaries,
            "resolved_source": source,
        }
    finally:
        await db.close()


@router.get("")
async def get_memory(user: dict = Depends(get_current_user)):
    """Returns memory facts for the current user (for UI management; up to 500)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return await get_user_memory(user["id"], limit=500, active_only=False)


@router.get("/profile")
async def get_profile(user: dict = Depends(get_current_user)):
    """Server-side user profile (name, occupation, custom instructions, memory toggle)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return await get_user_profile(user["id"])


@router.put("/profile")
async def put_profile(body: ProfileUpdate, user: dict = Depends(get_current_user)):
    """Create or update server-side profile fields."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    mem = None
    if body.memory_enabled is not None:
        mem = 1 if body.memory_enabled else 0
    return await upsert_user_profile(
        user_id=user["id"],
        display_name=body.display_name,
        full_name=body.full_name,
        occupation=body.occupation,
        custom_instructions=body.custom_instructions,
        memory_enabled=mem,
    )


@router.get("/extractor-config")
async def get_extractor_config(user: dict = Depends(get_current_user)):
    """Cheap model used by the background memory extractor (admin waterfall settings)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return await _get_extractor_config()


@router.put("/extractor-config")
async def put_extractor_config(body: ExtractorConfigIn, user: dict = Depends(get_current_user)):
    """Save dedicated extractor provider/model (empty string clears → falls back to enhancer)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    db = await get_db()
    try:
        if body.memory_extractor_provider_id is not None:
            val = (body.memory_extractor_provider_id or "").strip()
            if val:
                await _meta_set(db, "memory_extractor_provider_id", val)
            else:
                await db.execute("DELETE FROM meta WHERE key = ?", ("memory_extractor_provider_id",))
        if body.memory_extractor_model_id is not None:
            val = (body.memory_extractor_model_id or "").strip()
            if val:
                await _meta_set(db, "memory_extractor_model_id", val)
            else:
                await db.execute("DELETE FROM meta WHERE key = ?", ("memory_extractor_model_id",))
        if body.memory_extractor_enabled is not None:
            await _meta_set(db, "memory_extractor_enabled", "1" if body.memory_extractor_enabled else "0")
        if body.memory_llm_summaries_enabled is not None:
            await _meta_set(
                db,
                "memory_llm_summaries_enabled",
                "1" if body.memory_llm_summaries_enabled else "0",
            )
        await db.commit()
        return await _get_extractor_config()
    finally:
        await db.close()


@router.get("/summaries")
async def get_summaries(user: dict = Depends(get_current_user), scope: Optional[str] = None):
    """List rolling memory summaries (global / project)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return await list_memory_summaries(user["id"], scope=scope)


@router.post("/summaries/refresh")
async def refresh_summaries(user: dict = Depends(get_current_user)):
    """Rebuild global (+ known project) summaries from current facts."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    await refresh_memory_summaries(user["id"], conversation_id=None)
    return await list_memory_summaries(user["id"])


@router.get("/preview")
async def preview_memory_block(user: dict = Depends(get_current_user)):
    """Returns the exact markdown block that would be injected in the next system prompt."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    profile = await get_user_profile(user["id"])
    mem_rows = []
    global_sum = None
    if profile.get("memory_enabled", 1):
        mem_rows = await get_user_memory(user["id"], active_only=True)
        global_sum = await get_memory_summary(user["id"], "global", "")
    summaries = [global_sum] if global_sum else []
    block = build_memory_block(
        mem_rows,
        profile=profile,
        global_summary=global_sum,
        project_summary=None,
    )
    return {
        "fact_count": len(mem_rows),
        "block": block,
        "block_chars": len(block),
        "fingerprint": build_memory_fingerprint(mem_rows, profile=profile, summaries=summaries),
        "profile": profile,
        "global_summary": global_sum,
    }


@router.get("/stats")
async def memory_stats(user: dict = Depends(get_current_user)):
    """Phase D: local metrics (fact counts, extractions today/total)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return await get_memory_stats(user["id"])


@router.get("/export")
async def export_memory(user: dict = Depends(get_current_user)):
    """Phase D: downloadable JSON bundle of profile + facts + summaries."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    profile = await get_user_profile(user["id"])
    # Export active facts only by default (full list for management uses limit high)
    facts = await get_user_memory(user["id"], limit=500, active_only=True)
    summaries = await list_memory_summaries(user["id"])
    from datetime import datetime, timezone

    return {
        "format": "nexuslocal-memory-v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user_id": user["id"],
        "profile": {
            "display_name": profile.get("display_name"),
            "full_name": profile.get("full_name"),
            "occupation": profile.get("occupation"),
            "custom_instructions": profile.get("custom_instructions"),
            "memory_enabled": profile.get("memory_enabled", 1),
        },
        "facts": [
            {
                "category": f.get("category"),
                "fact": f.get("fact"),
                "fact_key": f.get("fact_key"),
                "confidence": f.get("confidence"),
                "is_pinned": f.get("is_pinned"),
            }
            for f in facts
        ],
        "summaries": [
            {
                "scope": s.get("scope"),
                "scope_ref": s.get("scope_ref") or "",
                "summary_md": s.get("summary_md"),
            }
            for s in summaries
        ],
    }


@router.get("/import-prompt")
async def get_import_prompt(user: dict = Depends(get_current_user)):
    """
    Prompt pronto para colar em ChatGPT / Claude / Gemini / etc.
    e exportar memórias no formato que o NexusLocal importa.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    return {
        "prompt": EXTERNAL_MEMORY_EXPORT_PROMPT,
        "title": "Importar memória de outros provedores",
        "steps": [
            "Copie o prompt e cole em um chat com o outro provedor de IA.",
            "Cole a resposta abaixo (export com seções) para adicionar à memória do NexusLocal.",
        ],
    }


@router.post("/import")
async def import_memory(body: MemoryImportIn, user: dict = Depends(get_current_user)):
    """
    Phase D: import JSON bundle.
    mode=merge (default): upsert facts by fact_key / text.
    mode=replace: soft-clear active facts first, then import.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    mode = (body.mode or "merge").lower()
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="mode deve ser merge ou replace")

    if mode == "replace":
        await clear_all_memory(user["id"])

    imported_facts = 0
    for item in body.facts or []:
        if not isinstance(item, dict):
            continue
        fact = (item.get("fact") or "").strip()
        if not fact:
            continue
        cat = (item.get("category") or "preference").strip()
        if cat not in MEMORY_CATEGORIES:
            cat = "preference"
        key = item.get("fact_key")
        if key:
            key = str(key).strip().lower().replace(" ", "_")
        conf = float(item.get("confidence", 0.8) or 0.8)
        await add_memory_fact(
            user_id=user["id"],
            category=cat,
            fact=fact,
            fact_key=key or None,
            confidence=conf,
        )
        imported_facts += 1

    if body.profile and isinstance(body.profile, dict):
        p = body.profile
        mem = p.get("memory_enabled")
        mem_i = None
        if mem is not None:
            mem_i = 1 if mem in (True, 1, "1", "true") else 0
        await upsert_user_profile(
            user_id=user["id"],
            display_name=p.get("display_name"),
            full_name=p.get("full_name"),
            occupation=p.get("occupation"),
            custom_instructions=p.get("custom_instructions"),
            memory_enabled=mem_i,
        )

    imported_summaries = 0
    for s in body.summaries or []:
        if not isinstance(s, dict):
            continue
        scope = s.get("scope") or "global"
        if scope not in ("global", "project", "conversation"):
            continue
        md = (s.get("summary_md") or "").strip()
        if not md:
            continue
        await upsert_memory_summary(
            user["id"],
            scope,
            md,
            scope_ref=(s.get("scope_ref") or ""),
        )
        imported_summaries += 1

    if imported_facts and not (body.summaries):
        await refresh_memory_summaries(user["id"], conversation_id=None)

    return {
        "status": "ok",
        "mode": mode,
        "imported_facts": imported_facts,
        "imported_summaries": imported_summaries,
    }


@router.post("/import-text")
async def import_memory_text(body: MemoryImportTextIn, user: dict = Depends(get_current_user)):
    """
    Import free-text memory dump from another AI (Claude / ChatGPT / Gemini).
    Parses sections Instructions / Identity / Career / Projects / Preferences
    into structured user_memory facts (merge by default).
    """
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Cole o texto exportado da outra IA.")
    if len(text) > 200_000:
        raise HTTPException(status_code=400, detail="Texto de importação grande demais (máx. 200k caracteres).")

    mode = (body.mode or "merge").lower()
    if mode not in ("merge", "replace"):
        raise HTTPException(status_code=400, detail="mode deve ser merge ou replace")

    parsed = parse_external_memory_export(text)
    facts = parsed.get("facts") or []
    if not facts:
        raise HTTPException(
            status_code=400,
            detail=(
                "Não foi possível extrair entradas. Use o prompt de exportação e cole "
                "o bloco com seções Instructions / Identity / Career / Projects / Preferences."
            ),
        )

    if mode == "replace":
        await clear_all_memory(user["id"])

    imported_facts = 0
    for item in facts:
        fact = (item.get("fact") or "").strip()
        if not fact:
            continue
        cat = (item.get("category") or "preference").strip()
        if cat not in MEMORY_CATEGORIES:
            cat = "preference"
        key = item.get("fact_key")
        if key:
            key = str(key).strip().lower().replace(" ", "_")
        conf = float(item.get("confidence", 0.88) or 0.88)
        await add_memory_fact(
            user_id=user["id"],
            category=cat,
            fact=fact,
            fact_key=key or None,
            confidence=conf,
        )
        imported_facts += 1

    profile_updated = False
    try:
        existing = await get_user_profile(user["id"])
        hints = parsed.get("profile_hints") or {}
        old = (existing or {}).get("custom_instructions") or ""
        new_instr = old
        if body.merge_instructions_into_profile is not False and parsed.get("instructions_blob"):
            blob = parsed["instructions_blob"]
            marker = "<!-- imported-from-other-ai -->"
            if not (marker in old and blob in old):
                block = f"{marker}\n{blob}".strip()
                if old.strip():
                    if marker in old:
                        head = old.split(marker, 1)[0].rstrip()
                        new_instr = f"{head}\n\n{block}".strip() if head else block
                    else:
                        new_instr = f"{old.rstrip()}\n\n{block}".strip()
                else:
                    new_instr = block

        full_name = (hints.get("full_name") or "").strip() or None
        display_name = (hints.get("display_name") or "").strip() or None
        if display_name and display_name.startswith("*"):
            display_name = full_name.split()[0] if full_name else None
        # Occupation: prefer founder/company facts over job-search bullets
        occupation = None
        prof = [item for item in facts if item.get("category") == "professional"]
        prof_sorted = sorted(
            prof,
            key=lambda it: (
                0
                if re.search(
                    r"fundador|founder|fix\s*servi|empresa",
                    (it.get("fact") or ""),
                    re.I,
                )
                else 1,
                len(it.get("fact") or ""),
            ),
        )
        if prof_sorted:
            occupation = (prof_sorted[0].get("fact") or "")[:160]

        if (
            full_name
            or display_name
            or occupation
            or (new_instr and new_instr != old)
        ):
            await upsert_user_profile(
                user_id=user["id"],
                display_name=display_name or (full_name.split()[0] if full_name else None),
                full_name=full_name,
                occupation=occupation,
                custom_instructions=(new_instr[:8000] if new_instr != old else None),
            )
            profile_updated = True
    except Exception as e:
        logger.info("[Memory Import Text] profile merge: %s", e)

    if imported_facts:
        try:
            await refresh_memory_summaries(user["id"], conversation_id=None)
        except Exception as e:
            logger.info("[Memory Import Text] refresh summaries: %s", e)

    return {
        "status": "ok",
        "mode": mode,
        "imported_facts": imported_facts,
        "sections_found": parsed.get("sections_found") or [],
        "profile_instructions_updated": profile_updated,
    }

@router.patch("/{fact_id}/pin")
async def pin_fact(fact_id: str, body: PinUpdate, user: dict = Depends(get_current_user)):
    """Pin or unpin a memory fact (always injected when relevant)."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    ok = await set_memory_fact_pinned(user["id"], fact_id, body.pinned)
    if not ok:
        raise HTTPException(status_code=404, detail="Fato não encontrado.")
    return {"status": "ok", "id": fact_id, "is_pinned": body.pinned}


@router.delete("/{fact_id}")
async def delete_fact(fact_id: str, user: dict = Depends(get_current_user)):
    """Hard-deletes a single memory fact by its ID."""
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    reserved = {
        "profile", "preview", "clear", "extractor-config",
        "summaries", "export", "import", "import-text", "import-prompt", "stats",
    }
    if fact_id in reserved:
        raise HTTPException(status_code=400, detail="ID inválido")
    ok = await delete_memory_fact(fact_id, user_id=user["id"])
    if not ok:
        raise HTTPException(status_code=404, detail="Fato não encontrado.")
    return {"status": "ok", "message": "Fato removido da memória com sucesso."}


@router.post("/clear")
async def clear_memory(user: dict = Depends(get_current_user)):
    """
    Esquecer tudo: desativa todos os fatos ativos e apaga resumos rolling
    (global + projetos). Perfil manual (nome/instruções) é preservado.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Não autorizado")
    await clear_all_memory(user["id"])
    return {
        "status": "ok",
        "message": "Toda a memória adaptativa foi apagada (fatos e resumos rolling).",
    }
