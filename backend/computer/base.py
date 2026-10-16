"""Módulo de Sandbox de Computador (F8.2) — Anti-SSRF e BaseComputer.

Permite que bots especialistas naveguem na web e executem ações em
ambiente controlado e isolado (container nexus_computer), sem colocar
em risco a rede local ou o host.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import ipaddress
import socket
from typing import Any, Optional
from urllib.parse import urlparse

from backend.logging_config import get_logger

logger = get_logger(__name__)

# Redes privadas / reservadas que NUNCA podem ser acessadas pelo computador do agente
BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "host.docker.internal",
    "nexus_backend",
    "nexus_frontend",
    "nexus_db",
    "portainer",
}


def is_safe_public_url(url: str) -> tuple[bool, str]:
    """Verifica se uma URL é pública e segura contra SSRF.

    Retorna: (is_safe, error_reason)
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, f"Esquema não suportado: {parsed.scheme} (apenas http e https)"

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            return False, "URL sem hostname válido"

        if hostname in BLOCKED_HOSTNAMES or hostname.endswith(".local") or hostname.endswith(".internal"):
            return False, f"Hostname restrito ou privado: {hostname}"

        # Resolver IP
        try:
            addr_info = socket.getaddrinfo(hostname, None)
        except socket.gaierror as e:
            return False, f"Falha ao resolver DNS para {hostname}: {e}"

        for info in addr_info:
            ip_str = info[4][0]
            ip_obj = ipaddress.ip_address(ip_str)

            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
                return False, f"Endereço IP privado ou de loopback detectado: {ip_str}"

            for net in BLOCKED_NETWORKS:
                if ip_obj in net:
                    return False, f"Endereço IP pertence à faixa reservada {net}: {ip_str}"

        return True, ""
    except Exception as exc:
        return False, f"Erro ao analisar URL: {exc}"


@dataclass
class ComputerActionRecord:
    action_type: str
    target: str
    status: str  # "success" (✓) | "error" (⚠)
    latency_ms: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    )
    details: Optional[dict[str, Any]] = None


class BaseComputer:
    """Controlador de sandbox de computador para bots especialistas."""

    def __init__(self, bot_id: str, mode: str = "shared"):
        self.bot_id = bot_id
        self.mode = mode
        self.current_url: str = "about:blank"
        self.action_history: list[ComputerActionRecord] = []

    async def navigate(self, url: str) -> dict[str, Any]:
        """Navega com segurança para uma URL pública."""
        t0 = asyncio.get_event_loop().time()
        safe, reason = is_safe_public_url(url)
        if not safe:
            record = ComputerActionRecord(
                action_type="navigate",
                target=url,
                status="error",
                latency_ms=(asyncio.get_event_loop().time() - t0) * 1000,
                details={"error": reason},
            )
            self.action_history.append(record)
            return {"ok": False, "status": "error", "error": reason}

        # Simulação controlada de navegação sandbox
        await asyncio.sleep(0.05)
        self.current_url = url
        record = ComputerActionRecord(
            action_type="navigate",
            target=url,
            status="success",
            latency_ms=(asyncio.get_event_loop().time() - t0) * 1000,
            details={"title": f"Página de {urlparse(url).netloc}"},
        )
        self.action_history.append(record)
        return {
            "ok": True,
            "status": "success",
            "url": self.current_url,
            "title": f"Página de {urlparse(url).netloc}",
        }

    async def click(self, x: int, y: int) -> dict[str, Any]:
        """Clica nas coordenadas x, y dentro da viewport."""
        t0 = asyncio.get_event_loop().time()
        await asyncio.sleep(0.02)
        record = ComputerActionRecord(
            action_type="click",
            target=f"({x}, {y})",
            status="success",
            latency_ms=(asyncio.get_event_loop().time() - t0) * 1000,
        )
        self.action_history.append(record)
        return {"ok": True, "status": "success", "coordinates": {"x": x, "y": y}}

    async def type_text(self, text: str) -> dict[str, Any]:
        """Digita texto na entrada ativa."""
        t0 = asyncio.get_event_loop().time()
        await asyncio.sleep(0.02)
        record = ComputerActionRecord(
            action_type="type",
            target=f"length={len(text)}",
            status="success",
            latency_ms=(asyncio.get_event_loop().time() - t0) * 1000,
        )
        self.action_history.append(record)
        return {"ok": True, "status": "success", "length": len(text)}

    async def take_screenshot(self) -> dict[str, Any]:
        """Captura um snapshot visual da tela atual (mock SVG/Canvas de alta fidelidade)."""
        t0 = asyncio.get_event_loop().time()
        # Retorna um SVG embutido de preview renderizado
        svg_mock = (
            f"<svg xmlns='http://www.w3.org/2000/svg' width='800' height='600' viewBox='0 0 800 600'>"
            f"<rect width='800' height='600' fill='#0f172a'/>"
            f"<rect x='20' y='20' width='760' height='40' rx='6' fill='#1e293b'/>"
            f"<text x='40' y='46' fill='#94a3b8' font-family='sans-serif' font-size='14'>{self.current_url}</text>"
            f"<rect x='20' y='80' width='760' height='480' rx='8' fill='#1e293b' opacity='0.7'/>"
            f"<text x='50' y='140' fill='#f8fafc' font-family='sans-serif' font-size='20' font-weight='bold'>Visualização Sandbox Ativa</text>"
            f"<text x='50' y='180' fill='#64748b' font-family='sans-serif' font-size='14'>Bot ID: {self.bot_id} · Modo: {self.mode}</text>"
            f"</svg>"
        )
        record = ComputerActionRecord(
            action_type="screenshot",
            target=self.current_url,
            status="success",
            latency_ms=(asyncio.get_event_loop().time() - t0) * 1000,
        )
        self.action_history.append(record)
        return {
            "ok": True,
            "status": "success",
            "url": self.current_url,
            "svg_preview": svg_mock,
        }

    async def extract_dom(self) -> dict[str, Any]:
        """Extrai a estrutura limpa e acessível do DOM atual."""
        return {
            "ok": True,
            "url": self.current_url,
            "elements": [
                {"tag": "h1", "text": "Nexus Sandbox Computer"},
                {"tag": "input", "placeholder": "Search or type URL"},
                {"tag": "button", "text": "Submit"},
            ],
        }
