"""Single broker supervision and bounded attach streaming; no provider credentials."""

import fcntl
import json
import os
import queue
import subprocess
import threading
from contextlib import nullcontext
from time import monotonic, time

from pilot.codex_research_worker import _kill_group
from pilot.research_container_entry import validate_manifest


class _BrokerStopping(Exception):
    pass


class ContainerLifecycle:
    def _mark(self, key, suffix):
        try:
            fd = os.open(self.ledger_root/(key+'.'+suffix), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return False
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        fd = os.open(self.ledger_root, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return True

    def __enter__(self):
        if getattr(self, '_supervisor_thread', None) is not None:
            raise ValueError('supervisor_already_started')
        self._supervisor_lock = open(self.ledger_root/'supervisor.lock', 'a')
        try:
            fcntl.flock(self._supervisor_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._active = set()
            self._active_guard = threading.Lock()
            self._recovery_keys = {p.stem for p in self.ledger_root.glob('*.started')}
            self.reconcile(recover=True)
            self._halt = threading.Event()
            self._slots = threading.BoundedSemaphore(2)
            self._supervisor_thread = threading.Thread(target=self._watch, daemon=True)
            self._supervisor_thread.start()
        except BaseException:
            self._supervisor_lock.close()
            raise
        return self

    def _watch(self):
        try:
            while not self._halt.wait(.5):
                self.reconcile()
        finally:
            with self._active_guard:
                self._halt.set()

    def __exit__(self, *_):
        with self._active_guard:
            self._halt.set()
        try:
            self._supervisor_thread.join(timeout=25)
            self.reconcile(recover=True)
        finally:
            # Do not allow another supervisor while a previous scan is still active.
            if not self._supervisor_thread.is_alive():
                self._supervisor_lock.close()

    def reconcile(self, *, recover=False):
        results = []
        pending = []
        for path in self.ledger_root.glob('*.json'):
            key = path.stem
            if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
                continue
            if (self.ledger_root/(key+'.terminal')).exists():
                continue
            claim = self._claim(key)
            if claim is None:
                continue
            if recover and (self.ledger_root/(key+'.started')).exists():
                self._mark(key, 'cancelled')
            if (claim['expires_at'] <= time()
                    or (self.ledger_root/(key+'.cancelled')).exists()
                    or recover and (self.ledger_root/(key+'.started')).exists()):
                pending.append(key)
        with getattr(self, '_active_guard', nullcontext()):
            active = set(getattr(self, '_active', ()))
        current = sorted(key for key in pending if key in active)
        history = sorted(key for key in pending if key not in active)
        if history:
            cursor = getattr(self, '_history_cursor', 0) % len(history)
            current.append(history[cursor])
            self._history_cursor = cursor + 1
        for key in current:
            results.append(self._stop_key(key))
        return results

    def _attach(self, key):
        with self._active_guard:
            if self._halt.is_set() or (self.ledger_root/(key+'.cancelled')).exists():
                raise _BrokerStopping()
            return subprocess.Popen(['docker','start','--attach','--interactive','yike-r-'+key],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                start_new_session=True, env={'PATH':'/usr/local/bin:/usr/bin:/bin'})

    def execute(self, identity, manifest, *, emit, cancelled=lambda: False):
        # Import only at invocation to keep the broker core/lifecycle dependency acyclic.
        from pilot.research_container_broker import task_key
        thread = getattr(self, '_supervisor_thread', None)
        if thread is None or not thread.is_alive() or self._halt.is_set():
            raise ValueError('supervisor_required')
        with self._active_guard:
            recovery_keys = tuple(self._recovery_keys)
        if any(not (self.ledger_root/(key+'.terminal')).exists() for key in recovery_keys):
            raise ValueError('broker_recovery_pending')
        key = task_key(identity)
        manifest = dict(validate_manifest(manifest))
        claim = self._claim(key)
        if (claim is None or claim['expires_at'] <= time()
                or (self.ledger_root/(key+'.cancelled')).exists()
                or self.status(identity)['status'] != 'CREATED'):
            raise ValueError('task_not_startable')
        process = None
        workers = []
        stop = threading.Event()
        code = 'runtime_unavailable'
        owns_start = False
        owns_slot = False
        physical = None
        try:
            with self._active_guard:
                if self._halt.is_set() or not thread.is_alive():
                    raise ValueError('supervisor_required')
                if any(not (self.ledger_root/(k+'.terminal')).exists() for k in self._recovery_keys):
                    raise ValueError('broker_recovery_pending')
                if not self._slots.acquire(blocking=False):
                    raise ValueError('broker_busy')
                owns_slot = True
                if not self._mark(key, 'started'):
                    raise ValueError('task_not_startable')
                owns_start = True
                self._active.add(key)
            manifest['expires_at'] = min(manifest['expires_at'], claim['expires_at'])
            payload = json.dumps(manifest, separators=(',', ':'), ensure_ascii=False).encode()
            if len(payload) > 1024*1024:
                raise ValueError('invalid_task_manifest')
            if self._halt.is_set() or (self.ledger_root/(key+'.cancelled')).exists() or cancelled():
                code = 'cancelled'
            else:
                process = self._attach(key)
                chunks = queue.Queue(maxsize=16)
                def feed():
                    try:
                        process.stdin.write(payload)
                        process.stdin.close()
                    except (OSError, ValueError):
                        pass
                def drain():
                    try:
                        while not stop.is_set():
                            chunk = process.stdout.read1(65536)
                            while not stop.is_set():
                                try:
                                    chunks.put(chunk, timeout=.05)
                                    break
                                except queue.Full:
                                    pass
                            if not chunk:
                                return
                    except (OSError, ValueError):
                        stop.set()
                for target in (feed, drain):
                    worker = threading.Thread(target=target, daemon=True)
                    worker.start()
                    workers.append(worker)
                size, eof, last_heartbeat = 0, False, monotonic()
                while True:
                    if cancelled() or self._halt.is_set() or (self.ledger_root/(key+'.cancelled')).exists():
                        code = 'cancelled'
                        break
                    if time() >= manifest['expires_at']:
                        code = 'timeout'
                        break
                    if stop.is_set():
                        break
                    if eof and process.poll() is not None:
                        code = None if process.returncode == 0 else 'runtime_failed'
                        break
                    try:
                        chunk = chunks.get(timeout=.05)
                    except queue.Empty:
                        if monotonic()-last_heartbeat >= 1:
                            emit(b'')
                            last_heartbeat = monotonic()
                        continue
                    if not chunk:
                        eof = True
                        continue
                    size += len(chunk)
                    if size > 2*1024*1024:
                        code = 'output_limit'
                        break
                    emit(chunk)
        except _BrokerStopping:
            code = 'cancelled'
        finally:
            stop.set()
            try:
                if process is not None:
                    _kill_group(process)
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        code = 'runtime_unavailable'
                if owns_start:
                    physical = self._stop_key(key)
            finally:
                try:
                    for worker in workers:
                        worker.join(timeout=.3)
                    if process is not None and all(not worker.is_alive() for worker in workers):
                        process.stdin.close()
                        process.stdout.close()
                finally:
                    if owns_start:
                        with self._active_guard:
                            if physical is not None and physical['status'] == 'STOPPED':
                                self._active.discard(key)
                            else:
                                self._active.add(key)
                                self._recovery_keys.add(key)
                    if owns_slot:
                        self._slots.release()
        return dict(physical, code=code)
