"""Additive diagnostics; never changes the sanitized nexus-ui/1 contract.

Keep classification and signatures mirrored in frontend/src/lib/nexusUi.ts.
Messages contain schema information, never model/user values or URLs.
"""
from __future__ import annotations

import copy
import json
from typing import Any

ERROR_CODES = (
    'unknown_type', 'missing_required', 'type_mismatch', 'limit_exceeded',
    'invalid_action', 'invalid_expression', 'unsafe_url', 'duplicate_id',
    'invalid_json', 'fence_unclosed', 'rejected_envelope', 'invalid_scene_code',
)
SIGNATURES = {
    'progress': 'progress: value, max or steps[{label,state}]',
    'card': 'card: title, body?, facts?, image?',
    'chart': 'chart: kind bar|line|compare|pie, x_key, series[{key,label}], rows[]',
    'table': 'table: columns[{key,label,kind?,unit?}], rows[]',
    'controls': 'controls: fields[], action{name:send_message|set_model,template?|field?}',
    'options': 'options: question, options[{value,label}], action{name:send_message,template}',
    'sandbox': 'sandbox: title, html or kind:scene with code',
    'metric': 'metric: items[{label,value}]',
    'callout': 'callout: body, kind info|success|warning|danger',
    'follow_up': 'follow_up: items[string]',
}
REQUIRED = {'chart': 'series', 'table': 'columns', 'controls': 'fields', 'options': 'question',
            'sandbox': 'html', 'metric': 'items', 'callout': 'body', 'follow_up': 'items'}


def ui_error(code: str, block_id: str = '', path: str = '', hint: str = '') -> dict:
    return {'code': code, 'block_id': block_id[:32], 'path': path[:80],
            'message': f'{code}: {path or "envelope"}'[:160], 'hint': hint[:160]}


def validate_with_diagnostics(raw: Any, **kwargs) -> dict:
    from backend.ui_blocks.validate import (
        MAX_BLOCKS, MAX_BLOCKS_PER_TYPE, MAX_RAW_JSON_LENGTH, _infer_type, validate_envelope,
    )
    result = {'envelope': None, 'errors': [], 'dropped': 0}

    def error(code, block_id='', path='', hint=''):
        if len(result['errors']) < 4:
            result['errors'].append(ui_error(code, block_id, path, hint))

    if isinstance(raw, str):
        if len(raw) > MAX_RAW_JSON_LENGTH:
            error('limit_exceeded')
            return result
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            error('invalid_json')
            return result
    if not isinstance(raw, dict):
        error('rejected_envelope')
        return result
    data = copy.deepcopy(raw)
    blocks = data.get('blocks', [data] if data.get('type') or _infer_type(data) else [])
    if isinstance(blocks, dict):
        blocks = [blocks]
    if 'v' in data and (isinstance(data['v'], bool) or data['v'] not in (1, '1')):
        result['dropped'] = len(blocks) if isinstance(blocks, list) else 0
        error('rejected_envelope', path='v')
        return result
    if not isinstance(blocks, list) or not blocks:
        error('rejected_envelope', path='blocks')
        return result
    result['envelope'] = validate_envelope(copy.deepcopy(data), **kwargs)
    counts = {}
    for idx, block in enumerate(blocks[:MAX_BLOCKS]):
        block_id = str(idx)
        if not isinstance(block, dict):
            result['dropped'] += 1
            error('type_mismatch', block_id, f'blocks[{idx}]')
            continue
        if isinstance(block.get('id'), str):
            block_id = block['id']
        kind = str(block.get('type') or _infer_type(block) or '').strip().lower()
        hint = SIGNATURES.get(kind, '')
        code, path = None, ''
        if kind not in SIGNATURES:
            code, path = 'unknown_type', 'type'
        elif counts.get(kind, 0) >= MAX_BLOCKS_PER_TYPE.get(kind, MAX_BLOCKS):
            code, path = 'limit_exceeded', 'blocks'
        else:
            clean = validate_envelope({'v': 1, 'blocks': [copy.deepcopy(block)]}, **kwargs)
            if clean:
                counts[kind] = counts.get(kind, 0) + 1
                # An unsafe image is removed, not a dropped block.
                image = block.get('image')
                if isinstance(image, dict) and isinstance(image.get('url'), str) and 'image' not in clean['blocks'][0]:
                    from backend.ui_blocks.validate import is_allowed_image_url
                    if not is_allowed_image_url(image['url'], **kwargs):
                        error('unsafe_url', block_id, 'image.url', hint)
                continue
            is_scene = kind == 'sandbox' and (block.get('kind') == 'scene' or ('code' in block and 'html' not in block))
            required = 'code' if is_scene else REQUIRED.get(kind)
            if required and (required not in block or block[required] is None or block[required] == '' or block[required] == []):
                code, path = 'missing_required', required
            elif kind == 'controls' and (not isinstance(block.get('action'), dict) or block['action'].get('name') not in ('send_message', 'set_model')):
                code, path = 'invalid_action', 'action.name'
            elif kind == 'controls':
                fields = block.get('fields', [])
                if isinstance(fields, list):
                    f_ids = [f.get('id') for f in fields if isinstance(f, dict) and f.get('id')]
                    if len(f_ids) != len(set(f_ids)):
                        code, path = 'duplicate_id', 'fields'
                    else:
                        comp = block.get('computed')
                        if comp:
                            from backend.ui_blocks.expr import check_dependency_cycles
                            comp_list = [comp] if isinstance(comp, dict) else (comp if isinstance(comp, list) else [])
                            val_cyc, err_cyc, _ = check_dependency_cycles(comp_list, set(f_ids))
                            if not val_cyc:
                                code = 'duplicate_id' if err_cyc == 'duplicate_id' else 'invalid_expression'
                                path = 'computed'
                if not code:
                    code, path = 'invalid_action', 'action'
            elif kind == 'options' and (not isinstance(block.get('action'), dict) or block['action'].get('name') != 'send_message'):
                code, path = 'invalid_action', 'action.name'
            elif kind == 'options' and (not isinstance(block.get('action', {}).get('template'), str) or '{choice}' not in block['action']['template']):
                code, path = 'invalid_action', 'action.template'
            elif kind == 'sandbox' and (block.get('kind') == 'scene' or ('code' in block and 'html' not in block)):
                import re
                from backend.ui_blocks.validate import FORBIDDEN_SCENE_TERMS, MAX_SCENE_CODE
                code_str = block.get('code')
                if not isinstance(code_str, str) or not code_str.strip():
                    code, path = 'missing_required', 'code'
                elif len(code_str) > MAX_SCENE_CODE:
                    code, path = 'limit_exceeded', 'code'
                else:
                    for pat in FORBIDDEN_SCENE_TERMS:
                        if re.search(pat, code_str):
                            code, path = 'invalid_scene_code', 'code'
                            break
                    if not code:
                        code, path = 'type_mismatch', 'params'
            elif kind == 'sandbox' and isinstance(block.get('html'), str) and len(block['html']) > 12000:
                code, path = 'limit_exceeded', 'html'
            elif kind == 'chart' and (not block.get('rows')) and not (isinstance(block.get('series'), list) and block['series'] and isinstance(block['series'][0], dict) and 'rows' in block['series'][0]):
                code, path = 'missing_required', 'rows'
            elif kind == 'table' and (not block.get('rows')):
                code, path = 'missing_required', 'rows'
            else:
                code = 'type_mismatch'
                path = 'kind' if kind == 'chart' and str(block.get('kind') or 'bar').strip().lower() not in ('bar', 'line', 'compare', 'pie') else required or 'value'
        result['dropped'] += 1
        error(code, block_id, path, hint)
    if len(blocks) > MAX_BLOCKS:
        result['dropped'] += len(blocks) - MAX_BLOCKS
        error('limit_exceeded', str(MAX_BLOCKS), 'blocks')
    return result
