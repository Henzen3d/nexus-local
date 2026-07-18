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
                extracted_text = await extract_text(str(abs_path), mime_type)
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
