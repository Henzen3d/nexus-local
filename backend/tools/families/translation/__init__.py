"""backend/tools/families/translation — Provedores de tradução.
"""
from backend.tools.families.translation.libretranslate import LibreTranslateProvider
from backend.tools.families.translation.mymemory import MyMemoryProvider

__all__ = [
    "LibreTranslateProvider",
    "MyMemoryProvider",
]
