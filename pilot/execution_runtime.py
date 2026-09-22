"""Database-only execution fences. No worker, platform calls, or production policy.

The injected strategy resolver must lock/prove current confirmation and source
scope using this cursor only. Neither callbacks nor transactions may cross a
network/model/browser wait. Default construction intentionally fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
import base64
from datetime import datetime
import hashlib
import json
import math
from typing import Callable
from uuid import uuid4
from weakref import WeakKeyDictionary

from psycopg import Cursor
from pydantic import BaseModel, ValidationError

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.candidate_contract import CandidateBatch, CandidateRecord, CandidateContractError, batch_fingerprint, validate_candidate_batch
from pilot.connection_versions import ConnectionOperationError, ConnectionOperationStore
from pilot.device_keys import DeviceKeyError, verify_signature
from pilot.execution_contract import ExecutionOperation, ExecutionRuntimeError, ExecutionTarget, MAX_VERSION, canonical_uuid
from pilot.public_sampling_progress import committed_public_sampling_round
from pilot.sessions import PilotSessionRegistry


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _raw_model(value):
    # Pydantic serializers may coerce a forged model_copy field (True -> 1).
    # Read raw values before revalidation, including nested frozen 02A models.
    if isinstance(value, BaseModel):
        raw = {key: _raw_model(getattr(value, key)) for key in type(value).model_fields}
        # Absence is valid; explicitly supplied null remains invalid. Do not use
        # model_dump here: its serializers can normalize forged scalar types.
        if isinstance(value, CandidateRecord) and value.source_context is None \
                and 'source_context' not in value.__pydantic_fields_set__:
            raw.pop('source_context', None)
        if isinstance(value, CandidateRecord) and value.page_metadata is None \
                and 'page_metadata' not in value.__pydantic_fields_set__:
            raw.pop('page_metadata', None)
        if isinstance(value, CandidateBatch) and value.native_progress is None \
                and 'native_progress' not in value.__pydantic_fields_set__:
            raw.pop('native_progress', None)
        if isinstance(value, CandidateBatch) and value.public_revisit is None \
                and 'public_revisit' not in value.__pydantic_fields_set__:
            raw.pop('public_revisit', None)
        if isinstance(value, ExecutionOperation) and value.public_sampling_version is None \
                and 'public_sampling_version' not in value.__pydantic_fields_set__:
            raw.pop('public_sampling_version', None)
        if isinstance(value, ExecutionOperation) and value.native_progress_version is None \
                and 'native_progress_version' not in value.__pydantic_fields_set__:
            raw.pop('native_progress_version', None)
        return raw
    if isinstance(value, (tuple, list)):
        return [_raw_model(item) for item in value]
    return value


def _row(cursor):
    value = cursor.fetchone()
    return dict(zip((column.name for column in cursor.description), value)) if value else None


@dataclass(frozen=True)
class ConfirmedExecutionStrategy:
    profile_version_id: str
    strategy_version_id: str
    configuration_sha256: str
    configuration: dict
    platforms: tuple[str, ...]
    max_records: int
    max_runtime_seconds: int


StrategyResolver = Callable[[Cursor, TokenClaims, str, str], ConfirmedExecutionStrategy]
CapabilityCheck = Callable[[str, str, dict], bool]


def execution_signing_payload(*, tenant_id: str, claims: TokenClaims, operation: ExecutionOperation) -> str:
    operation = _operation(operation)
    return _json(dict(protocol='yike-execution-operation-v1', tenant_id=tenant_id,
        user_id=claims.user_id, session_digest=claims.revocation_key, operation=operation.model_dump(mode='json')))


def submission_signing_payload(*, tenant_id: str, claims: TokenClaims, batch: CandidateBatch) -> str:
    # The 02A fingerprint excludes request_id, so bind that separately.
    return _json(dict(protocol='yike-candidate-submission-v1', tenant_id=tenant_id,
        user_id=claims.user_id, session_digest=claims.revocation_key,
        request_id=batch.request_id, batch_fingerprint=batch_fingerprint(batch)))


def _operation(value):
    try:
        return ExecutionOperation.model_validate(value)
    except (ValidationError, TypeError, ValueError):
        raise ExecutionRuntimeError('invalid_request', 422) from None


def _json_tree(value, depth=0):
    if depth > 20:
        raise ValueError
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str: raise ValueError
            _json_tree(item, depth + 1)
    elif type(value) is list:
        for item in value: _json_tree(item, depth + 1)
    elif value is not None and type(value) not in (str, int, float, bool):
        raise ValueError
    elif type(value) is float and not math.isfinite(value):
        raise ValueError


class ExecutionRuntime:
    def __init__(self, database, *, strategy_resolver: StrategyResolver | None = None,
                 capability_check: CapabilityCheck | None = None):
        self.database = database
        self.sessions = PilotSessionRegistry(database)
        self.connections = ConnectionOperationStore(database)
        self.strategy_resolver, self.capability_check = strategy_resolver, capability_check
        self.monitor_runtime = None
        # A final fence must follow a successful guard on this cursor/transaction.
        # These markers are NOT authority; the full stored join is rechecked.
        self._submission_guards = WeakKeyDictionary()

    def _active(self, cursor, claims):
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise ExecutionRuntimeError('invalid_session', 401) from None

    @staticmethod
    def _now(cursor):
        cursor.execute('SELECT clock_timestamp()')
        return cursor.fetchone()[0]

    def _key(self, cursor, claims, tenant, device_id, version):
        cursor.execute('SELECT status FROM pilot_devices WHERE tenant_id=%s AND owner_user_id=%s '
                       'AND device_id=%s FOR UPDATE', (tenant, claims.user_id, device_id))
        device = cursor.fetchone()
        self._active(cursor, claims)
        if not device or device[0] != 'ACTIVE':
            raise ExecutionRuntimeError('device_unavailable', 404)
        cursor.execute('SELECT public_key,credential_version FROM pilot_device_credentials '
                       'WHERE tenant_id=%s AND owner_user_id=%s AND device_id=%s FOR UPDATE',
                       (tenant, claims.user_id, device_id))
        key = cursor.fetchone()
        self._active(cursor, claims)
        if not key or key[1] != version:
            raise ExecutionRuntimeError('credential_conflict')
        return key[0]

    @staticmethod
    def _signature(key, signature, payload):
        try:
            verify_signature(key, signature, payload)
        except DeviceKeyError:
            raise ExecutionRuntimeError('invalid_proof', 400) from None

    def _connection(self, cursor, claims, device_id, target):
        if target.access_mode == 'PUBLIC_ANONYMOUS': return
        try:
            self.connections.lock_current(cursor, claims, device_id=device_id,
                connection_id=target.connection_id, connection_version=target.connection_version,
                platform=target.platform)
        except ConnectionOperationError as error:
            raise ExecutionRuntimeError(error.code, error.status) from None

    def _strategy(self, cursor, claims, tenant, profile_id, strategy_id, expected_hash, targets):
        if self.strategy_resolver is None or self.capability_check is None:
            raise ExecutionRuntimeError('capability_unavailable', 501)
        cursor.execute('SELECT profile_id FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s',
                       (tenant, profile_id))
        profile = cursor.fetchone()
        if profile is None: raise ExecutionRuntimeError('profile_unavailable')
        cursor.execute('SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE',
                       (tenant, profile[0]))
        cursor.execute('SELECT status FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s FOR UPDATE',
                       (tenant, profile_id))
        version = cursor.fetchone()
        self._active(cursor, claims)
        if not version or version[0] != 'CONFIRMED': raise ExecutionRuntimeError('profile_unavailable')
        value = self.strategy_resolver(cursor, claims, profile_id, strategy_id)
        try:
            if not isinstance(value, ConfirmedExecutionStrategy): raise ValueError
            if (value.profile_version_id, value.strategy_version_id) != (profile_id, strategy_id): raise ValueError
            if type(value.configuration) is not dict: raise ValueError
            _json_tree(value.configuration)
            if len(_json(value.configuration).encode('utf-8')) > 65536: raise ValueError
            if type(value.platforms) is not tuple or not 1 <= len(value.platforms) <= 5: raise ValueError
            if len(set(value.platforms)) != len(value.platforms): raise ValueError
            if any(p not in ('XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB') for p in value.platforms): raise ValueError
            if type(value.max_records) is not int or not 1 <= value.max_records <= 10000: raise ValueError
            if type(value.max_runtime_seconds) is not int or not 1 <= value.max_runtime_seconds <= 86400: raise ValueError
            snapshot = dict(profile_version_id=profile_id, strategy_version_id=strategy_id,
                configuration=value.configuration, platforms=list(value.platforms),
                max_records=value.max_records, max_runtime_seconds=value.max_runtime_seconds)
            actual_hash = _hash(snapshot)
            if value.configuration_sha256 != actual_hash or expected_hash != actual_hash: raise ValueError
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ExecutionRuntimeError('strategy_conflict') from None
        for target in targets:
            if target.platform not in value.platforms:
                raise ExecutionRuntimeError('strategy_conflict')
            if self.capability_check(target.platform, target.access_mode, json.loads(_json(value.configuration))) is not True:
                raise ExecutionRuntimeError('capability_unavailable', 501)
        self._active(cursor, claims)
        return json.loads(_json(snapshot))

    def _receipt(self, cursor, tenant, user, request_id):
        cursor.execute('SELECT operation_sha256,receipt FROM pilot_execution_operations '
            'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s', (tenant, user, request_id))
        return cursor.fetchone()

    def prepare_signing_payload(self, claims, request: ExecutionOperation) -> dict:
        request = _operation(request)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            self._key(cursor, claims, tenant, request.device_id, request.credential_version)
            result = dict(
                signing_payload=execution_signing_payload(
                    tenant_id=tenant, claims=claims, operation=request),
                request_id=request.request_id,
                device_id=request.device_id,
                credential_version=request.credential_version,
                request_sha256=_hash(request.model_dump(mode='json')),
            )
            self._active(cursor, claims)
            return result

    def prepare_submission_signing_payload(self, claims, payload: dict) -> dict:
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            batch = validate_candidate_batch(payload, now=self._now(cursor))
            execution = batch.execution
            self._key(cursor, claims, tenant, execution.device_id, execution.credential_version)
            from pilot.public_source_revisit import validate_public_revisit
            if validate_public_revisit(cursor, tenant_id=tenant, owner_user_id=claims.user_id, batch=batch):
                self._submission(cursor, claims, batch)
            result = dict(
                signing_payload=submission_signing_payload(tenant_id=tenant, claims=claims, batch=batch),
                request_id=batch.request_id,
                device_id=execution.device_id,
                credential_version=execution.credential_version,
                batch_fingerprint=batch_fingerprint(batch),
            )
            self._active(cursor, claims)
            return result

    def apply(self, claims, request: ExecutionOperation, signature: str) -> dict:
        return self._apply(claims, request, signature, research_hook=None)

    def apply_research(self, claims, request: ExecutionOperation, signature: str, research_hook) -> dict:
        if not callable(research_hook):
            raise ExecutionRuntimeError('capability_unavailable', 503)
        return self._apply(claims, request, signature, research_hook=research_hook)

    @staticmethod
    def _research_row(cursor, tenant, user, *, request_id=None, task_id=None):
        field, value = ('request_id', request_id) if request_id is not None else ('task_id', task_id)
        cursor.execute(f'SELECT receipt FROM pilot_research_reservations WHERE tenant_id=%s '
            f'AND owner_user_id=%s AND {field}=%s', (tenant, user, value))
        row = cursor.fetchone()
        return row[0] if row else None

    def _apply(self, claims, request: ExecutionOperation, signature: str, research_hook) -> dict:
        request = _operation(request)
        fingerprint = _hash(request.model_dump(mode='json', exclude={'request_id'}))
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            lock = int.from_bytes(hashlib.sha256((tenant+'\0'+claims.user_id+'\0'+request.request_id).encode()).digest()[:4], 'big', signed=True)
            cursor.execute('SELECT pg_advisory_xact_lock(11101,%s)', (lock,))
            self._active(cursor, claims)
            previous = self._receipt(cursor, tenant, claims.user_id, request.request_id)
            if previous:
                if previous[0] != fingerprint: raise ExecutionRuntimeError('request_conflict')
                self._active(cursor, claims)
                research = self._research_row(cursor, tenant, claims.user_id, request_id=request.request_id)
                if research_hook is None:
                    if research is not None: raise ExecutionRuntimeError('capability_unavailable', 409)
                    return previous[1]  # Historical receipt is not a renewed authorization.
                if research is None:
                    raise ExecutionRuntimeError('request_conflict', 409)
                return research_hook(cursor, tenant, request, previous[1], research)
            if request.operation == 'FINISH':
                # Same immutable upload lock and order as CandidateIngestionStore:
                # sessions -> execution request -> upload -> device/key -> task.
                upload_lock = int.from_bytes(hashlib.sha256(_json([
                    tenant, request.platform_run_id, request.upload_request_id]).encode()).digest()[:4], 'big', signed=True)
                cursor.execute('SELECT pg_advisory_xact_lock(11201,%s)', (upload_lock,))
                self._active(cursor, claims)
            key = self._key(cursor, claims, tenant, request.device_id, request.credential_version)
            self._signature(key, signature, execution_signing_payload(tenant_id=tenant, claims=claims, operation=request))
            reservation = None
            if request.operation == 'START':
                result, snapshot = self._start(cursor, claims, tenant, request)
                is_research = type(snapshot['configuration'].get('research')) is dict
                if research_hook is None and is_research:
                    raise ExecutionRuntimeError('capability_unavailable', 409)
                reservation = research_hook(cursor, tenant, request, result, None, snapshot) if research_hook else None
            else:
                if research_hook is not None:
                    raise ExecutionRuntimeError('invalid_request', 422)
                result = self._mutate(cursor, claims, tenant, request)
            result.update(schema_version='execution-runtime-v1', request_id=request.request_id, operation=request.operation)
            self._active(cursor, claims)
            cursor.execute('INSERT INTO pilot_execution_operations(tenant_id,owner_user_id,request_id,operation,'
                'operation_sha256,task_id,run_id,receipt) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                (tenant, claims.user_id, request.request_id, request.operation, fingerprint,
                 result['task_id'], result['run_id'], _json(result)))
            self._active(cursor, claims)
            if request.operation not in ('CANCEL', 'STOP'):
                task, run, platforms = self._locks(cursor, claims, tenant, result['task_id'])
                finishing = request.operation == 'FINISH'
                now, _ = self._live(cursor, task, run, platforms, budget=not finishing, finished=finishing)
                if request.operation != 'START':
                    platform = next(p for p in platforms if p['platform_run_id']==result['platform_run_id'])
                    self._lease(platform, request.credential_version, result['lease_id'], result['execution_generation'], now,
                                status='SUCCEEDED' if finishing else 'RUNNING')
            return reservation if reservation is not None else result

    def _start(self, cursor, claims, tenant, request):
        for target in sorted(request.targets, key=lambda t: (t.platform, t.connection_id or '')):
            self._connection(cursor, claims, request.device_id, target)
        snapshot = self._strategy(cursor, claims, tenant, request.profile_version_id,
            request.strategy_version_id, request.configuration_sha256, request.targets)
        occurrence_id = None
        if snapshot['configuration'].get('mode') == 'monitor':
            if self.monitor_runtime is None:
                raise ExecutionRuntimeError('monitor_occurrence_required')
            occurrence_id = self.monitor_runtime.guard_start(cursor, claims, tenant, request, snapshot)
        task_id, run_id = str(uuid4()), str(uuid4())
        now = self._now(cursor)
        cursor.execute('INSERT INTO pilot_collection_tasks(tenant_id,owner_user_id,task_id,device_id,'
            'profile_version_id,strategy_version_id,configuration_sha256,configuration_snapshot,max_records,'
            'max_runtime_seconds,created_at,deadline_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s + %s * interval \'1 second\')',
            (tenant, claims.user_id, task_id, request.device_id, request.profile_version_id,
             request.strategy_version_id, request.configuration_sha256, _json(snapshot),
             snapshot['max_records'], snapshot['max_runtime_seconds'], now, now, snapshot['max_runtime_seconds']))
        cursor.execute('INSERT INTO pilot_collection_runs(tenant_id,owner_user_id,task_id,run_id,device_id,profile_version_id) '
            'VALUES (%s,%s,%s,%s,%s,%s)', (tenant, claims.user_id, task_id, run_id, request.device_id, request.profile_version_id))
        platforms = []
        for index, target in enumerate(request.targets):
            platform_id = str(uuid4())
            cursor.execute('INSERT INTO pilot_collection_platform_runs(tenant_id,owner_user_id,task_id,run_id,platform_run_id,'
                'device_id,profile_version_id,platform,target_order,access_mode,connection_id,connection_version,credential_version) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (tenant, claims.user_id, task_id, run_id, platform_id, request.device_id, request.profile_version_id,
                 target.platform, index, target.access_mode, target.connection_id, target.connection_version, request.credential_version))
            platforms.append(dict(platform_run_id=platform_id, platform=target.platform, status='PENDING'))
        if occurrence_id is not None:
            self.monitor_runtime.link_start(cursor, claims, tenant, occurrence_id, task_id, run_id)
        return (dict(task_id=task_id, run_id=run_id, status='PENDING', stop_confirmed=False,
            platform_runs=platforms), snapshot)

    def _peek_task(self, cursor, tenant, user, task_id):
        cursor.execute('SELECT * FROM pilot_collection_tasks WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s',
                       (tenant, user, task_id))
        task = _row(cursor)
        if task is None: raise ExecutionRuntimeError('task_not_found', 404)
        return task

    def _locks(self, cursor, claims, tenant, task_id):
        params = (tenant, claims.user_id, task_id)
        cursor.execute('SELECT * FROM pilot_collection_tasks WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s FOR UPDATE', params)
        task = _row(cursor)
        if task is None: raise ExecutionRuntimeError('task_not_found', 404)
        cursor.execute('SELECT * FROM pilot_collection_runs WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s FOR UPDATE', params)
        run = _row(cursor)
        cursor.execute('SELECT * FROM pilot_collection_platform_runs WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s '
                       'ORDER BY platform,platform_run_id FOR UPDATE', params)
        columns = [c.name for c in cursor.description]
        platforms = [dict(zip(columns, row)) for row in cursor.fetchall()]
        self._active(cursor, claims)
        return task, run, platforms

    @staticmethod
    def _target(platform):
        return ExecutionTarget.model_validate({key: platform[key] for key in
            ('platform', 'access_mode', 'connection_id', 'connection_version')})

    def _versions(self, cursor, claims, tenant, task, platform_id, device_id):
        if task['device_id'] != device_id: raise ExecutionRuntimeError('device_unavailable', 404)
        monitor = task['configuration_snapshot'].get('configuration', {}).get('mode') == 'monitor'
        if monitor and self.monitor_runtime is None:
            raise ExecutionRuntimeError('monitor_occurrence_required')
        cursor.execute('SELECT * FROM pilot_collection_platform_runs WHERE tenant_id=%s AND owner_user_id=%s '
            'AND task_id=%s AND platform_run_id=%s', (tenant, claims.user_id, task['task_id'], platform_id))
        platform = _row(cursor)
        if platform is None: raise ExecutionRuntimeError('platform_run_not_found', 404)
        target = self._target(platform)
        self._connection(cursor, claims, device_id, target)
        snapshot = self._strategy(cursor, claims, tenant, task['profile_version_id'], task['strategy_version_id'],
            task['configuration_sha256'], (target,))
        if _json(snapshot) != _json(task['configuration_snapshot']): raise ExecutionRuntimeError('strategy_conflict')
        if monitor:
            self.monitor_runtime.guard_task(cursor, claims, tenant, task)

    def _live(self, cursor, task, run, platforms, *, budget, finished=False):
        if task['status'] in ('CANCELLING','CANCELED') or run['status'] in ('CANCELLING','CANCELED'):
            raise ExecutionRuntimeError('task_cancelled')
        if not finished and (task['status'] == 'SUCCEEDED' or run['status'] == 'SUCCEEDED'):
            raise ExecutionRuntimeError('task_finished')
        now = self._now(cursor)
        if now >= task['deadline_at']: raise ExecutionRuntimeError('task_expired')
        remaining = task['max_records'] - sum(p['records_used'] for p in platforms)
        if budget and remaining <= 0: raise ExecutionRuntimeError('budget_exhausted')
        return now, remaining

    def _mutate(self, cursor, claims, tenant, request):
        peek = self._peek_task(cursor, tenant, claims.user_id, request.task_id)
        research_task = type(peek.get('configuration_snapshot', {}).get('configuration', {}).get('research')) is dict
        if request.operation != 'CANCEL' and (research_task or self._research_row(
                cursor, tenant, claims.user_id, task_id=request.task_id) is not None):
            raise ExecutionRuntimeError('capability_unavailable', 409)
        if peek['device_id'] != request.device_id: raise ExecutionRuntimeError('device_unavailable', 404)
        if peek['status'] == 'SUCCEEDED': raise ExecutionRuntimeError('task_finished')
        if request.operation not in ('CANCEL', 'STOP'):
            # Cancellation failure takes precedence even when strategy was revoked.
            if peek['status'] in ('CANCELED','CANCELLING'): raise ExecutionRuntimeError('task_cancelled')
            self._versions(cursor, claims, tenant, peek, request.platform_run_id, request.device_id)
        task, run, platforms = self._locks(cursor, claims, tenant, request.task_id)
        params = (tenant, claims.user_id, request.task_id)
        if task['status'] == 'SUCCEEDED': raise ExecutionRuntimeError('task_finished')
        if request.operation == 'CANCEL':
            for platform in platforms:
                if platform['status'] not in ('SUCCEEDED', 'CANCELED'):
                    platform['status'] = 'CANCELED' if platform['execution_generation'] == 0 else 'CANCELLING'
            cursor.execute("UPDATE pilot_collection_platform_runs SET status=CASE WHEN execution_generation=0 "
                "THEN 'CANCELED' ELSE 'CANCELLING' END WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s "
                "AND status NOT IN ('SUCCEEDED','CANCELED')", params)
            stopped = all(p['status'] in ('SUCCEEDED', 'CANCELED') for p in platforms)
            status = 'CANCELED' if stopped else 'CANCELLING'
            for table in ('pilot_collection_tasks', 'pilot_collection_runs'):
                cursor.execute(f'UPDATE {table} SET status=%s WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s '
                               "AND status<>'SUCCEEDED'", (status, *params))
            return dict(task_id=task['task_id'], run_id=run['run_id'], status=status, stop_confirmed=stopped)
        if request.operation == 'STOP':
            if task['status'] not in ('CANCELLING', 'CANCELED') or run['status'] not in ('CANCELLING', 'CANCELED'):
                raise ExecutionRuntimeError('task_not_cancelling')
            platform = next((p for p in platforms if p['platform_run_id'] == request.platform_run_id), None)
            if platform is None: raise ExecutionRuntimeError('platform_run_not_found', 404)
            # A STOP proves quiescence of this exact claimed execution, not a
            # renewed right to execute. Expiry and revoked strategy/connection
            # therefore do not block it; current device proof was checked above.
            if (platform['credential_version'], platform['lease_id'], platform['execution_generation']) != (
                    request.credential_version, request.lease_id, request.execution_generation):
                raise ExecutionRuntimeError('lease_conflict')
            if platform['status'] not in ('CANCELLING', 'CANCELED'):
                raise ExecutionRuntimeError('lease_conflict')
            cursor.execute("UPDATE pilot_collection_platform_runs SET status='CANCELED' "
                'WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND platform_run_id=%s',
                (*params, request.platform_run_id))
            stopped = all(p['platform_run_id'] == request.platform_run_id or p['status'] in ('SUCCEEDED', 'CANCELED')
                          for p in platforms)
            status = 'CANCELED' if stopped else 'CANCELLING'
            for table in ('pilot_collection_tasks', 'pilot_collection_runs'):
                cursor.execute(f'UPDATE {table} SET status=%s WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s',
                               (status, *params))
            return dict(task_id=task['task_id'], run_id=run['run_id'], platform_run_id=request.platform_run_id,
                lease_id=request.lease_id, execution_generation=request.execution_generation,
                status=status, stop_confirmed=stopped)
        now, _ = self._live(cursor, task, run, platforms, budget=request.operation != 'FINISH')
        platform = next((p for p in platforms if p['platform_run_id'] == request.platform_run_id), None)
        if platform is None: raise ExecutionRuntimeError('platform_run_not_found', 404)
        if request.operation == 'FINISH':
            self._lease(platform, request.credential_version, request.lease_id, request.execution_generation, now)
            return self._finish(cursor, claims, tenant, request, task, run, platforms, platform)
        if request.operation == 'CLAIM':
            if platform['status'] not in ('PENDING','RUNNING') or (platform['lease_expires_at'] and platform['lease_expires_at'] > now):
                raise ExecutionRuntimeError('lease_conflict')
            if platform['execution_generation'] == MAX_VERSION: raise ExecutionRuntimeError('generation_exhausted')
            lease_id, generation = str(uuid4()), platform['execution_generation'] + 1
        else:
            self._lease(platform, request.credential_version, request.lease_id, request.execution_generation, now)
            lease_id, generation = request.lease_id, request.execution_generation
        cursor.execute('UPDATE pilot_collection_platform_runs SET status=\'RUNNING\',credential_version=%s,lease_id=%s,'
            'execution_generation=%s,lease_expires_at=LEAST(clock_timestamp()+interval \'120 seconds\',%s) '
            'WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND platform_run_id=%s RETURNING lease_expires_at',
            (request.credential_version, lease_id, generation, task['deadline_at'], *params, request.platform_run_id))
        expires = cursor.fetchone()[0]
        for table in ('pilot_collection_tasks','pilot_collection_runs'):
            cursor.execute(f'UPDATE {table} SET status=\'RUNNING\' WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s', params)
        self._live(cursor, task, run, platforms, budget=True)
        result = dict(task_id=task['task_id'], run_id=run['run_id'], status='RUNNING', stop_confirmed=False,
            platform_run_id=request.platform_run_id, lease_id=lease_id, execution_generation=generation,
            lease_expires_at=expires.isoformat(), deadline_at=task['deadline_at'].isoformat())
        if request.public_sampling_version is not None:
            from pilot.foreground_collection import (
                four_platform_public_bili_links_monitor_policy,
                four_platform_public_node_monitor_policy,
                four_platform_public_project_monitor_policy,
                four_platform_public_sampling_monitor_policy,
            )
            if self.capability_check not in (
                    four_platform_public_sampling_monitor_policy,
                    four_platform_public_node_monitor_policy,
                    four_platform_public_project_monitor_policy,
                    four_platform_public_bili_links_monitor_policy):
                raise ExecutionRuntimeError('capability_unavailable', 409)
            result['public_sampling'] = committed_public_sampling_round(
                cursor, tenant_id=tenant, owner_user_id=claims.user_id, task=task, platform=platform,
                version=request.public_sampling_version)
        if request.native_progress_version is not None:
            from pilot.native_search_progress import claim_native_search_progress
            result['native_progress'] = claim_native_search_progress(
                cursor, tenant_id=tenant, owner_user_id=claims.user_id,
                task=task, platform=platform, capability_check=self.capability_check,
            )
        return result

    @staticmethod
    def _lease(platform, credential_version, lease_id, generation, now, *, status='RUNNING'):
        if (platform['credential_version'], platform['lease_id'], platform['execution_generation']) != (credential_version, lease_id, generation):
            raise ExecutionRuntimeError('lease_conflict')
        if platform['status'] != status: raise ExecutionRuntimeError('lease_conflict')
        if platform['lease_expires_at'] <= now: raise ExecutionRuntimeError('lease_expired')

    def _finish(self, cursor, claims, tenant, request, task, run, platforms, platform):
        # Batches are immutable and SELECT-only to the app. The ingest advisory
        # lock is already held, so an in-flight upload must commit before this read.
        cursor.execute('SELECT * FROM pilot_candidate_batches WHERE tenant_id=%s AND owner_user_id=%s '
            'AND platform_run_id=%s AND request_id=%s',
            (tenant, claims.user_id, request.platform_run_id, request.upload_request_id))
        batch = _row(cursor)
        expected_context = dict(device_id=request.device_id, credential_version=request.credential_version,
            task_id=task['task_id'], run_id=run['run_id'], platform_run_id=request.platform_run_id,
            lease_id=request.lease_id, execution_generation=request.execution_generation,
            access_mode=platform['access_mode'], connection_id=platform['connection_id'],
            connection_version=platform['connection_version'])
        binding = dict(task_id=task['task_id'], run_id=run['run_id'], platform=platform['platform'],
            profile_version_id=task['profile_version_id'], strategy_version_id=task['strategy_version_id'])
        if not batch or any(batch[key] != value for key, value in binding.items()) or \
                _json(batch['execution_context']) != _json(expected_context):
            raise ExecutionRuntimeError('upload_unavailable')
        receipt = batch['receipt']
        evidence = dict(schema_version='candidate-receipt-v1', request_id=request.upload_request_id,
            task_id=task['task_id'], run_id=run['run_id'], platform_run_id=request.platform_run_id,
            accepted_count=batch['accepted_count'], received_at=batch['received_at'].isoformat())
        if type(receipt) is not dict or _json({key:receipt.get(key) for key in evidence}) != _json(evidence) or \
                type(receipt.get('items')) is not list or len(receipt['items']) != batch['accepted_count'] or \
                batch['accepted_count'] > platform['records_used']:
            raise ExecutionRuntimeError('upload_unavailable')
        cursor.execute("UPDATE pilot_collection_platform_runs SET status='SUCCEEDED' "
            'WHERE tenant_id=%s AND owner_user_id=%s AND platform_run_id=%s',
            (tenant, claims.user_id, request.platform_run_id))
        succeeded = all(p['platform_run_id'] == request.platform_run_id or p['status'] == 'SUCCEEDED' for p in platforms)
        status = 'SUCCEEDED' if succeeded else 'RUNNING'
        for table in ('pilot_collection_tasks', 'pilot_collection_runs'):
            cursor.execute(f'UPDATE {table} SET status=%s WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s',
                (status, tenant, claims.user_id, task['task_id']))
        return dict(task_id=task['task_id'], run_id=run['run_id'], platform_run_id=request.platform_run_id,
            lease_id=request.lease_id, execution_generation=request.execution_generation,
            upload_request_id=request.upload_request_id, records_used=platform['records_used'],
            status=status, stop_confirmed=succeeded)

    @staticmethod
    def _transaction(cursor):
        if cursor.connection.autocommit:
            raise ExecutionRuntimeError('transaction_required', 400)
        cursor.execute('SELECT txid_current()')
        return cursor.fetchone()[0]

    def _batch(self, cursor, batch):
        if not isinstance(batch, CandidateBatch): raise ExecutionRuntimeError('invalid_batch', 422)
        try:
            return validate_candidate_batch(_raw_model(batch), now=self._now(cursor))
        except (CandidateContractError, ValidationError, ValueError):
            raise ExecutionRuntimeError('invalid_batch', 422) from None

    def _submission(self, cursor, claims, batch, *, signature=None, budget=True):
        tenant = self._active(cursor, claims)
        ex = batch.execution
        key = self._key(cursor, claims, tenant, ex.device_id, ex.credential_version)
        if signature is not None:
            self._signature(key, signature, submission_signing_payload(tenant_id=tenant, claims=claims, batch=batch))
        peek = self._peek_task(cursor, tenant, claims.user_id, ex.task_id)
        research_task = type(peek.get('configuration_snapshot', {}).get('configuration', {}).get('research')) is dict
        if research_task or self._research_row(cursor, tenant, claims.user_id, task_id=ex.task_id) is not None:
            raise ExecutionRuntimeError('capability_unavailable', 409)
        if peek['status'] in ('CANCELLING','CANCELED'): raise ExecutionRuntimeError('task_cancelled')
        if (peek['profile_version_id'], peek['strategy_version_id']) != (batch.profile_version_id, batch.strategy_version_id):
            raise ExecutionRuntimeError('execution_conflict')
        self._versions(cursor, claims, tenant, peek, ex.platform_run_id, ex.device_id)
        task, run, platforms = self._locks(cursor, claims, tenant, ex.task_id)
        if run['run_id'] != ex.run_id: raise ExecutionRuntimeError('execution_conflict')
        platform = next((p for p in platforms if p['platform_run_id'] == ex.platform_run_id), None)
        if platform is None: raise ExecutionRuntimeError('execution_conflict')
        if (platform['platform'],platform['access_mode'],platform['connection_id'],platform['connection_version']) != (
                batch.platform,ex.access_mode,ex.connection_id,ex.connection_version):
            raise ExecutionRuntimeError('execution_conflict')
        now, remaining = self._live(cursor, task, run, platforms, budget=budget)
        self._lease(platform, ex.credential_version, ex.lease_id, ex.execution_generation, now)
        if budget and len(batch.records) > remaining: raise ExecutionRuntimeError('budget_exhausted')
        from pilot.public_source_revisit import validate_public_revisit
        validate_public_revisit(cursor, tenant_id=tenant, owner_user_id=claims.user_id, batch=batch)
        self._active(cursor, claims)
        return dict(tenant_id=tenant, owner_user_id=claims.user_id, task_id=task['task_id'], run_id=run['run_id'],
            platform_run_id=platform['platform_run_id'], profile_version_id=task['profile_version_id'],
            strategy_version_id=task['strategy_version_id'], remaining_records=remaining,
            deadline_at=task['deadline_at'].isoformat(), execution_generation=platform['execution_generation'])

    def lock_submission(self, cursor, claims, *, batch: CandidateBatch, signature: str) -> dict:
        txid = self._transaction(cursor)
        if type(signature) is not str:
            raise ExecutionRuntimeError('invalid_proof', 400)
        batch = self._batch(cursor, batch)
        result = self._submission(cursor, claims, batch, signature=signature)
        self._submission_guards[cursor] = (txid, claims, batch.request_id, batch_fingerprint(batch))
        return result

    def recheck_submission_fence(self, cursor, claims, *, batch: CandidateBatch) -> None:
        txid = self._transaction(cursor)
        batch = self._batch(cursor, batch)
        if self._submission_guards.get(cursor) != (txid, claims, batch.request_id, batch_fingerprint(batch)):
            raise ExecutionRuntimeError('submission_guard_required', 400)
        self._submission(cursor, claims, batch, budget=False)

    def get_receipt(self, claims, request_id: str) -> dict:
        canonical_uuid(request_id)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            receipt = self._receipt(cursor, tenant, claims.user_id, request_id)
            self._active(cursor, claims)
            if receipt is None: raise ExecutionRuntimeError('request_not_found', 404)
            return receipt[1]

    def get_task(self, claims, task_id: str) -> dict:
        if type(task_id) is not str or not 1 <= len(task_id) <= 128:
            raise ExecutionRuntimeError('invalid_request', 422)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            # Locking makes this live multi-table view internally coherent.
            task, run, platforms = self._locks(cursor, claims, tenant, task_id)
            self._active(cursor, claims)
            return dict(task_id=task_id, run_id=run['run_id'], status=task['status'],
                stop_confirmed=task['status']=='SUCCEEDED' or (task['status']=='CANCELED' and
                    all(p['status'] in ('SUCCEEDED', 'CANCELED') for p in platforms)),
                profile_version_id=task['profile_version_id'], strategy_version_id=task['strategy_version_id'],
                max_records=task['max_records'], records_used=sum(p['records_used'] for p in platforms),
                deadline_at=task['deadline_at'].isoformat(), platform_runs=[{
                    key: p[key] for key in ('platform_run_id','platform','status','execution_generation','records_used')
                } for p in sorted(platforms, key=lambda p: p['target_order'])])

    _FEED_SQL = """
        SELECT t.task_id,t.device_id,t.profile_version_id,v.version AS profile_version,t.strategy_version_id,
               t.configuration_snapshot,t.created_at,t.deadline_at,t.status,t.max_records,
               r.run_id,o.request_id AS start_request_id,
               jsonb_agg(jsonb_build_object(
                   'platform_run_id',p.platform_run_id,'platform',p.platform,'status',p.status,
                   'execution_generation',p.execution_generation,'records_used',p.records_used
               ) ORDER BY p.target_order) AS platform_runs
          FROM pilot_collection_tasks t
          JOIN pilot_collection_runs r
            ON r.tenant_id=t.tenant_id AND r.owner_user_id=t.owner_user_id AND r.task_id=t.task_id
          JOIN business_profile_versions v
            ON v.tenant_id=t.tenant_id AND v.profile_version_id=t.profile_version_id
          JOIN pilot_execution_operations o
            ON o.tenant_id=t.tenant_id AND o.owner_user_id=t.owner_user_id
           AND o.task_id=t.task_id AND o.operation='START'
          JOIN pilot_collection_platform_runs p
            ON p.tenant_id=t.tenant_id AND p.owner_user_id=t.owner_user_id AND p.task_id=t.task_id
         WHERE t.tenant_id=%s AND t.owner_user_id=%s
    """

    @staticmethod
    def _feed_cursor(created_at, task_id):
        value = _json({'created_at': created_at.isoformat(), 'task_id': task_id}).encode()
        return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')

    @classmethod
    def _decode_feed_cursor(cls, value):
        try:
            if type(value) is not str or not 1 <= len(value) <= 1024:
                raise ValueError
            raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
            decoded = json.loads(raw)
            if type(decoded) is not dict or set(decoded) != {'created_at', 'task_id'}:
                raise ValueError
            created_at = datetime.fromisoformat(decoded['created_at'])
            if created_at.tzinfo is None:
                raise ValueError
            task_id = canonical_uuid(decoded['task_id'])
            if cls._feed_cursor(created_at, task_id) != value:
                raise ValueError
            return created_at, task_id
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, ExecutionRuntimeError):
            raise ExecutionRuntimeError('invalid_request', 422) from None

    @staticmethod
    def _feed_item(row):
        configuration = row['configuration_snapshot'].get('configuration', {})
        name = configuration.get('name') if type(configuration) is dict else None
        if type(name) is not str or not 1 <= len(name) <= 60:
            name = None
        mode = configuration.get('mode') if type(configuration) is dict else None
        if mode not in ('once', 'monitor'):
            mode = None
        platforms = row['platform_runs']
        return dict(
            task_id=row['task_id'], run_id=row['run_id'], device_id=row['device_id'],
            profile_version_id=row['profile_version_id'], profile_version=row['profile_version'],
            strategy_version_id=row['strategy_version_id'],
            start_request_id=row['start_request_id'], name=name, mode=mode,
            **({'research': True} if type(configuration.get('research')) is dict else {}),
            created_at=row['created_at'].isoformat(), deadline_at=row['deadline_at'].isoformat(),
            status=row['status'], max_records=row['max_records'],
            records_used=sum(item['records_used'] for item in platforms),
            stop_confirmed=row['status'] == 'SUCCEEDED' or (row['status'] == 'CANCELED' and
                all(item['status'] in ('SUCCEEDED', 'CANCELED') for item in platforms)),
            platform_runs=platforms,
        )

    def _read_feed(self, claims, *, task_id=None, limit=None, cursor=None):
        with self.database.connect() as connection, connection.cursor() as db_cursor:
            tenant = self._active(db_cursor, claims)
            parameters = [tenant, claims.user_id]
            sql = self._FEED_SQL
            if task_id is not None:
                sql += ' AND t.task_id=%s'
                parameters.append(task_id)
            elif cursor is not None:
                sql += ' AND (t.created_at,t.task_id)<(%s,%s)'
                parameters.extend(cursor)
            sql += (' GROUP BY t.tenant_id,t.owner_user_id,t.task_id,r.run_id,o.request_id,v.version '
                    'ORDER BY t.created_at DESC,t.task_id DESC')
            if limit is not None:
                sql += ' LIMIT %s'
                parameters.append(limit)
            db_cursor.execute(sql, parameters)
            rows = [dict(zip((column.name for column in db_cursor.description), row))
                    for row in db_cursor.fetchall()]
            self._active(db_cursor, claims)
            return [self._feed_item(row) for row in rows]

    def get_task_feed(self, claims, *, limit=20, cursor=None, query_fields=None):
        if query_fields is not None and not query_fields <= {'limit', 'cursor'}:
            raise ExecutionRuntimeError('invalid_request', 422)
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ExecutionRuntimeError('invalid_request', 422)
        decoded = self._decode_feed_cursor(cursor) if cursor is not None else None
        items = self._read_feed(claims, limit=limit + 1, cursor=decoded)
        more = len(items) > limit
        items = items[:limit]
        next_cursor = None
        if more:
            last = items[-1]
            next_cursor = self._feed_cursor(datetime.fromisoformat(last['created_at']), last['task_id'])
        return {'schema_version': 'execution-task-feed-v1', 'items': items, 'next_cursor': next_cursor}

    def get_task_feed_item(self, claims, task_id):
        canonical_uuid(task_id)
        items = self._read_feed(claims, task_id=task_id)
        if not items:
            raise ExecutionRuntimeError('task_not_found', 404)
        return items[0]
