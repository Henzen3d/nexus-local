"""backend/tools/registry.py — Registro em memória dos provedores de ferramentas.
"""
from __future__ import annotations

import asyncio
from typing import Dict, List, Optional
import aiosqlite

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider

logger = get_logger(__name__)


class ToolRegistry:
    """Singleton thread-safe para registro e resolução de provedores de ferramentas."""
    _instance: Optional[ToolRegistry] = None
    _lock = asyncio.Lock()

    def __init__(self) -> None:
        # family -> list of ToolProvider instances
        self._families: dict[str, list[ToolProvider]] = {}
        # provider_id -> ToolProvider instance
        self._providers: dict[str, ToolProvider] = {}

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            cls._instance = ToolRegistry()
        return cls._instance

    def register(self, provider: ToolProvider) -> None:
        """Registra um provedor de ferramenta."""
        self._providers[provider.provider_id] = provider
        if provider.family not in self._families:
            self._families[provider.family] = []

        # Remove existente se mesmo provider_id
        self._families[provider.family] = [
            p for p in self._families[provider.family] if p.provider_id != provider.provider_id
        ]
        self._families[provider.family].append(provider)
        # Ordena por fallback_order crescente
        self._families[provider.family].sort(key=lambda p: p.fallback_order)
        logger.debug("[ToolRegistry] Registrado %s para família %s (ordem %d)", provider.provider_id, provider.family, provider.fallback_order)

    def get_providers(self, family: str) -> list[ToolProvider]:
        """Retorna lista de provedores para a família, ordenados por fallback_order."""
        return list(self._families.get(family, []))

    def get_provider(self, provider_id: str) -> Optional[ToolProvider]:
        """Busca um provedor específico pelo ID."""
        return self._providers.get(provider_id)

    def get_all_families(self) -> list[str]:
        """Retorna todas as famílias com provedores registrados."""
        return list(self._families.keys())

    def get_all_providers(self) -> list[ToolProvider]:
        """Retorna todos os provedores registrados."""
        return list(self._providers.values())

    async def sync_with_db(self, db: aiosqlite.Connection) -> None:
        """Sincroniza o status enabled dos provedores e famílias a partir do banco."""
        try:
            # 1. Famílias
            async with db.execute("SELECT id, enabled FROM tool_families") as cur:
                rows = await cur.fetchall()
                fam_enabled = {r[0]: bool(r[1]) for r in rows}

            # 2. Provedores
            async with db.execute("SELECT id, family_id, enabled, fallback_order FROM tool_providers") as cur:
                prows = await cur.fetchall()
                for pid, fid, en, forder in prows:
                    p = self._providers.get(pid)
                    if p:
                        family_on = fam_enabled.get(fid, True)
                        p.enabled = bool(en) and family_on
                        p.fallback_order = forder

            # Reordena cada família
            for fam in self._families:
                self._families[fam].sort(key=lambda p: p.fallback_order)

        except Exception as e:
            logger.error("[ToolRegistry] Erro ao sincronizar com DB: %s", e)


def register_provider(provider: ToolProvider) -> None:
    """Função de conveniência para registrar provider no singleton."""
    ToolRegistry.get_instance().register(provider)


def get_providers(family: str) -> list[ToolProvider]:
    """Função de conveniência para listar provedores de uma família."""
    return ToolRegistry.get_instance().get_providers(family)


def get_provider(provider_id: str) -> Optional[ToolProvider]:
    """Função de conveniência para buscar provider por ID."""
    return ToolRegistry.get_instance().get_provider(provider_id)


def get_all_families() -> list[str]:
    """Função de conveniência para listar famílias registradas."""
    return ToolRegistry.get_instance().get_all_families()


def auto_register_default_providers() -> None:
    """Instancia e registra todos os provedores embutidos das 10 famílias de ferramentas."""
    from backend.tools.families.brasil import BrasilAPIProvider, ViaCEPProvider
    from backend.tools.families.code_exec import Judge0Provider, PistonProvider
    from backend.tools.families.currency import AwesomeAPIProvider, FrankfurterProvider
    from backend.tools.families.diagrams import KrokiProvider, QuickChartProvider
    from backend.tools.families.fun import RandomFactsProvider
    from backend.tools.families.geo import NominatimProvider, OpenMeteoGeoProvider
    from backend.tools.families.knowledge import OpenLibraryProvider, WikipediaProvider
    from backend.tools.families.news import CurrentsProvider, DDGNewsProvider, GNewsProvider
    from backend.tools.families.translation import LibreTranslateProvider, MyMemoryProvider
    from backend.tools.families.weather import HGBrasilWeatherProvider, OpenMeteoProvider, WttrProvider

    providers = [
        # Weather
        OpenMeteoProvider(),
        WttrProvider(),
        HGBrasilWeatherProvider(),
        # Currency
        AwesomeAPIProvider(),
        FrankfurterProvider(),
        # Brasil
        BrasilAPIProvider(),
        ViaCEPProvider(),
        # Knowledge
        WikipediaProvider(),
        OpenLibraryProvider(),
        # News
        GNewsProvider(),
        CurrentsProvider(),
        DDGNewsProvider(),
        # Translation
        LibreTranslateProvider(),
        MyMemoryProvider(),
        # Geo
        NominatimProvider(),
        OpenMeteoGeoProvider(),
        # Fun
        RandomFactsProvider(),
        # Code Exec
        PistonProvider(),
        Judge0Provider(),
        # Diagrams
        KrokiProvider(),
        QuickChartProvider(),
    ]

    for p in providers:
        register_provider(p)

    logger.info("[ToolRegistry] %d provedores padrão auto-registrados em 10 famílias", len(providers))

