"""One fixed, private Windows source IPC operation; never grants authority.

The main process must first bind a live lease and the account/profile identity.
It keeps stdin open until completion, and closes it to request cancellation.
Only the existing source driver owns processes, cleanup and platform access.
"""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import threading

from app.collector import _EXIT_RESULTS
from app.repository import canonical_single_keyword
from app.windows_source_driver import collect_windows_source
from app.platform_login_worker import valid_account
from connectors.candidate_mapping import build_comment_batch
from pilot.native_collection_links import validate_bili_collection_target
from app.bili_search_progress import checked_input, checked_delta


SCHEMA_VERSION = 'windows-source-host-v1'
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_FIELDS = {'schema_version', 'runtime_path', 'profile_path', 'output_path',
           'platform', 'query', 'max_records', 'timeout_seconds', 'mapping'}
_MAPPING_FIELDS = {'request_id', 'profile_version_id', 'strategy_version_id', 'execution'}
_FAILURE_STATES = {'CANCELLED', 'TIMED_OUT', 'BLOCKED_INPUT', 'FAILED'}


def _failure(code: str, state: str = 'FAILED') -> dict:
    return {'schema_version': SCHEMA_VERSION, 'state': state, 'error_code': code}


def _unique_pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def _reject_constant(_):
    raise ValueError()


def _request(stdin) -> dict:
    frame = stdin.readline(MAX_REQUEST_BYTES + 1)
    if isinstance(frame, str):
        frame = frame.encode('utf-8')
    if len(frame) > MAX_REQUEST_BYTES or not frame.endswith(b'\n'):
        raise ValueError()
    payload = json.loads(frame.decode('utf-8'), object_pairs_hook=_unique_pairs,
                         parse_constant=_reject_constant)
    if (not isinstance(payload, dict) or not _FIELDS <= set(payload)
            or set(payload) - _FIELDS - {'expected_account_public_id', 'native_link', 'native_progress'}):
        raise ValueError()
    if payload['schema_version'] != SCHEMA_VERSION:
        raise ValueError()
    if payload['platform'] not in ('DOUYIN', 'BILIBILI', 'XIAOHONGSHU', 'ZHIHU'):
        raise ValueError()
    if payload['platform'] == 'ZHIHU' and 'expected_account_public_id' not in payload:
        raise ValueError()
    if 'expected_account_public_id' in payload:
        expected = payload['expected_account_public_id']
        if not valid_account(payload['platform'], expected):
            raise ValueError()
    if (type(payload['max_records']) is not int or not 1 <= payload['max_records'] <= 100
            or type(payload['timeout_seconds']) is not int or not 1 <= payload['timeout_seconds'] <= 900):
        raise ValueError()
    query = payload['query']
    if 'native_link' in payload:
        validate_bili_collection_target(payload['native_link'])
        if payload['platform'] != 'BILIBILI' or query is not None or 'expected_account_public_id' not in payload:
            raise ValueError()
    else:
        if not isinstance(query, str) or not 1 <= len(query) <= 80 or canonical_single_keyword(query) != query:
            raise ValueError()
        query.encode('utf-8')
    if 'native_progress' in payload:
        if payload['platform'] != 'BILIBILI' or 'native_link' in payload or 'expected_account_public_id' not in payload:
            raise ValueError()
        checked_input(payload['native_progress'],query)
    for key in ('runtime_path', 'profile_path', 'output_path'):
        value = payload[key]
        if not isinstance(value, str) or not value or not value.isprintable():
            raise ValueError()
        value.encode('utf-8')
        path = Path(value)
        if not path.is_absolute() or path.drive.startswith('\\'):
            raise ValueError()
        payload[key] = path
    mapping = payload['mapping']
    if not isinstance(mapping, dict) or set(mapping) != _MAPPING_FIELDS:
        raise ValueError()
    # Use the real formal validator even for the empty preflight. No source
    # process is started on invalid mapping/execution claims.
    build_comment_batch(raw_records=[], platform=payload['platform'],
        collector_version='windows-source-host-preflight-v1', query=query,
        now=datetime.now(timezone.utc), **mapping)
    return payload


def _watch_input(stdin, cancelled: threading.Event) -> None:
    try:
        # Any subsequent byte, including whitespace, or EOF is a stop request.
        stdin.read(1)
    except Exception:
        pass
    finally:
        cancelled.set()


def _collect(payload: dict, cancelled: threading.Event) -> dict:
    binding = {'expected_account_public_id': payload['expected_account_public_id']} if 'expected_account_public_id' in payload else {}
    if 'native_link' in payload:
        binding['native_link'] = payload['native_link']
    if 'native_progress' in payload:
        binding['native_progress'] = payload['native_progress']
    result = collect_windows_source(**{key: payload[key] for key in (
        'runtime_path', 'profile_path', 'output_path', 'platform', 'query',
        'max_records', 'timeout_seconds')}, cancel_requested=cancelled.is_set, **binding)
    # The driver only returns after physical cleanup of its complete owned tree.
    if cancelled.is_set():
        return _failure('COLLECTION_CANCELLED', 'CANCELLED')
    state = result.get('state')
    if state == 'COLLECTED':
        delta = {}
        if 'native_progress' in payload:
            if result.get('query') != payload['query']: raise ValueError()
            delta = {'native_progress':checked_delta(result.get('native_progress'),payload['native_progress'],min(5,payload['max_records']))}
        elif 'native_progress' in result:
            raise ValueError()
        if 'native_link' in payload and result.get('query') is not None:
            raise ValueError()
        if not isinstance(result['records'], list) or len(result['records']) > payload['max_records']:
            raise ValueError()
        batch = build_comment_batch(raw_records=result['records'], platform=payload['platform'],
            collector_version=result['collector_version'], query=result['query'],
            now=datetime.now(timezone.utc), **payload['mapping'])
        return {'schema_version': SCHEMA_VERSION, 'state': 'COLLECTED',
                'records': [record.model_dump(mode='json') for record in batch.records], **delta}
    if state not in _FAILURE_STATES:
        return _failure('SOURCE_HOST_FAILED')
    # Never interpolate an exception or arbitrary driver field into the wire.
    code = result.get('error_code')
    if (state, code) in _EXIT_RESULTS.values():
        return _failure(code, state)
    return {'schema_version': SCHEMA_VERSION, 'state': state}


def main(stdin=None, stdout=None) -> int:
    """Emit exactly one bounded envelope. Business failure still exits zero."""
    # A daemon blocking on BufferedReader can abort Python shutdown while
    # holding its buffered-I/O lock. Use raw FileIO for the actual pipe instead.
    if stdin is None:
        stdin = sys.stdin.buffer.raw
    if stdout is None:
        stdout = sys.stdout.buffer
    cancelled = threading.Event()
    with open(os.devnull, 'w', encoding='utf-8') as quiet, redirect_stdout(quiet), redirect_stderr(quiet):
        try:
            payload = _request(stdin)
        except Exception:
            envelope = _failure('SOURCE_HOST_INPUT_INVALID')
        except KeyboardInterrupt:
            cancelled.set()
            envelope = _failure('COLLECTION_CANCELLED', 'CANCELLED')
        else:
            threading.Thread(target=_watch_input, args=(stdin, cancelled), daemon=True).start()
            try:
                envelope = _collect(payload, cancelled)
            except KeyboardInterrupt:
                # run_supervised_process cleans its Job/tree before re-raising.
                cancelled.set()
                envelope = _failure('COLLECTION_CANCELLED', 'CANCELLED')
            except Exception:
                envelope = _failure('SOURCE_HOST_FAILED')
        try:
            wire = (json.dumps(envelope, ensure_ascii=False, allow_nan=False,
                               separators=(',', ':')) + '\n').encode('utf-8')
            if len(wire) > MAX_RESPONSE_BYTES:
                raise ValueError()
        except Exception:
            wire = (json.dumps(_failure('SOURCE_HOST_RESPONSE_INVALID'), separators=(',', ':')) + '\n').encode('utf-8')
    try:
        stdout.write(wire)
        stdout.flush()
    except (OSError, ValueError):
        # The parent may already have gone away; there is no second frame.
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
