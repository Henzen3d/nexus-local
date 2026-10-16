"""backend/tools/families/knowledge — Provedores de conhecimento e fatos verificáveis.
"""
from backend.tools.families.knowledge.open_library import OpenLibraryProvider
from backend.tools.families.knowledge.wikipedia import WikipediaProvider

__all__ = [
    "WikipediaProvider",
    "OpenLibraryProvider",
]
