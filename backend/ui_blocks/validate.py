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
from urllib.parse import urlparse

from backend.ui_blocks.expr import (
    check_dependency_cycles,
    is_expression,
    validate_expression,
)

ID_REGEX = re.compile(r"^[a-z0-9_-]{1,32}$")
SELECT_VALUE_REGEX = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
FIELD_ID_REGEX = re.compile(r"^[a-z0-9_]{1,32}$")
PLACEHOLDER_REGEX = re.compile(r"\{([a-zA-Z0-9_]+)\}")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MAX_RAW_JSON_LENGTH = 16000
# Plano 12 §0: teto 6 com subtetos por tipo (iframe pesado, gráfico caro, follow_up único).
MAX_BLOCKS = 6
MAX_BLOCKS_PER_TYPE = {"sandbox": 1, "chart": 2, "follow_up": 1, "options": 1}
MAX_CONTROL_FIELDS = 4
MAX_METRIC_ITEMS = 4
MAX_FOLLOW_UP_ITEMS = 4
CALLOUT_KINDS = ("info", "success", "warning", "danger")
# Sinônimos que modelos usam; qualquer outra coisa vira `info`.
CALLOUT_KIND_ALIASES = {
    "error": "danger",
    "erro": "danger",
    "alert": "danger",
    "critical": "danger",
    "warn": "warning",
    "aviso": "warning",
    "atencao": "warning",
    "atenção": "warning",
    "caution": "warning",
    "ok": "success",
    "sucesso": "success",
    "done": "success",
    "note": "info",
    "tip": "info",
    "nota": "info",
    "dica": "info",
}
# Limites por campo do bloco `sandbox`. O envelope inteiro já é cortado em
# MAX_RAW_JSON_LENGTH, então o teto real de html+css+js é menor que a soma.
MAX_SANDBOX_HTML = 12000
MAX_SANDBOX_CSS = 4000
MAX_SANDBOX_JS = 8000


def _env_hosts() -> set[str]:
    raw = os.getenv("INTELLIGENT_UI_IMAGE_HOSTS", "")
    return {h.strip().lower() for h in raw.split(",") if h.strip()}


def _env_allow_private() -> bool:
    return os.getenv("INTELLIGENT_UI_ALLOW_PRIVATE_HTTP", "false").strip().lower() in ("true", "1", "yes", "on")


def is_allowed_image_url(
    url: str,
    image_hosts: list[str] | set[str] | None = None,
    allow_private_http: bool | None = None,
) -> bool:
    """Verifica se uma URL de imagem atende às regras da Seção 6 da spec.

    ``image_hosts`` e ``allow_private_http`` vêm da configuração efetiva do turno
    (painel admin > ``.env``). Quando ``None``, cai no ambiente — mantém os
    chamadores antigos funcionando.
    """
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

    allowed_hosts = (
        {str(h).strip().lower() for h in image_hosts if str(h).strip()}
        if image_hosts is not None
        else _env_hosts()
    )

    if host in allowed_hosts:
        return True

    # Checagem de IP privado / rede local
    allow_private = bool(allow_private_http) if allow_private_http is not None else _env_allow_private()
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
        if is_expression(val):
            try:
                mx_f = float(mx)
                if not (math.isnan(mx_f) or math.isinf(mx_f)) and 1 <= mx_f <= 1000:
                    clean_value = str(val).strip()[:160]
                    clean_max = round(mx_f, 2)
            except (ValueError, TypeError):
                pass
        else:
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


def _validate_card(
    block: dict[str, Any],
    image_hosts: list[str] | None = None,
    allow_private_http: bool | None = None,
) -> dict[str, Any] | None:
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
            val_raw = f.get("value", "")
            if is_expression(val_raw):
                f_val = str(val_raw).strip()[:160]
            else:
                f_val = str(val_raw).strip()[:40]
            if f_label and f_val:
                clean_facts.append({"label": f_label, "value": f_val})
        if clean_facts:
            out["facts"] = clean_facts

    image = block.get("image")
    if isinstance(image, dict):
        url = image.get("url")
        alt = image.get("alt")
        if isinstance(url, str) and isinstance(alt, str) and (1 <= len(alt) <= 120):
            if is_allowed_image_url(url, image_hosts, allow_private_http):
                out["image"] = {"url": url.strip(), "alt": alt.strip()}

    return out


def _validate_chart(block: dict[str, Any]) -> dict[str, Any] | None:
    title = block.get("title")
    if not isinstance(title, str) or not title.strip():
        title = "Gráfico Comparativo"
    else:
        title = title.strip()[:80]

    # `kind` ausente vira `bar` (tolerância); `kind` escrito e fora da união é descartado
    kind = str(block.get("kind") or "bar").lower().strip()
    if kind not in ("bar", "line", "compare", "pie"):
        return None

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
        elif kind == "pie" and len(clean_series) > 1:
            clean_series = clean_series[:1]
        if kind == "pie":
            if len(clean_rows) < 2:
                return None
            if len(clean_rows) > 8:
                s_k = clean_series[0]["key"]
                top7 = clean_rows[:7]
                others_sum = sum(float(r.get(s_k, 0.0)) for r in clean_rows[7:])
                top7.append({x_key: "Outros", s_k: others_sum})
                clean_rows = top7
        out: dict[str, Any] = {
            "id": block.get("id") or "chart_1",
            "type": "chart",
            "title": title,
            "kind": kind,
            "x_key": x_key,
            "series": clean_series,
            "rows": clean_rows,
        }
        unit = _clean_text(block.get("unit"), 1, 8)
        if unit is not None:
            out["unit"] = unit
        x_label = _clean_text(block.get("x_label"), 1, 40)
        if x_label is not None:
            out["x_label"] = x_label
        y_label = _clean_text(block.get("y_label"), 1, 40)
        if y_label is not None:
            out["y_label"] = y_label
        if kind == "compare" and block.get("stacked") is True:
            out["stacked"] = True
        return out

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
    elif kind == "pie":
        # Tolerância: pie com 2+ séries → usa a primeira
        if len(clean_series) > 1:
            clean_series = clean_series[:1]
            seen_series_keys = {clean_series[0]["key"]}

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
            if is_expression(val):
                row_obj[s_key] = str(val).strip()[:160]
                has_any_num = True
            else:
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

    if kind == "pie":
        # rows: 2 a 8; Tolerância: mais de 8 linhas → agrupa o resto em "Outros"
        if len(clean_rows) < 2:
            return None
        if len(clean_rows) > 8:
            s_k = clean_series[0]["key"]
            top7 = clean_rows[:7]
            others_sum = sum(float(r.get(s_k, 0.0)) for r in clean_rows[7:])
            top7.append({x_key: "Outros", s_k: others_sum})
            clean_rows = top7

    out: dict[str, Any] = {
        "id": block.get("id") or "chart_1",
        "type": "chart",
        "title": title,
        "kind": kind,
        "x_key": x_key,
        "series": clean_series,
        "rows": clean_rows,
    }
    unit = _clean_text(block.get("unit"), 1, 8)
    if unit is not None:
        out["unit"] = unit
    x_label = _clean_text(block.get("x_label"), 1, 40)
    if x_label is not None:
        out["x_label"] = x_label
    y_label = _clean_text(block.get("y_label"), 1, 40)
    if y_label is not None:
        out["y_label"] = y_label
    if kind == "compare" and block.get("stacked") is True:
        out["stacked"] = True
    return out


def _validate_table(block: dict[str, Any]) -> dict[str, Any] | None:
    """`table` (plano 12 §2.4): dados tabulares com colunas tipadas e ordenação."""
    raw_columns = block.get("columns")
    if not isinstance(raw_columns, list) or not raw_columns:
        return None

    clean_columns: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for col in raw_columns[:8]:
        if not isinstance(col, dict):
            continue
        key = col.get("key")
        if not isinstance(key, str) or not FIELD_ID_REGEX.match(key) or key in seen_keys:
            continue
        seen_keys.add(key)
        label = _clean_text(col.get("label"), 1, 40) or key
        raw_kind = str(col.get("kind") or "text").strip().lower()
        kind = raw_kind if raw_kind in ("text", "number", "date") else "text"
        clean_col: dict[str, Any] = {"key": key, "label": label, "kind": kind}
        if kind == "number":
            unit = _clean_text(col.get("unit"), 1, 8)
            if unit is not None:
                clean_col["unit"] = unit
        clean_columns.append(clean_col)

    if len(clean_columns) < 2:
        return None

    raw_rows = block.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        return None

    clean_rows: list[dict[str, Any]] = []
    for r in raw_rows[:50]:
        if not isinstance(r, dict):
            continue
        row_obj: dict[str, Any] = {}
        for col in clean_columns:
            k = col["key"]
            kind = col["kind"]
            val = r.get(k)
            if kind == "number":
                if is_expression(val):
                    row_obj[k] = str(val).strip()[:160]
                else:
                    num = _finite_number(val)
                    row_obj[k] = num
            elif kind == "date":
                if isinstance(val, str) and DATE_REGEX.match(val.strip()):
                    row_obj[k] = val.strip()
                else:
                    row_obj[k] = None
            else:
                if val is not None and not isinstance(val, (dict, list)):
                    row_obj[k] = str(val)[:120]
                else:
                    row_obj[k] = ""
        clean_rows.append(row_obj)

    if not clean_rows:
        return None

    out: dict[str, Any] = {
        "id": block.get("id") or "table_1",
        "type": "table",
        "columns": clean_columns,
        "rows": clean_rows,
    }
    title = _clean_text(block.get("title"), 1, 80)
    if title is not None:
        out["title"] = title

    raw_sort = block.get("sort")
    if isinstance(raw_sort, dict):
        s_key = raw_sort.get("key")
        if isinstance(s_key, str) and s_key in seen_keys:
            s_dir = str(raw_sort.get("dir") or "asc").strip().lower()
            if s_dir not in ("asc", "desc"):
                s_dir = "asc"
            out["sort"] = {"key": s_key, "dir": s_dir}

    return out


def _validate_controls(block: dict[str, Any]) -> dict[str, Any] | None:
    title = str(block.get("title") or "Controles").strip()[:80]
    submit_label = str(block.get("submit_label") or "Enviar").strip()[:32]

    fields = block.get("fields")
    if not isinstance(fields, list) or not fields:
        return None

    clean_fields = []
    seen_field_ids = set()
    select_fields = []

    for idx, f in enumerate(fields[:MAX_CONTROL_FIELDS]):
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

    # computed opcional (dicionário legado ou lista de computeds)
    clean_computed = None
    computed = block.get("computed")
    computed_list: list[dict[str, Any]] = []
    is_legacy_dict = False
    if isinstance(computed, dict):
        is_legacy_dict = True
        tmpl = computed.get("template")
        formula = computed.get("formula")
        c_id = computed.get("id") or "resultado"
        if isinstance(tmpl, str) and (1 <= len(tmpl) <= 200) and isinstance(formula, str) and (1 <= len(formula) <= 300):
            computed_list.append({"id": c_id, "template": tmpl, "formula": formula})
    elif isinstance(computed, list):
        for c in computed[:4]:
            if isinstance(c, dict):
                c_id = str(c.get("id") or "resultado").strip()[:32]
                c_tmpl = str(c.get("template") or f"{{{c_id}}}").strip()[:200]
                c_formula = str(c.get("formula") or "").strip()[:300]
                if c_id and c_tmpl and c_formula:
                    computed_list.append({"id": c_id, "template": c_tmpl, "formula": c_formula})

    if computed_list:
        valid_cycles, _, _ = check_dependency_cycles(computed_list, set(seen_field_ids))
        if valid_cycles:
            clean_computed = computed_list[0] if is_legacy_dict else computed_list

    # action — obrigatória e fechada (spec 4.4): nome fora da lista descarta o bloco.
    action = block.get("action")
    if not isinstance(action, dict):
        return None

    action_name = action.get("name")
    if action_name not in ("send_message", "set_model"):
        return None

    # Validação de placeholders em send_message
    clean_action: dict[str, Any] = {"name": action_name}
    if action_name == "send_message":
        tmpl = action.get("template")
        if not isinstance(tmpl, str) or not (1 <= len(tmpl) <= 500):
            return None
        placeholders = PLACEHOLDER_REGEX.findall(tmpl)
        valid_keys = set(seen_field_ids)
        if clean_computed:
            if isinstance(clean_computed, dict):
                valid_keys.add(clean_computed.get("id") or "resultado")
            elif isinstance(clean_computed, list):
                for c in clean_computed:
                    valid_keys.add(c.get("id") or "resultado")
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
    if not isinstance(html, str) or not (1 <= len(html) <= MAX_SANDBOX_HTML):
        return None

    initial_height = block.get("initial_height")
    try:
        h_num = int(round(float(initial_height))) if initial_height is not None else None
    except (TypeError, ValueError):
        h_num = None
    h = h_num if h_num is not None and 120 <= h_num <= 800 else 300

    out: dict[str, Any] = {
        "id": block.get("id") or "sandbox_1",
        "type": "sandbox",
        "title": title,
        "html": html,
        "initial_height": h,
        "standalone_download": bool(block.get("standalone_download", True)),
    }

    css = block.get("css")
    if isinstance(css, str) and len(css) <= MAX_SANDBOX_CSS:
        out["css"] = css

    js = block.get("js")
    if isinstance(js, str) and len(js) <= MAX_SANDBOX_JS:
        out["js"] = js

    return out


def _clean_text(value: Any, min_len: int, max_len: int) -> str | None:
    """Texto aparado dentro de [min_len, max_len]; qualquer outra coisa → None."""
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    text = str(value).strip()
    if len(text) < min_len:
        return None
    return text[:max_len]


def _finite_number(value: Any) -> int | float | None:
    """Número finito (int ou float, nunca bool); mantém o tipo para o JSON gravado ficar limpo."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def _validate_metric(block: dict[str, Any]) -> dict[str, Any] | None:
    """`metric` (plano 12 §2.1): 1 a 4 indicadores com valor, delta e tendência."""
    items = block.get("items")
    if not isinstance(items, list):
        return None

    clean_items: list[dict[str, Any]] = []
    for raw in items:
        if len(clean_items) >= MAX_METRIC_ITEMS:
            break
        if not isinstance(raw, dict):
            continue
        label = _clean_text(raw.get("label"), 1, 40)
        if label is None:
            continue
        raw_value = raw.get("value")
        if is_expression(raw_value):
            value = str(raw_value).strip()[:160]
        elif isinstance(raw_value, bool):
            value = None
        elif isinstance(raw_value, (int, float)):
            value = _finite_number(raw_value)  # NaN/inf não vira texto "nan"
        else:
            value = _clean_text(raw_value, 1, 24)
        if value is None:
            continue
        item: dict[str, Any] = {"label": label, "value": value}
        unit = _clean_text(raw.get("unit"), 1, 8)
        if unit is not None and (not isinstance(value, str) or is_expression(value)):
            item["unit"] = unit
        delta = _clean_text(raw.get("delta"), 1, 12)
        if delta is not None:
            item["delta"] = delta
        trend = str(raw.get("trend") or "").strip().lower()
        if trend in ("up", "down", "flat"):
            item["trend"] = trend
        good = str(raw.get("good") or "").strip().lower()
        if good in ("up", "down"):
            item["good"] = good
        hint = _clean_text(raw.get("hint"), 1, 40)
        if hint is not None:
            item["hint"] = hint
        clean_items.append(item)

    if not clean_items:
        return None

    out: dict[str, Any] = {
        "id": block.get("id") or "metric_1",
        "type": "metric",
        "items": clean_items,
    }
    title = _clean_text(block.get("title"), 1, 80)
    if title is not None:
        out["title"] = title
    return out


def _validate_callout(block: dict[str, Any]) -> dict[str, Any] | None:
    """`callout` (plano 12 §2.2): aviso curto com tipo; `kind` desconhecido vira `info`."""
    body = _clean_text(block.get("body"), 1, 400)
    if body is None:
        return None
    raw_kind = str(block.get("kind") or "info").strip().lower()
    kind = raw_kind if raw_kind in CALLOUT_KINDS else CALLOUT_KIND_ALIASES.get(raw_kind, "info")
    out: dict[str, Any] = {
        "id": block.get("id") or "callout_1",
        "type": "callout",
        "kind": kind,
        "body": body,
    }
    title = _clean_text(block.get("title"), 1, 60)
    if title is not None:
        out["title"] = title
    return out


def _validate_follow_up(block: dict[str, Any]) -> dict[str, Any] | None:
    """`follow_up` (plano 12 §2.3): 1 a 4 sugestões de próxima pergunta (texto 3–80)."""
    items = block.get("items")
    if not isinstance(items, list):
        return None
    clean_items: list[str] = []
    seen: set[str] = set()
    for raw in items:
        if len(clean_items) >= MAX_FOLLOW_UP_ITEMS:
            break
        if isinstance(raw, dict):
            raw = raw.get("label") or raw.get("text")
        text = _clean_text(raw, 3, 80)
        if text is None or text.lower() in seen:
            continue
        seen.add(text.lower())
        clean_items.append(text)
    if not clean_items:
        return None
    return {
        "id": block.get("id") or "follow_up_1",
        "type": "follow_up",
        "items": clean_items,
    }


def _validate_options(block: dict[str, Any]) -> dict[str, Any] | None:
    """`options` (plano 12 §2.5): 2 a 6 escolhas clicáveis para uma pergunta."""
    question = _clean_text(block.get("question"), 1, 160)
    if question is None:
        return None

    raw_options = block.get("options")
    if not isinstance(raw_options, list):
        return None

    clean_options: list[dict[str, Any]] = []
    seen_values: set[str] = set()

    for idx, opt in enumerate(raw_options[:6]):
        if not isinstance(opt, dict):
            continue
        raw_val = opt.get("value")
        val = str(raw_val).strip() if raw_val is not None else ""
        if not val or not SELECT_VALUE_REGEX.match(val):
            val = f"opt_{idx+1}"
        if val in seen_values:
            continue
        label = _clean_text(opt.get("label", val), 1, 60)
        if label is None:
            continue
        seen_values.add(val)
        clean_opt: dict[str, Any] = {"value": val, "label": label}
        desc = _clean_text(opt.get("description"), 1, 100)
        if desc is not None:
            clean_opt["description"] = desc
        clean_options.append(clean_opt)

    if len(clean_options) < 2:
        return None

    raw_mode = str(block.get("mode") or "single").strip().lower()
    mode = raw_mode if raw_mode in ("single", "multiple") else "single"

    # Ação obrigatória: send_message com {choice} no template
    raw_action = block.get("action")
    if not isinstance(raw_action, dict):
        return None
    act_name = str(raw_action.get("name") or "").strip()
    if act_name != "send_message":
        return None
    template = _clean_text(raw_action.get("template"), 1, 300)
    if template is None or "{choice}" not in template:
        return None

    out: dict[str, Any] = {
        "id": block.get("id") or "options_1",
        "type": "options",
        "question": question,
        "mode": mode,
        "options": clean_options,
        "action": {"name": "send_message", "template": template},
    }
    if bool(block.get("allow_other", False)):
        out["allow_other"] = True

    return out


def _infer_type(item: dict[str, Any]) -> str | None:
    """Bloco sem `type`: inferido pelos campos, na mesma ordem do frontend (spec §4).

    `items` de textos → follow_up; `items` de {label, value} → metric; `kind` de
    callout com `body` → callout. O card fica por último porque `title`/`body`
    aparecem em quase todos os tipos.
    """
    if "kind" in item and "series" in item:
        return "chart"
    if "columns" in item and "rows" in item:
        return "table"
    if "steps" in item or ("value" in item and "max" in item):
        return "progress"
    if "fields" in item:
        return "controls"
    if "question" in item and "options" in item:
        return "options"
    if "html" in item:
        return "sandbox"
    items = item.get("items")
    if isinstance(items, list) and items:
        if all(isinstance(x, str) for x in items):
            return "follow_up"
        if all(isinstance(x, dict) and "label" in x and "value" in x for x in items):
            return "metric"
    kind = str(item.get("kind") or "").strip().lower()
    if "body" in item and (kind in CALLOUT_KINDS or kind in CALLOUT_KIND_ALIASES):
        return "callout"
    if "facts" in item or "body" in item or "title" in item:
        return "card"
    return None


def validate_envelope(
    raw: str | dict[str, Any],
    *,
    image_hosts: list[str] | None = None,
    allow_private_http: bool | None = None,
) -> dict[str, Any] | None:
    """Valida um JSON bruto ou dicionário com o envelope nexus-ui/1.

    Retorna o dicionário sanitizado {"v": 1, "blocks": [...]} ou None se inválido.

    Tolerâncias deliberadas (documentadas na spec, seção 4, "Tolerâncias"):
    envelope sem ``v`` ou bloco solto sem envelope; bloco sem ``type`` inferido
    pelos campos; ``id`` ausente/duplicado gerado; títulos e labels padrão.
    Rejeições estritas: ``v`` presente e diferente de 1; ``kind`` de chart fora
    da união; ação de controls ausente ou fora de ``send_message``/``set_model``.

    Teto de ``MAX_BLOCKS`` blocos com subtetos por tipo (``MAX_BLOCKS_PER_TYPE``);
    ``follow_up`` é reordenado para o fim. Tipos: progress, card, chart, controls,
    sandbox, metric, callout, follow_up (plano 12). Tipo desconhecido → bloco fora.
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

    # `v` escrito e diferente de 1 é outro contrato: envelope inteiro descartado.
    # `v` ausente é tolerado (assume 1).
    if "v" in data and (isinstance(data.get("v"), bool) or data.get("v") not in (1, "1")):
        return None

    # Normalização de bloco único ou envelope sem "v"
    if "blocks" not in data:
        if "type" in data:
            data = {"v": 1, "blocks": [data]}
        else:
            inferred = _infer_type(data)
            if inferred is None:
                return None
            data["type"] = inferred
            data = {"v": 1, "blocks": [data]}
    elif isinstance(data.get("blocks"), dict):
        data["blocks"] = [data["blocks"]]

    data["v"] = 1

    blocks_raw = data.get("blocks")
    if not isinstance(blocks_raw, list) or not blocks_raw:
        return None

    blocks_to_check = blocks_raw[:MAX_BLOCKS]
    clean_blocks: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_control_field_ids: set[str] = set()
    per_type: dict[str, int] = {}

    for idx, item in enumerate(blocks_to_check):
        if not isinstance(item, dict):
            continue

        b_type = item.get("type")
        if not b_type:
            b_type = _infer_type(item)
            if b_type:
                item["type"] = b_type
        if isinstance(b_type, str):
            b_type = b_type.strip().lower()
        else:
            b_type = ""

        # Subteto por tipo (plano 12 §0): o excedente cai, os demais seguem.
        if b_type in MAX_BLOCKS_PER_TYPE and per_type.get(b_type, 0) >= MAX_BLOCKS_PER_TYPE[b_type]:
            continue

        b_id = item.get("id")
        if not isinstance(b_id, str) or not ID_REGEX.match(b_id) or b_id in seen_ids:
            b_id = f"{b_type or 'block'}_{idx+1}"
        item["id"] = b_id

        validated: dict[str, Any] | None = None
        if b_type == "progress":
            validated = _validate_progress(item)
        elif b_type == "card":
            validated = _validate_card(item, image_hosts, allow_private_http)
        elif b_type == "chart":
            validated = _validate_chart(item)
        elif b_type == "table":
            validated = _validate_table(item)
        elif b_type == "controls":
            validated = _validate_controls(item)
        elif b_type == "options":
            validated = _validate_options(item)
        elif b_type == "sandbox":
            validated = _validate_sandbox(item)
        elif b_type == "metric":
            validated = _validate_metric(item)
        elif b_type == "callout":
            validated = _validate_callout(item)
        elif b_type == "follow_up":
            validated = _validate_follow_up(item)

        if validated is not None:
            if b_type == "controls":
                ctrl_f_ids = {f["id"] for f in validated.get("fields", [])}
                if seen_control_field_ids.intersection(ctrl_f_ids):
                    # Rejeita o bloco duplicado (duplicate_id)
                    continue
                seen_control_field_ids.update(ctrl_f_ids)

            seen_ids.add(b_id)
            per_type[b_type] = per_type.get(b_type, 0) + 1
            clean_blocks.append(validated)

    if not clean_blocks:
        return None

    # Coleta todos os IDs conhecidos de controls (fields + computeds) do envelope
    all_control_ids: set[str] = set(seen_control_field_ids)
    for b in clean_blocks:
        if b["type"] == "controls":
            computed = b.get("computed")
            if isinstance(computed, dict):
                all_control_ids.add(computed.get("id") or "resultado")
            elif isinstance(computed, list):
                for c in computed:
                    all_control_ids.add(c.get("id") or "resultado")

    # Validação pós-processamento de expressões contra IDs de controls do envelope
    for b in clean_blocks:
        b_k = b["type"]
        if b_k == "metric":
            for it in b.get("items", []):
                val = it.get("value")
                if is_expression(val):
                    valid, _, _ = validate_expression(val, all_control_ids)
                    if not valid:
                        it["value"] = "—"
        elif b_k == "table":
            num_cols = {c["key"] for c in b.get("columns", []) if c.get("kind") == "number"}
            for r in b.get("rows", []):
                for k in num_cols:
                    val = r.get(k)
                    if is_expression(val):
                        valid, _, _ = validate_expression(val, all_control_ids)
                        if not valid:
                            r[k] = None
        elif b_k == "chart":
            s_keys = {s["key"] for s in b.get("series", [])}
            for r in b.get("rows", []):
                for k in s_keys:
                    val = r.get(k)
                    if is_expression(val):
                        valid, _, _ = validate_expression(val, all_control_ids)
                        if not valid:
                            r[k] = 0.0
        elif b_k == "progress":
            val = b.get("value")
            if is_expression(val):
                valid, _, _ = validate_expression(val, all_control_ids)
                if not valid:
                    b.pop("value", None)
                    b.pop("max", None)
        elif b_k == "card":
            for f in b.get("facts", []):
                val = f.get("value")
                if is_expression(val):
                    valid, _, _ = validate_expression(val, all_control_ids)
                    if not valid:
                        f["value"] = "—"

    # `follow_up` é sempre o último bloco (plano 12 §2.3): se veio antes, vai para o fim.
    follow_ups = [b for b in clean_blocks if b["type"] == "follow_up"]
    if follow_ups and clean_blocks[-1]["type"] != "follow_up":
        clean_blocks = [b for b in clean_blocks if b["type"] != "follow_up"] + follow_ups

    return {"v": 1, "blocks": clean_blocks}
