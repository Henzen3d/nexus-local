"""
Text chunking for project files and chat turns.

Boundary-aware + markdown-structure-aware:
  - Prefer splitting on ## headings, list items, and paragraphs
  - Never start/end a chunk mid-word when avoidable
  - Overlap snaps to a safe boundary (not raw char offset)
  - Size + overlap configurable by file type / extension
"""

from __future__ import annotations

import re
from typing import Optional

# Default: ~300–400 tokens; enough for technical markdown bullets + context
_DEFAULT = {"size": 1000, "overlap": 120}

_BY_MIME_OR_EXT: dict[str, dict] = {
    "application/pdf": {"size": 1200, "overlap": 150},
    "pdf": {"size": 1200, "overlap": 150},
    "text/markdown": {"size": 1100, "overlap": 140},
    "md": {"size": 1100, "overlap": 140},
    "markdown": {"size": 1100, "overlap": 140},
    "text/csv": {"size": 1000, "overlap": 50},
    "csv": {"size": 1000, "overlap": 50},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "size": 1200,
        "overlap": 150,
    },
    "docx": {"size": 1200, "overlap": 150},
    "text/plain": {"size": 1000, "overlap": 120},
    "txt": {"size": 1000, "overlap": 120},
    "chat": {"size": 800, "overlap": 80},
}

# Generic MIME types that should not override a useful file extension
_GENERIC_MIME = {
    "application/octet-stream",
    "binary/octet-stream",
    "application/x-download",
    "text/plain",  # browsers often label .md as text/plain — prefer extension
}

_HEADING_RE = re.compile(r"(?m)^(#{1,6}\s+\S.*)$")
_LIST_ITEM_RE = re.compile(r"(?m)^(\s*(?:[-*+]|\d+[.)])\s+|\s*[-*+]\s+\[[ xX]\]\s+)")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")


def resolve_file_type(
    mime_type: Optional[str] = None,
    filename: Optional[str] = None,
) -> Optional[str]:
    """
    Prefer extension when MIME is missing/generic so .md gets markdown chunking
    even if the browser sent application/octet-stream or text/plain.
    """
    ext = None
    if filename:
        name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if "." in name:
            ext = name.rsplit(".", 1)[-1].lower().strip()

    mime = (mime_type or "").lower().strip() or None

    if ext and (not mime or mime in _GENERIC_MIME or mime not in _BY_MIME_OR_EXT):
        if ext in _BY_MIME_OR_EXT:
            return ext
    if mime and mime in _BY_MIME_OR_EXT:
        return mime
    if mime:
        tail = mime.split("/")[-1]
        if tail in _BY_MIME_OR_EXT:
            return tail
    return ext or mime


def _settings_for(file_type: Optional[str]) -> dict:
    if not file_type:
        return _DEFAULT
    key = file_type.lower().strip()
    if key in _BY_MIME_OR_EXT:
        return _BY_MIME_OR_EXT[key]
    ext = key.split("/")[-1].split(".")[-1]
    return _BY_MIME_OR_EXT.get(ext, _DEFAULT)


def _is_markdown(file_type: Optional[str]) -> bool:
    if not file_type:
        return False
    key = file_type.lower()
    return key in ("md", "markdown", "text/markdown") or key.endswith(".md")


def _snap_start_forward(text: str, pos: int) -> int:
    """If pos lands mid-token, move forward to the next whitespace/newline."""
    if pos <= 0:
        return 0
    if pos >= len(text):
        return len(text)
    # Already at a clean boundary
    if text[pos - 1].isspace() or text[pos].isspace():
        while pos < len(text) and text[pos] in " \t":
            pos += 1
        return pos
    # Mid-word: advance to end of token, then skip spaces
    n = len(text)
    while pos < n and not text[pos].isspace():
        pos += 1
    while pos < n and text[pos] in " \t":
        pos += 1
    return pos


def _snap_start_prefer_line(text: str, pos: int, hard_limit: int) -> int:
    """
    Prefer starting at a line boundary near `pos` (for overlap), without
    going past hard_limit. Falls back to word snap.
    """
    if pos <= 0:
        return 0
    if pos >= len(text):
        return len(text)

    # Search backward a bit for a newline (stay within overlap window)
    search_back = min(pos, 200)
    window = text[pos - search_back : pos]
    nl = window.rfind("\n")
    if nl >= 0:
        candidate = pos - search_back + nl + 1
        if candidate <= hard_limit:
            return candidate

    return _snap_start_forward(text, pos)


def _best_break(text: str, start: int, end: int, min_ratio: float = 0.45) -> int:
    """
    Find a clean break point in [start, end), preferring structure-aware seps.
    Returns absolute end index. If nothing good, returns end (caller may still
    snap mid-word only as last resort for pathological tokens).
    """
    n = len(text)
    if end >= n:
        return n

    window = text[start:end]
    min_pos = int(len(window) * min_ratio)

    # Prefer paragraph, then line, then sentence/clause, then space
    for sep in ("\n\n", "\n", ". ", "; ", ", ", " "):
        idx = window.rfind(sep)
        if idx >= min_pos:
            return start + idx + len(sep)

    return end


def _split_markdown_units(text: str) -> list[str]:
    """
    Split markdown into semantic units:
      1) by ATX headings (## …)
      2) within each section, by blank lines / whole list items
    Never splits mid-line.
    """
    if not text.strip():
        return []

    # First pass: sections by headings (keep heading with following body)
    parts: list[str] = []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        sections = [text]
    else:
        sections = []
        if matches[0].start() > 0:
            pre = text[: matches[0].start()].strip()
            if pre:
                sections.append(pre)
        for i, m in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append(text[m.start() : end].strip())

    for section in sections:
        if not section:
            continue
        # Split body into blocks (paragraphs / list clusters / tables), keep lines intact
        lines = section.split("\n")
        block: list[str] = []
        in_table = False

        def flush_block() -> None:
            nonlocal block, in_table
            if block:
                parts.append("\n".join(block).strip())
            block = []
            in_table = False

        for line in lines:
            is_blank = not line.strip()
            is_table = bool(_TABLE_LINE_RE.match(line))
            is_list = bool(_LIST_ITEM_RE.match(line))
            is_heading = bool(re.match(r"^#{1,6}\s+\S", line))

            # Markdown tables are atomic units (never split mid-table)
            if is_table:
                if block and not in_table:
                    flush_block()
                in_table = True
                block.append(line)
                continue
            if in_table:
                # blank or non-table ends the table unit
                flush_block()
                if is_blank:
                    continue

            if is_blank:
                flush_block()
                continue

            # Start a new unit on heading or list item after content
            if block and (is_heading or (is_list and not _LIST_ITEM_RE.match(block[-1]))):
                if is_heading:
                    flush_block()
                    block = [line]
                    continue
                # list after prose → flush prose first
                if not any(_LIST_ITEM_RE.match(b) for b in block):
                    flush_block()
                    block = [line]
                    continue

            block.append(line)

        flush_block()

    return [p for p in parts if p]


def _pack_units(units: list[str], size: int, overlap: int) -> list[str]:
    """
    Greedy pack of units into chunks ≤ size, with boundary-safe overlap
    carried as text suffix (not char-offset into previous chunk mid-token).
    Oversized units are sub-split on lines / soft breaks.
    """
    if not units:
        return []

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        piece = current.strip()
        if piece:
            chunks.append(piece)
        current = ""

    for unit in units:
        unit = unit.strip()
        if not unit:
            continue

        # Unit fits in current chunk
        if not current:
            if len(unit) <= size:
                current = unit
                continue
            # Oversized unit → line-aware subsplit
            for sub in _split_oversized(unit, size):
                if current and len(current) + 1 + len(sub) > size:
                    flush()
                if not current:
                    current = sub
                else:
                    current = current + "\n" + sub
            continue

        candidate = current + "\n\n" + unit
        if len(candidate) <= size:
            current = candidate
            continue

        # Current is full enough — flush and start new with optional overlap
        prev = current
        flush()

        def _start_with(piece: str) -> None:
            """Start a new chunk from piece, sub-splitting if oversized (never flush whole)."""
            nonlocal current
            if len(piece) <= size:
                current = piece
                return
            for sub in _split_oversized(piece, size):
                if current and len(current) + 1 + len(sub) > size:
                    flush()
                if not current:
                    current = sub
                else:
                    current = current + "\n" + sub

        if overlap > 0 and prev:
            tail = _overlap_tail(prev, overlap)
            if tail and len(tail) + 2 + len(unit) <= size:
                current = tail + "\n\n" + unit
                continue
            if tail and len(unit) <= size:
                # tail + unit too big: start with unit only (overlap already in prev chunk)
                current = unit
                continue
            # unit itself oversized
            _start_with(unit)
            continue

        _start_with(unit)

    flush()
    return chunks


def _overlap_tail(text: str, overlap: int) -> str:
    """Last ~overlap chars of text, starting at a clean line/word boundary."""
    if overlap <= 0 or not text:
        return ""
    if len(text) <= overlap:
        return text
    start = len(text) - overlap
    start = _snap_start_prefer_line(text, start, hard_limit=len(text))
    tail = text[start:].strip()
    return tail if tail and tail != text.strip() else ""


def _is_table_block(text: str) -> bool:
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 2:
        return False
    return sum(1 for ln in lines if _TABLE_LINE_RE.match(ln)) >= max(2, len(lines) // 2)


def _split_table_atomic(text: str, size: int) -> list[str]:
    """
    Keep tables atomic when possible. If too large, split by full rows and
    repeat the header row so each chunk keeps column context.
    """
    lines = text.split("\n")
    table_lines = [ln for ln in lines if _TABLE_LINE_RE.match(ln) or not ln.strip()]
    if len(text) <= size:
        return [text.strip()]

    # Header = first two table lines (header + separator) when present
    non_empty = [ln for ln in lines if ln.strip()]
    header: list[str] = []
    body_start = 0
    if len(non_empty) >= 2 and _TABLE_LINE_RE.match(non_empty[0]):
        header = [non_empty[0]]
        if re.match(r"^\s*\|?\s*:?-{2,}", non_empty[1].replace(" ", "")) or set(
            non_empty[1].replace("|", "").replace(":", "").replace("-", "").strip()
        ) <= {"", " "}:
            header.append(non_empty[1])
            body_start = 2
        else:
            body_start = 1
    body = non_empty[body_start:]
    header_text = "\n".join(header)
    header_len = len(header_text) + (1 if header else 0)

    out: list[str] = []
    buf_rows: list[str] = []
    for row in body:
        candidate_rows = buf_rows + [row]
        candidate = (header_text + "\n" if header else "") + "\n".join(candidate_rows)
        if len(candidate) <= size or not buf_rows:
            buf_rows.append(row)
            # Single row still oversized → soft-split as last resort
            if len(candidate) > size and len(buf_rows) == 1:
                out.extend(_split_by_soft_breaks(candidate, size))
                buf_rows = []
        else:
            chunk = (header_text + "\n" if header else "") + "\n".join(buf_rows)
            out.append(chunk.strip())
            buf_rows = [row]
    if buf_rows:
        chunk = (header_text + "\n" if header else "") + "\n".join(buf_rows)
        out.append(chunk.strip())
    return [c for c in out if c] or [text[:size]]


def _split_oversized(text: str, size: int) -> list[str]:
    """Split a single oversized unit without mid-word cuts when possible."""
    text = text.strip()
    if len(text) <= size:
        return [text]

    # Tables: never cut mid-row; repeat header across chunks
    if _is_table_block(text):
        return _split_table_atomic(text, size)

    # Prefer whole lines
    lines = text.split("\n")
    if len(lines) > 1:
        out: list[str] = []
        buf = ""
        for line in lines:
            if not buf:
                if len(line) <= size:
                    buf = line
                else:
                    out.extend(_split_by_soft_breaks(line, size))
                continue
            if len(buf) + 1 + len(line) <= size:
                buf = buf + "\n" + line
            else:
                out.append(buf)
                if len(line) <= size:
                    buf = line
                else:
                    out.extend(_split_by_soft_breaks(line, size))
                    buf = ""
        if buf:
            out.append(buf)
        return out

    return _split_by_soft_breaks(text, size)


def _split_by_soft_breaks(text: str, size: int) -> list[str]:
    """Character window with soft boundary preference + no mid-word start."""
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            end = _best_break(text, start, end, min_ratio=0.4)
            # Absolute last resort: if break still mid-word near end, force space
            if end < n and not text[end - 1].isspace() and not text[end].isspace():
                sp = text.rfind(" ", start + max(1, (end - start) // 3), end)
                if sp > start:
                    end = sp + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        # Advance with small structural overlap snapped cleanly
        next_start = max(end - min(80, size // 8), start + 1)
        next_start = _snap_start_forward(text, next_start)
        if next_start <= start:
            next_start = end
        start = next_start
    return chunks


def _chunk_plain(text: str, size: int, overlap: int) -> list[str]:
    """Paragraph-preferring sliding window for non-markdown text."""
    cleaned = text.strip()
    if len(cleaned) <= size:
        return [cleaned]

    chunks: list[str] = []
    start = 0
    n = len(cleaned)

    while start < n:
        end = min(start + size, n)
        if end < n:
            end = _best_break(cleaned, start, end, min_ratio=0.45)
            if end < n and not cleaned[end - 1].isspace() and not cleaned[end].isspace():
                sp = cleaned.rfind(" ", start + max(1, (end - start) // 3), end)
                if sp > start:
                    end = sp + 1

        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= n:
            break

        next_start = max(end - overlap, start + 1) if overlap else end
        next_start = _snap_start_prefer_line(cleaned, next_start, hard_limit=end)
        if next_start <= start:
            next_start = end
        start = next_start

    return chunks


def chunk_text(
    text: str,
    file_type: Optional[str] = None,
    chunk_size: Optional[int] = None,
    overlap: Optional[int] = None,
    filename: Optional[str] = None,
) -> list[str]:
    """
    Split text into overlapping, boundary-aware chunks.

    For markdown (md / text/markdown), split by headings and list/paragraph
    units, then pack. For other types, use soft boundary sliding windows.
    """
    if not text or not text.strip():
        return []

    cleaned = text.replace("\r\n", "\n").strip()
    resolved = resolve_file_type(file_type, filename) if filename else file_type
    # If only file_type given, still try resolve (handles "file.md" style)
    if filename is None and file_type and ("/" not in file_type and "." in file_type):
        resolved = resolve_file_type(None, file_type)
    elif filename is None:
        resolved = resolve_file_type(file_type, None)

    cfg = _settings_for(resolved)
    size = max(200, chunk_size if chunk_size is not None else cfg["size"])
    ov = max(0, min(overlap if overlap is not None else cfg["overlap"], size // 3))

    if len(cleaned) <= size:
        return [cleaned]

    # Heuristic: treat as markdown if type says so OR content has ATX headings
    as_md = _is_markdown(resolved) or bool(_HEADING_RE.search(cleaned[:2000]))

    if as_md:
        units = _split_markdown_units(cleaned)
        packed = _pack_units(units, size=size, overlap=ov)
        if packed:
            return packed
        # Fallback if unitizer produced nothing useful
        return _chunk_plain(cleaned, size=size, overlap=ov)

    return _chunk_plain(cleaned, size=size, overlap=ov)
