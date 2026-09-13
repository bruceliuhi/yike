"""Private Unix-socket control service; never expose this listener over TCP."""

import argparse
import base64
from http.server import BaseHTTPRequestHandler
import json
import signal
import stat
import threading

from pilot.responses_bridge import _UnixServer, _private_socket_path


class _BoundedServer(_UnixServer):
    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(4)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            self.shutdown_request(request)
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        # No request bodies, task tokens or exception details in service logs.
        pass


class BrokerServer:
    def __init__(self, broker, socket_path):
        self.broker = broker
        self.path = _private_socket_path(socket_path)
        self._inode = None
        self._server = None
        self._thread = None

    def __enter__(self):
        broker = self.broker
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(5)
                super().setup()

            def log_message(self, *_):
                pass

            def reply(self, status, value):
                payload = json.dumps(value, separators=(',', ':')).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                self.reply(405, {'error':'method_not_allowed'})

            def do_POST(self):
                fields = {'/v1/create': {'identity','expires_at'},
                          '/v1/status': {'identity'}, '/v1/stop': {'identity'},
                          '/v1/execute': {'identity','manifest'}}
                if self.path not in fields:
                    self.reply(404, {'error':'not_found'})
                    return
                try:
                    lengths = self.headers.get_all('Content-Length', [])
                    if (len(lengths) != 1 or not lengths[0].isdigit()
                            or not 0 < int(lengths[0]) <= 1024*1024
                            or self.headers.get('Transfer-Encoding') is not None
                            or self.headers.get_content_type() != 'application/json'):
                        raise ValueError()
                    body = json.loads(self.rfile.read(int(lengths[0])))
                    if type(body) is not dict or set(body) != fields[self.path]:
                        raise ValueError()
                except (ValueError, TypeError, RecursionError):
                    self.reply(400, {'error':'invalid_request'})
                    return
                if self.path == '/v1/execute':
                    self.send_response(200)
                    self.send_header('Content-Type','application/x-ndjson')
                    self.send_header('Connection','close')
                    self.end_headers()
                    def frame(value):
                        self.wfile.write(json.dumps(value,separators=(',',':')).encode()+b'\n')
                        self.wfile.flush()
                    def emit(data):
                        if type(data) is not bytes or len(data) > 65536:
                            raise ValueError('invalid_output_chunk')
                        if not data:
                            frame({'type':'heartbeat'})
                        else:
                            frame({'type':'chunk','data':base64.b64encode(data).decode('ascii')})
                    try:
                        result = broker.execute(body['identity'],body['manifest'],emit=emit)
                        frame({'type':'result','value':result})
                    except Exception:
                        # A lost stream is UNKNOWN to the caller, never an implicit retry.
                        frame({'type':'error','code':'broker_execution_unavailable'})
                    return
                try:
                    if self.path == '/v1/create':
                        result = broker.create(body['identity'],expires_at=body['expires_at'])
                    elif self.path == '/v1/status':
                        result = broker.status(body['identity'])
                    else:
                        result = broker.stop(body['identity'])
                except ValueError:
                    self.reply(400, {'error':'invalid_request'})
                except Exception:
                    self.reply(503, {'error':'broker_unavailable'})
                else:
                    self.reply(200,result)
        try:
            self._server = _BoundedServer(str(self.path), Handler, bind_and_activate=False)
            self._server.server_bind()
            info = self.path.lstat()
            self._inode = (info.st_dev, info.st_ino)
            self.path.chmod(0o600)
            self._server.server_activate()
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
        except BaseException:
            if self._server is not None:
                self._server.server_close()
            self._remove_socket()
            raise
        return self

    def _remove_socket(self):
        try:
            info = self.path.lstat()
            if stat.S_ISSOCK(info.st_mode) and (info.st_dev,info.st_ino) == self._inode:
                self.path.unlink()
        except FileNotFoundError:
            pass

    def __exit__(self, *_):
        try:
            self._server.shutdown()
            self._server.server_close()
            self._thread.join(timeout=1)
        finally:
            self._remove_socket()


def main():
    from pilot.research_container_broker import TaskContainerBroker
    parser = argparse.ArgumentParser()
    for name in ('socket','image','tasks-root','ledger-root'):
        parser.add_argument('--'+name,required=True)
    args = parser.parse_args()
    stopping = threading.Event()
    signal.signal(signal.SIGTERM,lambda *_: stopping.set())
    signal.signal(signal.SIGINT,lambda *_: stopping.set())
    with TaskContainerBroker(image=args.image,tasks_root=args.tasks_root,ledger_root=args.ledger_root) as broker:
        with BrokerServer(broker,args.socket):
            stopping.wait()


if __name__ == '__main__':
    main()
