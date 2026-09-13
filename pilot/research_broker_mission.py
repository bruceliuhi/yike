"""Host-side isolated mission adapter; permissions and evidence parsing stay here."""
import json
import os
from pathlib import Path
import queue
import stat
import threading
from time import monotonic

from pilot.research_broker_contract import STREAM_JOIN_TIMEOUT, task_key


class BrokerMissionExecution:
    def __init__(self, identity, client, tasks_root):
        self.identity = dict(identity)
        self.key = task_key(identity)
        self.client = client
        self.root = Path(tasks_root)

    def prepare_socket(self):
        info = self.root.lstat()
        if (not self.root.is_absolute() or self.root.resolve()!=self.root
                or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o077):
            raise ValueError('invalid_task_directory')
        directory = self.root/self.key
        directory.mkdir(mode=0o700)  # Never reuse another execution's directory.
        return str(directory/'bridge.sock')

    def execute(self, manifest, *, deadline, cancelled, events, revoke):
        from pilot.codex_research_worker import _InvalidOutput
        finished = threading.Event()
        messages = queue.Queue(maxsize=16)
        reader = None
        terminal = None
        complete_stream = False
        status, code = 'FAILED', 'broker_unavailable'
        def put(value):
            while not finished.is_set():
                try:
                    messages.put(value,timeout=.05)
                    return
                except queue.Full:
                    pass
        def receive():
            try:
                for frame in self.client.events(self.identity,manifest):
                    if finished.is_set():
                        break
                    put(frame)
                put({'type':'end'})
            except Exception:
                put({'type':'error'})
        try:
            created = self.client.create(self.identity,expires_at=manifest['expires_at'])
            if created['status'] != 'CREATED':
                raise ValueError('broker_unavailable')
            reader = threading.Thread(target=receive,daemon=True)
            reader.start()
            pending, total = b'', 0
            while True:
                if cancelled():
                    status, code = 'CANCELLED', 'cancelled'
                    break
                if monotonic() >= deadline:
                    code = 'timeout'
                    break
                try:
                    frame = messages.get(timeout=.05)
                except queue.Empty:
                    continue
                kind = frame['type']
                if kind == 'heartbeat':
                    continue
                if kind == 'error':
                    break
                if kind == 'result':
                    terminal = frame['value']
                    continue
                if kind == 'end':
                    complete_stream = True
                    if pending:
                        events.accept(json.loads(pending.decode()))
                    if terminal is None or terminal['status']!='STOPPED':
                        break
                    if terminal['code'] is not None:
                        code = terminal['code']
                    elif events.failed or not events.done:
                        code = 'runtime_failed'
                    elif events.search_enabled and not events.searches and not events.entry_urls:
                        code = 'no_verified_searches'
                    elif not events.reads:
                        code = 'no_verified_reads'
                    else:
                        status, code = 'COMPLETED', None
                    break
                if kind != 'chunk':
                    raise ValueError('invalid_runtime_output')
                total += len(frame['data'])
                if total > 2*1024*1024:
                    code = 'output_limit'
                    break
                pending += frame['data']
                while b'\n' in pending:
                    line,pending = pending.split(b'\n',1)
                    if line.strip():
                        events.accept(json.loads(line.decode()))
        except (ValueError, TypeError, RecursionError, _InvalidOutput):
            code = 'invalid_runtime_output'
        except Exception:
            code = 'broker_unavailable'
        finally:
            revoke()  # Fence future host effects before asking the privileged side to stop.
            finished.set()
            if not (complete_stream and terminal is not None and terminal['status']=='STOPPED'):
                try:
                    if self.client.stop(self.identity)['status']!='STOPPED':
                        status,code = 'FAILED','broker_stop_unknown'
                except Exception:
                    status,code = 'FAILED','broker_stop_unknown'
            if reader is not None and reader.ident is not None:
                reader.join(timeout=STREAM_JOIN_TIMEOUT)
                if reader.is_alive():
                    status,code = 'FAILED','broker_stream_unknown'
        return status,code
