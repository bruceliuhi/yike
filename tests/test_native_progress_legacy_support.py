"""Freeze the actual previous support handler behavior; no network or database."""
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

from tests.test_public_sampling_progress import _support_client
from tests.test_execution_api import auth_headers


def test_previous_handler_rejects_new_query_but_plain_capability_remains_readable(monkeypatch):
    from pilot import ui_api
    source=subprocess.check_output(['git','show','f9b4c3514a1d9c8780453290e11e4346d1d24731:pilot/execution_api.py'],
        cwd=Path(__file__).resolve().parents[1],text=True)
    module=ModuleType('yike_legacy_execution_api')
    monkeypatch.setitem(sys.modules,module.__name__,module)
    exec(compile(source,'<previous-execution-api>','exec'),module.__dict__)
    monkeypatch.setattr(ui_api,'register_execution_api',module.register_execution_api)
    client,_=_support_client('four-platform-monitor-v1')
    rejected=client.get('/api/ui/execution-support?native_progress_version=1',headers=auth_headers())
    plain=client.get('/api/ui/execution-support',headers=auth_headers())
    assert rejected.status_code==422 and rejected.json()['detail']['code']=='invalid_request'
    assert plain.status_code==200 and 'native_progress' not in plain.json()
    Path('/tmp/yike-native-progress-legacy-support.json').write_text(json.dumps({
        'negotiated':{'status':rejected.status_code,'body':rejected.json()},
        'plain':{'status':plain.status_code,'body':plain.json()}},ensure_ascii=False))
