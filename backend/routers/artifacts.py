import uuid
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from backend.database import get_db
from backend.models import ArtifactCreate
from backend.auth import get_current_user

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

# Campos retornados em todas as queries de artifact (prefixado com alias 'a')
_ARTIFACT_COLS = "a.id, a.conv_id, a.msg_id, a.type, a.title, a.content, a.version, a.artifact_group_id, a.created_at, a.visibility, a.view_count, a.thumbnail"


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "conv_id": row[1],
        "msg_id": row[2],
        "type": row[3],
        "title": row[4],
        "content": row[5],
        "version": row[6],
        "artifact_group_id": row[7],
        "created_at": row[8],
        "visibility": row[9] if len(row) > 9 and row[9] is not None else "Privado",
        "view_count": row[10] if len(row) > 10 and row[10] is not None else 0,
        "thumbnail": row[11] if len(row) > 11 else None,
    }


# ── GET /api/artifacts — lista todos os artifacts do usuário ─────────────────
@router.get("")
async def list_all_user_artifacts(search: Optional[str] = None, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        query_cols = "id, conv_id, msg_id, type, title, content, version, artifact_group_id, created_at, visibility, view_count, thumbnail"
        query = f"""
            WITH ranked AS (
                SELECT a.id, a.conv_id, a.msg_id, a.type, a.title, a.content, a.version, a.artifact_group_id, a.created_at,
                       a.visibility, a.view_count, a.thumbnail,
                       ROW_NUMBER() OVER (PARTITION BY a.artifact_group_id ORDER BY a.version DESC) as rn
                FROM artifacts a
                JOIN conversations c ON c.id = a.conv_id
                WHERE c.user_id = ?
                { "AND a.title LIKE ?" if search else "" }
            )
            SELECT {query_cols}
            FROM ranked
            WHERE rn = 1
            ORDER BY created_at DESC
        """
        params = [current_user["id"]]
        if search:
            params.append(f"%{search}%")

        async with db.execute(query, params) as cur:
            rows = await cur.fetchall()
            
        return [
            {
                "id": r[0],
                "conv_id": r[1],
                "msg_id": r[2],
                "type": r[3],
                "title": r[4],
                "content": r[5],
                "version": r[6],
                "artifact_group_id": r[7],
                "created_at": r[8],
                "visibility": r[9] or "Privado",
                "view_count": r[10] or 0,
                "thumbnail": r[11]
            }
            for r in rows
        ]
    finally:
        await db.close()


async def _get_artifact_by_id_and_user(db, artifact_id: str, user_id: str):
    async with db.execute(
        f"""SELECT {_ARTIFACT_COLS} 
           FROM artifacts a
           JOIN conversations c ON c.id = a.conv_id
           WHERE a.id = ? AND c.user_id = ?""",
        (artifact_id, user_id)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


# ── GET /api/artifacts/{conv_id} — lista artifacts de uma conversa ────────────
@router.get("/{conv_id}")
async def list_artifacts(conv_id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        async with db.execute(
            f"""SELECT {_ARTIFACT_COLS} 
               FROM artifacts a
               JOIN conversations c ON c.id = a.conv_id
               WHERE a.conv_id = ? AND c.user_id = ?
               ORDER BY a.created_at DESC""",
            (conv_id, current_user["id"])
        ) as cur:
            rows = await cur.fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        await db.close()


# ── GET /api/artifacts/item/{id} — retorna um artifact específico ─────────────
@router.get("/item/{id}")
async def get_artifact(id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        artifact = await _get_artifact_by_id_and_user(db, id, current_user["id"])
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact não encontrado ou acesso não autorizado.")
        return artifact
    finally:
        await db.close()


# ── GET /api/artifacts/history/{group_id} — todas as versões de um grupo ─────
@router.get("/history/{group_id}")
async def get_artifact_history(group_id: str, current_user: dict = Depends(get_current_user)):
    """
    Retorna todas as versões de um artifact lógico (identificado pelo group_id),
    em ordem crescente de versão.
    """
    db = await get_db()
    try:
        async with db.execute(
            f"""SELECT {_ARTIFACT_COLS} 
               FROM artifacts a
               JOIN conversations c ON c.id = a.conv_id
               WHERE a.artifact_group_id = ? AND c.user_id = ?
               ORDER BY a.version ASC""",
            (group_id, current_user["id"])
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            raise HTTPException(status_code=404, detail="Grupo de artifact não encontrado ou acesso não autorizado.")
        return [_row_to_dict(r) for r in rows]
    finally:
        await db.close()


# ── POST /api/artifacts — cria novo artifact (uso manual/testes) ──────────────
@router.post("")
async def create_artifact(body: ArtifactCreate, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        # Verifica se o usuário é dono da conversa correspondente
        async with db.execute("SELECT user_id FROM conversations WHERE id = ?", (body.conv_id,)) as cur:
            row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conversa não encontrada.")
        if row[0] != current_user["id"]:
            raise HTTPException(status_code=403, detail="Não autorizado a criar artifacts para esta conversa.")

        artifact_id = body.id or str(uuid.uuid4())
        group_id = body.artifact_group_id or str(uuid.uuid4())
        await db.execute(
            """INSERT INTO artifacts (id, conv_id, msg_id, type, title, content, version, artifact_group_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                artifact_id,
                body.conv_id,
                body.msg_id,
                body.type,
                body.title,
                body.content,
                body.version or 1,
                group_id,
            )
        )
        await db.commit()

        artifact = await _get_artifact_by_id_and_user(db, artifact_id, current_user["id"])
        if not artifact:
            raise HTTPException(status_code=500, detail="Erro ao recuperar artifact criado.")
        return artifact
    finally:
        await db.close()


# ── DELETE /api/artifacts/{id} — remove um artifact ──────────────────────────
@router.delete("/{id}")
async def delete_artifact(id: str, current_user: dict = Depends(get_current_user)):
    db = await get_db()
    try:
        artifact = await _get_artifact_by_id_and_user(db, id, current_user["id"])
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact não encontrado ou acesso não autorizado.")

        await db.execute("DELETE FROM artifacts WHERE id = ?", (id,))
        await db.commit()
        return {"ok": True}
    finally:
        await db.close()
