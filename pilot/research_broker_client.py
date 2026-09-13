"""Unprivileged client: fixed local socket/routes, never imports Docker control."""
import base64
import json
import os
from pathlib import Path
import stat

import httpx

from pilot.research_broker_contract import task_key


class BrokerClient:
    def __init__(self, socket_path):
        path = Path(socket_path)
        info = path.lstat()
        if (not path.is_absolute() or not stat.S_ISSOCK(info.st_mode)
                or info.st_uid != os.getuid() or info.st_mode & 0o077):
            raise ValueError('invalid_broker_socket')
        self.path = str(path)

    def _client(self, *, streaming=False):
        return httpx.Client(transport=httpx.HTTPTransport(uds=self.path),
            base_url='http://broker',trust_env=False,timeout=1830 if streaming else 10)

    def _result(self, identity, value, *, execution=False):
        fields = {'key','status','code'} if execution else {'key','status'}
        if (type(value) is not dict or set(value) != fields or value['key'] != task_key(identity)
                or value['status'] not in ('CREATED','RUNNING','STOPPED','UNKNOWN')
                or execution and value['code'] not in (None,'cancelled','timeout','output_limit',
                                                        'runtime_failed','runtime_unavailable')):
            raise ValueError('invalid_broker_result')
        return value

    def _request(self, action, identity, **extra):
        task_key(identity)
        with self._client() as client:
            with client.stream('POST','/v1/'+action,json={'identity':identity,**extra}) as response:
                response.raise_for_status()
                data = b''
                for chunk in response.iter_bytes(4096):
                    data += chunk
                    if len(data) > 4096:
                        raise ValueError('invalid_broker_result')
                return self._result(identity,json.loads(data))

    def create(self, identity, *, expires_at):
        return self._request('create',identity,expires_at=expires_at)

    def status(self, identity):
        return self._request('status',identity)

    def stop(self, identity):
        return self._request('stop',identity)

    def events(self, identity, manifest):
        task_key(identity)
        with self._client(streaming=True) as client:
            with client.stream('POST','/v1/execute',json={'identity':identity,'manifest':manifest}) as response:
                response.raise_for_status()
                pending, total, done = b'', 0, False
                for chunk in response.iter_bytes():
                    pending += chunk
                    if len(pending) > 192*1024:
                        raise ValueError('invalid_broker_stream')
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n',1)
                        value = json.loads(line)
                        if done or type(value) is not dict:
                            raise ValueError('invalid_broker_stream')
                        if set(value)=={'type','data'} and value['type']=='chunk':
                            data = base64.b64decode(value['data'],validate=True)
                            total += len(data)
                            if not 0 < len(data) <= 65536 or total > 2*1024*1024:
                                raise ValueError('invalid_broker_stream')
                            yield {'type':'chunk','data':data}
                        elif set(value)=={'type','value'} and value['type']=='result':
                            done = True
                            yield {'type':'result','value':self._result(identity,value['value'],execution=True)}
                        else:
                            raise ValueError('invalid_broker_stream')
                if pending or not done:
                    raise ValueError('incomplete_broker_stream')
