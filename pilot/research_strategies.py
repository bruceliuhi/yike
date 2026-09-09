"""Durable private research intent and same-transaction execution validation.

No network, model, source approval, or execution dispatch. Historical receipts
remain historical; only resolve proves the current confirmed version under locks.
"""
from __future__ import annotations

from functools import wraps
import hashlib
import json
import re
import unicodedata
from uuid import UUID, uuid4

import psycopg
from pydantic import ValidationError

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.execution_contract import ExecutionRuntimeError
from pilot.execution_runtime import ConfirmedExecutionStrategy
from pilot.research_strategy_contract import (PrepareStrategyRequest, ConfirmStrategyRequest,
    RevokeStrategyRequest, StrategyStoreError, strategy_snapshot, configuration_digest)
from pilot.sessions import PilotSessionRegistry


_VERSION_FIELDS = ('strategy_version_id','draft_id','draft_revision','profile_version_id','profile_sha256',
                   'configuration_sha256','snapshot','state','created_at','confirmed_at','revoked_at')


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _safe_database_errors(method):
    @wraps(method)
    def wrapped(*args,**kwargs):
        try:
            return method(*args,**kwargs)
        except psycopg.Error:
            pass
        # Outside the transaction context and exception handler: no original SQL/DSN chain.
        raise StrategyStoreError('strategy_store_unavailable',503)
    return wrapped


def _request(model,value):
    try:
        # Contract validates raw instance fields before serializers can coerce them.
        return model.model_validate(value)
    except (ValidationError,ValueError,TypeError,UnicodeError,RecursionError):
        pass
    raise StrategyStoreError('invalid_request',422)


def _uuid(value):
    try:
        if type(value) is str and len(value)==36 and str(UUID(value))==value:
            return value
    except (ValueError,TypeError):
        pass
    raise StrategyStoreError('invalid_request',422)


class ResearchStrategyStore:
    def __init__(self,database):
        self.database=database
        self.sessions=PilotSessionRegistry(database)

    def _active(self,cursor,claims):
        if (not isinstance(claims,TokenClaims) or type(claims.user_id) is not str
                or not 1<=len(claims.user_id)<=256 or claims.user_id.strip()!=claims.user_id
                or any(unicodedata.category(ch)[0]=='C' for ch in claims.user_id)
                or type(claims.revocation_key) is not str or not re.fullmatch('[0-9a-f]{64}',claims.revocation_key)
                or type(claims.expires_at) is not int or not 0<claims.expires_at<=253402300799):
            raise StrategyStoreError('invalid_session',401)
        try:
            return self.sessions.require_active(cursor,claims)
        except (InvalidPilotToken,PermissionError):
            pass
        raise StrategyStoreError('invalid_session',401)

    @staticmethod
    def _version(cursor,tenant,user,version,*,lock=False):
        cursor.execute('SELECT '+','.join(_VERSION_FIELDS)+' FROM pilot_research_strategy_versions '
            'WHERE tenant_id=%s AND owner_user_id=%s AND strategy_version_id=%s'+(' FOR UPDATE' if lock else ''),
            (tenant,user,version))
        row=cursor.fetchone()
        return dict(zip(_VERSION_FIELDS,row)) if row else None

    def _profile(self,cursor,claims,tenant,version):
        cursor.execute('SELECT profile_id FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s',
                       (tenant,version))
        row=cursor.fetchone()
        if row is None:
            return None
        cursor.execute('SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE',(tenant,row[0]))
        parent=cursor.fetchone()
        self._active(cursor,claims)
        if parent is None:
            return None
        cursor.execute('SELECT payload,content_sha256,status FROM business_profile_versions '
            'WHERE tenant_id=%s AND profile_id=%s AND profile_version_id=%s FOR UPDATE',(tenant,parent[0],version))
        row=cursor.fetchone()
        self._active(cursor,claims)
        if row is None:
            return None
        valid=False
        try:
            valid=type(row[0]) is dict and _digest(row[0])==row[1] and row[2]=='CONFIRMED'
        except (ValueError,TypeError,UnicodeError,RecursionError):
            pass
        return {'sha256':row[1],'valid':valid}

    def _draft(self,cursor,claims,tenant,draft_id):
        cursor.execute('SELECT current_revision,current_version_id FROM pilot_research_strategy_drafts '
            'WHERE tenant_id=%s AND owner_user_id=%s AND draft_id=%s FOR UPDATE',(tenant,claims.user_id,draft_id))
        row=cursor.fetchone()
        self._active(cursor,claims)
        return row

    def _locked_version(self,cursor,claims,tenant,version_id):
        # The first read only locates lock targets; it never authorizes mutation.
        peek=self._version(cursor,tenant,claims.user_id,version_id)
        if peek is None:
            self._active(cursor,claims)
            raise StrategyStoreError('strategy_not_found',404)
        profile=self._profile(cursor,claims,tenant,peek['profile_version_id'])
        draft=self._draft(cursor,claims,tenant,peek['draft_id'])
        row=self._version(cursor,tenant,claims.user_id,version_id,lock=True)
        self._active(cursor,claims)
        if row is None:
            raise StrategyStoreError('strategy_not_found',404)
        return row,profile,draft

    @staticmethod
    def _intact(row):
        try:
            snapshot=row['snapshot']
            return (configuration_digest(snapshot)==row['configuration_sha256']
                and snapshot['profile_version_id']==row['profile_version_id']
                and snapshot['strategy_version_id']==row['strategy_version_id'])
        except (StrategyStoreError,KeyError,ValueError,TypeError,UnicodeError,RecursionError):
            return False

    @staticmethod
    def _current(row,draft):
        return bool(draft and draft==(row['draft_revision'],row['strategy_version_id']))

    @staticmethod
    def _profile_current(row,profile):
        return bool(profile and profile['valid'] and profile['sha256']==row['profile_sha256'])

    def _operation(self,cursor,claims,request,operation):
        tenant=self._active(cursor,claims)
        key=(tenant+'\0'+claims.user_id+'\0'+request.request_id).encode('utf-8')
        lock=int.from_bytes(hashlib.sha256(key).digest()[:4],'big',signed=True)
        cursor.execute('SELECT pg_advisory_xact_lock(11401,%s)',(lock,))
        self._active(cursor,claims)
        fingerprint=_digest(request.model_dump(mode='json'))
        cursor.execute('SELECT operation,request_sha256,receipt FROM pilot_research_strategy_operations '
            'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',(tenant,claims.user_id,request.request_id))
        row=cursor.fetchone()
        self._active(cursor,claims)
        if row and (row[0]!=operation or row[1]!=fingerprint):
            raise StrategyStoreError('request_conflict')
        return tenant,fingerprint,row[2] if row else None

    def _record(self,cursor,claims,tenant,request,operation,fingerprint,row):
        cursor.execute('SELECT clock_timestamp()')
        recorded=cursor.fetchone()[0]
        receipt={name:row[name] for name in _VERSION_FIELDS if name not in ('created_at','confirmed_at','revoked_at')}
        receipt.update(schema_version='strategy-confirmation-v1',request_id=request.request_id,
                       operation=operation,recorded_at=recorded.isoformat())
        self._active(cursor,claims)
        cursor.execute('INSERT INTO pilot_research_strategy_operations(tenant_id,owner_user_id,request_id,operation,'
            'request_sha256,strategy_version_id,receipt,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s)',
            (tenant,claims.user_id,request.request_id,operation,fingerprint,row['strategy_version_id'],_json(receipt),recorded))
        self._active(cursor,claims)
        return receipt

    @_safe_database_errors
    def prepare(self,claims,request):
        request=_request(PrepareStrategyRequest,request)
        with self.database.connect() as connection,connection.cursor() as cursor:
            tenant,fingerprint,previous=self._operation(cursor,claims,request,'PREPARE')
            if previous is not None:
                return previous
            profile=self._profile(cursor,claims,tenant,request.profile_version_id)
            self._active(cursor,claims)
            if not profile or not profile['valid']:
                raise StrategyStoreError('profile_unavailable')
            version_id=str(uuid4())
            snapshot=strategy_snapshot(request.profile_version_id,version_id,request.configuration,
                request.platforms,request.max_records,request.max_runtime_seconds)
            cursor.execute('INSERT INTO pilot_research_strategy_drafts(tenant_id,owner_user_id,draft_id,current_revision,current_version_id) '
                'VALUES (%s,%s,%s,%s,%s) ON CONFLICT (tenant_id,owner_user_id,draft_id) DO NOTHING RETURNING draft_id',
                (tenant,claims.user_id,request.draft_id,request.draft_revision,version_id))
            inserted=cursor.fetchone() is not None
            self._active(cursor,claims)
            draft=self._draft(cursor,claims,tenant,request.draft_id)
            if not inserted and draft[0]>=request.draft_revision:
                if draft[0]>request.draft_revision:
                    raise StrategyStoreError('draft_conflict')
                row=self._version(cursor,tenant,claims.user_id,draft[1],lock=True)
                self._active(cursor,claims)
                comparison=snapshot | {'strategy_version_id':draft[1]}
                if (row is None or row['profile_sha256']!=profile['sha256'] or _json(row['snapshot'])!=_json(comparison)
                        or not self._intact(row)):
                    raise StrategyStoreError('draft_conflict')
            else:
                cursor.execute('INSERT INTO pilot_research_strategy_versions(tenant_id,owner_user_id,strategy_version_id,draft_id,draft_revision,'
                    'profile_version_id,profile_sha256,snapshot,configuration_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)',
                    (tenant,claims.user_id,version_id,request.draft_id,request.draft_revision,request.profile_version_id,
                     profile['sha256'],_json(snapshot),configuration_digest(snapshot)))
                if not inserted:
                    cursor.execute('UPDATE pilot_research_strategy_drafts SET current_revision=%s,current_version_id=%s '
                        'WHERE tenant_id=%s AND owner_user_id=%s AND draft_id=%s',
                        (request.draft_revision,version_id,tenant,claims.user_id,request.draft_id))
                row=self._version(cursor,tenant,claims.user_id,version_id)
            return self._record(cursor,claims,tenant,request,'PREPARE',fingerprint,row)

    @_safe_database_errors
    def confirm(self,claims,request):
        request=_request(ConfirmStrategyRequest,request)
        with self.database.connect() as connection,connection.cursor() as cursor:
            tenant,fingerprint,previous=self._operation(cursor,claims,request,'CONFIRM')
            if previous is not None:
                return previous
            row,profile,draft=self._locked_version(cursor,claims,tenant,request.strategy_version_id)
            if (not self._current(row,draft) or row['state'] not in ('DRAFT','CONFIRMED')
                    or request.configuration_sha256!=row['configuration_sha256'] or not self._intact(row)):
                raise StrategyStoreError('strategy_conflict')
            if not self._profile_current(row,profile):
                raise StrategyStoreError('profile_unavailable')
            if row['state']=='DRAFT':
                cursor.execute("UPDATE pilot_research_strategy_versions SET state='CONFIRMED' "
                    'WHERE tenant_id=%s AND owner_user_id=%s AND strategy_version_id=%s',
                    (tenant,claims.user_id,request.strategy_version_id))
                row=self._version(cursor,tenant,claims.user_id,request.strategy_version_id)
            return self._record(cursor,claims,tenant,request,'CONFIRM',fingerprint,row)

    @_safe_database_errors
    def revoke(self,claims,request):
        request=_request(RevokeStrategyRequest,request)
        with self.database.connect() as connection,connection.cursor() as cursor:
            tenant,fingerprint,previous=self._operation(cursor,claims,request,'REVOKE')
            if previous is not None:
                return previous
            row,_,_=self._locked_version(cursor,claims,tenant,request.strategy_version_id)
            if row['state']!='REVOKED':
                cursor.execute("UPDATE pilot_research_strategy_versions SET state='REVOKED' "
                    'WHERE tenant_id=%s AND owner_user_id=%s AND strategy_version_id=%s',
                    (tenant,claims.user_id,request.strategy_version_id))
                row=self._version(cursor,tenant,claims.user_id,request.strategy_version_id)
            return self._record(cursor,claims,tenant,request,'REVOKE',fingerprint,row)

    @_safe_database_errors
    def get_receipt(self,claims,request_id):
        _uuid(request_id)
        with self.database.connect() as connection,connection.cursor() as cursor:
            tenant=self._active(cursor,claims)
            cursor.execute('SELECT receipt FROM pilot_research_strategy_operations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
                           (tenant,claims.user_id,request_id))
            row=cursor.fetchone()
            self._active(cursor,claims)
            if row is None:
                raise StrategyStoreError('request_not_found',404)
            return row[0]

    @_safe_database_errors
    def get_strategy(self,claims,strategy_version_id):
        _uuid(strategy_version_id)
        with self.database.connect() as connection,connection.cursor() as cursor:
            tenant=self._active(cursor,claims)
            row,profile,draft=self._locked_version(cursor,claims,tenant,strategy_version_id)
            result=dict(row)
            for key in ('created_at','confirmed_at','revoked_at'):
                result[key]=result[key].isoformat() if result[key] is not None else None
            result.update(schema_version='strategy-confirmation-v1',is_current=self._current(row,draft),
                          profile_current=self._profile_current(row,profile))
            self._active(cursor,claims)
            return result

    def resolve(self,cursor,claims,profile_version_id,strategy_version_id):
        """Reuse the caller transaction; profile -> draft -> version, no request/device/task lock."""
        error_code,error_status='strategy_conflict',409
        try:
            if cursor.connection.autocommit:
                raise StrategyStoreError('strategy_conflict')
            tenant=self._active(cursor,claims)
            _uuid(profile_version_id)
            _uuid(strategy_version_id)
            # The caller may already hold its supplied profile lock. Never
            # follow a mismatched binding to another profile in reverse order.
            peek=self._version(cursor,tenant,claims.user_id,strategy_version_id)
            self._active(cursor,claims)
            if peek is None or peek['profile_version_id']!=profile_version_id:
                raise StrategyStoreError('strategy_conflict')
            row,profile,draft=self._locked_version(cursor,claims,tenant,strategy_version_id)
            if (row['profile_version_id']!=profile_version_id or row['state']!='CONFIRMED'
                    or not self._current(row,draft) or not self._profile_current(row,profile) or not self._intact(row)):
                raise StrategyStoreError('strategy_conflict')
            self._active(cursor,claims)
            snapshot=row['snapshot']
            return ConfirmedExecutionStrategy(**(snapshot | {'platforms':tuple(snapshot['platforms']),
                'configuration_sha256':row['configuration_sha256']}))
        except StrategyStoreError as error:
            if error.code=='invalid_session':
                error_code,error_status='invalid_session',401
        except psycopg.Error:
            error_code,error_status='strategy_store_unavailable',503
        raise ExecutionRuntimeError(error_code,error_status)
