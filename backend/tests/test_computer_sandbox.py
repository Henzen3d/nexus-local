"""Testes do Sandbox de Computador (F8.2) — Anti-SSRF e BaseComputer."""
import pytest
from backend.computer.base import BaseComputer, is_safe_public_url


def test_ssrf_blocks_private_ips():
    # Loopback
    safe, reason = is_safe_public_url("http://127.0.0.1/admin")
    assert not safe
    assert "loopback" in reason.lower() or "privado" in reason.lower()

    # Localhost
    safe, reason = is_safe_public_url("http://localhost:8000/api")
    assert not safe

    # RFC 1918 Private ranges
    safe, reason = is_safe_public_url("http://192.168.1.100")
    assert not safe
    assert "privado" in reason.lower() or "reservada" in reason.lower()

    safe, reason = is_safe_public_url("http://10.0.0.1")
    assert not safe

    safe, reason = is_safe_public_url("http://172.16.0.5")
    assert not safe

    # Cloud metadata (AWS/GCP link-local)
    safe, reason = is_safe_public_url("http://169.254.169.254/latest/meta-data/")
    assert not safe

    # Unsupported scheme
    safe, reason = is_safe_public_url("file:///etc/passwd")
    assert not safe
    assert "apenas http e https" in reason


def test_ssrf_allows_public_urls():
    # Domínios públicos legítimos
    safe, _ = is_safe_public_url("https://example.com")
    assert safe

    safe, _ = is_safe_public_url("https://www.google.com/search?q=test")
    assert safe


@pytest.mark.asyncio
async def test_base_computer_actions():
    comp = BaseComputer(bot_id="bot_test_123", mode="shared")

    # Tentar navegar para IP privado deve falhar no gateway
    res = await comp.navigate("http://127.0.0.1:8000")
    assert not res["ok"]
    assert res["status"] == "error"

    # Navegação pública
    res = await comp.navigate("https://example.com")
    assert res["ok"]
    assert res["url"] == "https://example.com"
    assert comp.current_url == "https://example.com"

    # Click e digitação
    c_res = await comp.click(100, 250)
    assert c_res["ok"]
    assert c_res["coordinates"] == {"x": 100, "y": 250}

    t_res = await comp.type_text("Hello agent")
    assert t_res["ok"]
    assert t_res["length"] == 11

    # Screenshot
    s_res = await comp.take_screenshot()
    assert s_res["ok"]
    assert "<svg" in s_res["svg_preview"]

    # Histórico registrado
    assert len(comp.action_history) == 5
