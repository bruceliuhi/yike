import subprocess
import sys

import pytest

from app.collector import _minimal_child_environment


@pytest.mark.skipif(sys.platform != 'win32', reason='real Windows getpass import')
def test_windows_minimal_environment_supports_username_without_secrets(monkeypatch):
    for name in ('LOGNAME', 'USER', 'LNAME'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('USERNAME', 'yike-runtime-test')
    monkeypatch.setenv('YIKE_PRIVATE_TEST_SECRET', 'must-not-be-forwarded')
    environment = _minimal_child_environment()
    assert 'YIKE_PRIVATE_TEST_SECRET' not in environment
    # getpass is called while aiomysql imports, even for the runtime's --help.
    # Real Windows lacks pwd, so it needs the ordinary Windows USERNAME value.
    child = subprocess.run([sys._base_executable, '-I', '-S', '-c',
        'import getpass; print(getpass.getuser())'], env=environment,
        capture_output=True, text=True, timeout=10)
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == 'yike-runtime-test'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows executable discovery')
def test_windows_minimal_environment_supplies_only_exe_search(monkeypatch):
    # PyExecJS uses PATHEXT to discover its Node executable. Do not inherit
    # ambient shell-script suffixes when only a governed executable is needed.
    monkeypatch.setenv('PATHEXT', '.EXE;.BAT;.CMD;.UNTRUSTED')
    assert _minimal_child_environment().get('PATHEXT') == '.EXE'
