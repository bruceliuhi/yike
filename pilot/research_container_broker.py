"""Privileged broker core. Never import into the customer API execution path."""

import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
from time import time
from uuid import UUID
from pilot.research_container_lifecycle import ContainerLifecycle

_RUNTIME_UID = 10001


def task_key(identity):
    try:
        if type(identity) is not dict or set(identity) != {'tenant_id', 'task_id', 'run_id', 'generation'}:
            raise ValueError()
        for field in ('tenant_id', 'task_id', 'run_id'):
            if type(identity[field]) is not str or str(UUID(identity[field])) != identity[field]:
                raise ValueError()
        if type(identity['generation']) is not int or not 1 <= identity['generation'] <= 2**31-1:
            raise ValueError()
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    except (ValueError, TypeError, AttributeError):
        raise ValueError('invalid_task_identity') from None


def _private_directory(path):
    path = Path(path)
    info = path.lstat()
    if (not path.is_absolute() or path.resolve() != path or ',' in str(path)
            or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077):
        raise ValueError('invalid_broker_directory')
    return path


def _run(command):
    try:
        return subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, timeout=2,
            env={'PATH': '/usr/local/bin:/usr/bin:/bin'})
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess(command, 1, '')


class TaskContainerBroker(ContainerLifecycle):
    def __init__(self, *, image, tasks_root, ledger_root):
        if os.getuid() != _RUNTIME_UID:
            raise ValueError('runtime_uid_required')
        if type(image) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
            raise ValueError('immutable_image_required')
        self.image = image
        self.tasks_root = _private_directory(tasks_root)
        Path(ledger_root).mkdir(mode=0o700, exist_ok=True)
        self.ledger_root = _private_directory(ledger_root)

    def _claim(self, key):
        try:
            path = self.ledger_root/(key+'.json')
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1024 or info.st_mode & 0o077:
                return None
            value = json.loads(path.read_text())
            if (set(value) != {'key', 'image', 'expires_at'} or value['key'] != key
                    or type(value['image']) is not str
                    or not re.fullmatch(r'sha256:[0-9a-f]{64}', value['image'])
                    or type(value['expires_at']) not in (int, float)
                    or not math.isfinite(value['expires_at'])):
                return None
            return value
        except (OSError, ValueError, TypeError):
            return None

    def _inspect(self, key):
        claim = self._claim(key)
        if claim is None:
            return None
        result = _run(['docker', 'inspect', '--type=container', '--format',
            '{"state":{{json .State}},"labels":{{json .Config.Labels}}}', 'yike-r-'+key])
        try:
            if result.returncode != 0:
                return None
            value = json.loads(result.stdout)
            if (value['labels'].get('yike.research.key') != key
                    or value['labels'].get('yike.research.image') != claim['image']
                    or type(value['state']) is not dict):
                return None
            return value['state']
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    def status(self, identity):
        key = task_key(identity)
        return self._status_key(key)

    def _status_key(self, key):
        state = self._inspect(key)
        if state is None:
            status = 'UNKNOWN'
        elif state.get('Running') is True:
            status = 'RUNNING'
        elif state.get('Status') == 'created':
            status = ('UNKNOWN' if (self.ledger_root/(key+'.started')).exists() else 'CREATED')
        elif state.get('Status') in ('exited', 'dead') and state.get('Running') is False:
            status = 'STOPPED'
        else:
            status = 'UNKNOWN'
        return {'key': key, 'status': status}

    def create(self, identity, *, expires_at):
        key = task_key(identity)
        if type(expires_at) not in (int, float) or not math.isfinite(expires_at) or not 0 < expires_at-time() <= 1800:
            raise ValueError('invalid_task_deadline')
        record = self.ledger_root/(key+'.json')
        # Any existing reservation, including a partial/unknown one, prevents recreation.
        if os.path.lexists(record):
            return self.status(identity)
        directory = _private_directory(self.tasks_root/key)
        info = (directory/'bridge.sock').lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('invalid_task_socket')
        try:
            fd = os.open(record, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self.status(identity)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'key': key, 'image': self.image, 'expires_at': expires_at}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        directory_fd = os.open(self.ledger_root, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        _run(['docker', 'create', '--name=yike-r-'+key, '--interactive', '--network=none',
            '--read-only', '--user='+str(_RUNTIME_UID)+':'+str(_RUNTIME_UID), '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--memory=512m', '--cpus=1', '--pids-limit=64',
            '--restart=no', '--log-driver=none',
            '--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777',
            '--mount=type=bind,src='+str(directory)+',dst=/run/yike,readonly',
            '--label=yike.research.key='+key, '--label=yike.research.image='+self.image,
            '--entrypoint=/app/.venv/bin/python', self.image,
            '-I', '-m', 'pilot.research_container_entry'])
        return self.status(identity)

    def stop(self, identity):
        key = task_key(identity)
        return self._stop_key(key)

    def _stop_key(self, key):
        self._mark(key, 'cancelled')
        state = self._inspect(key)
        if state is None:
            return {'key': key, 'status': 'UNKNOWN'}
        if state.get('Running') is True:
            _run(['docker', 'kill', '--signal=KILL', 'yike-r-'+key])
        result = self._status_key(key)
        if result['status'] == 'STOPPED':
            self._mark(key, 'terminal')
        return result
