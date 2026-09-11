"""One-shot, scoped header fix for the original 056e258 ops deployment.

No credentials, runtime changes or weakened request validation. The application
fix supersedes this equivalent edge policy on the next image deployment.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

SITE = Path('/www/server/panel/vhost/nginx/yike.tuokexing.net.conf')
CONF = Path('/opt/yike-ai2026/ops/ops-locations-056e258.conf')
BACKUP = CONF.with_name('ops-locations-before-browser-origin.conf')
NGINX = '/www/server/nginx/sbin/nginx'


def replace_config(contents):
    fd, staged = tempfile.mkstemp(prefix='ops-origin-', dir=CONF.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(staged, CONF.stat().st_mode & 0o777)
        os.replace(staged, CONF)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)


def main():
    assert hashlib.sha256(SITE.read_bytes()).hexdigest() == (
        '9a4a77be7e40105914534808c0bf36713a6ac0c05f499feafdb0e7f725d79180')
    original = CONF.read_bytes()
    assert hashlib.sha256(original).hexdigest() == (
        '452c317aefa8c1f8ad453d0a5fcd0e2854f640af861c452352c76b71925a1a5e')
    anchor = b'    proxy_cache off;\n'
    assert original.count(anchor) == 2
    assert b'proxy_hide_header Referrer-Policy' not in original
    replacement = (b'    proxy_hide_header Referrer-Policy;\n'
                   b'    add_header Referrer-Policy same-origin always;\n'
                   # Location add_header stops inheriting the server header.
                   b'    add_header Strict-Transport-Security "max-age=86400" always;\n'
                   + anchor)
    with BACKUP.open('xb') as backup:
        backup.write(original)
    try:
        replace_config(original.replace(anchor, replacement))
        subprocess.run([NGINX, '-t'], check=True, capture_output=True)
        subprocess.run([NGINX, '-s', 'reload'], check=True, capture_output=True)
    except Exception:
        replace_config(original)
        subprocess.run([NGINX, '-t'], check=True, capture_output=True)
        subprocess.run([NGINX, '-s', 'reload'], check=True, capture_output=True)
        raise RuntimeError('ops_header_fix_failed_original_restored') from None
    print('OPS_ORIGIN_HEADER_FIXED', hashlib.sha256(CONF.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
