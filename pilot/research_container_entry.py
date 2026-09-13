"""Fixed container entry: Codex/MCP only, via the task's mounted gateway."""

import json
import math
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
from time import monotonic, time
from types import SimpleNamespace

from pilot.codex_research_worker import _command, _kill_group
from pilot.research_entry_urls import validate_entry_urls
from pilot.research_socket_relay import TaskSocketRelay


_FIELDS = {'version', 'model', 'token', 'mission', 'instructions', 'entry_urls',
           'max_reads', 'max_requests', 'max_searches', 'max_seconds', 'expires_at'}
_MAX_INPUT = 1024 * 1024
_cancel_requested = False


def validate_manifest(value):
    try:
        valid = type(value) is dict and set(value) == _FIELDS
        if not valid:
            raise ValueError()
        valid = type(value['version']) is int and value['version'] == 1
        for key, maximum in [('max_reads', 100), ('max_requests', 20),
                             ('max_searches', 10), ('max_seconds', 1800)]:
            valid &= type(value[key]) is int and 1 <= value[key] <= maximum
        for key, maximum in [('mission', 512 * 1024), ('instructions', 256 * 1024)]:
            valid &= type(value[key]) is str and 1 <= len(value[key].encode('utf-8')) <= maximum
        valid &= (type(value['model']) is str
                  and re.fullmatch(r'[A-Za-z0-9_./:-]{1,128}', value['model']) is not None)
        valid &= (type(value['token']) is str and 1 <= len(value['token']) <= 4096
                  and not any(c.isspace() for c in value['token']))
        valid &= (type(value['expires_at']) in (int, float) and math.isfinite(value['expires_at'])
                  and 0 < value['expires_at'] - time() <= 1800)
        valid &= type(value['entry_urls']) is list
        validate_entry_urls(value['entry_urls'])
        if not valid:
            raise ValueError()
    except (ValueError, TypeError, KeyError, OverflowError):
        raise ValueError('invalid_task_manifest') from None
    return value


def run_task(value):
    task = validate_manifest(value)
    deadline = monotonic() + min(task['max_seconds'], task['expires_at'] - time())
    with tempfile.TemporaryDirectory(prefix='yike-task-', dir='/tmp') as directory:
        root = Path(directory)
        for name in ('state', 'work', 'home'):
            (root / name).mkdir(mode=0o700)
        with TaskSocketRelay('/run/yike/bridge.sock', deadline=deadline) as relay:
            bridge = SimpleNamespace(base_url=relay.base_url, token=task['token'],
                search_url=relay.base_url+'/public-search', read_url=relay.base_url+'/public-read')
            command = _command(root, codex_binary='/opt/codex/bin/codex',
                python_binary='/app/.venv/bin/python', model=task['model'], bridge=bridge,
                max_reads=task['max_reads'], max_requests=task['max_requests'],
                max_seconds=task['max_seconds'], max_searches=task['max_searches'],
                search_enabled=True, controlled=True, entry_urls=tuple(task['entry_urls']),
                research_instructions=task['instructions'])
            remaining = deadline - monotonic()
            if remaining <= 0:
                return 124
            process = None
            try:
                if _cancel_requested:
                    raise _Cancelled()
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    start_new_session=True, cwd=root/'work', env={'PATH': '/usr/bin:/bin',
                    'HOME': str(root/'home'), 'CODEX_HOME': str(root/'state'),
                    'YIKE_BRIDGE_TOKEN': task['token']})
                data = task['mission'].encode('utf-8')
                while True:
                    if _cancel_requested:
                        raise _Cancelled()
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        return 124
                    try:
                        process.communicate(data, timeout=min(.1, remaining))
                        return process.returncode
                    except subprocess.TimeoutExpired:
                        data = None
            finally:
                if process is not None:
                    _kill_group(process)
                    process.wait()


class _Cancelled(Exception):
    pass


def _cancel(*_):
    global _cancel_requested
    _cancel_requested = True


def main():
    # The broker also owns an independent absolute deadline, including stdin setup.
    signal.signal(signal.SIGTERM, _cancel)
    signal.signal(signal.SIGINT, _cancel)
    try:
        raw = sys.stdin.buffer.read(_MAX_INPUT + 1)
        if len(raw) > _MAX_INPUT:
            return 2
        return run_task(json.loads(raw))
    except _Cancelled:
        return 130
    except Exception:
        # Never print manifest, task token, provider responses or exception details.
        return 2


if __name__ == '__main__':
    sys.exit(main())
