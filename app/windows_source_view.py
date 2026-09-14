"""Private supervised Windows viewer. SOURCE_OPENED is a nonterminal event."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sys
import threading
import time

from app.collector import _minimal_child_environment, run_supervised_process
from app.windows_private_directory import create_private_directory, verify_private_tree, verify_browser_profile_tree
from app.windows_source_driver import _exclusive_paths, verify_installed_runtime, WindowsSourceError
from app.windows_platform_login import _paths, _decode, _marker, _watch
from app.source_view_worker import SCHEMA, CODES, failure, valid_target

_OPENED = dict(schema_version=SCHEMA,state='SOURCE_OPENED')
_TARGET = {'note_id','expected_account','author_id','original_query','timeout_seconds'}
_FIELDS = _TARGET | {'schema_version','runtime_path','profile_path','output_path'}


def _request(stdin):
    raw = stdin.readline(65537)
    if isinstance(raw,str): raw = raw.encode('utf-8')
    if len(raw)>65536 or not raw.endswith(b'\n'): raise ValueError()
    value = _decode(raw)
    if not isinstance(value,dict) or set(value)!=_FIELDS or value['schema_version']!=SCHEMA: raise ValueError()
    if not valid_target(**{key:value[key] for key in _TARGET}): raise ValueError()
    if any(not isinstance(value[key],str) for key in ('runtime_path','profile_path','output_path')): raise ValueError()
    paths = _paths(*(value[key] for key in ('runtime_path','profile_path','output_path')))
    for key,path in zip(('runtime_path','profile_path','output_path'), paths): value[key]=path
    value.pop('schema_version')
    return value


def _terminal(value):
    if not isinstance(value,dict) or value.get('schema_version')!=SCHEMA: raise ValueError()
    if value.get('state')=='CLOSED':
        if set(value)!={'schema_version','state'}: raise ValueError()
    else:
        if set(value)!={'schema_version','state','error_code'} or value['error_code'] not in CODES: raise ValueError()
        state, code = value['state'], value['error_code']
        if state not in ('FAILED','CANCELLED','TIMED_OUT'): raise ValueError()
        if state=='CANCELLED' and code!='XHS_SOURCE_CANCELLED': raise ValueError()
        if state=='TIMED_OUT' and code!='XHS_SOURCE_TIMED_OUT': raise ValueError()
        if state=='FAILED' and code in ('XHS_SOURCE_CANCELLED','XHS_SOURCE_TIMED_OUT'): raise ValueError()
    return value


def view_windows_source(*,runtime_path,profile_path,output_path,note_id,expected_account,
                        author_id,original_query,timeout_seconds,on_opened,cancel_requested=None):
    started = time.monotonic()
    lock_acquired = False
    def interrupted():
        if cancel_requested and cancel_requested(): return failure('XHS_SOURCE_CANCELLED','CANCELLED')
        if time.monotonic()-started>=timeout_seconds: return failure('XHS_SOURCE_TIMED_OUT','TIMED_OUT')
        return None
    try:
        target = dict(note_id=note_id,expected_account=expected_account,author_id=author_id,
            original_query=original_query,timeout_seconds=timeout_seconds)
        if not valid_target(**target): return failure('XHS_SOURCE_INVALID_INPUT')
        if sys.platform!='win32' or not callable(on_opened): raise ValueError()
        runtime_path,profile_path,output_path=_paths(runtime_path,profile_path,output_path)
        if os.path.lexists(output_path): raise ValueError()
        with _exclusive_paths([runtime_path,profile_path]):
            lock_acquired = True
            if stopped:=interrupted(): return stopped
            python = verify_installed_runtime(runtime_path)
            # Unlike login, viewing must never create a new account profile.
            verify_browser_profile_tree(profile_path)
            if stopped:=interrupted(): return stopped
            output_path=create_private_directory(output_path)
            temporary=output_path/'.temporary'; temporary.mkdir()
            (temporary/'matplotlib').mkdir()
            env=_minimal_child_environment(YIKE_PROFILE_PATH=str(profile_path),
                YIKE_SOURCE_OUTPUT_PATH=str(output_path),YIKE_SOURCE_TARGET=json.dumps(target,ensure_ascii=False),
                PYTHONDONTWRITEBYTECODE='1',PLAYWRIGHT_BROWSERS_PATH=str(runtime_path/'.venv/playwright-browsers'),
                TEMP=str(temporary),TMP=str(temporary),MPLCONFIGDIR=str(temporary/'matplotlib'))
            env['PATH']=str(runtime_path/'.venv/Lib/site-packages/playwright/driver')+os.pathsep+env.get('PATH','')
            opened=False
            def poll():
                nonlocal opened
                if opened or not os.path.lexists(output_path/'.yike-source-opened.json'): return
                if _marker(output_path/'.yike-source-opened.json')!=_OPENED: raise ValueError()
                on_opened(); opened=True
            command=[str(python),'-B','-X','utf8',str(Path(__file__).with_name('source_view_worker.py').resolve())]
            if stopped:=interrupted(): return stopped
            result=run_supervised_process(command,cwd=runtime_path,env=env,
                timeout_seconds=timeout_seconds-(time.monotonic()-started),
                cancel_requested=cancel_requested,poll_callback=poll)
            # The supervisor has confirmed the whole Windows Job is gone before any terminal.
            verify_browser_profile_tree(profile_path)
            verify_private_tree(output_path)
            poll()
            if stopped:=interrupted(): return stopped
            if result.cancelled: return failure('XHS_SOURCE_CANCELLED','CANCELLED')
            if result.timed_out: return failure('XHS_SOURCE_TIMED_OUT','TIMED_OUT')
            if result.returncode!=0: return failure()
            terminal=_terminal(_marker(output_path/'.yike-source-terminal.json'))
            if terminal['state']=='CLOSED' and not opened: raise ValueError()
            return terminal
    except WindowsSourceError as error:
        if not lock_acquired and str(error) == 'source_busy':
            return failure('XHS_SOURCE_BUSY')
        return failure()
    except KeyboardInterrupt:
        # An arbitrary interrupt can occur during post-Job verification or lock
        # release. Only explicit supervised cancellation proves clean release.
        return failure()
    except Exception:
        return failure()


def main(stdin=None,stdout=None):
    if stdin is None: stdin=sys.stdin.buffer.raw
    if stdout is None: stdout=sys.stdout.buffer
    cancelled=threading.Event()
    opened=False
    def emit(payload):
        stdout.write((json.dumps(payload,separators=(',',':'))+'\n').encode('utf-8')); stdout.flush()
    def on_opened():
        nonlocal opened
        if not opened: emit(_OPENED); opened=True
    with open(os.devnull,'w',encoding='utf-8') as quiet,redirect_stdout(quiet),redirect_stderr(quiet):
        try:
            payload=_request(stdin)
        except Exception:
            terminal=failure('XHS_SOURCE_INVALID_INPUT')
        except KeyboardInterrupt:
            terminal=failure('XHS_SOURCE_CANCELLED','CANCELLED')
        else:
            threading.Thread(target=_watch,args=(stdin,cancelled),daemon=True).start()
            try:
                terminal=_terminal(view_windows_source(**payload,on_opened=on_opened,cancel_requested=cancelled.is_set))
            except (Exception,KeyboardInterrupt): terminal=failure()
        try: emit(terminal)
        except (OSError,ValueError): pass
    return 0


if __name__=='__main__':
    raise SystemExit(main())
