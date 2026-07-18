"""
Shared embedding engine for Cache Semântico and Projects RAG.

Uses fastembed (ONNX, no PyTorch) with the same multilingual MiniLM model
as the semantic cache so a single model download is reused.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from backend.logging_config import get_logger

logger = get_logger(__name__)

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

# Shared singleton — also used by cache.manager after re-export
_EMBEDDER = None
_EMBEDDER_INIT = False
_EMBEDDER_LOADING = False
_EMBEDDER_ERROR: Optional[str] = None

# Keep in sync with cache.manager historical choice (multilingual)
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def get_embedder_error() -> Optional[str]:
    return _EMBEDDER_ERROR


def is_embedder_ready() -> bool:
    return _EMBEDDER is not None and _HAS_NUMPY


def init_embedder(model_name: str = DEFAULT_MODEL) -> Optional[object]:
    """Initialize (or return) the global TextEmbedding instance. Safe to call repeatedly."""
    global _EMBEDDER, _EMBEDDER_INIT, _EMBEDDER_LOADING, _EMBEDDER_ERROR
    if _EMBEDDER_INIT:
        return _EMBEDDER
    if _EMBEDDER_LOADING:
        return None
    _EMBEDDER_LOADING = True
    try:
        from fastembed import TextEmbedding


        _EMBEDDER = TextEmbedding(model_name=model_name)
        logger.info("✅ Embedder pronto (%s)", model_name)
        _EMBEDDER_INIT = True
        _EMBEDDER_ERROR = None
    except ImportError:
        _EMBEDDER_ERROR = "fastembed não instalado. Rode: pip install fastembed"
        logger.warning("⚠️  %s", _EMBEDDER_ERROR)
        _EMBEDDER_INIT = True
    except Exception as e:
        _EMBEDDER_ERROR = f"Erro ao inicializar embedder: {e}"
        logger.warning("⚠️  %s", _EMBEDDER_ERROR)
        _EMBEDDER_INIT = True
    finally:
        _EMBEDDER_LOADING = False
    return _EMBEDDER


def warm_up_embedder(model_name: str = DEFAULT_MODEL) -> bool:
    """
    Load model and run a tiny encode so first request is not cold.
    Call once at FastAPI startup (preferably in a thread).
    """
    emb = init_embedder(model_name)
    if emb is None or not _HAS_NUMPY:
        return False
    try:
        list(emb.embed(["warmup"]))
        logger.info("✅ Embedder warm-up concluído")
        return True
    except Exception as e:
        logger.error("⚠️  Embedder warm-up falhou:", exc_info=e)
        return False


async def warm_up_embedder_async(model_name: str = DEFAULT_MODEL) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, warm_up_embedder, model_name)


def embedding_to_blob(vec) -> bytes:
    arr = np.array(vec, dtype=np.float32)
    return arr.tobytes()


def blob_to_embedding(blob: bytes):
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(a, b) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def embed_text(text: str) -> Optional[bytes]:
    """Sync embed → BLOB float32. Returns None if embedder unavailable."""
    embedder = init_embedder()
    if embedder is None or not _HAS_NUMPY:
        return None
    if not text or not str(text).strip():
        return None
    embeddings = list(embedder.embed([str(text)[:8000]]))
    return embedding_to_blob(embeddings[0])


def embed_texts(texts: list[str]) -> list[Optional[bytes]]:
    embedder = init_embedder()
    if embedder is None or not _HAS_NUMPY or not texts:
        return [None] * len(texts)
    cleaned = [str(t)[:8000] if t else "" for t in texts]
    # Preserve empties as None without calling embed on empty batch only
    non_empty_idx = [i for i, t in enumerate(cleaned) if t.strip()]
    result: list[Optional[bytes]] = [None] * len(texts)
    if not non_empty_idx:
        return result
    batch = [cleaned[i] for i in non_empty_idx]
    vectors = list(embedder.embed(batch))
    for j, i in enumerate(non_empty_idx):
        result[i] = embedding_to_blob(vectors[j])
    return result


async def embed_text_async(text: str) -> Optional[bytes]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, embed_text, text)


async def embed_texts_async(texts: list[str]) -> list[Optional[bytes]]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, embed_texts, texts)
