"""Main-owned, two-frame XHS comment bridge.  It installs no public sender."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import json, os, re, socket, sys, threading, time
from pathlib import Path

from app.collector import _minimal_child_environment, run_supervised_process
from app.windows_private_directory import create_private_directory, verify_private_tree
from app.windows_source_driver import _exclusive_paths, verify_installed_runtime

SCHEMA = 'windows-platform-outreach-v1'
_FIRST = {'schema_version','action','runtime_path','profile_path','output_path','context','timeout_seconds'}
_SECOND = {'schema_version','action','operation'}

def _fail(): return {'schema_version': SCHEMA, 'state': 'FAILED', 'error_code': 'OUTREACH_HOST_FAILED'}
def _pairs(items):
    out = {}
    for key, value in items:
        if key in out: raise ValueError()
        out[key] = value
    return out
def _decode(raw): return json.loads(raw.decode('utf-8'), object_pairs_hook=_pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
def _frame(stream):
    raw = stream.readline(131073)
    if isinstance(raw, str): raw = raw.encode()
    if not raw.endswith(b'\n') or len(raw) > 131072: raise ValueError()
    return _decode(raw)
def _paths(*values):
    paths=[]
    for value in values:
        if not isinstance(value, str) or not value.isprintable() or not re.match(r'^[A-Za-z]:[\\/]', value): raise ValueError()
        path=Path(value)
        if not path.is_absolute() or len(path.drive)!=2: raise ValueError()
        paths.append(path)
    resolved=[p.resolve() for p in paths]
    if any(a.is_relative_to(b) or b.is_relative_to(a) for i,a in enumerate(resolved) for b in resolved[i+1:]): raise ValueError()
    return paths
def _first(stream):
    value=_frame(stream)
    if not isinstance(value,dict) or set(value)!=_FIRST or value['schema_version']!=SCHEMA or value['action']!='CHECK': raise ValueError()
    if type(value['timeout_seconds']) is not int or not 1<=value['timeout_seconds']<=90 or not isinstance(value['context'],dict): raise ValueError()
    value['runtime_path'],value['profile_path'],value['output_path']=_paths(value['runtime_path'],value['profile_path'],value['output_path'])
    return value
def _second(stream):
    value=_frame(stream)
    if not isinstance(value,dict) or set(value)!=_SECOND or value['schema_version']!=SCHEMA or value['action']!='EXECUTE' or not isinstance(value['operation'],dict) or set(value['operation'])!={'requestId','claimId','dispatchBefore'}: raise ValueError()
    if not all(isinstance(value['operation'][k],str) and value['operation'][k].isprintable() for k in value['operation']): raise ValueError()
    return value['operation']
def _wire(value): return (json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode()

def run_outreach(**request):
    """Windows-only runtime owner; context/token travel only over its loopback socket."""
    if sys.platform != 'win32': raise ValueError()
    started=time.monotonic(); cancelled=request.get('cancel_requested',lambda:False)
    runtime,profile,output=request['runtime_path'],request['profile_path'],request['output_path']
    with _exclusive_paths([runtime,profile]):
        python=verify_installed_runtime(runtime); verify_private_tree(profile)
        if os.path.lexists(output): raise ValueError()
        output=create_private_directory(output); temporary=output/'.temporary'; temporary.mkdir(); (temporary/'matplotlib').mkdir()
        server=socket.socket(socket.AF_INET,socket.SOCK_STREAM); server.bind(('127.0.0.1',0)); server.listen(1); server.settimeout(.1)
        token=os.urandom(32).hex(); state={'conn':None,'ready':None,'result':None,'buffer':b''}
        env=_minimal_child_environment(YIKE_PROFILE_PATH=str(profile),YIKE_OUTREACH_PORT=str(server.getsockname()[1]),YIKE_OUTREACH_TOKEN=token,PYTHONDONTWRITEBYTECODE='1',PLAYWRIGHT_BROWSERS_PATH=str(runtime/'.venv/playwright-browsers'),TEMP=str(temporary),TMP=str(temporary),MPLCONFIGDIR=str(temporary/'matplotlib'))
        env['PATH']=str(runtime/'.venv/Lib/site-packages/playwright/driver')+os.pathsep+env.get('PATH','')
        def poll():
            if state['conn'] is None:
                try: state['conn'],_=server.accept(); state['conn'].setblocking(False)
                except TimeoutError: return
            conn=state['conn']
            if b'\n' not in state['buffer']:
                try: data=conn.recv(131073)
                except BlockingIOError: return
                if not data: return
                state['buffer']+=data
            if b'\n' not in state['buffer']: return
            raw,state['buffer']=state['buffer'].split(b'\n',1)
            message=_decode(raw)
            if state.get('auth') is None:
                if set(message)!={'token'} or message['token']!=token: raise ValueError()
                state['auth']=True; conn.sendall(_wire({'context':request['context']})); return
            if message.get('state')=='READY' and set(message)=={'state','observation'}:
                state['ready']=message['observation']
                operation=request.get('on_ready', lambda _:{ })(message['observation'])
                if not isinstance(operation, dict): raise ValueError()
                conn.sendall(_wire({'operation':operation})); return
            if message.get('state')=='RESULT' and set(message)=={'state','outcome'}: state['result']=message['outcome']; return
            raise ValueError()
        command=[str(python),'-B','-X','utf8',str(Path(__file__).with_name('platform_outreach_worker.py').resolve())]
        cleanup_confirmed=True
        try:
            result=run_supervised_process(command,cwd=runtime,env=env,timeout_seconds=max(0.01,request['timeout_seconds']-(time.monotonic()-started)),cancel_requested=cancelled,poll_callback=poll)
        except Exception:
            # A receipt observed before Job cleanup remains fact, never a retry permit.
            cleanup_confirmed=False
            # Consume an already-buffered terminal frame before deciding whether
            # cleanup erased our ability to report an externally observed fact.
            try: poll(); poll()
            except Exception: pass
            if state['result'] is None: raise
        finally: server.close()
        verify_private_tree(profile); verify_private_tree(output)
        if state['result'] is None: raise ValueError()
        return {'observation':state['ready'], 'outcome':state['result'], 'cleanupConfirmed':cleanup_confirmed}

def main(stdin=None,stdout=None):
    stdin=stdin or sys.stdin.buffer; stdout=stdout or sys.stdout.buffer; written=0
    def emit(value):
        nonlocal written
        data=_wire(value)
        if written+len(data)>32768: raise ValueError()
        stdout.write(data); stdout.flush(); written+=len(data)
    with open(os.devnull,'w',encoding='utf-8') as quiet,redirect_stdout(quiet),redirect_stderr(quiet):
        try:
            first=_first(stdin)
            def ready(observation):
                emit({'schema_version':SCHEMA,'state':'READY','observation':observation})
                return _second(stdin)
            # The worker function is deliberately injectable for fixed host tests.
            response=run_outreach(**(first | {'on_ready': ready}))
            if response.get('observation') is None: raise ValueError()
            # A synthetic test driver can return its receipt after receiving the callback.
            if response.get('operation_required'): raise ValueError()
            outcome=response['outcome']; cleanup=bool(response['cleanupConfirmed'])
            emit({'schema_version':SCHEMA,'state':'RESULT','outcome':outcome,'cleanupConfirmed':cleanup})
        except Exception:
            try: emit(_fail())
            except Exception: pass
    return 0

if __name__=='__main__': raise SystemExit(main())
