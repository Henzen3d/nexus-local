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
    "nexus-ui", "nexus", "nexus_ui",
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


_RE_FILENAME_COMMENT = re.compile(
    r'^(?:#|//|<!--|/\*|\*)\s*([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]{1,8})(?:\s*-->|\s*\*\/)?\s*$',
    re.MULTILINE,
)


def _extract_code_filename(body: str, lang: str, fallback_title: str) -> str:
    """Extrai o nome do arquivo da primeira ou segunda linha comentada de um bloco de código."""
    if not body:
        return fallback_title
    first_lines = body.strip().split("\n")[:2]
    for line in first_lines:
        m = _RE_FILENAME_COMMENT.match(line.strip())
        if m:
            candidate = m.group(1).strip()
            if "/" in candidate:
                candidate = candidate.split("/")[-1]
            if "\\" in candidate:
                candidate = candidate.split("\\")[-1]
            if len(candidate) <= 64:
                return candidate
    return fallback_title


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


# Padrões que indicam pedido explícito de documento/relatório/arquivo pelo usuário
_DOC_INTENT_PATTERN = re.compile(
    r'\b('
    r'documento|relat[oó]rio|artigo|redaç[aã]o|redacao|ensaio|'
    r'apostila|manual|especificaç[aã]o|especificacao|documentaç[aã]o|documentacao|'
    r'minuta|proposta\s+comercial|proposta|termo\s+de|contrato|'
    r'arquivo\s+markdown|em\s+markdown|salve?\s+em\s+markdown|gerar\s+markdown|'
    r'crie?\s+(?:um\s+)?(?:documento|arquivo|relat[oó]rio|artigo|manual)|'
    r'ger(?:e|ar)\s+(?:um\s+)?(?:documento|arquivo|relat[oó]rio|artigo|manual)|'
    r'artefato|artifact|'
    r'document|report|article|essay|specification|spec|whitepaper|'
    r'create\s+(?:a\s+)?(?:document|file|report|spec|article)'
    r')\b',
    re.IGNORECASE,
)

# Aberturas conversacionais que desqualificam um texto de ser um documento puro
_CONVERSATIONAL_PREFIX_PATTERN = re.compile(
    r'^\s*('
    r'claro[,!.]|certamente[,!.]|com certeza[,!.]|ol[aá][,!.]|oi[,!.]|'
    r'bom dia|boa tarde|boa noite|aqui est[aá][,!.]|aqui est[aã]o[,!.]|veja abaixo[,!.]|'
    r'[eé] muito atencioso|compreendo[,!.]|entendo[,!.]|'
    r'espero ter ajudado|espero que ajude|boa sorte[,!.]|'
    r'com base (?:nas?|nos?)|de acordo com|'
    r'sure[,!.]|certainly[,!.]|hello[,!.]|hi[,!.]|here is[,!.]|here are[,!.]|'
    r'i hope|as requested'
    r')',
    re.IGNORECASE,
)


def detect_artifacts(content: str, user_message: str = "") -> list[dict]:
    """Analisa o conteúdo de uma resposta e extrai todos os Artifacts presentes.

    Artifacts legítimos incluem:
    - Blocos de código com linguagem explícita (HTML, SVG, JSX, Markdown, scripts >= 15 linhas)
    - Documentos HTML/SVG completos soltos (tags <!DOCTYPE html> ou <svg>)
    - Markdown solto SOMENTE se o usuário solicitou explicitamente um documento/relatório
      e a resposta foi estruturada desde a primeira linha como documento formal (sem preâmbulos de chat).
    """
    content = strip_thinking_tags(content)
    if not content:
        return []

    artifacts = []

    for m in re.finditer(r'```(\w*)\s*([\s\S]+?)```', content):
        lang = m.group(1).lower()
        body = m.group(2).strip()
        line_count = len(body.split("\n"))

        if lang == "html":
            fallback_title = _extract_html_svg_title(body, fallback="HTML Document")
            artifacts.append({
                "type": "html",
                "title": _extract_code_filename(body, lang, fallback_title),
                "content": body,
            })
        elif lang == "svg":
            fallback_title = _extract_html_svg_title(body, fallback="SVG Image")
            artifacts.append({
                "type": "svg",
                "title": _extract_code_filename(body, lang, fallback_title),
                "content": body,
            })
        elif lang in ("jsx", "tsx"):
            if line_count >= 8:
                fallback_title = _extract_jsx_title(body, fallback="React Component")
                artifacts.append({
                    "type": "jsx",
                    "title": _extract_code_filename(body, lang, fallback_title),
                    "content": body,
                })
        elif lang in ("markdown", "md"):
            if line_count >= 8:
                fallback_title = _extract_markdown_title(body, fallback="Markdown Document")
                artifacts.append({
                    "type": "markdown",
                    "title": _extract_code_filename(body, lang, fallback_title),
                    "content": body,
                })
        elif lang not in _EXCLUDED_LANGS_FROM_CODE:
            if line_count >= 15:
                fallback_title = f"{lang.upper() if lang else 'CODE'} Code"
                artifacts.append({
                    "type": "code",
                    "title": _extract_code_filename(body, lang, fallback_title),
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

    # Fallback para markdown solto: apenas se o usuário pediu explicitamente um documento
    # e a resposta é estruturada formalmente (sem abertura de conversa, começando com #)
    if not artifacts and user_message:
        if _DOC_INTENT_PATTERN.search(user_message):
            raw_lines = content.split("\n")
            non_empty_lines = [line for line in raw_lines if line.strip()]
            first_line = non_empty_lines[0] if non_empty_lines else ""
            is_conversational = bool(_CONVERSATIONAL_PREFIX_PATTERN.match(first_line))
            starts_with_doc_title = bool(re.match(r'^(#\s+\S|---\s*$)', first_line))
            real_heading_count = sum(
                1 for line in raw_lines if re.match(r'^#{1,6}\s+\S', line)
            )
            if not is_conversational and starts_with_doc_title and len(raw_lines) >= 15 and real_heading_count >= 2:
                artifacts.append({
                    "type": "markdown",
                    "title": _extract_markdown_title(content.strip(), fallback="Document"),
                    "content": content.strip(),
                })

    return artifacts


def detect_artifact(content: str, user_message: str = "") -> dict | None:
    """Retorna o primeiro Artifact detectado (retrocompatibilidade)."""
    arts = detect_artifacts(content, user_message=user_message)
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
