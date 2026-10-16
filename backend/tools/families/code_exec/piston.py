"""backend/tools/families/code_exec/piston.py — Provedor Piston para execução remota de código (Primário).
"""
from __future__ import annotations

import time
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)

# Mapeamento de extensões e aliases comuns de linguagem para o Piston
PISTON_LANG_MAP = {
    "py": "python",
    "python3": "python",
    "js": "javascript",
    "node": "javascript",
    "ts": "typescript",
    "c++": "cpp",
    "golang": "go",
    "rs": "rust",
    "cs": "csharp",
    "c#": "csharp",
    "sh": "bash",
    "shell": "bash",
}

LANGUAGE_FILES = {
    "python": "main.py",
    "javascript": "index.js",
    "typescript": "index.ts",
    "java": "Main.java",
    "cpp": "main.cpp",
    "c": "main.c",
    "go": "main.go",
    "rust": "main.rs",
    "csharp": "Program.cs",
    "php": "index.php",
    "ruby": "main.rb",
    "bash": "script.sh",
}


class PistonProvider(ToolProvider):
    provider_id = "piston"
    family = "code_exec"
    base_url = "https://emkc.org/api/v2/piston"
    fallback_order = 1
    requires_key = False

    def cache_key(self, params: dict) -> str:
        # Execução de código nunca deve ser cacheada
        return ""

    @property
    def ttl_seconds(self) -> int:
        return 0

    async def execute(self, params: dict) -> ToolResult:
        raw_lang = (params.get("language") or "python").strip().lower()
        lang = PISTON_LANG_MAP.get(raw_lang, raw_lang)
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

        filename = LANGUAGE_FILES.get(lang, "script.txt")
        payload = {
            "language": lang,
            "version": "*",
            "files": [{"name": filename, "content": code}],
            "stdin": stdin,
            "args": [],
            "compile_timeout": 10000,
            "run_timeout": 5000,
        }

        url = f"{self.base_url}/execute"
        t_start = time.perf_counter()

        try:
            resp = await self._http_post(url, json_data=payload, timeout=16.0)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0

            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Piston rate limit (HTTP 429)",
                )
            if resp.status_code != 200:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Piston HTTP {resp.status_code}: {resp.text[:200]}",
                )

            body = resp.json()
            run_stage = body.get("run", {})
            compile_stage = body.get("compile", {})

            stdout = run_stage.get("stdout", "")
            stderr = run_stage.get("stderr", "")
            compile_output = compile_stage.get("output", "")
            exit_code = run_stage.get("code", 0)

            # Se falhou na compilação, o erro geralmente fica em compile.output
            if compile_stage.get("code") is not None and compile_stage.get("code") != 0:
                exit_code = compile_stage.get("code")
                stderr = (compile_output or "") + ("\n" if stderr else "") + stderr

            # Trunca saídas gigantes para prevenir sobrecarga de contexto
            if len(stdout) > 8192:
                stdout = stdout[:8192] + "\n... [saída truncada]"
            if len(stderr) > 8192:
                stderr = stderr[:8192] + "\n... [erros truncados]"

            normalized = {
                "language": body.get("language", lang),
                "version": body.get("version", ""),
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "compile_output": compile_output,
                "execution_time_ms": round(elapsed_ms, 2),
                "source": "Piston",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            logger.error("[PistonProvider] Erro ao executar código: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
