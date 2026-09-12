"""Synthetic safe-diagnostic tests; UNKNOWN is deliberately not converted to success."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pilot.candidate_assessment_model import AssessmentModelError
from pilot.research_assessment import ResearchAssessmentRunner


@pytest.mark.parametrize('code,status,diagnostic', [
    ('assessment_provider_rejected', 502, None),
    ('invalid_assessment_result', 502, None),
    ('assessment_result_unknown', 504, 'worker_deadline'),
    ('invalid_assessment_result', 502, 'return_invalid_result'),
])
def test_known_error_is_diagnosable_without_releasing_unknown_or_losing_usage(monkeypatch, caplog, code, status, diagnostic):
    import pilot.research_assessment as module
    usage = {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12}
    original = AssessmentModelError(code, status, usage=usage)
    original.diagnostic = diagnostic
    class Model:
        def assess_before(self, deadline, **kwargs):
            if diagnostic == 'return_invalid_result':
                return {'invalid': True}, usage
            raise original
    def run_resource(*args, action, **kwargs):
        try:
            action(datetime.now(timezone.utc)+timedelta(seconds=30))
        except AssessmentModelError:
            pass
        return {'event': {'status': 'UNKNOWN'}, 'result': None, 'replayed': False}
    monkeypatch.setattr(module, 'run_resource', run_resource)
    snapshot = {key: {} for key in ('research','binding','description','content','strategy','model')}
    snapshot['description'] = 'PRIVATE_DESCRIPTION'
    snapshot['content'] = {'title': 'PRIVATE_SOURCE', 'body': 'PRIVATE_SOURCE', 'parent': None}
    snapshot['research'] = {'taskId': str(uuid4()), 'runId': str(uuid4())}
    request = SimpleNamespace(requestId=str(uuid4()))
    with pytest.raises(AssessmentModelError) as caught:
        ResearchAssessmentRunner(None).assess(None, request, snapshot, Model(),
            review_deadline=datetime.now(timezone.utc)+timedelta(seconds=30),
            before_dispatch=lambda: None)
    assert caught.value.code == 'assessment_result_unknown'
    assert caught.value.usage == usage
    records = [r for r in caplog.records if r.name == 'pilot.research_assessment']
    assert len(records) == 1
    data = json.loads(records[0].getMessage())
    assert data['model_error'] == code
    assert data['diagnostic'] == (None if diagnostic == 'return_invalid_result' else diagnostic)
    assert data['task_id'] == snapshot['research']['taskId']
    assert data['usage_reported'] is True
    assert type(data['elapsed_ms']) is int and data['elapsed_ms'] >= 0
    assert 'PRIVATE' not in records[0].getMessage()


def test_diagnostic_constructor_never_retains_unknown_text():
    error = AssessmentModelError('assessment_result_unknown', 504, diagnostic='PRIVATE_PROVIDER_TEXT')
    assert error.diagnostic is None
    assert 'PRIVATE' not in str(error)


@pytest.mark.parametrize('script,expected', [
    ('import time; time.sleep(2)', 'worker_deadline'),
    ('import sys; sys.exit(7)', 'worker_exit'),
    ('print("PRIVATE_INVALID_PROTOCOL")', 'worker_protocol'),
])
def test_actual_owned_child_diagnostics_never_include_output(monkeypatch, script, expected):
    import subprocess
    from tests.test_candidate_assessment_model import adapter, DESCRIPTION, CONTENT
    real_popen = subprocess.Popen
    children = []
    def popen(command, **kwargs):
        altered = list(command)
        altered[3] = script
        child = real_popen(altered, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(subprocess, 'Popen', popen)
    with pytest.raises(AssessmentModelError) as caught:
        adapter(timeout_seconds=0.2).assess(description=DESCRIPTION, content=CONTENT)
    assert caught.value.diagnostic == expected
    assert 'PRIVATE' not in str(caught.value)
    assert len(children) == 1 and children[0].poll() is not None
