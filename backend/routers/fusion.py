from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from backend.database import get_db
from backend.auth import get_current_user, require_admin

router = APIRouter(prefix="/api/fusion", tags=["fusion"])

from backend.fusion.orchestrator import JUDGE_SYSTEM_PROMPT_DEFAULT as DEFAULT_JUDGE_PROMPT


class FusionModelOut(BaseModel):
    id: int
    provider_id: str
    model_id: str
    position: int


class FusionModelIn(BaseModel):
    provider_id: str
    model_id: str
    position: int = 0


class FusionJudgeIn(BaseModel):
    judge_provider_id: str
    judge_model_id: str
    judge_system_prompt: Optional[str] = None


class FusionConfigOut(BaseModel):
    judge_provider_id: str
    judge_model_id: str
    judge_system_prompt: str
    enabled: bool
    grounding_enabled: bool
    models: List[FusionModelOut]


class FusionConfigIn(BaseModel):
    judge_provider_id: Optional[str] = None
    judge_model_id: Optional[str] = None
    judge_system_prompt: Optional[str] = None
    enabled: Optional[bool] = None
    grounding_enabled: Optional[bool] = None
    models: Optional[List[FusionModelIn]] = None


async def _get_judge_config() -> dict:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT judge_provider_id, judge_model_id, judge_system_prompt, enabled, grounding_enabled "
            "FROM fusion_config WHERE id = 1"
        ) as cur:
            row = await cur.fetchone()
        if row:
            return {
                "judge_provider_id": row[0],
                "judge_model_id": row[1],
                "judge_system_prompt": row[2] or DEFAULT_JUDGE_PROMPT,
                "enabled": bool(row[3]),
                "grounding_enabled": bool(row[4]) if row[4] is not None else True,
            }
        return {
            "judge_provider_id": "",
            "judge_model_id": "",
            "judge_system_prompt": DEFAULT_JUDGE_PROMPT,
            "enabled": True,
            "grounding_enabled": True,
        }
    finally:
        await db.close()


async def _get_models() -> List[dict]:
    db = await get_db()
    try:
        async with db.execute(
            "SELECT id, provider_id, model_id, position FROM fusion_models ORDER BY position"
        ) as cur:
            rows = await cur.fetchall()
        return [
            {"id": r[0], "provider_id": r[1], "model_id": r[2], "position": r[3]}
            for r in rows
        ]
    finally:
        await db.close()


@router.get("/config", response_model=FusionConfigOut)
async def get_config(current_user: dict = Depends(get_current_user)):
    judge = await _get_judge_config()
    models = await _get_models()
    return {**judge, "models": models}


@router.post("/config", response_model=FusionConfigOut)
async def save_config(body: FusionConfigIn, current_user: dict = Depends(require_admin)):
    db = await get_db()
    try:
        current = await _get_judge_config()
        updates = {k: v for k, v in body.model_dump().items() if v is not None and k != "models"}
        merged = {**current, **updates}

        await db.execute(
            """INSERT INTO fusion_config (id, judge_provider_id, judge_model_id, judge_system_prompt, enabled, grounding_enabled)
               VALUES (1, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   judge_provider_id = excluded.judge_provider_id,
                   judge_model_id = excluded.judge_model_id,
                   judge_system_prompt = excluded.judge_system_prompt,
                   enabled = excluded.enabled,
                   grounding_enabled = excluded.grounding_enabled""",
            (
                merged["judge_provider_id"],
                merged["judge_model_id"],
                merged["judge_system_prompt"],
                1 if merged["enabled"] else 0,
                1 if merged["grounding_enabled"] else 0,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    if body.models is not None:
        db = await get_db()
        try:
            await db.execute("DELETE FROM fusion_models")
            for i, m in enumerate(body.models):
                await db.execute(
                    "INSERT INTO fusion_models (provider_id, model_id, position) VALUES (?, ?, ?)",
                    (m.provider_id, m.model_id, i),
                )
            await db.commit()
        finally:
            await db.close()

    judge = await _get_judge_config()
    models = await _get_models()
    return {**judge, "models": models}


@router.post("/judge", response_model=FusionConfigOut)
async def save_judge(body: FusionJudgeIn, current_user: dict = Depends(require_admin)):
    db = await get_db()
    try:
        current = await _get_judge_config()
        merged = {**current, **body.model_dump()}

        await db.execute(
            """INSERT INTO fusion_config (id, judge_provider_id, judge_model_id, judge_system_prompt, enabled)
               VALUES (1, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   judge_provider_id = excluded.judge_provider_id,
                   judge_model_id = excluded.judge_model_id,
                   judge_system_prompt = excluded.judge_system_prompt""",
            (
                merged["judge_provider_id"],
                merged["judge_model_id"],
                merged["judge_system_prompt"],
                1 if merged["enabled"] else 0,
            ),
        )
        await db.commit()
    finally:
        await db.close()

    judge = await _get_judge_config()
    models = await _get_models()
    return {**judge, "models": models}


@router.post("/models", response_model=FusionConfigOut)
async def add_model(body: FusionModelIn, current_user: dict = Depends(require_admin)):
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO fusion_models (provider_id, model_id, position)
               VALUES (?, ?, ?)
               ON CONFLICT(provider_id) DO UPDATE SET
                   model_id = excluded.model_id,
                   position = excluded.position""",
            (body.provider_id, body.model_id, body.position),
        )
        await db.commit()
    finally:
        await db.close()

    judge = await _get_judge_config()
    models = await _get_models()
    return {**judge, "models": models}


@router.delete("/models/{model_id}", response_model=FusionConfigOut)
async def remove_model(model_id: int, current_user: dict = Depends(require_admin)):
    db = await get_db()
    try:
        await db.execute("DELETE FROM fusion_models WHERE id = ?", (model_id,))
        await db.commit()
    finally:
        await db.close()

    judge = await _get_judge_config()
    models = await _get_models()
    return {**judge, "models": models}
