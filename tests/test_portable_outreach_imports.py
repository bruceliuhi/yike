"""Copy the actual governed project subset, never import missing files from checkout."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

from app.windows_portable_inventory import HOST_FILES


def test_portable_project_subset_imports_outreach_without_checkout(tmp_path):
    root = Path(__file__).resolve().parents[1]
    staged = tmp_path / 'project'
    for name in HOST_FILES:
        target = staged / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, target)
    modules = ('app.windows_platform_outreach', 'app.platform_outreach_worker',
               'app.platform_outreach_runtime', 'app.xhs_comment_channel')
    script = '''
import importlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
for name in sys.argv[2:]:
    importlib.import_module(name)
loaded = {name: str(pathlib.Path(module.__file__).resolve())
          for name, module in sys.modules.items()
          if name.split('.')[0] in ('app', 'pilot', 'connectors')
          and getattr(module, '__file__', None)}
assert all(pathlib.Path(value).is_relative_to(root) for value in loaded.values())
print(json.dumps(loaded))
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', script, str(staged), *modules],
                            cwd=tmp_path, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout)
    assert set(modules) <= loaded.keys()
    assert not list(staged.rglob('__pycache__'))
