"""Detecção e persistência de artifacts (HTML, SVG, JSX, Markdown, code blocks).

Extraído de `backend/routers/chat.py` para ser compartilhado entre o
controller WebSocket e o orquestrador do Fusion, eliminando a duplicação
de responsabilidade de detecção/persistência de artifacts.
"""

from __future__ import annotations

import html as _html_lib
import re
import uuid

from backend.logging_config import get_logger

logger = get_logger(__name__)

# Linguagens cujo tratamento já está nas regras específicas de html/svg/jsx
# (não caem no detector genérico de blocos de código >= 15 linhas)
_EXCLUDED_LANGS_FROM_CODE = {
    "html", "svg", "xml", "jsx", "tsx", "markdown", "md",
    "bash", "sh", "shell", "zsh", "powershell", "ps1", "cmd", "bat", "plaintext", "txt",
}


def _extract_html_svg_title(content: str, fallback: str) -> str:
    """Extrai o conteúdo da tag <title> de HTML ou SVG gerado por LLM."""
    if not content:
        return fallback

    stripped = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    m = re.search(r'<title[^>]*>(.*?)</title>', stripped, re.IGNORECASE | re.DOTALL)
    if not m:
        return fallback

    raw = m.group(1)
    cdata = re.match(r'\s*<!\[CDATA\[(.*?)\]\]>\s*$', raw, re.DOTALL)
    if cdata:
        raw = cdata.group(1)

    unescaped = _html_lib.unescape(raw)
    title = ' '.join(unescaped.split())
    if not title:
        return fallback
    return title[:80]


def _extract_markdown_title(content: str, fallback: str = "Document") -> str:
    """Extrai o primeiro heading real (# a ######) de um documento Markdown."""
    if not content:
        return fallback
    no_code = re.sub(r'```[\s\S]*?```', '', content)
    m = re.search(r'^#{1,6}\s+(.+)$', no_code, re.MULTILINE)
    if not m:
        return fallback
    title = m.group(1).strip().rstrip('#').strip()
    return title[:80] if title else fallback


def _extract_jsx_title(content: str, fallback: str = "React Component") -> str:
    """Extrai um título significativo de código JSX/TSX."""
    m = re.search(r'(?:function|class|const|let)\s+([A-Z][a-zA-Z0-9_$]*)', content)
    if m:
        name = m.group(1)
        spaced = re.sub(r'(?<=[a-z0-9])(?=[A-Z])', ' ', name)
        return spaced[:80]
    return fallback


def strip_thinking_tags(content: str) -> str:
    """Remove blocos e tags de raciocínio (<think>...</think>, etc.)."""
    if not content:
        return ""

    tags = ["think", "thinking", "reasoning", "analysis", "reflection", "assistant_thought"]
    pattern = r"<(" + "|".join(tags) + r")(?:\s+[^>]*)?>[\s\S]*?</\1>"
    cleaned = re.sub(pattern, "", content, flags=re.IGNORECASE)

    pattern_unclosed = r"<(" + "|".join(tags) + r")(?:\s+[^>]*)?>[\s\S]*$"
    cleaned = re.sub(pattern_unclosed, "", cleaned, flags=re.IGNORECASE)

    pattern_orphan = r"</(" + "|".join(tags) + r")>"
    cleaned = re.sub(pattern_orphan, "", cleaned, flags=re.IGNORECASE)

    return cleaned.strip()


def detect_artifacts(content: str) -> list[dict]:
    """Analisa o conteúdo de uma resposta e extrai todos os Artifacts presentes."""
    content = strip_thinking_tags(content)
    if not content:
        return []

    artifacts = []

    for m in re.finditer(r'```(\w*)\s*([\s\S]+?)```', content):
        lang = m.group(1).lower()
        body = m.group(2).strip()
        line_count = len(body.split("\n"))

        if lang == "html":
            artifacts.append({
                "type": "html",
                "title": _extract_html_svg_title(body, fallback="HTML Document"),
                "content": body,
            })
        elif lang == "svg":
            artifacts.append({
                "type": "svg",
                "title": _extract_html_svg_title(body, fallback="SVG Image"),
                "content": body,
            })
        elif lang in ("jsx", "tsx"):
            if line_count >= 8:
                artifacts.append({
                    "type": "jsx",
                    "title": _extract_jsx_title(body, fallback="React Component"),
                    "content": body,
                })
        elif lang in ("markdown", "md"):
            if line_count >= 8:
                artifacts.append({
                    "type": "markdown",
                    "title": _extract_markdown_title(body, fallback="Markdown Document"),
                    "content": body,
                })
        elif lang not in _EXCLUDED_LANGS_FROM_CODE:
            if line_count >= 15:
                artifacts.append({
                    "type": "code",
                    "title": f"{lang.upper() if lang else 'CODE'} Code",
                    "content": body,
                })

    if not artifacts:
        html_bare = re.search(
            r'(<!DOCTYPE\s+html[\s\S]+?</html>|<html[\s\S]+?</html>)',
            content,
            re.IGNORECASE,
        )
        if html_bare:
            body = html_bare.group(1).strip()
            artifacts.append({
                "type": "html",
                "title": _extract_html_svg_title(body, fallback="HTML Document"),
                "content": body,
            })

        svg_bare = re.search(r'(<svg[\s\S]+?</svg>)', content, re.IGNORECASE)
        if svg_bare:
            body = svg_bare.group(1).strip()
            artifacts.append({
                "type": "svg",
                "title": _extract_html_svg_title(body, fallback="SVG Image"),
                "content": body,
            })

    if not artifacts:
        lines = content.split("\n")
        real_heading_count = sum(
            1 for line in lines if re.match(r'^#{1,6}\s+\S', line)
        )
        if len(lines) >= 20 and real_heading_count >= 2:
            artifacts.append({
                "type": "markdown",
                "title": _extract_markdown_title(content.strip(), fallback="Document"),
                "content": content.strip(),
            })

    return artifacts


def detect_artifact(content: str) -> dict | None:
    """Retorna o primeiro Artifact detectado (retrocompatibilidade)."""
    arts = detect_artifacts(content)
    return arts[0] if arts else None


async def save_artifact(db, conv_id: str, msg_id: str, detected: dict) -> str:
    """Persiste o artifact detectado no banco com versionamento por grupo."""
    async with db.execute(
        """SELECT artifact_group_id, version FROM artifacts
           WHERE conv_id = ? AND type = ?
           ORDER BY version DESC LIMIT 1""",
        (conv_id, detected["type"])
    ) as cur:
        existing = await cur.fetchone()

    if existing:
        group_id = existing[0]
        new_version = existing[1] + 1
    else:
        group_id = str(uuid.uuid4())
        new_version = 1

    artifact_id = str(uuid.uuid4())
    await db.execute(
        """INSERT INTO artifacts (id, conv_id, msg_id, type, title, content, version, artifact_group_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            artifact_id,
            conv_id,
            msg_id,
            detected["type"],
            detected["title"],
            detected["content"],
            new_version,
            group_id,
        ),
    )
    await db.commit()
    return artifact_id
