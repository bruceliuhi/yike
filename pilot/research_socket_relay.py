"""Bounded loopback transport to one task-owned gateway socket."""

import math
import os
from pathlib import Path
import socket
import stat
import threading
from time import monotonic


_MAX_BYTES = 2 * 1024 * 1024 + 65536


class TaskSocketRelay:
    def __init__(self, socket_path: str, *, deadline: float):
        try:
            path = Path(socket_path)
            valid = (
                os.name == 'posix' and path.is_absolute()
                and len(os.fsencode(path)) <= 100
                and stat.S_ISSOCK(path.lstat().st_mode)
                and math.isfinite(deadline) and 0 < deadline - monotonic() <= 1800
            )
        except (OSError, TypeError, ValueError):
            valid = False
        if not valid:
            raise ValueError('invalid_relay_configuration')
        self._path = str(path)
        self._deadline = deadline
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sockets = set()
        self._slots = threading.BoundedSemaphore(4)
        self._listener = None

    def __enter__(self):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(('127.0.0.1', 0))
            listener.listen(4)
            listener.settimeout(.1)
        except BaseException:
            listener.close()
            raise
        self._listener = listener
        self.address = listener.getsockname()
        self.base_url = f'http://127.0.0.1:{self.address[1]}/v1'
        try:
            self._thread = threading.Thread(target=self._accept, daemon=True)
            self._thread.start()
        except BaseException:
            self._close()
            raise
        return self

    def _accept(self):
        try:
            while not self._stop.is_set() and monotonic() < self._deadline:
                try:
                    client, _ = self._listener.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not self._slots.acquire(blocking=False):
                    client.close()
                    continue
                with self._lock:
                    if self._stop.is_set():
                        client.close()
                        self._slots.release()
                        break
                    self._sockets.add(client)
                try:
                    threading.Thread(target=self._serve, args=(client,), daemon=True).start()
                except RuntimeError:
                    with self._lock:
                        self._sockets.discard(client)
                    client.close()
                    self._slots.release()
                    break
        finally:
            self._close()

    def _copy(self, source, target, failed):
        total = 0
        try:
            while not self._stop.is_set() and not failed.is_set() and monotonic() < self._deadline:
                try:
                    data = source.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    target.shutdown(socket.SHUT_WR)
                    return
                total += len(data)
                if total > _MAX_BYTES:
                    break
                target.sendall(data)
        except OSError:
            pass
        failed.set()

    def _serve(self, client):
        upstream = None
        try:
            upstream = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            with self._lock:
                if self._stop.is_set():
                    return
                self._sockets.add(upstream)
            client.settimeout(.1)
            upstream.settimeout(.1)
            upstream.connect(self._path)
            failed = threading.Event()
            sender = threading.Thread(target=self._copy, args=(client, upstream, failed), daemon=True)
            sender.start()
            self._copy(upstream, client, failed)
            failed.set()
            sender.join(timeout=.3)
        except (OSError, RuntimeError):
            pass
        finally:
            with self._lock:
                self._sockets.discard(client)
                self._sockets.discard(upstream)
            client.close()
            if upstream is not None:
                upstream.close()
            self._slots.release()

    def _close(self):
        self._stop.set()
        if self._listener is not None:
            self._listener.close()
        with self._lock:
            for connection in self._sockets:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                connection.close()

    def __exit__(self, *_):
        self._close()
        self._thread.join(timeout=.5)
