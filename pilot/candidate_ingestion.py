"""Atomic signed raw ingestion. Claimed observation time is not platform truth."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from uuid import UUID, uuid4

from pilot.auth import InvalidPilotToken
from pilot.candidate_contract import batch_fingerprint, content_version, source_identity, validate_candidate_batch
from pilot.sessions import PilotSessionRegistry


class CandidateIngestionError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def _row(cursor):
    value = cursor.fetchone()
    return dict(zip((c.name for c in cursor.description), value)) if value else None


def _primitive(value):
    if isinstance(value, (UUID, datetime)): return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, dict): return {key: _primitive(item) for key, item in value.items()}
    if isinstance(value, list): return [_primitive(item) for item in value]
    return value


def _id(value, *, opaque=False):
    valid = type(value) is str and (bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value)) if opaque
        else bool(re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', value)))
    if not valid: raise CandidateIngestionError('invalid_request', 422)


class CandidateIngestionStore:
    def __init__(self, database, execution_runtime=None):
        self.database, self.execution_runtime = database, execution_runtime
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise CandidateIngestionError('invalid_session', 401) from None

    @staticmethod
    def _receipt(cursor, tenant, user, platform_run_id, request_id):
        cursor.execute('SELECT fingerprint,receipt FROM pilot_candidate_batches WHERE tenant_id=%s '
            'AND owner_user_id=%s AND platform_run_id=%s AND request_id=%s', (tenant,user,platform_run_id,request_id))
        return cursor.fetchone()

    def ingest(self, claims, payload: dict, signature: str) -> dict:
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute('SELECT clock_timestamp()')
            batch = validate_candidate_batch(payload, now=cursor.fetchone()[0])
            fingerprint = batch_fingerprint(batch)
            ex = batch.execution
            lock = int.from_bytes(hashlib.sha256(_json([tenant,ex.platform_run_id,batch.request_id]).encode()).digest()[:4], 'big', signed=True)
            cursor.execute('SELECT pg_advisory_xact_lock(11201,%s)', (lock,))
            self._active(cursor, claims)
            previous = self._receipt(cursor,tenant,claims.user_id,ex.platform_run_id,batch.request_id)
            if previous:
                if previous[0] != fingerprint: raise CandidateIngestionError('request_conflict',409)
                self._active(cursor, claims)
                return previous[1]
            if self.execution_runtime is None: raise CandidateIngestionError('capability_unavailable',501)
            authority = self.execution_runtime.lock_submission(cursor,claims,batch=batch,signature=signature)
            cursor.execute('SELECT clock_timestamp()')
            received = cursor.fetchone()[0]
            items = []
            for index, record in sorted(enumerate(batch.records), key=lambda item: source_identity(item[1],batch.platform)):
                identity = source_identity(record,batch.platform)
                source_lock = int.from_bytes(hashlib.sha256(_json([tenant,claims.user_id,identity]).encode()).digest()[:4], 'big', signed=True)
                cursor.execute('SELECT pg_advisory_xact_lock(11202,%s)', (source_lock,))
                cursor.execute('SELECT source_id FROM pilot_candidate_sources WHERE tenant_id=%s AND owner_user_id=%s AND source_identity=%s', (tenant,claims.user_id,identity))
                source = cursor.fetchone()
                source_id = str(source[0]) if source else str(uuid4())
                if source is None:
                    cursor.execute('INSERT INTO pilot_candidate_sources(tenant_id,owner_user_id,source_id,source_identity,platform,kind,external_source_id,external_comment_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                        (tenant,claims.user_id,source_id,identity,batch.platform,record.kind,record.external_source_id,record.external_comment_id))
                digest = content_version(record)
                cursor.execute('SELECT version_id FROM pilot_candidate_versions WHERE tenant_id=%s AND owner_user_id=%s AND source_id=%s AND content_version=%s', (tenant,claims.user_id,source_id,digest))
                version = cursor.fetchone()
                version_id = str(version[0]) if version else str(uuid4())
                if version is None:
                    content = record.model_dump(mode='json', include={'public_url','title','author_public_id','body','published_at','parent'})
                    cursor.execute('INSERT INTO pilot_candidate_versions(tenant_id,owner_user_id,source_id,version_id,content_version,content,received_at) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)',
                        (tenant,claims.user_id,source_id,version_id,digest,_json(content),received))
                scope = (tenant,claims.user_id,batch.profile_version_id,batch.strategy_version_id,source_id)
                cursor.execute('SELECT * FROM pilot_candidate_projections WHERE tenant_id=%s AND owner_user_id=%s AND profile_version_id=%s AND strategy_version_id=%s AND source_id=%s FOR UPDATE', scope)
                candidate = _row(cursor)
                observation_id = str(uuid4())
                observed = datetime.fromisoformat(record.observed_at.replace('Z','+00:00'))
                if candidate is None:
                    candidate_id, revision = str(uuid4()), 1
                    cursor.execute('INSERT INTO pilot_candidate_projections(tenant_id,owner_user_id,profile_version_id,strategy_version_id,source_id,candidate_id,version_id,current_observation_id,revision,latest_observed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                        (*scope,candidate_id,version_id,observation_id,revision,observed))
                else:
                    candidate_id, revision = str(candidate['candidate_id']),candidate['revision']
                    different = str(candidate['version_id']) != version_id
                    if observed > candidate['latest_observed_at']:
                        revision += int(different or candidate['ambiguous'])
                        cursor.execute('UPDATE pilot_candidate_projections SET version_id=%s,current_observation_id=%s,revision=%s,latest_observed_at=%s,ambiguous=false WHERE tenant_id=%s AND owner_user_id=%s AND candidate_id=%s',
                            (version_id,observation_id,revision,observed,tenant,claims.user_id,candidate_id))
                    elif observed == candidate['latest_observed_at'] and different and not candidate['ambiguous']:
                        revision += 1
                        cursor.execute('UPDATE pilot_candidate_projections SET ambiguous=true,revision=%s WHERE tenant_id=%s AND owner_user_id=%s AND candidate_id=%s', (revision,tenant,claims.user_id,candidate_id))
                cursor.execute('INSERT INTO pilot_candidate_observations(tenant_id,owner_user_id,observation_id,candidate_id,source_id,version_id,platform_run_id,request_id,record_index,observed_at,received_at,query,collector_version,normalizer_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                    (tenant,claims.user_id,observation_id,candidate_id,source_id,version_id,ex.platform_run_id,batch.request_id,index,observed,received,record.query,record.collector_version,record.normalizer_version))
                items.append(dict(index=index,candidate_id=candidate_id,version_id=version_id,observation_id=observation_id,revision=revision))
            receipt = dict(schema_version='candidate-receipt-v1',request_id=batch.request_id,
                platform_run_id=authority['platform_run_id'],task_id=authority['task_id'],run_id=authority['run_id'],
                accepted_count=len(batch.records),received_at=received.isoformat(),items=sorted(items,key=lambda item:item['index']))
            cursor.execute('UPDATE pilot_collection_platform_runs SET records_used=records_used+%s WHERE tenant_id=%s AND owner_user_id=%s AND task_id=%s AND run_id=%s AND platform_run_id=%s',
                (len(batch.records),tenant,claims.user_id,authority['task_id'],authority['run_id'],authority['platform_run_id']))
            cursor.execute('INSERT INTO pilot_candidate_batches(tenant_id,owner_user_id,platform_run_id,request_id,task_id,run_id,fingerprint,accepted_count,received_at,receipt,platform,profile_version_id,strategy_version_id,execution_context) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb)',
                (tenant,claims.user_id,ex.platform_run_id,batch.request_id,authority['task_id'],authority['run_id'],fingerprint,len(batch.records),received,_json(receipt),batch.platform,batch.profile_version_id,batch.strategy_version_id,_json(ex.model_dump(mode='json'))))
            self.execution_runtime.recheck_submission_fence(cursor,claims,batch=batch)
            return receipt

    def get_receipt(self, claims, platform_run_id: str, request_id: str) -> dict:
        _id(platform_run_id); _id(request_id,opaque=True)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor,claims)
            receipt = self._receipt(cursor,tenant,claims.user_id,platform_run_id,request_id)
            self._active(cursor,claims)
            if receipt is None: raise CandidateIngestionError('request_not_found',404)
            return receipt[1]

    _projection_sql = '''SELECT p.candidate_id,s.platform,s.kind,s.external_source_id,s.external_comment_id,
        p.profile_version_id,p.strategy_version_id,s.source_identity,p.revision,p.ambiguous,p.latest_observed_at,
        p.current_observation_id,v.version_id,v.content_version,v.content
        FROM pilot_candidate_projections p JOIN pilot_candidate_sources s USING(tenant_id,owner_user_id,source_id)
        JOIN pilot_candidate_versions v USING(tenant_id,owner_user_id,source_id,version_id)'''

    @staticmethod
    def _projection(row):
        row = _primitive(row)
        row['current_version'] = row.pop('content') | {'version_id':row.pop('version_id'),'content_version':row.pop('content_version')}
        row['status'] = 'UNVERIFIED'
        return row

    def list_candidates(self, claims, *, task_id=None, platform=None, page=1, page_size=20) -> dict:
        if type(page) is not int or page<1 or type(page_size) is not int or not 1<=page_size<=100:
            raise CandidateIngestionError('invalid_request',422)
        if task_id is not None: _id(task_id)
        if platform is not None and platform not in ('XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB'):
            raise CandidateIngestionError('invalid_request',422)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor,claims)
            where = ' WHERE p.tenant_id=%s AND p.owner_user_id=%s'
            params = [tenant,claims.user_id]
            if platform is not None:
                where += ' AND s.platform=%s'; params.append(platform)
            if task_id is not None:
                where += ''' AND EXISTS(SELECT 1 FROM pilot_candidate_observations o JOIN pilot_candidate_batches b
                    USING(tenant_id,owner_user_id,platform_run_id,request_id) WHERE o.tenant_id=p.tenant_id
                    AND o.owner_user_id=p.owner_user_id AND o.candidate_id=p.candidate_id AND b.task_id=%s)'''
                params.append(task_id)
            # One statement snapshot for count and page, including empty pages.
            # Materialize IDs only; never load every full content body to count.
            cursor.execute('''WITH matching AS MATERIALIZED (
                SELECT p.candidate_id,p.latest_observed_at FROM pilot_candidate_projections p
                JOIN pilot_candidate_sources s USING(tenant_id,owner_user_id,source_id)'''+where+'''),
                selected AS (SELECT candidate_id FROM matching ORDER BY latest_observed_at DESC,candidate_id LIMIT %s OFFSET %s),
                page_values AS ('''+self._projection_sql+''' JOIN selected picked ON picked.candidate_id=p.candidate_id
                    WHERE p.tenant_id=%s AND p.owner_user_id=%s)
                SELECT (SELECT count(*) FROM matching),
                    COALESCE((SELECT jsonb_agg(to_jsonb(page_values) ORDER BY latest_observed_at DESC,candidate_id)
                        FROM page_values),'[]'::jsonb)''',
                (*params,page_size,(page-1)*page_size,tenant,claims.user_id))
            total, rows = cursor.fetchone()
            items = [self._projection(row) for row in rows]
            self._active(cursor,claims)
            return dict(schema_version='candidate-inbox-v1',items=items,page=page,page_size=page_size,total=total)

    def get_candidate(self, claims, candidate_id: str) -> dict:
        _id(candidate_id)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor,claims)
            params = (tenant,claims.user_id,candidate_id)
            # Projection, narrow count and bounded history share one MVCC snapshot.
            # Session checks stay separate/live; no repeatable-read session snapshot.
            cursor.execute('WITH candidate AS ('+self._projection_sql+''' WHERE p.tenant_id=%s AND p.owner_user_id=%s AND p.candidate_id=%s),
                total AS (SELECT count(*) AS count FROM pilot_candidate_observations
                    WHERE tenant_id=%s AND owner_user_id=%s AND candidate_id=%s),
                history AS (SELECT o.observation_id,o.version_id,o.platform_run_id,o.request_id,o.record_index,
                o.observed_at,o.received_at,o.query,o.collector_version,o.normalizer_version,b.task_id,b.run_id,
                b.execution_context,b.platform,b.profile_version_id,b.strategy_version_id,
                v.content_version,v.content FROM pilot_candidate_observations o JOIN pilot_candidate_batches b
                USING(tenant_id,owner_user_id,platform_run_id,request_id) JOIN pilot_candidate_versions v
                USING(tenant_id,owner_user_id,source_id,version_id) WHERE o.tenant_id=%s AND o.owner_user_id=%s
                AND o.candidate_id=%s ORDER BY o.observed_at DESC,o.received_at DESC,o.observation_id LIMIT 100)
                SELECT (SELECT to_jsonb(candidate) FROM candidate),(SELECT count FROM total),
                    COALESCE((SELECT jsonb_agg(to_jsonb(history) ORDER BY observed_at DESC,received_at DESC,observation_id)
                        FROM history),'[]'::jsonb)''',params*3)
            row, total, observations = cursor.fetchone()
            self._active(cursor,claims)
            if row is None: raise CandidateIngestionError('candidate_not_found',404)
            candidate = self._projection(row)
            return dict(schema_version='candidate-inbox-v1',candidate=candidate,
                observations=dict(items=observations,total=total,truncated=total>100,page_size=100))
