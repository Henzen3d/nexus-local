"""backend/tools/families/code_exec/wandbox.py — Provedor Wandbox para execução server-side de código.
Serviço público aberto, gratuito, sem necessidade de whitelist nem chave de API.
Suporta Python, JavaScript, TypeScript, C/C++, Rust, Go, Java, Bash, PHP, Ruby e mais.
"""
from __future__ import annotations

import time
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)

# Mapeamento oficial de linguagens para os compiladores estáveis do Wandbox
WANDBOX_COMPILER_MAP: dict[str, str] = {
    # Python
    "python": "cpython-3.12.7",
    "py": "cpython-3.12.7",
    "python3": "cpython-3.12.7",
    # JavaScript / Node / TypeScript
    "javascript": "nodejs-20.17.0",
    "js": "nodejs-20.17.0",
    "node": "nodejs-20.17.0",
    "typescript": "typescript-5.6.2",
    "ts": "typescript-5.6.2",
    # C / C++
    "c": "gcc-head-c",
    "cpp": "gcc-head",
    "c++": "gcc-head",
    # Rust
    "rust": "rust-1.82.0",
    "rs": "rust-1.82.0",
    # Go
    "go": "go-1.23.2",
    "golang": "go-1.23.2",
    # Java
    "java": "openjdk-jdk-22+36",
    # Shell / Bash
    "bash": "bash",
    "sh": "bash",
    "shell": "bash",
    # PHP
    "php": "php-8.3.12",
    # Ruby
    "ruby": "ruby-4.0.2",
    "rb": "ruby-4.0.2",
    # C# (.NET / Mono)
    "csharp": "mono-6.12.0.199",
    "cs": "mono-6.12.0.199",
    "c#": "mono-6.12.0.199",
    # SQL
    "sql": "sqlite-3.46.1",
    # Lua
    "lua": "lua-5.4.7",
    # Swift
    "swift": "swift-6.0.1",
    # R & Zig
    "r": "r-4.4.1",
    "zig": "zig-head",
}


class WandboxProvider(ToolProvider):
    provider_id = "wandbox"
    family = "code_exec"
    base_url = "https://wandbox.org/api"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        # Execução de código nunca é cacheada
        return ""

    @property
    def ttl_seconds(self) -> int:
        return 0

    async def execute(self, params: dict) -> ToolResult:
        raw_lang = (params.get("language") or "python").strip().lower()
        compiler = WANDBOX_COMPILER_MAP.get(raw_lang, "cpython-3.12.7")
        code = params.get("code") or ""
        stdin = params.get("stdin") or ""

        if not code.strip():
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Nenhum código fornecido para execução",
            )

        # Limite de tamanho de código (máx 32KB)
        if len(code) > 32768:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="Código muito longo (máximo 32KB permitido)",
            )

        payload: dict[str, Any] = {
            "compiler": compiler,
            "code": code,
            "stdin": stdin,
        }

        url = f"{self.base_url}/compile.json"
        t_start = time.perf_counter()

        try:
            resp = await self._http_post(url, json_data=payload, timeout=18.0)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0

            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Wandbox rate limit excedido (HTTP 429)",
                )

            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Wandbox HTTP {resp.status_code}: {resp.text[:300]}",
                )

            body = resp.json()
            stdout = body.get("program_output") or ""
            stderr = body.get("program_error") or ""
            compiler_output = body.get("compiler_output") or ""
            compiler_error = body.get("compiler_error") or ""

            # Converte status string para int
            raw_status = body.get("status", "0")
            try:
                exit_code = int(raw_status)
            except Exception:
                exit_code = 0 if not stderr and not compiler_error else 1

            if compiler_error and not stderr:
                stderr = compiler_error

            # Trunca saídas gigantes para prevenir sobrecarga
            if len(stdout) > 8192:
                stdout = stdout[:8192] + "\n... [saída truncada]"
            if len(stderr) > 8192:
                stderr = stderr[:8192] + "\n... [erros truncados]"

            normalized = {
                "language": raw_lang,
                "compiler": compiler,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "compile_output": compiler_output,
                "execution_time_ms": round(elapsed_ms, 2),
                "source": "Wandbox",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            logger.error("[WandboxProvider] Erro ao executar código: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=f"Wandbox falhou: {e}",
            )
