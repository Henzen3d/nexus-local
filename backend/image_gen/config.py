from typing import Any, Dict, List, Optional
import aiosqlite


DEFAULT_CONFIG: Dict[str, Any] = {
    "id": 1,
    "enabled": False,
    "auto_detect": True,
    "provider_id": "cloudflare",
    "model_id": "cloudflare/flux-1-schnell",
    "steps": 4,
    "width": 1024,
    "height": 1024,
    "daily_cap_per_user": 20,
}


class ImageGenConfigObj:
    def __init__(self, data: Dict[str, Any]):
        self.id = 1
        self.enabled = bool(data.get("enabled", False))
        self.auto_detect = bool(data.get("auto_detect", True))
        self.provider_id = data.get("provider_id", "cloudflare")
        self.model_id = data.get("model_id", "cloudflare/flux-1-schnell")
        self.steps = int(data.get("steps", 4))
        self.width = int(data.get("width", 1024))
        self.height = int(data.get("height", 1024))
        self.daily_cap_per_user = int(data.get("daily_cap_per_user", 20))

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": 1,
            "enabled": self.enabled,
            "auto_detect": self.auto_detect,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "steps": self.steps,
            "width": self.width,
            "height": self.height,
            "daily_cap_per_user": self.daily_cap_per_user,
        }


async def get_image_gen_config(db: Optional[aiosqlite.Connection] = None) -> ImageGenConfigObj:
    """Carrega configuração singleton do módulo de imagem."""
    should_close = False
    if db is None:
        from backend.database import get_db
        db = await get_db()
        should_close = True

    try:
        async with db.execute(
            """SELECT enabled, auto_detect, provider_id, model_id, steps, width, height, daily_cap_per_user
               FROM image_gen_config WHERE id = 1"""
        ) as cur:
            row = await cur.fetchone()
            if row:
                return ImageGenConfigObj({
                    "enabled": bool(row[0]),
                    "auto_detect": bool(row[1]),
                    "provider_id": row[2] or "cloudflare",
                    "model_id": row[3] or "cloudflare/flux-1-schnell",
                    "steps": row[4] or 4,
                    "width": row[5] or 1024,
                    "height": row[6] or 1024,
                    "daily_cap_per_user": row[7] or 20,
                })
    except Exception:
        pass
    finally:
        if should_close:
            await db.close()

    return ImageGenConfigObj(DEFAULT_CONFIG)


async def update_image_gen_config(
    arg1: Any,
    arg2: Optional[Dict[str, Any]] = None,
) -> ImageGenConfigObj:
    """
    Atualiza a configuração singleton.
    Suporta:
      - update_image_gen_config(db, updates)
      - update_image_gen_config(updates)
    """
    if isinstance(arg1, dict):
        updates = arg1
        db = None
    else:
        db = arg1
        updates = arg2 or {}

    should_close = False
    if db is None:
        from backend.database import get_db
        db = await get_db()
        should_close = True

    try:
        current = await get_image_gen_config(db)
        new_data = current.to_dict()

        if "enabled" in updates:
            new_data["enabled"] = bool(updates["enabled"])
        if "auto_detect" in updates:
            new_data["auto_detect"] = bool(updates["auto_detect"])
        if "provider_id" in updates and updates["provider_id"]:
            new_data["provider_id"] = str(updates["provider_id"])
        if "model_id" in updates and updates["model_id"]:
            new_data["model_id"] = str(updates["model_id"])
        if "steps" in updates:
            new_data["steps"] = max(1, min(int(updates["steps"]), 8))
        if "width" in updates:
            new_data["width"] = int(updates["width"])
        if "height" in updates:
            new_data["height"] = int(updates["height"])
        if "daily_cap_per_user" in updates:
            new_data["daily_cap_per_user"] = max(1, int(updates["daily_cap_per_user"]))

        await db.execute(
            """INSERT INTO image_gen_config (id, enabled, auto_detect, provider_id, model_id, steps, width, height, daily_cap_per_user)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                   enabled = excluded.enabled,
                   auto_detect = excluded.auto_detect,
                   provider_id = excluded.provider_id,
                   model_id = excluded.model_id,
                   steps = excluded.steps,
                   width = excluded.width,
                   height = excluded.height,
                   daily_cap_per_user = excluded.daily_cap_per_user""",
            (
                1 if new_data["enabled"] else 0,
                1 if new_data["auto_detect"] else 0,
                new_data["provider_id"],
                new_data["model_id"],
                new_data["steps"],
                new_data["width"],
                new_data["height"],
                new_data["daily_cap_per_user"],
            ),
        )
        await db.commit()
        return ImageGenConfigObj(new_data)
    finally:
        if should_close:
            await db.close()


async def list_image_models(db: Optional[aiosqlite.Connection] = None) -> List[Dict[str, Any]]:
    """Lista modelos de imagem cadastrados."""
    should_close = False
    if db is None:
        from backend.database import get_db
        db = await get_db()
        should_close = True

    try:
        async with db.execute(
            """SELECT id, provider_id, name, display_name, notes, enabled
               FROM image_models ORDER BY id ASC"""
        ) as cur:
            rows = await cur.fetchall()
            return [
                {
                    "id": r[0],
                    "model_id": r[0],
                    "provider_id": r[1],
                    "name": r[2],
                    "display_name": r[3],
                    "notes": r[4],
                    "enabled": bool(r[5]),
                }
                for r in rows
            ]
    except Exception:
        return []
    finally:
        if should_close:
            await db.close()
