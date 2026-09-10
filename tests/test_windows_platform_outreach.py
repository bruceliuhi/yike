"""Fixed, synthetic loopback protocol tests; never touch a platform."""
import importlib
import io
import json
import threading
import asyncio
import socket
import time
from contextlib import asynccontextmanager, nullcontext
from types import SimpleNamespace

import pytest


SCHEMA = "windows-platform-outreach-v1"


def api():
    return importlib.import_module("app.windows_platform_outreach")


def request(tmp_path):
    return {"schema_version": SCHEMA, "action": "CHECK", "runtime_path": str(tmp_path / "runtime"),
            "profile_path": str(tmp_path / "profile"), "output_path": str(tmp_path / "output"),
            "context": {"opaque": "body stays off argv"}, "timeout_seconds": 60}


@pytest.mark.parametrize("wire", [b"{}\n", b'{"x":NaN}\n', b'{"x":1,"x":2}\n', b"x" * 131072 + b"\n"])
def test_strict_first_frame_rejects_before_launch(tmp_path, monkeypatch, wire):
    host = api(); calls = []
    monkeypatch.setattr(host, "run_outreach", lambda **kw: calls.append(kw))
    output = io.BytesIO()
    assert host.main(io.BytesIO(wire), output) == 0
    assert json.loads(output.getvalue())["error_code"] == "OUTREACH_HOST_FAILED" and not calls


def test_operation_is_one_strict_frame_after_ready(tmp_path, monkeypatch):
    host = api(); calls = []
    monkeypatch.setattr(host, "_paths", lambda *values: tuple(tmp_path / str(i) for i, _ in enumerate(values)))
    def run(**kw):
        calls.append(kw); kw['on_ready']({'status':'AVAILABLE'})
        peer.sendall(host._wire({'schema_version':SCHEMA,'action':'EXECUTE','operation':OP}))
        end=time.monotonic()+1
        while time.monotonic()<end:
            if kw['take_operation']() == OP: break
            time.sleep(.001)
        else: pytest.fail('operation not delivered')
        peer.shutdown(socket.SHUT_WR)
        return {'observation':{},'outcome':{'status':'UNKNOWN'},'cleanupConfirmed':True}
    monkeypatch.setattr(host, 'run_outreach', run)
    local,peer=socket.socketpair(); peer.sendall(host._wire(request(tmp_path)))
    output = io.BytesIO()
    with local,peer,local.makefile('rb') as stream: assert host.main(stream, output) == 0
    assert [json.loads(x)["state"] for x in output.getvalue().splitlines()] == ["READY", "RESULT"]
    assert len(calls) == 1


def test_duplicate_or_early_execute_is_not_run(tmp_path, monkeypatch):
    host = api(); calls = []
    monkeypatch.setattr(host, "run_outreach", lambda **kw: calls.append(kw) or {"observation":{}, "outcome": {}, "cleanupConfirmed": True})
    bad = {"schema_version": SCHEMA, "action": "EXECUTE", "operation": {}}
    output = io.BytesIO(); host.main(io.BytesIO((json.dumps(bad) + "\n").encode()), output)
    assert not calls and json.loads(output.getvalue())["state"] == "FAILED"


OP={'requestId':'r','claimId':'c','dispatchBefore':'z'}
OBS={'status':'AVAILABLE','identity':{'account':'synthetic'},'target':{'postId':'synthetic'}}


@pytest.mark.parametrize('cleanup_failure', [False,'worker','supervisor','private'])
def test_real_loopback_worker_ready_execute_and_terminal_tail(tmp_path,monkeypatch,cleanup_failure):
    host=api(); worker=importlib.import_module('app.platform_outreach_worker')
    runtime=importlib.import_module('app.platform_outreach_runtime'); calls=[]; errors=[]
    class Channel:
        async def check(self,context): calls.append(('check',id(self))); return OBS
        async def execute(self,context,operation):
            calls.append(('execute',id(self))); assert operation==OP
            return {'status':'UNKNOWN'}
    @asynccontextmanager
    async def opened(context,**kwargs):
        yield Channel()
        if cleanup_failure=='worker': raise RuntimeError('synthetic cleanup')
    monkeypatch.setattr(runtime,'open_xhs_comment_channel',opened)
    monkeypatch.setattr(host.sys,'platform','win32')
    monkeypatch.setattr(host,'_exclusive_paths',lambda _:nullcontext())
    monkeypatch.setattr(host,'verify_installed_runtime',lambda _:tmp_path/'python')
    checks=[]
    def private(path):
        checks.append(path)
        if cleanup_failure=='private' and len(checks)>1: raise ValueError('synthetic ACL failure')
    monkeypatch.setattr(host,'verify_private_tree',private)
    monkeypatch.setattr(host,'create_private_directory',lambda p:(p.mkdir() or p))
    def supervise(command,**kw):
        def child():
            try:
                with socket.create_connection(('127.0.0.1',int(kw['env']['YIKE_OUTREACH_PORT']))) as conn:
                    conn.sendall(worker._wire({'token':kw['env']['YIKE_OUTREACH_TOKEN']}))
                    asyncio.run(worker._run(conn))
            except BaseException as exc: errors.append(exc)
        thread=threading.Thread(target=child,daemon=True); thread.start()
        end=time.monotonic()+2
        # Deliberately stop polling after READY, then return with RESULT unread.
        while len(calls)<1 and time.monotonic()<end: kw['poll_callback'](); time.sleep(.001)
        while thread.is_alive() and time.monotonic()<end:
            kw['poll_callback']()
            if any(c[0]=='execute' for c in calls): break
            time.sleep(.001)
        thread.join(1); assert not thread.is_alive()
        if cleanup_failure=='supervisor': raise OSError('synthetic Job cleanup failure')
        return SimpleNamespace(returncode=1 if errors else 0)
    monkeypatch.setattr(host,'run_supervised_process',supervise)
    ready=[]
    result=host.run_outreach(runtime_path=tmp_path/'runtime',profile_path=tmp_path/'profile',output_path=tmp_path/'output',context={},timeout_seconds=2,on_ready=lambda value:ready.append(value),take_operation=lambda:OP)
    assert ready==[OBS]
    assert calls[0][0]=='check' and calls[1]==('execute',calls[0][1])
    assert result['outcome']=={'status':'UNKNOWN'}
    assert result['cleanupConfirmed'] is (not cleanup_failure)


@pytest.mark.parametrize('stage',['setup','operation','execute'])
@pytest.mark.parametrize('extra',[False,True])
def test_worker_disconnect_or_extra_cancels_pending_await(monkeypatch,stage,extra):
    worker=importlib.import_module('app.platform_outreach_worker')
    runtime=importlib.import_module('app.platform_outreach_runtime'); entered=threading.Event(); stopped=threading.Event()
    class Channel:
        async def check(self,context): return OBS
        async def execute(self,*args): entered.set(); await asyncio.Event().wait()
    @asynccontextmanager
    async def opened(context,**kw):
        try:
            if stage=='setup': entered.set(); await asyncio.Event().wait()
            yield Channel()
        finally: stopped.set()
    monkeypatch.setattr(runtime,'open_xhs_comment_channel',opened)
    local,peer=socket.socketpair()
    def child():
        try: asyncio.run(worker._run(local))
        except BaseException: pass
        finally: local.close()
    thread=threading.Thread(target=child,daemon=True); thread.start()
    peer.sendall(worker._wire({'context':{}}))
    if stage in ('operation','execute'):
        peer.settimeout(1); assert b'READY' in peer.recv(8192)
        if stage=='execute': peer.sendall(worker._wire({'operation':OP}))
        else: entered.set()
    assert entered.wait(1)
    if extra: peer.sendall(b'{}\n')
    else: peer.shutdown(socket.SHUT_WR)
    assert stopped.wait(.4), 'worker await was not cancelled'
    peer.close(); thread.join(.5)


@pytest.mark.parametrize('mode',['early','duplicate','eof','invalid'])
def test_stdin_reader_cancels_without_blocking_ready(mode):
    host=api(); local,peer=socket.socketpair(); stream=local.makefile('rb')
    state=host._Input(stream)
    frame={'schema_version':SCHEMA,'action':'EXECUTE','operation':OP}
    try:
        if mode!='early':
            started=time.monotonic(); state.announce(lambda _:None,OBS)
            assert time.monotonic()-started<.1 and state.take() is None
        if mode=='invalid': peer.sendall(b'{"schema_version":NaN}\n')
        elif mode=='eof': peer.shutdown(socket.SHUT_WR)
        else:
            peer.sendall(host._wire(frame))
            if mode=='duplicate': peer.sendall(host._wire(frame))
        assert state.cancelled.wait(.5)
        assert state.take() is None
    finally:
        peer.close(); stream.close(); local.close()


@pytest.mark.parametrize('payload',[b'x'*131073,b'{"token":NaN}\n',b'{"token":"x","token":"y"}\n'])
def test_host_rejects_malformed_loopback_before_ready(tmp_path,monkeypatch,payload):
    host=api(); monkeypatch.setattr(host.sys,'platform','win32')
    monkeypatch.setattr(host,'_exclusive_paths',lambda _:nullcontext())
    monkeypatch.setattr(host,'verify_installed_runtime',lambda _:tmp_path/'python')
    monkeypatch.setattr(host,'verify_private_tree',lambda _:None)
    monkeypatch.setattr(host,'create_private_directory',lambda p:(p.mkdir() or p))
    def supervise(command,**kw):
        with socket.create_connection(('127.0.0.1',int(kw['env']['YIKE_OUTREACH_PORT']))) as conn:
            conn.sendall(payload)
            for _ in range(10): kw['poll_callback']()
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(host,'run_supervised_process',supervise)
    with pytest.raises(ValueError):
        host.run_outreach(runtime_path=tmp_path/'runtime',profile_path=tmp_path/'profile',output_path=tmp_path/'output',context={},timeout_seconds=1,on_ready=lambda _:pytest.fail('invalid auth reached READY'))


def test_real_host_pending_operation_keeps_supervisor_responsive(tmp_path,monkeypatch):
    host=api(); worker=importlib.import_module('app.platform_outreach_worker')
    runtime=importlib.import_module('app.platform_outreach_runtime')
    local,peer=socket.socketpair(); stream=local.makefile('rb'); inputs=host._Input(stream)
    announced=threading.Event(); closed=threading.Event()
    class Channel:
        async def check(self,context): return OBS
        async def execute(self,*args): pytest.fail('no operation was authorized')
    @asynccontextmanager
    async def opened(context,**kw):
        try: yield Channel()
        finally: closed.set()
    monkeypatch.setattr(runtime,'open_xhs_comment_channel',opened)
    monkeypatch.setattr(host.sys,'platform','win32')
    monkeypatch.setattr(host,'_exclusive_paths',lambda _:nullcontext())
    monkeypatch.setattr(host,'verify_installed_runtime',lambda _:tmp_path/'python')
    monkeypatch.setattr(host,'verify_private_tree',lambda _:None)
    monkeypatch.setattr(host,'create_private_directory',lambda p:(p.mkdir() or p))
    def ready(observation): inputs.announce(lambda _:announced.set(),observation)
    def supervise(command,**kw):
        def child():
            try:
                with socket.create_connection(('127.0.0.1',int(kw['env']['YIKE_OUTREACH_PORT']))) as conn:
                    conn.sendall(worker._wire({'token':kw['env']['YIKE_OUTREACH_TOKEN']})); asyncio.run(worker._run(conn))
            except BaseException: pass
        thread=threading.Thread(target=child,daemon=True); thread.start()
        end=time.monotonic()+1
        while not announced.is_set() and time.monotonic()<end: kw['poll_callback'](); time.sleep(.001)
        assert announced.is_set()
        for _ in range(3):
            started=time.monotonic(); kw['poll_callback']()
            assert time.monotonic()-started<.05
        peer.shutdown(socket.SHUT_WR)
        assert inputs.cancelled.wait(.5) and kw['cancel_requested']()
        kw['poll_callback']() # EOF also reaches worker, before supervisor cleanup.
        assert closed.wait(.5)
        thread.join(.5)
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(host,'run_supervised_process',supervise)
    try:
        with pytest.raises(ValueError):
            host.run_outreach(runtime_path=tmp_path/'runtime',profile_path=tmp_path/'profile',output_path=tmp_path/'output',context={},timeout_seconds=1,on_ready=ready,take_operation=inputs.take,cancel_requested=inputs.cancelled.is_set)
    finally: peer.close(); stream.close(); local.close()
