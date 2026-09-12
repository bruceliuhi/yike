"""Actual baseline support handler, isolated from the current production router."""
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

from tests.test_public_sampling_progress import _support_client
from tests.test_execution_api import auth_headers


def test_baseline_v2_rejection_allows_read_only_v1_negotiation(monkeypatch):
    from pilot import ui_api
    source = subprocess.check_output([
        'git', 'show', '031c14a170a6a45fe51677fabf6067340bb1b57a:pilot/execution_api.py',
    ], cwd=Path(__file__).resolve().parents[1], text=True)
    module = ModuleType('yike_revisit_legacy_execution_api')
    monkeypatch.setitem(sys.modules, module.__name__, module)
    exec(compile(source, '<baseline-execution-api>', 'exec'), module.__dict__)
    monkeypatch.setattr(ui_api, 'register_execution_api', module.register_execution_api)
    client, _ = _support_client()
    rejected = client.get('/api/ui/execution-support?sampling_version=2', headers=auth_headers())
    legacy = client.get('/api/ui/execution-support?sampling_version=1', headers=auth_headers())
    assert rejected.status_code == 422 and rejected.json()['detail']['code'] == 'invalid_request'
    assert legacy.status_code == 200 and legacy.json()['public_sampling'] == 'committed-round-v1'
    Path('/tmp/yike-public-revisit-legacy-support.json').write_text(json.dumps({
        'negotiated': {'status': rejected.status_code, 'body': rejected.json()},
        'legacy': {'status': legacy.status_code, 'body': legacy.json()},
    }, ensure_ascii=False))
