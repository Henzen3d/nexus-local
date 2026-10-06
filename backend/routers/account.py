from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from backend.auth import get_current_user
from backend.database import get_db

router = APIRouter(prefix="/api/me", tags=["me"])


class OwnProviderKey(BaseModel):
    api_key: str


@router.put("/providers/{provider_id}/key")
async def set_own_provider_key(
    provider_id: str,
    body: OwnProviderKey,
    current_user: dict = Depends(get_current_user),
):
    key = body.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="Chave vazia.")
    db = await get_db()
    try:
        async with db.execute("SELECT id FROM providers WHERE id = ?", (provider_id,)) as cur:
            if not await cur.fetchone():
                raise HTTPException(status_code=404, detail="Provedor não encontrado.")
        await db.execute(
            """INSERT INTO user_api_keys (user_id, provider_id, api_key)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id, provider_id) DO UPDATE SET api_key = excluded.api_key""",
            (current_user["id"], provider_id, key),
        )
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
