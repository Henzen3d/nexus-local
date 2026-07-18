import pypdf
import pdfplumber
import docx
import pandas as pd
import io

from backend.logging_config import get_logger
logger = get_logger(__name__)

class ExtractionError(Exception):
    pass

async def extract_text_from_pdf(filepath: str) -> str:
    text = ""
    # Try pypdf first
    try:
        with open(filepath, 'rb') as f:
            reader = pypdf.PdfReader(f)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        logger.error("pypdf extraction failed:", exc_info=e)

    # Fallback to pdfplumber if empty
    if not text.strip():
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
        except Exception as e:
            logger.error("pdfplumber extraction failed:", exc_info=e)

    if not text.strip():
        raise ExtractionError("PDF sem texto extraível — provavelmente escaneado. OCR necessário.")
    
    return text.strip()

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

async def extract_text(filepath: str, mime_type: str) -> str:
    import os

    _, ext = os.path.splitext(filepath.lower())

    if ext == '.pdf' or 'pdf' in mime_type:
        return await extract_text_from_pdf(filepath)
    elif ext == '.docx' or 'document' in mime_type:
        return await extract_text_from_docx(filepath)
    elif ext == '.csv' or 'csv' in mime_type:
        return await extract_text_from_csv(filepath)
    elif ext in ('.txt', '.md') or 'text' in mime_type:
        return await extract_text_from_text_file(filepath)
    else:
        raise ExtractionError(f"Tipo de arquivo '{ext}' não suportado para extração de texto.")
