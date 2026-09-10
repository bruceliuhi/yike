"""Governed lock/patch bytes must survive Git's Windows CRLF defaults."""
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_governed_vendor_bytes_survive_windows_checkout(tmp_path):
    source = tmp_path / 'source'
    checkout = tmp_path / 'windows-checkout'
    source.mkdir()

    def git(*args, cwd=source):
        return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.PIPE)

    git('init', '-q')
    git('config', 'core.autocrlf', 'false')
    git('config', 'user.name', 'Vendor checkout test')
    git('config', 'user.email', 'vendor-test@example.invalid')
    lock_bytes = git('show', 'HEAD:vendor/mediacrawler.lock', cwd=ROOT)
    lock = json.loads(lock_bytes)
    governed = {'vendor/mediacrawler.lock': lock_bytes}
    for patch in lock['patches']:
        governed[patch['path']] = git('show', 'HEAD:' + patch['path'], cwd=ROOT)
        assert hashlib.sha256(governed[patch['path']]).hexdigest() == patch['sha256']
    for relative, content in governed.items():
        target = source / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    attributes = ROOT / '.gitattributes'
    if attributes.exists():
        (source / '.gitattributes').write_bytes(attributes.read_bytes())
    git('add', '.')
    git('commit', '-qm', 'isolated governed source')
    # Apply the actual Git conversion, not a mocked newline replacement.
    git('clone', '-q', '--config', 'core.autocrlf=true', str(source), str(checkout))
    for relative, content in governed.items():
        assert (checkout / relative).read_bytes() == content, relative
