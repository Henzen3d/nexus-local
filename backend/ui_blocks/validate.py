"""Validador do contrato nexus-ui/1 para blocos de interface inteligente.

Garante esquema fixo, limites de tamanho e sanitização estrita de URLs e ações,
com tolerância e auto-recuperação (auto-healing) para pequenas variações de LLMs.
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
    if not isinstance(label, str) or not label.strip():
        label = "Progresso"
    else:
        label = label.strip()[:80]

    val = block.get("value")
    mx = block.get("max")
    clean_value = None
    clean_max = None
    if val is not None and mx is not None:
        try:
            val_f = float(val)
            mx_f = float(mx)
            if not (math.isnan(val_f) or math.isnan(mx_f) or math.isinf(val_f) or math.isinf(mx_f)):
                if 1 <= mx_f <= 1000 and 0 <= val_f <= mx_f:
                    clean_value = round(val_f, 2)
                    clean_max = round(mx_f, 2)
        except (ValueError, TypeError):
            pass

    steps = block.get("steps")
    clean_steps: list[dict[str, Any]] = []
    if isinstance(steps, list) and steps:
        active_count = 0
        seen_step_ids: set[str] = set()
        for idx, s in enumerate(steps[:12]):
            if not isinstance(s, dict):
                continue
            s_id = s.get("id")
            if not isinstance(s_id, str) or not ID_REGEX.match(s_id) or s_id in seen_step_ids:
                s_id = f"step_{idx+1}"
            seen_step_ids.add(s_id)

            s_label = str(s.get("label") or f"Etapa {idx+1}").strip()[:80]
            raw_state = str(s.get("state", "pending")).lower().strip()
            if raw_state in ("done", "concluido", "concluído", "completed", "finalizado"):
                s_state = "done"
            elif raw_state in ("active", "ativo", "executando", "running", "current"):
                s_state = "active"
                active_count += 1
            elif raw_state in ("error", "erro", "failed", "falha"):
                s_state = "error"
            else:
                s_state = "pending"
            clean_steps.append({"id": s_id, "label": s_label, "state": s_state})

        # Se houver mais de 1 active, mantém o último ativo e normaliza os anteriores
        if active_count > 1:
            last_active = False
            for step in reversed(clean_steps):
                if step["state"] == "active":
                    if not last_active:
                        last_active = True
                    else:
                        step["state"] = "done"

    if clean_value is None and not clean_steps:
        return None

    out: dict[str, Any] = {
        "id": block.get("id") or "progress_1",
        "type": "progress",
        "label": label,
    }
    if clean_value is not None:
        out["value"] = clean_value
        out["max"] = clean_max
    if clean_steps:
        out["steps"] = clean_steps
    return out


def _validate_card(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not title.strip():
        title = "Informações"
    else:
        title = title.strip()[:80]

    out: dict[str, Any] = {
        "id": block.get("id") or "card_1",
        "type": "card",
        "title": title,
    }

    body = block.get("body")
    if body is not None:
        out["body"] = str(body).strip()[:400]

    facts = block.get("facts")
    if isinstance(facts, list):
        clean_facts = []
        for f in facts[:6]:
            if not isinstance(f, dict):
                continue
            f_label = str(f.get("label", "")).strip()[:40]
            f_val = str(f.get("value", "")).strip()[:40]
            if f_label and f_val:
                clean_facts.append({"label": f_label, "value": f_val})
        if clean_facts:
            out["facts"] = clean_facts

    image = block.get("image")
    if isinstance(image, dict):
        url = image.get("url")
        alt = image.get("alt")
        if isinstance(url, str) and isinstance(alt, str) and (1 <= len(alt) <= 120):
            if is_allowed_image_url(url):
                out["image"] = {"url": url.strip(), "alt": alt.strip()}

    return out


def _validate_chart(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not title.strip():
        title = "Gráfico Comparativo"
    else:
        title = title.strip()[:80]

    kind = str(block.get("kind", "bar")).lower()
    if kind not in ("bar", "line", "compare"):
        kind = "bar"

    x_key = block.get("x_key") or "x"
    if not isinstance(x_key, str) or not (1 <= len(x_key) <= 40):
        x_key = "x"

    series = block.get("series")
    if not isinstance(series, list) or not series:
        return None

    # Normalização de series aninhadas (formato Chart.js / Highcharts gerado por LLMs)
    if isinstance(series[0], dict) and "rows" in series[0]:
        clean_series = []
        rows_by_x: dict[str, dict[str, Any]] = {}
        for idx, s in enumerate(series[:4]):
            if not isinstance(s, dict):
                continue
            s_key = f"series_{idx+1}"
            s_label = str(s.get("name") or s.get("label") or f"Série {idx+1}").strip()[:60]
            clean_series.append({"key": s_key, "label": s_label})
            for r in s.get("rows", []):
                if not isinstance(r, dict):
                    continue
                x_val = r.get("x") or r.get(x_key) or r.get("label")
                if x_val is None:
                    continue
                x_str = str(x_val)[:40]
                y_val = r.get("y", 0)
                try:
                    y_num = float(y_val)
                    if math.isnan(y_num) or math.isinf(y_num):
                        y_num = 0.0
                except (ValueError, TypeError):
                    y_num = 0.0
                if x_str not in rows_by_x:
                    rows_by_x[x_str] = {x_key: x_str}
                rows_by_x[x_str][s_key] = y_num

        clean_rows = list(rows_by_x.values())[:24]
        if len(clean_series) > 1 and kind == "bar":
            kind = "compare"
        return {
            "id": block.get("id") or "chart_1",
            "type": "chart",
            "title": title,
            "kind": kind,
            "x_key": x_key,
            "series": clean_series,
            "rows": clean_rows,
        }

    # Formato padrão plano
    clean_series = []
    seen_series_keys = set()
    for idx, s in enumerate(series[:4]):
        if not isinstance(s, dict):
            continue
        s_key = s.get("key") or f"s_{idx+1}"
        s_label = s.get("label") or s.get("name") or s_key
        if not isinstance(s_key, str) or not (1 <= len(s_key) <= 40) or s_key in seen_series_keys:
            continue
        seen_series_keys.add(s_key)
        clean_series.append({"key": s_key, "label": str(s_label)[:60]})

    if not clean_series:
        return None

    if kind == "bar" and len(clean_series) != 1:
        return None
    elif kind == "line" and not (1 <= len(clean_series) <= 3):
        return None
    elif kind == "compare" and not (2 <= len(clean_series) <= 4):
        return None

    rows = block.get("rows")
    if not isinstance(rows, list) or not rows:
        return None

    clean_rows = []
    for r in rows[:24]:
        if not isinstance(r, dict):
            continue
        x_val = r.get(x_key)
        if x_val is None:
            # Tenta pegar a primeira chave que não seja série
            for k, v in r.items():
                if k not in seen_series_keys:
                    x_val = v
                    x_key = k
                    break
        if x_val is None:
            continue
        row_obj: dict[str, Any] = {x_key: str(x_val)[:40]}
        has_any_num = False
        for s_key in seen_series_keys:
            val = r.get(s_key, 0)
            try:
                num = float(val)
                if not (math.isnan(num) or math.isinf(num)):
                    row_obj[s_key] = num
                    has_any_num = True
                else:
                    row_obj[s_key] = 0.0
            except (ValueError, TypeError):
                row_obj[s_key] = 0.0
        if has_any_num:
            clean_rows.append(row_obj)

    if not clean_rows:
        return None

    return {
        "id": block.get("id") or "chart_1",
        "type": "chart",
        "title": title,
        "kind": kind,
        "x_key": x_key,
        "series": clean_series,
        "rows": clean_rows,
    }


def _validate_controls(block: dict[str, Any]) -> dict[str, Any] | None:
    title = str(block.get("title") or "Controles").strip()[:80]
    submit_label = str(block.get("submit_label") or "Enviar").strip()[:32]

    fields = block.get("fields")
    if not isinstance(fields, list) or not fields:
        return None

    clean_fields = []
    seen_field_ids = set()
    select_fields = []

    for idx, f in enumerate(fields[:6]):
        if not isinstance(f, dict):
            continue
        f_id = f.get("id")
        if not isinstance(f_id, str) or not FIELD_ID_REGEX.match(f_id) or f_id in seen_field_ids:
            f_id = f"f_{idx+1}"
        seen_field_ids.add(f_id)

        f_kind = f.get("kind")
        f_label = str(f.get("label", f_id)).strip()[:60]
        clean_f: dict[str, Any] = {"id": f_id, "kind": f_kind, "label": f_label}

        if f_kind == "text":
            placeholder = f.get("placeholder")
            if placeholder is not None and isinstance(placeholder, str) and len(placeholder) <= 200:
                clean_f["placeholder"] = placeholder
        elif f_kind in ("number", "range"):
            mn = f.get("min", 0)
            mx = f.get("max", 100)
            try:
                mn = float(mn)
                mx = float(mx)
            except (ValueError, TypeError):
                mn, mx = 0, 100
            if mn >= mx or (mx - mn) > 1_000_000:
                mn, mx = 0, 100
            clean_f["min"] = mn
            clean_f["max"] = mx
            step = f.get("step", 1)
            try:
                step = float(step)
                if step <= 0 or math.isnan(step):
                    step = 1
            except (ValueError, TypeError):
                step = 1
            clean_f["step"] = step
            default = f.get("default")
            if default is not None:
                try:
                    def_val = float(default)
                    if mn <= def_val <= mx:
                        clean_f["default"] = def_val
                except (ValueError, TypeError):
                    pass
        elif f_kind == "select":
            opts = f.get("options")
            if not isinstance(opts, list) or not (2 <= len(opts) <= 8):
                continue
            clean_opts = []
            seen_vals = set()
            for o in opts:
                if not isinstance(o, dict):
                    continue
                val = str(o.get("value", "")).strip()
                lbl = str(o.get("label", val)).strip()
                if not val or val in seen_vals:
                    continue
                seen_vals.add(val)
                clean_opts.append({"value": val, "label": lbl[:40]})
            if len(clean_opts) < 2:
                continue
            clean_f["options"] = clean_opts
            select_fields.append(f_id)
        else:
            continue

        clean_fields.append(clean_f)

    if not clean_fields:
        return None

    # computed opcional
    clean_computed = None
    computed = block.get("computed")
    if isinstance(computed, dict):
        tmpl = computed.get("template")
        formula = computed.get("formula")
        if isinstance(tmpl, str) and (1 <= len(tmpl) <= 200) and isinstance(formula, str) and (1 <= len(formula) <= 300):
            clean_computed = {"template": tmpl, "formula": formula}

    # action
    action = block.get("action")
    if not isinstance(action, dict):
        action = {"name": "send_message", "template": "Atualizar"}

    action_name = action.get("name")
    if action_name not in ("send_message", "set_model"):
        action_name = "send_message"

    # Validação de placeholders em send_message
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
        "id": block.get("id") or "controls_1",
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
    title = str(block.get("title") or "Simulação").strip()[:80]
    html = block.get("html")
    if not isinstance(html, str) or not (1 <= len(html) <= 20000):
        return None

    initial_height = block.get("initial_height")
    if isinstance(initial_height, int) and 120 <= initial_height <= 800:
        h = initial_height
    else:
        h = 300

    out: dict[str, Any] = {
        "id": block.get("id") or "sandbox_1",
        "type": "sandbox",
        "title": title,
        "html": html,
        "initial_height": h,
        "standalone_download": bool(block.get("standalone_download", True)),
    }

    css = block.get("css")
    if isinstance(css, str) and len(css) <= 20000:
        out["css"] = css

    js = block.get("js")
    if isinstance(js, str) and len(js) <= 30000:
        out["js"] = js

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
        data = raw
    else:
        return None

    if not isinstance(data, dict):
        return None

    # Normalização de bloco único ou envelope sem "v"
    if "blocks" not in data:
        if "type" in data:
            data = {"v": 1, "blocks": [data]}
        elif "kind" in data and "series" in data:
            data["type"] = "chart"
            data = {"v": 1, "blocks": [data]}
        elif "steps" in data or ("value" in data and "max" in data):
            data["type"] = "progress"
            data = {"v": 1, "blocks": [data]}
        elif "fields" in data:
            data["type"] = "controls"
            data = {"v": 1, "blocks": [data]}
        elif "html" in data:
            data["type"] = "sandbox"
            data = {"v": 1, "blocks": [data]}
        elif "facts" in data or "body" in data or "title" in data:
            data["type"] = "card"
            data = {"v": 1, "blocks": [data]}
        else:
            return None
    elif isinstance(data.get("blocks"), dict):
        data["blocks"] = [data["blocks"]]

    data["v"] = 1

    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        return None

    blocks_to_check = blocks_raw[:MAX_BLOCKS]
    clean_blocks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, item in enumerate(blocks_to_check):
        if not isinstance(item, dict):
            continue

        b_type = item.get("type")
        if not b_type:
            if "kind" in item and "series" in item:
                b_type = "chart"
                item["type"] = "chart"
            elif "steps" in item or ("value" in item and "max" in item):
                b_type = "progress"
                item["type"] = "progress"
            elif "fields" in item:
                b_type = "controls"
                item["type"] = "controls"
            elif "html" in item:
                b_type = "sandbox"
                item["type"] = "sandbox"
            elif "facts" in item or "body" in item or "title" in item:
                b_type = "card"
                item["type"] = "card"

        b_id = item.get("id")
        if not isinstance(b_id, str) or not ID_REGEX.match(b_id) or b_id in seen_ids:
            b_id = f"{b_type or 'block'}_{idx+1}"
        item["id"] = b_id

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
