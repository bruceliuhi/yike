"""Fixed host protocol with controlled source fixtures; no platform network."""
import importlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import pytest

from tests.test_candidate_mapping import execution, raw, BODY


def host():
    assert importlib.util.find_spec('app.windows_collection_host') is not None, 'fixed source host missing'
    return importlib.import_module('app.windows_collection_host')


def request(tmp_path):
    return dict(schema_version='windows-source-host-v1',
        runtime_path=str(tmp_path / 'runtime'), profile_path=str(tmp_path / 'profile'),
        output_path=str(tmp_path / 'output'), platform='BILIBILI', query='设备',
        max_records=20, timeout_seconds=60, mapping=dict(request_id='request-1',
            profile_version_id='profile-1', strategy_version_id='strategy-1', execution=execution()))


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8') + b'\n'


class Input:
    """One frame followed by an open pipe until the test explicitly closes it."""
    def __init__(self, frame):
        self.frame = io.BytesIO(frame)
        self.closed = threading.Event()
        self.reading = threading.Event()
        self.extra = b''

    def readline(self, limit):
        return self.frame.readline(limit)

    def read(self, size):
        self.reading.set()
        assert self.closed.wait(5), 'fixture input not released'
        return self.extra


def run(monkeypatch, payload, driver):
    api = host()
    monkeypatch.setattr(api, 'collect_windows_source', driver)
    source = Input(payload)
    output = io.BytesIO()
    try:
        assert api.main(source, output) == 0
    finally:
        source.closed.set()
    frames = output.getvalue().splitlines()
    assert len(frames) == 1
    return json.loads(frames[0]), output.getvalue()


def test_maps_actual_formal_records_preserving_raw_and_driver_metadata(tmp_path, monkeypatch):
    calls = []
    def driver(**kwargs):
        calls.append(kwargs)
        print('secret driver stdout')
        print('secret driver stderr', file=sys.stderr)
        return dict(state='COLLECTED', records=[raw('BILIBILI')], query='实际搜索词',
                    collector_version='source-2', output_path='secret output path', task_completed=False)
    result, wire = run(monkeypatch, encoded(request(tmp_path)), driver)
    assert set(result) == {'schema_version', 'state', 'records'}
    assert result['state'] == 'COLLECTED'
    record = result['records'][0]
    assert record['body'] == BODY and record['query'] == '实际搜索词'
    assert record['collector_version'] == 'source-2'
    assert record['normalizer_version'] == 'raw-comment-candidate-v1'
    assert calls[0]['runtime_path'] == tmp_path / 'runtime'
    assert 'mapping' not in calls[0] and 'secret' not in wire.decode()


def test_optional_expected_account_passed_only_to_xhs_driver(tmp_path, monkeypatch):
    expected = '66c01234abcdef0123456789'
    calls = []
    def driver(**kwargs):
        calls.append(kwargs)
        return dict(state='COLLECTED', records=[], query=kwargs['query'], collector_version='source-1')
    result, _ = run(monkeypatch, encoded(request(tmp_path) | {'platform': 'XIAOHONGSHU',
        'expected_account_public_id': expected}), driver)
    assert result['state'] == 'COLLECTED' and calls[0]['expected_account_public_id'] == expected


@pytest.mark.parametrize('platform,expected', [('BILIBILI', '66c01234abcdef0123456789'),
    ('XIAOHONGSHU', None), ('XIAOHONGSHU', 1), ('XIAOHONGSHU', 'bad'),
    ('XIAOHONGSHU', '66c01234abcdef0123456789?token=private')])
def test_invalid_expected_account_never_launches(tmp_path, monkeypatch, platform, expected):
    calls = []
    result, _ = run(monkeypatch, encoded(request(tmp_path) | {'platform': platform,
        'expected_account_public_id': expected}), lambda **kwargs: calls.append(kwargs))
    assert result['state'] == 'FAILED' and not calls


@pytest.mark.parametrize('change', [dict(platform='ZHIHU'), dict(query='a,b'), dict(query=''),
    dict(query=' padded '), dict(query='x' * 81), dict(max_records=True), dict(max_records=101),
    dict(timeout_seconds=True), dict(timeout_seconds=901), dict(runtime_path='relative'),
    dict(schema_version='other'), dict(cookie='secret'), dict(mapping={})])
def test_invalid_requests_rejected_before_source(tmp_path, monkeypatch, change):
    calls = []
    result, _ = run(monkeypatch, encoded(request(tmp_path) | change), lambda **kw: calls.append(kw))
    assert result['state'] == 'FAILED' and calls == [] and 'records' not in result


@pytest.mark.parametrize('kind', ['extra-mapping', 'extra-execution', 'bad-id', 'bool-version'])
def test_mapping_really_validated_before_source(tmp_path, monkeypatch, kind):
    payload = request(tmp_path)
    if kind == 'extra-mapping': payload['mapping']['cookie'] = 'secret'
    elif kind == 'extra-execution': payload['mapping']['execution']['private_key'] = 'secret'
    elif kind == 'bad-id': payload['mapping']['request_id'] = 'bad id'
    else: payload['mapping']['execution']['credential_version'] = True
    calls = []
    result, wire = run(monkeypatch, encoded(payload), lambda **kw: calls.append(kw))
    assert result['state'] == 'FAILED' and not calls and b'secret' not in wire


@pytest.mark.parametrize('frame', [b'{}', b'\xff\n', b'[]\n', b'{"x":NaN}\n',
    b'{"x":Infinity}\n', b'{"x":1,"x":2}\n', b' ' * 65536 + b'\n',
    ('"' + '中' * 22000 + '"\n').encode('utf-8')],
    ids=['no-newline', 'invalid-utf8', 'array', 'nan', 'infinity', 'duplicate', 'long-ascii', 'long-utf8'])
def test_bad_or_oversize_json_never_launches(monkeypatch, frame):
    calls = []
    result, _ = run(monkeypatch, frame, lambda **kw: calls.append(kw))
    assert result['state'] == 'FAILED' and not calls


@pytest.mark.parametrize('extra', [b'', b'x'])
def test_cancel_waits_for_physical_driver_stop(tmp_path, monkeypatch, extra):
    api = host()
    source = Input(encoded(request(tmp_path)))
    source.extra = extra
    output = io.BytesIO()
    started, cancelled, cleanup = threading.Event(), threading.Event(), threading.Event()
    def driver(**kwargs):
        started.set()
        assert source.reading.wait(3)
        while not kwargs['cancel_requested']():
            threading.Event().wait(.005)
        cancelled.set()
        assert cleanup.wait(3)
        return {'state': 'CANCELLED', 'task_completed': False}
    monkeypatch.setattr(api, 'collect_windows_source', driver)
    worker = threading.Thread(target=lambda: api.main(source, output))
    worker.start()
    try:
        assert started.wait(3)
        source.closed.set()
        assert cancelled.wait(3)
        assert worker.is_alive() and output.getvalue() == b''
    finally:
        cleanup.set()
        source.closed.set()
        worker.join(3)
    assert not worker.is_alive()
    assert json.loads(output.getvalue())['state'] == 'CANCELLED'


@pytest.mark.parametrize('state', ['CANCELLED', 'TIMED_OUT', 'BLOCKED_INPUT', 'FAILED', 'UNKNOWN'])
def test_failure_envelopes_never_forward_arbitrary_fields(tmp_path, monkeypatch, state):
    result, wire = run(monkeypatch, encoded(request(tmp_path)), lambda **kw:
        dict(state=state, error_code='secret token', records=['secret data'], output_path='secret path'))
    assert result['state'] == (state if state != 'UNKNOWN' else 'FAILED')
    assert 'records' not in result and b'secret' not in wire


def test_exception_never_leaks(tmp_path, monkeypatch):
    def driver(**kwargs):
        raise RuntimeError('secret token path database')
    result, wire = run(monkeypatch, encoded(request(tmp_path)), driver)
    assert result['state'] == 'FAILED' and b'secret' not in wire
    assert result['error_code'] == 'SOURCE_HOST_FAILED'


def test_response_byte_budget_is_all_or_nothing(tmp_path, monkeypatch):
    payload = request(tmp_path) | {'max_records': 100}
    records = [raw('BILIBILI', str(1000 + index)) for index in range(100)]
    for record in records: record['comment']['content'] = '中' * 20000
    result, wire = run(monkeypatch, encoded(payload), lambda **kw: dict(state='COLLECTED',
        records=records, query='设备', collector_version='collector-1'))
    assert result['state'] == 'FAILED' and 'records' not in result
    assert len(wire) < 4096


def test_real_module_stdin_stdout_invalid_input_is_single_sanitized_frame():
    host()
    proc = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'app.windows_collection_host'],
        input=b'{"secret":"do-not-leak"}\n', capture_output=True, timeout=10,
        cwd=Path(__file__).resolve().parents[1])
    assert proc.returncode == 0 and proc.stderr == b''
    assert len(proc.stdout.splitlines()) == 1
    assert json.loads(proc.stdout)['state'] == 'FAILED'
    assert b'secret' not in proc.stdout and b'do-not-leak' not in proc.stdout


def test_nested_duplicate_key_in_otherwise_valid_request_is_rejected(tmp_path, monkeypatch):
    frame = encoded(request(tmp_path)).replace(b'"device_id": "device-1"',
        b'"device_id":"device-1","device_id":"device-2"')
    calls = []
    result, _ = run(monkeypatch, frame, lambda **kw: calls.append(kw))
    assert result['state'] == 'FAILED' and not calls


def test_mapping_failure_does_not_emit_partial_records(tmp_path, monkeypatch):
    result, wire = run(monkeypatch, encoded(request(tmp_path)), lambda **kw: dict(
        state='COLLECTED', records=[raw('BILIBILI'), {'secret': 'private data'}],
        query='设备', collector_version='source-1'))
    assert result['state'] == 'FAILED' and 'records' not in result and b'secret' not in wire
    assert result['error_code'] == 'COLLECTION_PARSE_FAILED'


def test_formal_record_failure_after_driver_return_is_not_a_stop_failure(tmp_path, monkeypatch):
    invalid = raw('BILIBILI')
    invalid['content']['title'] = ''
    result, wire = run(monkeypatch, encoded(request(tmp_path)), lambda **kw: dict(
        state='COLLECTED', records=[invalid], query='设备', collector_version='source-1'))
    assert result == dict(schema_version='windows-source-host-v1', state='FAILED',
                          error_code='COLLECTION_PARSE_FAILED')
    assert 'records' not in result and b'content' not in wire


def test_keyboard_interrupt_is_reported_only_after_driver_cleanup(tmp_path, monkeypatch):
    cleaned = []
    def driver(**kwargs):
        try:
            raise KeyboardInterrupt()
        finally:
            cleaned.append(True)
    result, _ = run(monkeypatch, encoded(request(tmp_path)), driver)
    assert cleaned == [True] and result['state'] == 'CANCELLED'


@pytest.mark.parametrize('cancel,invalid', [(False, False), (True, False), (False, True)])
def test_real_pipe_with_controlled_driver_waits_for_eof_cleanup_or_exits_with_open_stdin(tmp_path, cancel, invalid):
    host()
    marker = tmp_path / 'fixture-state'
    script = '''import sys, time
from pathlib import Path
from app import windows_collection_host as host
marker = Path(sys.argv[1])
def collect(**kw):
    print('secret log')
    print('secret diagnostic', file=sys.stderr)
    marker.write_text('started')
    if sys.argv[2] == 'cancel':
        while not kw['cancel_requested'](): time.sleep(.005)
        time.sleep(.05)
        marker.write_text('stopped')
        return {'state': 'CANCELLED', 'task_completed': False}
    return {'state': 'COLLECTED', 'records': [{}] if sys.argv[2] == 'invalid' else [], 'query': kw['query'],
            'collector_version': 'controlled-1', 'task_completed': False}
host.collect_windows_source = collect
raise SystemExit(host.main())
'''
    proc = subprocess.Popen([sys.executable, '-X', 'utf8', '-c', script, str(marker),
        'cancel' if cancel else 'invalid' if invalid else 'collect'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=Path(__file__).resolve().parents[1])
    lines = queue.Queue()
    reader = threading.Thread(target=lambda: lines.put(proc.stdout.readline()), daemon=True)
    reader.start()
    try:
        proc.stdin.write(encoded(request(tmp_path)))
        proc.stdin.flush()
        if cancel:
            deadline = time.monotonic() + 5
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.005)
            assert marker.exists() and marker.read_text() == 'started'
            assert lines.empty() and proc.poll() is None
            proc.stdin.close()
        wire = lines.get(timeout=5)
        result = json.loads(wire)
        assert result['state'] == ('CANCELLED' if cancel else 'FAILED' if invalid else 'COLLECTED')
        if invalid:
            assert result['error_code'] == 'COLLECTION_PARSE_FAILED' and 'records' not in result
        assert proc.wait(timeout=5) == 0
        assert proc.stdout.read() == b'' and proc.stderr.read() == b''
        if cancel: assert marker.read_text() == 'stopped'
        else: assert not proc.stdin.closed  # shutdown cannot deadlock on the input watcher
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
        for stream in (proc.stdin, proc.stdout, proc.stderr): stream.close()
        reader.join(3)
