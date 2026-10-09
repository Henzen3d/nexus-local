import pypdf
import pdfplumber
import docx
import pandas as pd

from backend.logging_config import get_logger
logger = get_logger(__name__)

_PDF_VISION_PAGES = 8


class ExtractionError(Exception):
    pass


def _pdf_native_text(filepath: str) -> str:
    text = ""
    try:
        with open(filepath, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        logger.error("pypdf extraction failed:", exc_info=e)

    if not text.strip():
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        except Exception as e:
            logger.error("pdfplumber extraction failed:", exc_info=e)
    return text


def _render_pdf_pages(filepath: str, max_pages: int = _PDF_VISION_PAGES) -> list[bytes]:
    import fitz  # PyMuPDF — render only, no Tesseract

    doc = fitz.open(filepath)
    try:
        n = min(max_pages, doc.page_count)
        matrix = fitz.Matrix(1.5, 1.5)
        pages: list[bytes] = []
        for i in range(n):
            pix = doc[i].get_pixmap(matrix=matrix, alpha=False)
            pages.append(pix.tobytes("png"))
        return pages
    finally:
        doc.close()


async def _vision_relay_enabled() -> bool:
    from backend.vision_relay.relay import get_db, get_vision_relay_config

    db = await get_db()
    try:
        config = await get_vision_relay_config(db)
        return bool(config and config.get("enabled"))
    finally:
        await db.close()


async def _cached_pdf_text(file_hash: str) -> str | None:
    if not file_hash:
        return None
    from backend.vision_relay.relay import (
        get_cached_description,
        get_db,
        get_vision_relay_config,
    )

    db = await get_db()
    try:
        config = await get_vision_relay_config(db)
        if not config or not config.get("cache_descriptions"):
            return None
        return await get_cached_description(file_hash, db)
    finally:
        await db.close()


async def _save_pdf_text_cache(file_hash: str, text: str, relay_model: str = "") -> None:
    if not file_hash or not text:
        return
    from backend.vision_relay.relay import (
        get_db,
        get_vision_relay_config,
        save_description_cache,
    )

    db = await get_db()
    try:
        config = await get_vision_relay_config(db)
        if not config or not config.get("cache_descriptions"):
            return
        await save_description_cache(file_hash, text, relay_model, db)
    finally:
        await db.close()


async def _describe_page_image(image_bytes: bytes, file_hash: str, user_id: str) -> dict:
    from backend.vision_relay.relay import describe_image_via_relay

    return await describe_image_via_relay(
        None,
        "image/png",
        file_hash,
        user_id,
        image_bytes=image_bytes,
    )


async def transcribe_scanned_pdf(
    filepath: str,
    file_hash: str | None = None,
    user_id: str | None = None,
) -> str:
    cached = await _cached_pdf_text(file_hash or "")
    if cached:
        return cached

    if not await _vision_relay_enabled():
        raise ExtractionError(
            "PDF sem texto extraível — provavelmente escaneado. "
            "Vision Relay desativado; não foi possível transcrever as páginas."
        )

    try:
        pages = _render_pdf_pages(filepath, max_pages=_PDF_VISION_PAGES)
    except Exception as e:
        logger.error("PyMuPDF render failed:", exc_info=e)
        raise ExtractionError(
            "PDF sem texto extraível — provavelmente escaneado. "
            "Não foi possível renderizar as páginas para transcrição."
        ) from e

    if not pages:
        raise ExtractionError(
            "PDF sem texto extraível — provavelmente escaneado. OCR necessário."
        )

    from backend.vision_relay.relay import RelayError

    parts: list[str] = []
    last_model = ""
    try:
        for i, png in enumerate(pages):
            page_hash = f"{file_hash}:p{i}" if file_hash else f"pdfpage-{i}"
            res = await _describe_page_image(png, page_hash, user_id or "")
            desc = (res.get("description") or "").strip()
            if desc:
                parts.append(f"[Página {i + 1}]\n{desc}")
            last_model = res.get("relay_model") or last_model
    except RelayError as e:
        raise ExtractionError(
            f"PDF sem texto extraível — provavelmente escaneado. Vision Relay falhou: {e}"
        ) from e

    if not parts:
        raise ExtractionError(
            "PDF sem texto extraível — provavelmente escaneado. OCR necessário."
        )

    text = "\n\n".join(parts)
    await _save_pdf_text_cache(file_hash or "", text, last_model)
    return text


async def extract_text_from_pdf(
    filepath: str,
    file_hash: str | None = None,
    user_id: str | None = None,
) -> str:
    text = _pdf_native_text(filepath)
    if text.strip():
        return text.strip()
    return await transcribe_scanned_pdf(filepath, file_hash=file_hash, user_id=user_id)

async def extract_text_from_docx(filepath: str) -> str:
    try:
        doc = docx.Document(filepath)
        text = []
        for paragraph in doc.paragraphs:
            text.append(paragraph.text)
        return "\n".join(text).strip()
    except Exception as e:
        raise ExtractionError(f"Erro ao extrair texto do DOCX: {e}")

async def extract_text_from_csv(filepath: str) -> str:
    try:
        # Load CSV using pandas and convert to Markdown table
        df = pd.read_csv(filepath, sep=None, engine='python')
        # Limit rows/cols to avoid huge prompt sizes (e.g. max 100 rows, 20 columns)
        if len(df) > 100:
            df_truncated = df.head(100)
            md = df_truncated.to_markdown(index=False)
            md += f"\n\n*(Tabela truncada: exibindo primeiras 100 de {len(df)} linhas)*"
            return md
        return df.to_markdown(index=False)
    except Exception as e:
        raise ExtractionError(f"Erro ao ler CSV: {e}")

async def extract_text_from_text_file(filepath: str) -> str:
    # Try different encodings
    for encoding in ('utf-8', 'latin-1', 'utf-16'):
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ExtractionError("Não foi possível decodificar o arquivo de texto (Múltiplas codificações falharam).")

async def extract_text(
    filepath: str,
    mime_type: str,
    file_hash: str | None = None,
    user_id: str | None = None,
) -> str:
    import os

    _, ext = os.path.splitext(filepath.lower())

    if ext == '.pdf' or 'pdf' in mime_type:
        return await extract_text_from_pdf(filepath, file_hash=file_hash, user_id=user_id)
    elif ext == '.docx' or 'document' in mime_type:
        return await extract_text_from_docx(filepath)
    elif ext == '.csv' or 'csv' in mime_type:
        return await extract_text_from_csv(filepath)
    elif ext in ('.txt', '.md') or 'text' in mime_type:
        return await extract_text_from_text_file(filepath)
    else:
        raise ExtractionError(f"Tipo de arquivo '{ext}' não suportado para extração de texto.")
