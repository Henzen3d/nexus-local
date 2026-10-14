import copy
import json
from pathlib import Path

import pytest

from backend.ui_blocks.diagnostics import ERROR_CODES, validate_with_diagnostics
from backend.ui_blocks.extract import extract_ui
from backend.ui_blocks.validate import validate_envelope
from backend.ui_blocks.telemetry import IntelligentUiTelemetry

CASES = json.loads((Path(__file__).parent / 'fixtures/ui-errors.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda c: c['name'])
def test_shared_diagnostics(case):
    original = copy.deepcopy(case['raw'])
    result = validate_with_diagnostics(case['raw'])
    assert [error['code'] for error in result['errors']] == case['codes']
    assert result['dropped'] == case['dropped']
    assert case['raw'] == original
    fence_raw = case['raw'] if isinstance(case['raw'], str) else json.dumps(case['raw'])
    fence_report = {}
    extract_ui('prose\n```nexus-ui\n' + fence_raw + '\n```', diagnostics=fence_report)
    assert fence_report['errors'] == result['errors']
    assert fence_report['dropped'] == result['dropped']
    for error in result['errors']:
        assert error['code'] in ERROR_CODES
        assert len(error['message']) <= 160
    assert result['envelope'] == validate_envelope(copy.deepcopy(case['raw']))


def test_fence_diagnostics_and_existing_tuple_contract():
    report = {}
    text, env = extract_ui('prose\n```nexus-ui\n{"blocks":[{"type":"callout"}]}\n```', diagnostics=report)
    assert text == 'prose' and env is None
    assert report['errors'][0]['code'] == 'missing_required'
    assert report['dropped'] == 1
    extract_ui('prose\n```nexus-ui\n{', diagnostics=report)
    assert report['errors'][0]['code'] == 'fence_unclosed'
    extract_ui('ordinary prose', diagnostics=report)
    assert report == {'errors': [], 'dropped': 0}


def test_image_configuration_and_no_payload_in_diagnostics():
    raw = {'blocks': [{'type': 'card', 'image': {'url': 'https://trusted.test/secret', 'alt': 'private'}}]}
    assert validate_with_diagnostics(raw, image_hosts=['trusted.test'])['errors'] == []
    report = validate_with_diagnostics(raw)
    assert report['errors'][0]['code'] == 'unsafe_url'
    assert 'secret' not in json.dumps(report['errors'])
    assert 'private' not in json.dumps(report['errors'])


def test_correction_counters_are_deduplicated_owner_scoped_and_bounded():
    telemetry = IntelligentUiTelemetry()
    telemetry.offer_correction('u', 'm', 'model')
    telemetry.offer_correction('u', 'm', 'model')
    assert telemetry.request_correction('other', 'm') is None
    assert telemetry.request_correction('u', 'm') == 'model'
    assert telemetry.request_correction('u', 'm') is None
    telemetry.correction_result('model', True)
    counts = telemetry.snapshot()['corrections']['model']
    assert counts == dict(correction_offered=1, correction_requested=1, correction_valid=1, valid_rate=1.0)
    for idx in range(2100):
        telemetry.offer_correction('u', str(idx), 'model')
    assert len(telemetry._correction_messages) == 2048
