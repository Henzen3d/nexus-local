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
    'invalid_json', 'fence_unclosed', 'rejected_envelope',
)
SIGNATURES = {
    'progress': 'progress: value, max or steps[{label,state}]',
    'card': 'card: title, body?, facts?, image?',
    'chart': 'chart: kind bar|line|compare, x_key, series[{key,label}], rows[]',
    'controls': 'controls: fields[], action{name:send_message|set_model,template?|field?}',
    'sandbox': 'sandbox: title, html, css?, js?',
    'metric': 'metric: items[{label,value}]',
    'callout': 'callout: body, kind info|success|warning|danger',
    'follow_up': 'follow_up: items[string]',
}
REQUIRED = {'chart': 'series', 'controls': 'fields', 'sandbox': 'html',
            'metric': 'items', 'callout': 'body', 'follow_up': 'items'}


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
            required = REQUIRED.get(kind)
            if required and (required not in block or block[required] is None or block[required] == '' or block[required] == []):
                code, path = 'missing_required', required
            elif kind == 'controls' and (not isinstance(block.get('action'), dict) or block['action'].get('name') not in ('send_message', 'set_model')):
                code, path = 'invalid_action', 'action.name'
            elif kind == 'controls':
                code, path = 'invalid_action', 'action'
            elif kind == 'sandbox' and isinstance(block.get('html'), str) and len(block['html']) > 12000:
                code, path = 'limit_exceeded', 'html'
            elif kind == 'chart' and (not block.get('rows')) and not (isinstance(block.get('series'), list) and block['series'] and isinstance(block['series'][0], dict) and 'rows' in block['series'][0]):
                code, path = 'missing_required', 'rows'
            else:
                code = 'type_mismatch'
                path = 'kind' if kind == 'chart' and str(block.get('kind') or 'bar').strip().lower() not in ('bar', 'line', 'compare') else required or 'value'
        result['dropped'] += 1
        error(code, block_id, path, hint)
    if len(blocks) > MAX_BLOCKS:
        result['dropped'] += len(blocks) - MAX_BLOCKS
        error('limit_exceeded', str(MAX_BLOCKS), 'blocks')
    return result
