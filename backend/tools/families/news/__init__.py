"""backend/tools/families/news — Provedores de notícias.
"""
from backend.tools.families.news.currents import CurrentsProvider
from backend.tools.families.news.ddg_news import DDGNewsProvider
from backend.tools.families.news.gnews import GNewsProvider

__all__ = [
    "GNewsProvider",
    "CurrentsProvider",
    "DDGNewsProvider",
]
