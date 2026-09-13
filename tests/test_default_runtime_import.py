"""The default server must start without optional research transport packages."""
import os
from pathlib import Path
import subprocess
import sys


def test_default_runtime_does_not_import_optional_mcp_transport():
    root = Path(__file__).resolve().parents[1]
    script = r'''
import importlib.abc
import sys
sys.path.insert(0, sys.argv[1])
class NoOptionalTransport(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'mcp' or fullname.startswith('mcp.'):
            raise ModuleNotFoundError('optional_research_transport_loaded')
sys.meta_path.insert(0, NoOptionalTransport())
from pilot.runtime import build_runtime_app
from pilot.db import PilotDatabase
from fastapi.testclient import TestClient
app = build_runtime_app(PilotDatabase('postgresql://synthetic:unused@127.0.0.1:1/synthetic'),
    auth_secret='synthetic-runtime-import-secret-32-bytes', environment={})
with TestClient(app) as client:
    assert client.get('/healthz').json() == {'status':'ok'}
assert not any(name == 'mcp' or name.startswith('mcp.') for name in sys.modules)
assert 'pilot.research_tools' not in sys.modules
print('DEFAULT_RUNTIME_WITHOUT_MCP_OK')
'''
    env = {name: value for name, value in os.environ.items()
           if name.upper() in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP')}
    result = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', '-c', script, str(root)],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'DEFAULT_RUNTIME_WITHOUT_MCP_OK'
