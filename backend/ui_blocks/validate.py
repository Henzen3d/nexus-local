"""Validador do contrato nexus-ui/1 para blocos de interface inteligente.

Garante esquema fixo, limites de tamanho e sanitização estrita de URLs e ações.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
from typing import Any
from urllib.parse import urlparse

ID_REGEX = re.compile(r"^[a-z0-9_-]{1,32}$")
SELECT_VALUE_REGEX = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
FIELD_ID_REGEX = re.compile(r"^[a-z0-9_]{1,32}$")
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z0-9_]+)\}")

MAX_RAW_JSON_LENGTH = 16000
MAX_BLOCKS = 4


def is_allowed_image_url(url: str) -> bool:
    """Verifica se uma URL de imagem atende às regras da Seção 6 da spec."""
    if not isinstance(url, str):
        return False
    url = url.strip()
    if not url or len(url) > 2048:
        return False

    lower = url.lower()
    # Esquemas expressamente proibidos
    for blocked in ("javascript:", "data:", "blob:", "file:"):
        if lower.startswith(blocked):
            return False

    # URL relativa do app (anexos locais, ex: /attachments/...)
    if url.startswith("/") and not url.startswith("//"):
        return True

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.username or parsed.password:
        return False

    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()

    if scheme not in ("http", "https") or not host:
        return False

    allowed_hosts_env = os.getenv("INTELLIGENT_UI_IMAGE_HOSTS", "")
    allowed_hosts = {h.strip().lower() for h in allowed_hosts_env.split(",") if h.strip()}

    if host in allowed_hosts:
        return True

    # Checagem de IP privado / rede local
    allow_private = os.getenv("INTELLIGENT_UI_ALLOW_PRIVATE_HTTP", "false").lower() in ("true", "1", "yes")
    is_private_target = False

    if host.endswith(".local") or host == "localhost":
        is_private_target = True
    else:
        try:
            ip_obj = ipaddress.ip_address(host)
            if ip_obj.is_private or ip_obj.is_loopback:
                is_private_target = True
        except ValueError:
            pass

    if is_private_target:
        return allow_private and scheme in ("http", "https")

    return False


def _validate_progress(block: dict[str, Any]) -> dict[str, Any] | None:
    label = block.get("label")
    if not isinstance(label, str) or not (1 <= len(label) <= 80):
        return None

    has_value = "value" in block
    has_max = "max" in block
    if has_value != has_max:
        return None

    clean_value = None
    clean_max = None
    if has_value and has_max:
        val = block.get("value")
        mx = block.get("max")
        if not (isinstance(val, (int, float)) and isinstance(mx, (int, float))):
            return None
        if math.isnan(val) or math.isnan(mx) or math.isinf(val) or math.isinf(mx):
            return None
        if not (1 <= mx <= 1000 and 0 <= val <= mx):
            return None
        clean_value = round(float(val), 2) if isinstance(val, float) else val
        clean_max = round(float(mx), 2) if isinstance(mx, float) else mx

    steps = block.get("steps")
    clean_steps: list[dict[str, Any]] = []
    if steps is not None:
        if not isinstance(steps, list) or len(steps) > 12:
            return None
        active_count = 0
        seen_step_ids = set()
        for s in steps:
            if not isinstance(s, dict):
                return None
            s_id = s.get("id")
            s_label = s.get("label")
            s_state = s.get("state")
            if not isinstance(s_id, str) or not ID_REGEX.match(s_id) or s_id in seen_step_ids:
                return None
            seen_step_ids.add(s_id)
            if not isinstance(s_label, str) or not (1 <= len(s_label) <= 80):
                return None
            if s_state not in ("pending", "active", "done", "error"):
                return None
            if s_state == "active":
                active_count += 1
            clean_steps.append({"id": s_id, "label": s_label, "state": s_state})
        if active_count > 1:
            return None

    if clean_value is None and not clean_steps:
        return None

    out: dict[str, Any] = {"id": block["id"], "type": "progress", "label": label}
    if clean_value is not None:
        out["value"] = clean_value
        out["max"] = clean_max
    if clean_steps:
        out["steps"] = clean_steps
    return out


def _validate_card(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 80):
        return None

    out: dict[str, Any] = {"id": block["id"], "type": "card", "title": title}

    body = block.get("body")
    if body is not None:
        if isinstance(body, str) and 0 <= len(body) <= 400:
            out["body"] = body
        else:
            return None

    facts = block.get("facts")
    if facts is not None:
        if not isinstance(facts, list) or len(facts) > 6:
            return None
        clean_facts = []
        for f in facts:
            if not isinstance(f, dict):
                return None
            f_label = f.get("label")
            f_val = f.get("value")
            if not isinstance(f_label, str) or not (1 <= len(f_label) <= 40):
                return None
            if not isinstance(f_val, str) or not (1 <= len(f_val) <= 40):
                return None
            clean_facts.append({"label": f_label, "value": f_val})
        out["facts"] = clean_facts

    image = block.get("image")
    if image is not None and isinstance(image, dict):
        url = image.get("url")
        alt = image.get("alt")
        if isinstance(url, str) and isinstance(alt, str) and (1 <= len(alt) <= 120):
            if is_allowed_image_url(url):
                out["image"] = {"url": url.strip(), "alt": alt}
            # Se a URL não for permitida, o cartão permanece sem imagem (regra spec 4.2 / 6)

    return out


def _validate_chart(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 80):
        return None

    kind = block.get("kind")
    if kind not in ("bar", "line", "compare"):
        return None

    x_key = block.get("x_key")
    if not isinstance(x_key, str) or not (1 <= len(x_key) <= 40):
        return None

    series = block.get("series")
    if not isinstance(series, list):
        return None

    if kind == "bar" and len(series) != 1:
        return None
    elif kind == "line" and not (1 <= len(series) <= 3):
        return None
    elif kind == "compare" and not (2 <= len(series) <= 4):
        return None

    clean_series = []
    seen_series_keys = set()
    for s in series:
        if not isinstance(s, dict):
            return None
        s_key = s.get("key")
        s_label = s.get("label", s_key)
        if not isinstance(s_key, str) or not (1 <= len(s_key) <= 40) or s_key in seen_series_keys:
            return None
        if not isinstance(s_label, str) or not (1 <= len(s_label) <= 60):
            return None
        seen_series_keys.add(s_key)
        clean_series.append({"key": s_key, "label": s_label})

    rows = block.get("rows")
    if not isinstance(rows, list) or not (1 <= len(rows) <= 24):
        return None

    clean_rows = []
    for r in rows:
        if not isinstance(r, dict):
            return None
        if x_key not in r:
            return None
        x_val = r[x_key]
        if not isinstance(x_val, (str, int)) or (isinstance(x_val, str) and not (1 <= len(x_val) <= 40)):
            return None
        row_obj: dict[str, Any] = {x_key: str(x_val)}
        for s_key in seen_series_keys:
            if s_key not in r:
                return None
            val = r[s_key]
            if not isinstance(val, (int, float)) or isinstance(val, bool):
                return None
            if math.isnan(val) or math.isinf(val):
                return None
            row_obj[s_key] = val
        clean_rows.append(row_obj)

    return {
        "id": block["id"],
        "type": "chart",
        "title": title,
        "kind": kind,
        "x_key": x_key,
        "series": clean_series,
        "rows": clean_rows,
    }


def _validate_controls(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 80):
        return None

    submit_label = block.get("submit_label")
    if not isinstance(submit_label, str) or not (1 <= len(submit_label) <= 32):
        return None

    fields = block.get("fields")
    if not isinstance(fields, list) or not (1 <= len(fields) <= 4):
        return None

    clean_fields = []
    seen_field_ids = set()
    select_fields = []

    for f in fields:
        if not isinstance(f, dict):
            return None
        f_id = f.get("id")
        f_kind = f.get("kind")
        f_label = f.get("label", f_id)
        if not isinstance(f_id, str) or not FIELD_ID_REGEX.match(f_id) or f_id in seen_field_ids:
            return None
        seen_field_ids.add(f_id)
        if not isinstance(f_label, str) or not (1 <= len(f_label) <= 60):
            return None

        clean_f: dict[str, Any] = {"id": f_id, "kind": f_kind, "label": f_label}

        if f_kind == "text":
            placeholder = f.get("placeholder")
            if placeholder is not None and isinstance(placeholder, str) and len(placeholder) <= 200:
                clean_f["placeholder"] = placeholder
        elif f_kind in ("number", "range"):
            mn = f.get("min")
            mx = f.get("max")
            if not (isinstance(mn, (int, float)) and isinstance(mx, (int, float))):
                return None
            if math.isnan(mn) or math.isnan(mx) or math.isinf(mn) or math.isinf(mx):
                return None
            if mn >= mx or (mx - mn) > 1_000_000:
                return None
            clean_f["min"] = mn
            clean_f["max"] = mx
            step = f.get("step", 1)
            if isinstance(step, (int, float)) and step > 0 and not math.isnan(step) and not math.isinf(step):
                clean_f["step"] = step
            default = f.get("default")
            if isinstance(default, (int, float)) and mn <= default <= mx:
                clean_f["default"] = default
        elif f_kind == "select":
            opts = f.get("options")
            if not isinstance(opts, list) or not (2 <= len(opts) <= 8):
                return None
            clean_opts = []
            seen_vals = set()
            for o in opts:
                if not isinstance(o, dict):
                    return None
                val = o.get("value")
                lbl = o.get("label", val)
                if not isinstance(val, str) or not SELECT_VALUE_REGEX.match(val) or val in seen_vals:
                    return None
                seen_vals.add(val)
                if not isinstance(lbl, str) or not (1 <= len(lbl) <= 40):
                    return None
                clean_opts.append({"value": val, "label": lbl})
            clean_f["options"] = clean_opts
            select_fields.append(f_id)
        else:
            return None

        clean_fields.append(clean_f)

    # computed opcional
    clean_computed = None
    computed = block.get("computed")
    if computed is not None:
        if isinstance(computed, dict):
            tmpl = computed.get("template")
            formula = computed.get("formula")
            if isinstance(tmpl, str) and (1 <= len(tmpl) <= 200) and isinstance(formula, str) and (1 <= len(formula) <= 300):
                clean_computed = {"template": tmpl, "formula": formula}
            else:
                return None
        else:
            return None

    # action
    action = block.get("action")
    if not isinstance(action, dict):
        return None
    action_name = action.get("name")
    if action_name not in ("send_message", "set_model"):
        return None

    clean_action: dict[str, Any] = {"name": action_name}

    if action_name == "send_message":
        tmpl = action.get("template")
        if not isinstance(tmpl, str) or not (1 <= len(tmpl) <= 500):
            return None
        placeholders = PLACEHOLDER_REGEX.findall(tmpl)
        valid_keys = set(seen_field_ids)
        if clean_computed:
            valid_keys.add("resultado")
        for ph in placeholders:
            if ph not in valid_keys:
                return None
        clean_action["template"] = tmpl
    elif action_name == "set_model":
        target_field = action.get("field")
        if not target_field or target_field not in select_fields:
            return None
        clean_action["field"] = target_field

    out: dict[str, Any] = {
        "id": block["id"],
        "type": "controls",
        "title": title,
        "submit_label": submit_label,
        "fields": clean_fields,
        "action": clean_action,
    }
    if clean_computed:
        out["computed"] = clean_computed
    return out


def _validate_sandbox(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not (1 <= len(title) <= 80):
        return None

    html = block.get("html")
    if not isinstance(html, str) or not (1 <= len(html) <= 20000):
        return None

    out: dict[str, Any] = {
        "id": block["id"],
        "type": "sandbox",
        "title": title,
        "html": html,
    }

    initial_height = block.get("initial_height")
    if initial_height is not None:
        if isinstance(initial_height, int) and 120 <= initial_height <= 800:
            out["initial_height"] = initial_height
        else:
            out["initial_height"] = 300
    else:
        out["initial_height"] = 300

    css = block.get("css")
    if css is not None and isinstance(css, str) and len(css) <= 20000:
        out["css"] = css

    js = block.get("js")
    if js is not None and isinstance(js, str) and len(js) <= 30000:
        out["js"] = js

    standalone_download = block.get("standalone_download")
    out["standalone_download"] = bool(standalone_download) if standalone_download is not None else True

    return out


def validate_envelope(raw: str | dict[str, Any]) -> dict[str, Any] | None:
    """Valida um JSON bruto ou dicionário com o envelope nexus-ui/1.

    Retorna o dicionário sanitizado {"v": 1, "blocks": [...]} ou None se inválido.
    """
    if isinstance(raw, str):
        if len(raw) > MAX_RAW_JSON_LENGTH:
            return None
        try:
            data = json.loads(raw)
        except Exception:
            return None
    elif isinstance(raw, dict):
        try:
            raw_str = json.dumps(raw)
            if len(raw_str) > MAX_RAW_JSON_LENGTH:
                return None
            data = raw
        except Exception:
            return None
    else:
        return None

    if not isinstance(data, dict):
        return None

    if data.get("v") != 1:
        return None

    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        return None

    # Teto de 4 blocos
    blocks_to_check = blocks_raw[:MAX_BLOCKS]

    clean_blocks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in blocks_to_check:
        if not isinstance(item, dict):
            continue

        b_id = item.get("id")
        if not isinstance(b_id, str) or not ID_REGEX.match(b_id) or b_id in seen_ids:
            continue

        b_type = item.get("type")
        validated: dict[str, Any] | None = None

        if b_type == "progress":
            validated = _validate_progress(item)
        elif b_type == "card":
            validated = _validate_card(item)
        elif b_type == "chart":
            validated = _validate_chart(item)
        elif b_type == "controls":
            validated = _validate_controls(item)
        elif b_type == "sandbox":
            validated = _validate_sandbox(item)

        if validated is not None:
            seen_ids.add(b_id)
            clean_blocks.append(validated)

    if not clean_blocks:
        return None

    return {"v": 1, "blocks": clean_blocks}
