import os
import re
import shutil
from pathlib import Path
from PIL import Image

from backend.logging_config import get_logger
logger = get_logger(__name__)

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage" / "attachments"

def get_absolute_path(relative_path: str) -> Path:
    return STORAGE_DIR / relative_path

def save_file(file_content: bytes, filename: str, attachment_id: str, is_image: bool) -> tuple[str, str | None]:
    # Ensure local directory exists
    unsent_dir = STORAGE_DIR / "unsent"
    unsent_dir.mkdir(parents=True, exist_ok=True)

    # Clean filename to avoid directory traversal
    safe_filename = os.path.basename(filename)
    dest_filename = f"{attachment_id}_{safe_filename}"
    
    # Save original file
    file_rel_path = f"unsent/{dest_filename}"
    dest_path = get_absolute_path(file_rel_path)
    with open(dest_path, "wb") as f:
        f.write(file_content)

    thumb_rel_path = None
    if is_image:
        try:
            # Generate thumbnail
            thumb_filename = f"{attachment_id}_thumb.jpg"
            thumb_rel_path = f"unsent/{thumb_filename}"
            thumb_path = get_absolute_path(thumb_rel_path)
            
            with Image.open(dest_path) as img:
                # Convert to RGB if necessary (e.g. RGBA png to JPG)
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.thumbnail((120, 120))
                img.save(thumb_path, "JPEG", quality=85)
        except Exception as e:
            logger.error("Failed to generate thumbnail:", exc_info=e)
            thumb_rel_path = None

    return file_rel_path, thumb_rel_path

_ATTACHMENT_ID_RE = re.compile(r"^att_[0-9a-f]{32}$")


async def move_attachments_to_conversation(
    attachment_ids: list[str],
    conversation_id: str,
    message_id: str,
    db,
    user_id: str | None = None,
) -> None:
    """Vincula anexos *unsent* à mensagem e move os arquivos para a pasta da conversa.

    Regras de autorização (antes inexistentes):
    - só anexos ainda sem ``message_id`` podem ser vinculados (um anexo já enviado
      em outra conversa nunca é "roubado");
    - quando ``user_id`` é informado, o anexo precisa ter sido enviado por ele
      (``attachments.user_id``); linhas legadas sem dono continuam aceitas.
    """
    if not attachment_ids:
        return

    # conversation_id compõe caminho no filesystem — nunca aceitar algo que não seja UUID.
    if not re.match(r"^[0-9a-fA-F-]{36}$", str(conversation_id or "")):
        logger.warning("move_attachments_to_conversation: conversation_id inválido ignorado")
        return

    # Ensure conversation storage directory exists
    conv_dir = STORAGE_DIR / conversation_id
    conv_dir.mkdir(parents=True, exist_ok=True)

    for att_id in attachment_ids:
        if not _ATTACHMENT_ID_RE.match(str(att_id or "")):
            continue
        # Fetch attachment info — apenas anexos "unsent" do próprio usuário
        async with db.execute(
            """SELECT filename, storage_path, thumbnail_path FROM attachments
               WHERE id = ? AND message_id IS NULL
                 AND (? IS NULL OR user_id IS NULL OR user_id = ?)""",
            (att_id, user_id, user_id)
        ) as cur:
            row = await cur.fetchone()
        
        if not row:
            logger.warning("Anexo %s ignorado: inexistente, já enviado ou de outro usuário", att_id)
            continue

        filename, rel_storage, rel_thumb = row
        safe_filename = os.path.basename(filename)

        # Build paths
        abs_old_storage = get_absolute_path(rel_storage)
        new_storage_rel = f"{conversation_id}/{att_id}_{safe_filename}"
        abs_new_storage = get_absolute_path(new_storage_rel)

        # Move original file
        if abs_old_storage.exists():
            shutil.move(str(abs_old_storage), str(abs_new_storage))
        
        # Move thumbnail if exists
        new_thumb_rel = None
        if rel_thumb:
            abs_old_thumb = get_absolute_path(rel_thumb)
            new_thumb_rel = f"{conversation_id}/{att_id}_thumb.jpg"
            abs_new_thumb = get_absolute_path(new_thumb_rel)
            if abs_old_thumb.exists():
                shutil.move(str(abs_old_thumb), str(abs_new_thumb))

        # Update in database
        await db.execute(
            """UPDATE attachments 
               SET message_id = ?, storage_path = ?, thumbnail_path = ?,
                   user_id = COALESCE(user_id, ?)
               WHERE id = ?""",
            (message_id, new_storage_rel.replace("\\", "/"), new_thumb_rel.replace("\\", "/") if new_thumb_rel else None, user_id, att_id)
        )
    await db.commit()


def save_attachment_for_conversation(
    file_content: bytes, filename: str, attachment_id: str, conversation_id: str
) -> tuple[str, str | None]:
    """Salva anexo diretamente no diretório final da conversa (storage/attachments/{conv_id})."""
    conv_dir = STORAGE_DIR / conversation_id
    conv_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = os.path.basename(filename)
    dest_filename = f"{attachment_id}_{safe_filename}"
    file_rel_path = f"{conversation_id}/{dest_filename}"
    dest_path = get_absolute_path(file_rel_path)
    with open(dest_path, "wb") as f:
        f.write(file_content)

    thumb_rel_path = None
    try:
        thumb_filename = f"{attachment_id}_thumb.jpg"
        thumb_rel_path = f"{conversation_id}/{thumb_filename}"
        thumb_path = get_absolute_path(thumb_rel_path)
        with Image.open(dest_path) as img:
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.thumbnail((240, 240))
            img.save(thumb_path, "JPEG", quality=85)
    except Exception as e:
        logger.error("Failed to generate thumbnail for generated image:", exc_info=e)
        thumb_rel_path = None

    return file_rel_path.replace("\\", "/"), thumb_rel_path.replace("\\", "/") if thumb_rel_path else None

