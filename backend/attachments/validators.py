import os
from typing import Dict, Any

MAX_FILE_SIZE_MB = 20
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

SUPPORTED_DOCUMENT_TYPES = {'.pdf', '.docx', '.txt', '.csv', '.md'}
SUPPORTED_IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.webp'}
SUPPORTED_EXTENSIONS = SUPPORTED_DOCUMENT_TYPES.union(SUPPORTED_IMAGE_TYPES)

class ValidationResult:
    def __init__(self, ok: bool, error_message: str = "", mime_type: str = ""):
        self.ok = ok
        self.error_message = error_message
        self.mime_type = mime_type

def validate_attachment(filename: str, size_bytes: int, file_content_peek: bytes = b"") -> ValidationResult:
    # 1. Validate file size
    if size_bytes > MAX_FILE_SIZE_BYTES:
        return ValidationResult(ok=False, error_message=f"Arquivo muito grande. Limite máximo de {MAX_FILE_SIZE_MB}MB.")

    # 2. Validate extension
    _, ext = os.path.splitext(filename.lower())
    if ext not in SUPPORTED_EXTENSIONS:
        return ValidationResult(ok=False, error_message=f"Extensão '{ext}' não suportada.")

    # 3. Detect MIME type
    mime_type = ""
    # Try using python-magic if possible, fallback to standard mimetypes
    try:
        import magic
        # python-magic-bin on Windows has magic.from_buffer
        mime_type = magic.from_buffer(file_content_peek, mime=True)
    except Exception:
        import mimetypes
        mime_type, _ = mimetypes.guess_type(filename)
    
    if not mime_type:
        # Fallback based on extension
        if ext in SUPPORTED_IMAGE_TYPES:
            mime_type = f"image/{ext.lstrip('.')}"
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"
        else:
            mime_type = "text/plain"

    return ValidationResult(ok=True, mime_type=mime_type)
