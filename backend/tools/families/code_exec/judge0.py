"""backend/tools/families/code_exec/judge0.py — Provedor Judge0 CE (Fallback para execução remota de código via RapidAPI).
"""
from __future__ import annotations

import base64
import time
from typing import Any

from backend.logging_config import get_logger
from backend.tools.base import ToolProvider, ToolResult

logger = get_logger(__name__)

# Mapeamento oficial de IDs de linguagem do Judge0 CE
JUDGE0_LANG_IDS = {
    "python": 71,       # Python 3.8.1
    "py": 71,
    "javascript": 63,   # JavaScript (Node.js 12.14.0)
    "js": 63,
    "typescript": 74,   # TypeScript (3.7.4)
    "ts": 74,
    "c": 50,            # C (GCC 9.2.0)
    "cpp": 54,          # C++ (GCC 9.2.0)
    "c++": 54,
    "java": 62,         # Java (OpenJDK 13.0.1)
    "csharp": 51,       # C# (Mono 6.6.0.161)
    "cs": 51,
    "go": 60,           # Go (1.13.5)
    "golang": 60,
    "rust": 73,         # Rust (1.40.0)
    "rs": 73,
    "bash": 46,         # Bash (5.0.0)
    "php": 68,          # PHP (7.4.1)
    "ruby": 72,         # Ruby (2.7.0)
}


class Judge0Provider(ToolProvider):
    provider_id = "judge0"
    family = "code_exec"
    base_url = "https://judge0-ce.p.rapidapi.com"
    fallback_order = 2
    requires_key = True
    env_key_name = "JUDGE0_RAPIDAPI_KEY"

    def cache_key(self, params: dict) -> str:
        return ""

    @property
    def ttl_seconds(self) -> int:
        return 0

    async def execute(self, params: dict) -> ToolResult:
        api_key = self.get_api_key()
        if not api_key:
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error="JUDGE0_RAPIDAPI_KEY não configurada",
            )

        raw_lang = (params.get("language") or "python").strip().lower()
        lang_id = JUDGE0_LANG_IDS.get(raw_lang, 71)
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

        # Base64 encoding
        b64_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
        b64_stdin = base64.b64encode(stdin.encode("utf-8")).decode("ascii") if stdin else ""

        url = f"{self.base_url}/submissions?base64_encoded=true&wait=true"
        headers = {
            "x-rapidapi-host": "judge0-ce.p.rapidapi.com",
            "x-rapidapi-key": api_key,
            "content-type": "application/json",
        }
        payload = {
            "source_code": b64_code,
            "language_id": lang_id,
            "stdin": b64_stdin,
        }

        t_start = time.perf_counter()
        try:
            resp = await self._http_post(url, json_data=payload, headers=headers, timeout=18.0)
            elapsed_ms = (time.perf_counter() - t_start) * 1000.0

            if resp.status_code == 429:
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error="Judge0 RapidAPI rate limit (HTTP 429)",
                )
            if resp.status_code not in (200, 201):
                return ToolResult(
                    success=False,
                    data={},
                    provider_id=self.provider_id,
                    family=self.family,
                    error=f"Judge0 HTTP {resp.status_code}: {resp.text[:200]}",
                )

            body = resp.json()
            # Decode b64 stdout/stderr
            raw_stdout = body.get("stdout") or ""
            raw_stderr = body.get("stderr") or ""
            raw_compile = body.get("compile_output") or ""

            try:
                stdout = base64.b64decode(raw_stdout).decode("utf-8", errors="replace") if raw_stdout else ""
            except Exception:
                stdout = raw_stdout

            try:
                stderr = base64.b64decode(raw_stderr).decode("utf-8", errors="replace") if raw_stderr else ""
            except Exception:
                stderr = raw_stderr

            try:
                compile_output = base64.b64decode(raw_compile).decode("utf-8", errors="replace") if raw_compile else ""
            except Exception:
                compile_output = raw_compile

            status_desc = body.get("status", {}).get("description", "Finished")
            exit_code = body.get("exit_code", 0)

            normalized = {
                "language": raw_lang,
                "version": f"Judge0 CE (ID {lang_id})",
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "compile_output": compile_output,
                "status_description": status_desc,
                "execution_time_ms": round(elapsed_ms, 2),
                "source": "Judge0 CE",
            }

            return ToolResult(
                success=True,
                data=normalized,
                provider_id=self.provider_id,
                family=self.family,
                latency_ms=elapsed_ms,
            )

        except Exception as e:
            logger.error("[Judge0Provider] Erro ao executar código: %s", e)
            return ToolResult(
                success=False,
                data={},
                provider_id=self.provider_id,
                family=self.family,
                error=str(e),
            )
