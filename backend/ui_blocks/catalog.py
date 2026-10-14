"""Catálogo por turno, somente contratos implementados; orçamento estimado chars/4."""
from pathlib import Path
from backend.ui_blocks.should_offer import select_modules, should_offer_ui

MAX_CATALOG_TOKENS = 450
ROOT = Path(__file__).resolve().parent
MODULE_NAMES = ("chart", "metric", "progress", "controls", "callout", "card", "sandbox", "follow_up")


def compose_catalog(modules: tuple[str, ...]) -> str:
    text = (ROOT / "catalog.txt").read_text(encoding="utf-8")
    for name in modules:
        if name not in MODULE_NAMES:
            raise ValueError(f"Unknown UI module: {name}")
        text += "\n" + (ROOT / "catalog_modules" / f"{name}.txt").read_text(encoding="utf-8")
    if len(text) / 4 > MAX_CATALOG_TOKENS:
        raise ValueError("UI catalog exceeds token budget")
    return text


def build_catalog(user_text: str) -> tuple[str, tuple[str, ...]]:
    if not should_offer_ui(user_text):
        return "", ()
    modules = select_modules(user_text)
    return compose_catalog(modules), modules
