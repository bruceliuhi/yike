import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest


def module():
    assert importlib.util.find_spec('app.windows_source_view'), 'source host missing'
    return importlib.import_module('app.windows_source_view')


def request(tmp_path):
    return dict(schema_version='windows-source-view-v1', runtime_path=str(tmp_path/'runtime'),
        profile_path=str(tmp_path/'profile'),output_path=str(tmp_path/'output'),timeout_seconds=300,
        note_id='a'*24,expected_account='b'*24,author_id='c'*24,original_query=None)


@pytest.mark.parametrize('change', [dict(note_id='secret'),dict(expected_account='secret'),dict(author_id=None),
    dict(timeout_seconds=301),dict(timeout_seconds=True),dict(original_query='\n'),dict(extra='secret')])
def test_bad_request_never_launches(tmp_path, monkeypatch, change):
    api = module()
    monkeypatch.setattr(api,'view_windows_source',lambda **kw: pytest.fail('launched'))
    output = io.BytesIO()
    api.main(io.BytesIO((json.dumps(request(tmp_path)|change)+'\n').encode()), output)
    assert json.loads(output.getvalue())['error_code'] == 'XHS_SOURCE_INVALID_INPUT'
    assert b'secret' not in output.getvalue()


@pytest.mark.parametrize('state', ['SOURCE_OPENED','AUTHENTICATED','BLOCKED_INPUT'])
def test_opened_is_not_terminal(state):
    with pytest.raises(ValueError): module()._terminal(dict(schema_version='windows-source-view-v1',state=state))


def test_eof_cancels_and_suppresses_raw_logs(tmp_path,monkeypatch):
    api=module()
    def viewer(**kw):
        print('secret raw logs')
        deadline=time.monotonic()+1
        while not kw['cancel_requested']() and time.monotonic()<deadline: time.sleep(0.001)
        assert kw['cancel_requested']()
        return dict(schema_version=api.SCHEMA,state='CANCELLED',error_code='XHS_SOURCE_CANCELLED')
    monkeypatch.setattr(api,'view_windows_source',viewer)
    output=io.BytesIO()
    api.main(io.BytesIO((json.dumps(request(tmp_path))+'\n').encode()),output)
    assert json.loads(output.getvalue())['state']=='CANCELLED'
    assert b'secret' not in output.getvalue()


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows paths')
def test_lock_busy_is_known_failure_without_supervisor(tmp_path,monkeypatch):
    api=module()
    from app.windows_source_driver import WindowsSourceError
    @contextmanager
    def busy(paths):
        raise WindowsSourceError('source_busy')
        yield
    monkeypatch.setattr(api,'_exclusive_paths',busy)
    monkeypatch.setattr(api,'run_supervised_process',lambda *a,**kw:pytest.fail('supervisor started'))
    payload=request(tmp_path); payload.pop('schema_version')
    result=api.view_windows_source(**payload,on_opened=lambda:pytest.fail('opened'))
    assert result==dict(schema_version=api.SCHEMA,state='FAILED',error_code='XHS_SOURCE_BUSY')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows private directories')
@pytest.mark.parametrize('outcome', ['closed','cleanup-unknown','cleanup-interrupt','missing-profile','unverified-close'])
def test_host_private_profile_job_cleanup_and_fail_closed(tmp_path,monkeypatch,outcome):
    api = module()
    from app.windows_private_directory import create_private_directory
    create_private_directory(tmp_path/'runtime')
    if outcome != 'missing-profile': create_private_directory(tmp_path/'profile')
    monkeypatch.setattr(api,'verify_installed_runtime',lambda _:Path(sys.executable))
    calls, opened = [],[]
    def runner(command, **kw):
        calls.append(kw)
        assert Path(command[-1]).name == 'source_view_worker.py'
        assert 0 < kw['timeout_seconds'] <= 300
        assert 'DATABASE_URL' not in kw['env']
        if outcome == 'cleanup-unknown': raise OSError('secret cleanup')
        if outcome == 'cleanup-interrupt': raise KeyboardInterrupt()
        output = Path(kw['env']['YIKE_SOURCE_OUTPUT_PATH'])
        if outcome != 'unverified-close':
            (output/'.yike-source-opened.json').write_text(json.dumps(dict(schema_version=api.SCHEMA,state='SOURCE_OPENED')))
            kw['poll_callback'](); kw['poll_callback']()
        (output/'.yike-source-terminal.json').write_text(json.dumps(dict(schema_version=api.SCHEMA,state='CLOSED')))
        return SimpleNamespace(returncode=0,cancelled=False,timed_out=False)
    monkeypatch.setenv('DATABASE_URL','secret')
    monkeypatch.setattr(api,'run_supervised_process',runner)
    payload=request(tmp_path); payload.pop('schema_version')
    result=api.view_windows_source(**payload,on_opened=lambda:opened.append(True))
    assert result['state'] == ('CLOSED' if outcome == 'closed' else 'FAILED')
    if outcome == 'closed': assert opened == [True]
    if outcome == 'missing-profile': assert not calls and not (tmp_path/'profile').exists()
    if outcome in ('cleanup-unknown','cleanup-interrupt'): assert result['error_code']=='SOURCE_HOST_FAILED'
    assert 'secret' not in str(result)
