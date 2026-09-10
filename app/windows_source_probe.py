"""Bounded, read-only installed-source probe; READY grants no source capability."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import re
import sys
import threading

from app.windows_source_driver import _exclusive_paths, verify_installed_runtime


SCHEMA = 'windows-source-probe-v1'


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value: raise ValueError()
        value[key] = item
    return value


def _constant(_): raise ValueError()


def _request(stdin):
    frame = stdin.readline(65537)
    if isinstance(frame, str): frame = frame.encode('utf-8')
    if len(frame) > 65536 or not frame.endswith(b'\n'): raise ValueError()
    value = json.loads(frame.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=_constant)
    if not isinstance(value, dict) or set(value) != {'schema_version', 'runtime_path'} or value['schema_version'] != SCHEMA:
        raise ValueError()
    text = value['runtime_path']
    if not isinstance(text, str) or not text.isprintable() or not re.match(r'^[A-Za-z]:[\\/]', text): raise ValueError()
    text.encode('utf-8')
    path = Path(text)
    if not path.is_absolute() or len(path.drive) != 2: raise ValueError()
    return path


def _watch(stdin, cancelled):
    try: stdin.read(1)
    except Exception: pass
    finally: cancelled.set()


def main(stdin=None, stdout=None):
    if stdin is None: stdin = sys.stdin.buffer.raw
    if stdout is None: stdout = sys.stdout.buffer
    cancelled = threading.Event()
    result = dict(schema_version=SCHEMA, state='FAILED', error_code='SOURCE_PROBE_FAILED')
    with open(os.devnull, 'w', encoding='utf-8') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            path = _request(stdin)
            threading.Thread(target=_watch, args=(stdin, cancelled), daemon=True).start()
            with _exclusive_paths([path]):
                if not cancelled.is_set(): verify_installed_runtime(path)
            if cancelled.is_set(): result['error_code'] = 'SOURCE_PROBE_CANCELLED'
            else: result = dict(schema_version=SCHEMA, state='READY')
        except (Exception, KeyboardInterrupt):
            pass
        wire = (json.dumps(result, separators=(',', ':')) + '\n').encode('utf-8')
        try: stdout.write(wire); stdout.flush()
        except (OSError, ValueError): pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
