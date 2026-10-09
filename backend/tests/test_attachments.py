"""Anexos: PDF escaneado via Vision Relay, fatia de contexto, flag de visão."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_vision_from_input_modalities_only():
    from backend.providers.model_fetcher import vision_from_architecture

    assert vision_from_architecture({"input_modalities": ["text", "image"]}) is True
    assert vision_from_architecture({"input_modalities": ["text"]}) is False
    assert vision_from_architecture({}) is False
    assert vision_from_architecture(None) is False
    # Campo antigo "modality" não vale — sem input_modalities fica 0
    assert vision_from_architecture({"modality": "text+image"}) is False
    assert vision_from_architecture({"input_modalities": "image"}) is True


def test_boot_does_not_mark_vision_by_vl_name():
    src = (ROOT / "backend" / "database.py").read_text(encoding="utf-8")
    assert "LIKE '%vl%'" not in src
    assert "LIKE '%vision%'" not in src


def test_doc_inject_budget_floor_and_ceiling():
    from backend.orchestration.handle_attachments import doc_inject_max_chars

    assert doc_inject_max_chars(500) == 6000
    assert doc_inject_max_chars(2000) == 6000
    mid = doc_inject_max_chars(5000)
    assert 6000 <= mid <= 24000
    assert doc_inject_max_chars(20000) == 24000
    assert doc_inject_max_chars(100000) == 24000


def test_select_document_excerpt_keeps_query_hits_not_just_head():
    from backend.orchestration.handle_attachments import select_document_excerpt

    head = ("AAA introdução sem valor. " * 400) + "\n\n"
    tail = "O contrato de aluguel vence em dezembro de 2026. " * 80
    text = head + tail
    assert len(text) > 6000

    out = select_document_excerpt(text, query="contrato aluguel dezembro", max_chars=6000)
    assert "contrato de aluguel" in out.lower() or "aluguel" in out.lower()
    assert "ficaram de fora" in out or "omit" in out.lower()
    # Não pode ser só o começo
    assert not out.startswith(head[:200]) or "aluguel" in out.lower()


def test_select_document_excerpt_short_text_unchanged():
    from backend.orchestration.handle_attachments import select_document_excerpt

    text = "Nota fiscal 123."
    assert select_document_excerpt(text, query="nota", max_chars=6000) == text


def test_is_vision_refusal_error():
    from backend.orchestration.handle_attachments import is_vision_refusal_error

    assert is_vision_refusal_error("This model does not support image inputs")
    assert is_vision_refusal_error("image_url is not supported for this model")
    assert not is_vision_refusal_error("rate limit exceeded")
    assert not is_vision_refusal_error("")


def _blank_pdf(path: str) -> None:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as f:
        writer.write(f)


def test_scanned_pdf_refuses_when_relay_off():
    from backend.attachments.extractors import ExtractionError, extract_text_from_pdf

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        _blank_pdf(path)

        async def _disabled(*_a, **_k):
            return False

        async def _no_cache(*_a, **_k):
            return None

        with patch(
            "backend.attachments.extractors._vision_relay_enabled",
            new=_disabled,
        ), patch(
            "backend.attachments.extractors._cached_pdf_text",
            new=_no_cache,
        ):
            try:
                run(extract_text_from_pdf(path, file_hash="h1", user_id="u1"))
                raise AssertionError("devia recusar")
            except ExtractionError as exc:
                msg = str(exc)
                assert "escaneado" in msg.lower() or "vision relay" in msg.lower()
                assert "conteúdo visual detectado" not in msg
    finally:
        os.unlink(path)


def test_scanned_pdf_transcribes_via_relay_and_caches():
    from backend.attachments.extractors import extract_text_from_pdf

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    calls = {"describe": 0, "cache_set": 0}

    try:
        _blank_pdf(path)

        async def _enabled(*_a, **_k):
            return True

        async def _cache_get(file_hash, *_a, **_k):
            return None

        async def _cache_set(file_hash, text, *_a, **_k):
            calls["cache_set"] += 1
            calls["cached_text"] = text

        async def _describe(*_a, **_k):
            calls["describe"] += 1
            return {"description": "Recibo no valor de R$ 50", "relay_model": "gemini/flash-2.0"}

        def _render(_filepath, max_pages=8):
            return [b"fake-png"]

        with patch("backend.attachments.extractors._vision_relay_enabled", new=_enabled), patch(
            "backend.attachments.extractors._cached_pdf_text", new=_cache_get
        ), patch(
            "backend.attachments.extractors._save_pdf_text_cache", new=_cache_set
        ), patch(
            "backend.attachments.extractors._describe_page_image", new=_describe
        ), patch(
            "backend.attachments.extractors._render_pdf_pages", new=_render
        ):
            text = run(extract_text_from_pdf(path, file_hash="h2", user_id="u1"))

        assert "Recibo no valor de R$ 50" in text
        assert calls["describe"] == 1
        assert calls["cache_set"] == 1
    finally:
        os.unlink(path)


def test_history_contains_images():
    from backend.orchestration.handle_attachments import history_contains_images

    assert history_contains_images(
        [{"role": "user", "content": [{"type": "text", "text": "oi"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}}]}]
    )
    assert not history_contains_images([{"role": "user", "content": "oi"}])


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore
    except Exception:
        pass
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    test_vision_from_input_modalities_only()
    print("OK test_vision_from_input_modalities_only")
    test_boot_does_not_mark_vision_by_vl_name()
    print("OK test_boot_does_not_mark_vision_by_vl_name")
    test_doc_inject_budget_floor_and_ceiling()
    print("OK test_doc_inject_budget_floor_and_ceiling")
    test_select_document_excerpt_keeps_query_hits_not_just_head()
    print("OK test_select_document_excerpt_keeps_query_hits_not_just_head")
    test_select_document_excerpt_short_text_unchanged()
    print("OK test_select_document_excerpt_short_text_unchanged")
    test_is_vision_refusal_error()
    print("OK test_is_vision_refusal_error")
    test_scanned_pdf_refuses_when_relay_off()
    print("OK test_scanned_pdf_refuses_when_relay_off")
    test_scanned_pdf_transcribes_via_relay_and_caches()
    print("OK test_scanned_pdf_transcribes_via_relay_and_caches")
    test_history_contains_images()
    print("OK test_history_contains_images")
    print("\nAll attachment tests passed.")
