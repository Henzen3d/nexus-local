import uuid
import hashlib
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from backend.database import get_db
from backend.auth import get_current_user
from backend.attachments import validate_attachment, save_file, extract_text, get_absolute_path

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

@router.post("/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    model_id: str = Form(...),
    current_user: dict = Depends(get_current_user)
):
    db = await get_db()
    try:
        # Read file contents
        contents = await file.read()
        size_bytes = len(contents)
        
        # We need a peek of content for MIME detection
        peek = contents[:2048]
        
        # Validate file
        validation = validate_attachment(file.filename, size_bytes, peek)
        if not validation.ok:
            raise HTTPException(status_code=400, detail=validation.error_message)
            
        # Detect category based on mime type
        mime_type = validation.mime_type
        is_image = mime_type.startswith("image/")
        category = "image" if is_image else "document"
        
        # Generate hash of contents
        file_hash = hashlib.sha256(contents).hexdigest()
        
        # Generate random ID
        attachment_id = f"att_{uuid.uuid4().hex}"
        
        # Save file to disk
        storage_rel, thumb_rel = save_file(contents, file.filename, attachment_id, is_image)
        abs_path = get_absolute_path(storage_rel)
        
        extracted_text = None
        if category == "document":
            try:
                extracted_text = await extract_text(
                    str(abs_path),
                    mime_type,
                    file_hash=file_hash,
                    user_id=current_user.get("id"),
                )
            except Exception as e:
                # If extraction fails (e.g. scanned PDF), cleanup file and return error
                if abs_path.exists():
                    abs_path.unlink()
                raise HTTPException(status_code=400, detail=f"Falha ao extrair texto do documento: {str(e)}")

        # Save record in db
        await db.execute(
            """INSERT INTO attachments (id, message_id, filename, mime_type, file_type, size_bytes, file_hash, extracted_text, storage_path, thumbnail_path)
               VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                attachment_id,
                file.filename,
                mime_type,
                category,
                size_bytes,
                file_hash,
                extracted_text,
                storage_rel,
                thumb_rel
            )
        )
        await db.commit()
        
        # Clean extracted text preview for response
        preview_text = None
        if extracted_text:
            preview_text = extracted_text[:200] + ("..." if len(extracted_text) > 200 else "")

        return {
            "id": attachment_id,
            "attachment_id": attachment_id,  # legacy alias
            "file_type": category,
            "filename": file.filename,
            "mime_type": mime_type,
            "size_bytes": size_bytes,
            "extracted_text_preview": preview_text,
            "thumbnail_url": f"/attachments/{thumb_rel}" if thumb_rel else None,
            "file_url": f"/attachments/{storage_rel}"
        }
    finally:
        await db.close()


@router.get("/library")
async def list_library_items(
    filter_type: str = "all",
    search: str = "",
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(get_current_user),
):
    """Lista todos os arquivos e imagens do usuário (gerados por IA ou anexados)."""
    user_id = current_user["id"]
    db = await get_db()
    try:
        query = """
            SELECT 
                a.id,
                a.message_id,
                a.filename,
                a.mime_type,
                a.file_type,
                a.size_bytes,
                a.storage_path,
                a.thumbnail_path,
                a.created_at,
                m.conversation_id,
                COALESCE(c.title, 'Sem título') AS conversation_title,
                t.prompt,
                t.model_id AS gen_model_id,
                CASE WHEN (t.id IS NOT NULL OR a.filename = 'image.jpg') THEN 1 ELSE 0 END AS is_generated
            FROM attachments a
            LEFT JOIN messages m ON a.message_id = m.id
            LEFT JOIN conversations c ON m.conversation_id = c.id
            LEFT JOIN image_gen_tasks t ON (t.attachment_id = a.id OR (a.message_id IS NOT NULL AND t.message_id = a.message_id))
            WHERE (c.user_id = ? OR t.user_id = ?)
        """
        params = [user_id, user_id]

        if filter_type == "generated":
            query += " AND (t.id IS NOT NULL OR a.filename = 'image.jpg')"
        elif filter_type == "image":
            query += " AND a.file_type = 'image'"
        elif filter_type == "document":
            query += " AND a.file_type = 'document'"

        if search and search.strip():
            term = f"%{search.strip()}%"
            query += " AND (a.filename LIKE ? OR t.prompt LIKE ? OR c.title LIKE ?)"
            params.extend([term, term, term])

        query += " ORDER BY a.created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 200)), max(0, offset)])

        async with db.execute(query, tuple(params)) as cur:
            rows = await cur.fetchall()

        items = []
        for r in rows:
            (
                a_id, msg_id, filename, mime_type, file_type, size_bytes,
                storage_path, thumbnail_path, created_at, conv_id,
                conv_title, prompt, gen_model_id, is_gen
            ) = r

            norm_storage = storage_path.replace("\\", "/") if storage_path else ""
            norm_thumb = thumbnail_path.replace("\\", "/") if thumbnail_path else None

            items.append({
                "id": a_id,
                "message_id": msg_id,
                "filename": filename,
                "mime_type": mime_type,
                "file_type": file_type,
                "size_bytes": size_bytes,
                "storage_path": norm_storage,
                "thumbnail_path": norm_thumb,
                "thumbnail_url": f"/attachments/{norm_thumb}" if norm_thumb else None,
                "file_url": f"/attachments/{norm_storage}",
                "created_at": created_at,
                "conversation_id": conv_id,
                "conversation_title": conv_title,
                "prompt": prompt,
                "model_id": gen_model_id,
                "is_generated": bool(is_gen),
            })

        return {"items": items, "total": len(items)}
    finally:
        await db.close()


@router.delete("/{attachment_id}")
async def delete_library_item(
    attachment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove um anexo/imagem da biblioteca e do disco."""
    user_id = current_user["id"]
    db = await get_db()
    try:
        async with db.execute(
            """
            SELECT a.storage_path, a.thumbnail_path
            FROM attachments a
            LEFT JOIN messages m ON a.message_id = m.id
            LEFT JOIN conversations c ON m.conversation_id = c.id
            LEFT JOIN image_gen_tasks t ON (t.attachment_id = a.id OR (a.message_id IS NOT NULL AND t.message_id = a.message_id))
            WHERE a.id = ? AND (c.user_id = ? OR t.user_id = ?)
            LIMIT 1
            """,
            (attachment_id, user_id, user_id),
        ) as cur:
            row = await cur.fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado ou sem permissão.")

        storage_path, thumbnail_path = row

        if storage_path:
            abs_p = get_absolute_path(storage_path)
            if abs_p.exists():
                try:
                    abs_p.unlink()
                except Exception:
                    pass

        if thumbnail_path:
            abs_t = get_absolute_path(thumbnail_path)
            if abs_t.exists():
                try:
                    abs_t.unlink()
                except Exception:
                    pass

        await db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        await db.execute("UPDATE image_gen_tasks SET attachment_id = NULL WHERE attachment_id = ?", (attachment_id,))
        await db.commit()

        return {"status": "ok", "deleted_id": attachment_id}
    finally:
        await db.close()

