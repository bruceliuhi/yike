"""Provider/worker boundary fixtures, not live model or billing evidence."""
import io
import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest

from pilot import candidate_assessment_model as api
from pilot import candidate_assessment_worker as worker
from tests.test_candidate_assessment_model import adapter, envelope, run_response, worker_input, DESCRIPTION, CONTENT

USAGE = dict(prompt_tokens=12, completion_tokens=8, total_tokens=20)


@pytest.mark.parametrize('change', ['bad_json', 'bad_grounding', 'refusal', 'length', 'no_choices'])
def test_complete_provider_envelope_retains_usage_even_when_answer_rejected(change):
    value = envelope()
    if change == 'bad_json': value['choices'][0]['message']['content'] = '{bad'
    if change == 'bad_grounding':
        answer = json.loads(value['choices'][0]['message']['content'])
        answer['intent']['citations'][0]['quote'] = 'SECRET_UNGROUNDED_QUOTE'
        value['choices'][0]['message']['content'] = json.dumps(answer)
    if change == 'refusal': value['choices'][0]['message']['refusal'] = 'SECRET_REFUSAL'
    if change == 'length': value['choices'][0]['finish_reason'] = 'length'
    if change == 'no_choices': value['choices'] = []
    with pytest.raises(api.AssessmentModelError) as caught:
        run_response(httpx.Response(200, json=value))
    assert caught.value.code == 'invalid_assessment_result'
    assert caught.value.usage == USAGE
    assert 'SECRET' not in str(caught.value) + repr(caught.value)


@pytest.mark.parametrize('usage', [None, {}, {'prompt_tokens':True,'completion_tokens':1,'total_tokens':2},
    {'prompt_tokens':1,'completion_tokens':1,'total_tokens':3}])
def test_invalid_error_usage_is_unknown_not_zero(usage):
    value = api.AssessmentModelError('invalid_assessment_result',502,usage=usage)
    assert value.usage is None


def test_error_usage_is_copied_and_strips_non_measured_fields():
    raw = USAGE | {'secret':'must not survive'}
    error = api.AssessmentModelError('invalid_assessment_result',502,usage=raw)
    raw['total_tokens'] = 200
    assert error.usage == USAGE and error.args == ('invalid_assessment_result',)


def test_worker_serializes_only_validated_error_usage(monkeypatch):
    def fail(*args,**kwargs):
        raise api.AssessmentModelError('invalid_assessment_result',502,usage=USAGE | {'secret':'discard'})
    monkeypatch.setattr(api.OpenAICompatibleCandidateAssessmentModel,'_assess_in_process',fail)
    output = io.BytesIO()
    monkeypatch.setattr(worker,'sys',SimpleNamespace(stdin=SimpleNamespace(buffer=io.BytesIO(json.dumps(worker_input()).encode())),
        stdout=SimpleNamespace(buffer=output)))
    worker.main()
    assert json.loads(output.getvalue()) == dict(error='invalid_assessment_result',status=502,usage=USAGE)


@pytest.mark.parametrize('kind', ['legacy','usage','bad_usage','extra'])
def test_parent_accepts_only_fixed_worker_error_frames(monkeypatch,kind):
    frame = dict(error='invalid_assessment_result',status=502)
    if kind != 'legacy': frame['usage'] = USAGE
    if kind == 'bad_usage': frame['usage'] = {'prompt_tokens': True}
    if kind == 'extra': frame['secret'] = 'must-not-leak'
    real_popen = subprocess.Popen
    def boundary(args,**kwargs):
        command = list(args)
        command[3] = 'import sys;sys.stdin.buffer.read();sys.stdout.buffer.write(' + repr(json.dumps(frame).encode()) + ')'
        return real_popen(command,**kwargs)
    monkeypatch.setattr(subprocess,'Popen',boundary)
    with pytest.raises(api.AssessmentModelError) as caught:
        adapter().assess(description=DESCRIPTION,content=CONTENT)
    assert caught.value.code == 'invalid_assessment_result'
    assert caught.value.usage == (USAGE if kind == 'usage' else None)


def test_incomplete_envelope_cannot_claim_usage():
    with pytest.raises(api.AssessmentModelError) as caught:
        run_response(httpx.Response(200,content=b'{"usage":{"prompt_tokens":12,"completion_tokens":8,"total_tokens":20},'))
    assert caught.value.usage is None


def test_real_owned_worker_and_loopback_provider_keep_rejected_answer_usage():
    requests = []
    value = envelope()
    value['choices'][0]['message']['content'] = '{invalid answer'
    body = json.dumps(value).encode()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            requests.append(self.path)
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self,*args): pass
    server = ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        with pytest.raises(api.AssessmentModelError) as caught:
            adapter(base_url=f'http://127.0.0.1:{server.server_port}/v1').assess(description=DESCRIPTION,content=CONTENT)
        assert caught.value.code == 'invalid_assessment_result' and caught.value.usage == USAGE
        assert requests == ['/v1/chat/completions']
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
