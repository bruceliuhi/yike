"""Owner-private assessment and human review; no provider call holds a DB transaction."""
from dataclasses import asdict
from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
from uuid import uuid4
from psycopg.errors import SerializationFailure

from pilot.candidate_ingestion import CandidateIngestionError, CandidateIngestionStore, _json, _row, _primitive, _id
from pilot.candidate_assessment_model import AssessmentModelError, validate_assessment, validate_assessment_input
from pilot.candidate_review_contract import CandidateReviewError, binding, validate_payload
from pilot.execution_runtime import ConfirmedExecutionStrategy
from pilot.execution_contract import ExecutionRuntimeError
from pilot.opportunity_evidence import build_evidence, canonical_json, evidence_digest
from pilot.store import PilotStore


def _hash(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _lock(cursor, namespace, value):
    key = int.from_bytes(hashlib.sha256(_json(value).encode()).digest()[:4], 'big', signed=True)
    cursor.execute('SELECT pg_advisory_xact_lock(%s,%s)', (namespace,key))


def _now(cursor):
    cursor.execute('SELECT clock_timestamp()')
    return cursor.fetchone()[0]


def _strategy_error(error):
    if error.status==401:
        return CandidateReviewError('invalid_session',401)
    if error.status>=500:
        return CandidateReviewError('strategy_store_unavailable',503)
    return CandidateReviewError('strategy_conflict',409)


class CandidateReviewStore(CandidateIngestionStore):
    def __init__(self, database, *, model=None, strategy_resolver=None,
                 strategy_snapshot_reader=None, max_daily_calls=20):
        super().__init__(database)
        if type(max_daily_calls) is not int or not 1 <= max_daily_calls <= 10000:
            raise ValueError('invalid assessment quota')
        self.model, self.strategy_resolver = model, strategy_resolver
        self.strategy_snapshot_reader = strategy_snapshot_reader
        self.max_daily_calls = max_daily_calls

    def _request(self, cursor, tenant, user, request_id):
        cursor.execute('SELECT * FROM pilot_candidate_review_requests WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s', (tenant,user,request_id))
        return _row(cursor)

    def _result(self, cursor, row):
        # Aliases always point to an invocation, never another alias.
        original = self._request(cursor,row['tenant_id'],row['owner_user_id'],row['invocation_id']) if row['invocation_id'] else row
        result = original['result']
        if original['status']=='PROCESSING' and _now(cursor)>=original['deadline_at']:
            result = dict(kind='pending', requestId=original['request_id'], candidateId=str(original['candidate_id']),status='UNKNOWN')
        if row['invocation_id']:
            result = result | {'requestId':row['request_id'], 'invocationRequestId':original['request_id']}
        return result

    def get_request(self, claims, request_id):
        _id(request_id,opaque=True)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor,claims)
            row = self._request(cursor,tenant,claims.user_id,request_id)
            if row is None: raise CandidateReviewError('request_not_found',404)
            result = self._result(cursor,row)
            self._active(cursor,claims)
            return result

    def _replay(self, cursor, tenant, claims, request, payload):
        _lock(cursor,11301,[tenant,claims.user_id,request.requestId])
        # Waiting for another attempt must not let an expired session replay data.
        self._active(cursor,claims)
        previous = self._request(cursor,tenant,claims.user_id,request.requestId)
        if previous:
            if previous['fingerprint'] != _hash(payload): raise CandidateReviewError('request_conflict',409)
            result = self._result(cursor,previous)
            self._active(cursor,claims)
            return result

    def _capture(self, cursor, tenant, claims, request, *, require_strategy=True):
        cursor.execute('SELECT profile_id FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s', (tenant,request.profileId))
        parent = cursor.fetchone()
        if not parent: raise CandidateReviewError('profile_unavailable',409)
        cursor.execute('SELECT profile_id FROM business_profiles WHERE tenant_id=%s AND profile_id=%s FOR UPDATE', (tenant,parent[0]))
        cursor.execute('SELECT version,status,payload FROM business_profile_versions WHERE tenant_id=%s AND profile_version_id=%s FOR UPDATE', (tenant,request.profileId))
        version, status, profile = cursor.fetchone()
        if status!='CONFIRMED' or version!=request.profileVersion: raise CandidateReviewError('profile_conflict',409)
        # Read immutable candidate scope before the resolver, lock raw only after it.
        cursor.execute('SELECT strategy_version_id FROM pilot_candidate_projections WHERE tenant_id=%s AND owner_user_id=%s AND candidate_id=%s', (tenant,claims.user_id,request.candidateId))
        scope = cursor.fetchone()
        if not scope: raise CandidateReviewError('candidate_not_found',404)
        strategy = None
        if require_strategy:
            if self.strategy_resolver is None: raise CandidateReviewError('capability_unavailable',501)
            try:
                strategy = self.strategy_resolver(cursor,claims,request.profileId,scope[0])
            except ExecutionRuntimeError as error:
                raise _strategy_error(error) from None
            if not isinstance(strategy,ConfirmedExecutionStrategy): raise CandidateReviewError('strategy_conflict',409)
        cursor.execute(self._projection_sql+' WHERE p.tenant_id=%s AND p.owner_user_id=%s AND p.candidate_id=%s FOR UPDATE OF p', (tenant,claims.user_id,request.candidateId))
        raw = _primitive(_row(cursor))
        current = dict(candidateId=raw['candidate_id'],candidateRevision=raw['revision'],sourceVersionId=raw['version_id'],profileId=raw['profile_version_id'],profileVersion=version)
        if binding(request)!=current or raw['ambiguous']: raise CandidateReviewError('candidate_conflict',409)
        cursor.execute('''SELECT t.configuration_sha256,t.configuration_snapshot FROM pilot_candidate_observations o
            JOIN pilot_candidate_batches b USING(tenant_id,owner_user_id,platform_run_id,request_id)
            JOIN pilot_collection_tasks t USING(tenant_id,owner_user_id,task_id)
            WHERE o.tenant_id=%s AND o.owner_user_id=%s AND o.observation_id=%s''', (tenant,claims.user_id,raw['current_observation_id']))
        stored_hash, stored_strategy = cursor.fetchone()
        if strategy is not None:
            snapshot = asdict(strategy)
            declared_hash = snapshot.pop('configuration_sha256')
            snapshot['platforms'] = list(snapshot['platforms'])
            if (snapshot!=stored_strategy or _hash(snapshot)!=stored_hash or declared_hash!=stored_hash
                    or snapshot['profile_version_id']!=request.profileId or snapshot['strategy_version_id']!=scope[0]
                    or raw['platform'] not in snapshot['platforms']):
                raise CandidateReviewError('strategy_conflict',409)
        body = raw['content']
        content = dict(title=body['title'],body=body['body'],parent=None)
        if body.get('parent'):
            content['parent'] = dict(title=None,body=body['parent'].get('body'))
        if raw['kind']=='COMMENT':
            content['title'] = None
            content['parent'] = dict(title=body['title'],body=(body.get('parent') or {}).get('body'))
        self._active(cursor,claims)
        return dict(binding=current, raw=raw, description=profile.get('description'), content=content,
                    strategy=stored_strategy, strategyHash=stored_hash)

    def _insert_request(self, cursor, tenant, claims, request, payload, snapshot, result, *, action,
                        status='SUCCEEDED', snapshot_key=None, invocation_id=None, attempt=0, now=None):
        now = now or _now(cursor)
        cursor.execute('''INSERT INTO pilot_candidate_review_requests(tenant_id,owner_user_id,request_id,candidate_id,
            fingerprint,action,binding_hash,snapshot_key,invocation_id,attempt,status,created_at,deadline_at,payload,snapshot,result)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)''',
            (tenant,claims.user_id,request.requestId,request.candidateId,_hash(payload),action,_hash(snapshot['binding']),
             snapshot_key,invocation_id,attempt,status,now,now+timedelta(seconds=90) if attempt else None,
             _json(payload),_json(snapshot),_json(result)))

    def review(self, claims, payload):
        request = validate_payload(payload)
        if request.action=='ASSESS': return self._assess(claims,request,payload)
        return self._decide(claims,request,payload)

    def _assess(self, claims, request, payload):
        model = self.model
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor,claims)
            previous = self._replay(cursor,tenant,claims,request,payload)
            if previous is not None: return previous
            if model is None: raise CandidateReviewError('capability_unavailable',501)
            snapshot = self._capture(cursor,tenant,claims,request)
            try:
                validate_assessment_input(description=snapshot['description'],content=snapshot['content'])
                metadata = {name:getattr(model,name) for name in ('provider','model','rule_version','rule_sha256')}
                if any(type(value) is not str or not value or len(value)>200 for value in metadata.values()): raise ValueError
            except (AssessmentModelError,AttributeError,ValueError):
                raise CandidateReviewError('assessment_unavailable',503) from None
            snapshot['model'] = metadata
            # Same-content observations do not change the snapshot cache key.
            snapshot_key = _hash({key:snapshot[key] for key in ('binding','description','content','strategy','model')})
            _lock(cursor,11302,[tenant,claims.user_id,snapshot_key])
            cursor.execute('''SELECT * FROM pilot_candidate_review_requests WHERE tenant_id=%s AND owner_user_id=%s
                AND snapshot_key=%s AND attempt>0 ORDER BY attempt DESC LIMIT 1''', (tenant,claims.user_id,snapshot_key))
            latest = _row(cursor)
            attempt = 1
            if latest:
                state = latest['status']
                if state=='PROCESSING' and _now(cursor)>=latest['deadline_at']:
                    state='UNKNOWN'
                    unknown = dict(kind='pending',requestId=latest['request_id'],candidateId=request.candidateId,status='UNKNOWN')
                    cursor.execute("UPDATE pilot_candidate_review_requests SET status='UNKNOWN',result=%s::jsonb WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s", (_json(unknown),tenant,claims.user_id,latest['request_id']))
                    latest['status'],latest['result']='UNKNOWN',unknown
                if state in ('SUCCEEDED','PROCESSING'):
                    if request.retryOf is not None: raise CandidateReviewError('retry_conflict',409)
                    result = self._result(cursor,latest) | dict(requestId=request.requestId,invocationRequestId=latest['request_id'])
                    self._insert_request(cursor,tenant,claims,request,payload,snapshot,result,action='ASSESS',status=state,
                                         snapshot_key=snapshot_key,invocation_id=latest['request_id'])
                    self._active(cursor,claims)
                    return result
                if request.retryOf!=latest['request_id']: raise CandidateReviewError('explicit_retry_required',409)
                attempt = latest['attempt']+1
                if attempt>3: raise CandidateReviewError('assessment_attempts_exhausted',429)
            elif request.retryOf is not None:
                raise CandidateReviewError('retry_conflict',409)
            cursor.execute("SELECT (clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date")
            day = cursor.fetchone()[0]
            cursor.execute('''INSERT INTO pilot_candidate_call_quota(tenant_id,reservation_day,reserved_calls) VALUES(%s,%s,1)
                ON CONFLICT(tenant_id,reservation_day) DO UPDATE SET reserved_calls=pilot_candidate_call_quota.reserved_calls+1
                WHERE pilot_candidate_call_quota.reserved_calls<%s RETURNING reserved_calls''', (tenant,day,self.max_daily_calls))
            if cursor.fetchone() is None: raise CandidateReviewError('assessment_quota_exhausted',429)
            result = dict(kind='pending',requestId=request.requestId,candidateId=request.candidateId,status='PROCESSING')
            self._insert_request(cursor,tenant,claims,request,payload,snapshot,result,action='ASSESS',status='PROCESSING',snapshot_key=snapshot_key,attempt=attempt)
            self._active(cursor,claims)
        # Reservation is committed before crossing the only model/network boundary.
        failure = None
        try:
            value, usage = model.assess(description=snapshot['description'],content=deepcopy(snapshot['content']))
            value = value.model_dump() if hasattr(value,'model_dump') else value
            content = validate_assessment(value,description=snapshot['description'],content=snapshot['content']).model_dump()
        except AssessmentModelError as error:
            failure = 'UNKNOWN' if error.code=='assessment_result_unknown' else 'FAILED'
        except Exception:
            failure = 'UNKNOWN'
        try:
            with self.database.connect() as connection, connection.cursor() as cursor:
                tenant = self._active(cursor,claims)
                _lock(cursor,11301,[tenant,claims.user_id,request.requestId])
                current = self._capture(cursor,tenant,claims,request)
                if any(current[key]!=snapshot[key] for key in ('binding','description','content','strategy')):
                    raise CandidateReviewError('candidate_conflict',409)
                row = self._request(cursor,tenant,claims.user_id,request.requestId)
                if row['status']!='PROCESSING': return self._result(cursor,row)
                now = _now(cursor)
                if now>=row['deadline_at']: failure='UNKNOWN'
                if failure:
                    result = dict(kind='pending' if failure=='UNKNOWN' else 'failure',requestId=request.requestId,
                                  candidateId=request.candidateId,status=failure,code='assessment_unknown' if failure=='UNKNOWN' else 'assessment_failed')
                else:
                    assessed = content | dict(id=str(uuid4()),**snapshot['binding'],assessedAt=now.isoformat(),
                        **snapshot['model'],strategyVersionId=snapshot['strategy']['strategy_version_id'],
                        effectiveDecision='REVIEW' if content['decision']=='SEND_READY' else content['decision'],
                        sendingAuthorized=False)
                    cursor.execute('INSERT INTO pilot_candidate_assessments(tenant_id,owner_user_id,assessment_id,request_id,binding_hash,content) VALUES(%s,%s,%s,%s,%s,%s::jsonb)',
                                   (tenant,claims.user_id,assessed['id'],request.requestId,_hash(snapshot['binding']),_json(assessed)))
                    result = dict(kind='assessment',requestId=request.requestId,candidateId=request.candidateId,assessment=assessed)
                cursor.execute('UPDATE pilot_candidate_review_requests SET status=%s,result=%s::jsonb WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
                               (failure or 'SUCCEEDED',_json(result),tenant,claims.user_id,request.requestId))
                self._active(cursor,claims)
                return result
        except CandidateIngestionError:
            raise
        except Exception:
            # Commit acknowledgement can be lost: never report a definitive rejection.
            raise CandidateReviewError('assessment_outcome_unknown',503) from None

    def verify_source(self, claims, payload):
        request = validate_payload(payload,verification=True)
        with self.database.connect() as connection, connection.cursor() as cursor:
            tenant = self._active(cursor,claims)
            previous = self._replay(cursor,tenant,claims,request,payload)
            if previous is not None: return previous
            snapshot = self._capture(cursor,tenant,claims,request,require_strategy=False)
            content = snapshot['content']
            if request.status=='OPEN' and not any(request.excerpt in (text or '') for text in (content['title'],content['body'])):
                raise CandidateReviewError('source_excerpt_mismatch',422)
            now = _now(cursor)
            receipt = dict(kind='sourceVerification',id=str(uuid4()),requestId=request.requestId,candidateId=request.candidateId,
                status=request.status,method='HUMAN_REOPENED',checkedBy=claims.user_id,checkedAt=now.isoformat(),
                openingMethod=request.openingMethod,locator=request.locator,excerpt=request.excerpt,
                contactMethod=request.contactMethod,binding=snapshot['binding'])
            self._insert_request(cursor,tenant,claims,request,payload,snapshot,receipt,action='VERIFY_SOURCE',now=now)
            cursor.execute('INSERT INTO pilot_candidate_source_verifications(tenant_id,owner_user_id,verification_id,request_id,binding_hash,checked_at,receipt) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)',
                (tenant,claims.user_id,receipt['id'],request.requestId,_hash(snapshot['binding']),now,_json(receipt)))
            self._active(cursor,claims)
            return receipt

    def _decide(self, claims, request, payload):
        try:
            with self.database.connect() as connection, connection.cursor() as cursor:
                tenant = self._active(cursor,claims)
                previous = self._replay(cursor,tenant,claims,request,payload)
                if previous is not None: return previous
                snapshot = self._capture(cursor,tenant,claims,request,require_strategy=request.action=='INCLUDE')
                bound = _hash(snapshot['binding'])
                cursor.execute('''SELECT a.content,r.snapshot FROM pilot_candidate_assessments a
                    JOIN pilot_candidate_review_requests r USING(tenant_id,owner_user_id,request_id)
                    WHERE a.tenant_id=%s AND a.owner_user_id=%s AND a.assessment_id=%s AND a.binding_hash=%s''',
                    (tenant,claims.user_id,request.assessmentId,bound))
                assessment_row = cursor.fetchone()
                if not assessment_row: raise CandidateReviewError('assessment_conflict',409)
                assessed, original = assessment_row
                if any(original[key]!=snapshot[key] for key in ('description','content','strategy')):
                    raise CandidateReviewError('assessment_conflict',409)
                now, opportunity = _now(cursor), None
                if request.action=='INCLUDE':
                    cursor.execute('SELECT verification_id,checked_at,receipt FROM pilot_candidate_source_verifications WHERE tenant_id=%s AND owner_user_id=%s AND binding_hash=%s ORDER BY checked_at DESC,verification_id DESC LIMIT 1', (tenant,claims.user_id,bound))
                    check = cursor.fetchone()
                    if (not check or str(check[0])!=request.sourceVerificationId or check[2]['status']!='OPEN'
                            or check[2]['contactMethod'] not in ('COMMENT','DM','PUBLIC_CONTACT')
                            or now-check[1]>timedelta(hours=24) or check[1]>now):
                        raise CandidateReviewError('source_verification_required',409)
                    published = snapshot['raw']['content']['published_at']
                    if published is None: raise CandidateReviewError('source_date_unknown',409)
                    published = datetime.fromisoformat(published.replace('Z','+00:00'))
                    if not timedelta(0)<=now-published<=timedelta(days=60): raise CandidateReviewError('source_expired',409)
                    raw, words = snapshot['raw'], request.evidence.model_dump()
                    source = raw['content']
                    data = dict(source_platform=raw['platform'],source_external_id='candidate:'+raw['source_identity'],
                        public_url=source['public_url'],source_published_at=published,title=source['title'] or source['body'][:120],
                        buyer=source['author_public_id'] or '',summary=assessed['summary'],contact_path=check[2]['contactMethod'],
                        public_excerpt=source['body'],match_reason=words['matchReason'],action_signal=words['actionSignal'],
                        value_judgment=words['value'],risk=words['risk']+'\n待确认：'+words['unknowns'],
                        reviewed_by=claims.user_id,reviewed_at=now,draft_comment=assessed['draftComment'],draft_dm=assessed['draftDm'])
                    opportunity = PilotStore(self.database)._import_opportunity(connection,tenant,request.profileId,
                        'candidate:'+_hash([request.profileId,raw['source_identity']]),data)
                    outcome = 'IMPORTED' if opportunity['created'] else 'ALREADY_IMPORTED'
                else:
                    outcome='EXCLUDED'
                receipt = dict(requestId=request.requestId,action=request.action,status='SUCCEEDED',outcome=outcome,
                    reviewedBy=claims.user_id,reviewedAt=now.isoformat(),review={key:payload[key] for key in (
                        'candidateRevision','sourceVersionId','profileId','profileVersion','assessmentId','evidence','reason')})
                if opportunity: receipt['opportunityId']=opportunity['opportunity_id']
                candidate = self._candidate(snapshot,assessed=assessed,receipt=receipt)
                result = dict(kind='decision',requestId=request.requestId,candidate=candidate,receipt=receipt)
                self._insert_request(cursor,tenant,claims,request,payload,snapshot,result,action=request.action,now=now)
                cursor.execute('INSERT INTO pilot_candidate_reviews(tenant_id,owner_user_id,request_id,binding_hash,assessment_id,verification_id,opportunity_id,result) VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                    (tenant,claims.user_id,request.requestId,bound,request.assessmentId,request.sourceVerificationId,
                     opportunity['opportunity_id'] if opportunity else None,_json(result)))
                if opportunity and opportunity['created']:
                    raw = snapshot['raw']
                    cursor.execute('''SELECT observation_id,candidate_id,version_id,observed_at,received_at
                        FROM pilot_candidate_observations
                        WHERE tenant_id=%s AND owner_user_id=%s AND observation_id=%s
                          AND candidate_id=%s AND version_id=%s''',
                        (tenant,claims.user_id,raw['current_observation_id'],raw['candidate_id'],raw['version_id']))
                    observation = _primitive(_row(cursor))
                    public = build_evidence(opportunity_id=opportunity['opportunity_id'],snapshot=snapshot,
                        assessment=assessed,observation=observation,verification=check[2],captured_at=now)
                    cursor.execute('''INSERT INTO pilot_opportunity_evidence
                        (tenant_id,opportunity_id,included_by_user_id,include_request_id,payload,payload_sha256)
                        VALUES(%s,%s,%s,%s,%s::jsonb,%s)''',
                        (tenant,opportunity['opportunity_id'],claims.user_id,request.requestId,
                         canonical_json(public),evidence_digest(public)))
                self._active(cursor,claims)
                return result
        except CandidateIngestionError:
            raise
        except Exception:
            raise CandidateReviewError('review_outcome_unknown',503) from None

    @staticmethod
    def _candidate(snapshot, *, assessed=None,receipt=None,verification=None,valid=True,historical=False):
        raw, b = snapshot['raw'], snapshot['binding']
        source = raw['content']
        status = {'IMPORTED':'IMPORTED','ALREADY_IMPORTED':'DUPLICATE','EXCLUDED':'EXCLUDED'}.get((receipt or {}).get('outcome'),'PENDING_REVIEW')
        result = dict(id=b['candidateId'],revision=b['candidateRevision'],sample=False,status=status,
            title=source['title'] or source['body'][:120],buyer=source['author_public_id'] or '',platform=raw['platform'],
            sourceLabel=raw['platform'],sourceId=raw['source_identity'],sourceVersionId=b['sourceVersionId'],
            sourceStatus=(verification or {}).get('status','UNVERIFIED'),url=source['public_url'],excerpt=source['body'],
            summary=(assessed or {}).get('summary',''),publishedAt=source['published_at'] or '',collectedAt=raw['latest_observed_at'],
            profileId=b['profileId'],profileVersion=b['profileVersion'],strategyVersionId=raw['strategy_version_id'],
            historical=historical,currentBindingValid=valid,assessmentStale=not valid)
        if assessed: result['assessment']=assessed
        if verification: result['sourceVerification']=verification
        if receipt: result['lastReview']=receipt
        if receipt and receipt.get('opportunityId'): result['opportunityId']=receipt['opportunityId']
        return result

    @contextmanager
    def _listing_snapshot(self, claims):
        # Keep authentication live and its session fence outside the data snapshot.
        # Starting RR before waiting for that fence could hide a preceding revoke.
        with self.database.connect() as auth_connection, auth_connection.cursor() as auth_cursor:
            tenant = self._active(auth_cursor,claims)
            try:
                with self.database.connect() as connection, connection.cursor() as cursor:
                    cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
                    cursor.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                                   (claims.user_id,tenant))
                    # Presentation reader uses this cursor only: no locks, writes,
                    # session fence reacquisition, new connection or network.
                    yield cursor,tenant,_now(cursor)
            except SerializationFailure:
                # Expose one rereadable conflict; never silently retry/mix snapshots.
                raise CandidateReviewError('candidate_snapshot_changed',409) from None
            # Original READ COMMITTED connection sees current revocation and clock,
            # even if credentials expire during a long data/strategy read.
            self._active(auth_cursor,claims)

    def list_candidates(self, claims, *, query=None,platform=None,status=None,ids=None,review_request_id=None,page=1,page_size=20):
        if type(page) is not int or page<1 or type(page_size) is not int or not 1<=page_size<=100:
            raise CandidateReviewError('invalid_request',422)
        if query is not None and (type(query) is not str or not query.strip() or len(query)>200):
            raise CandidateReviewError('invalid_request',422)
        if platform is not None and platform not in ('XIAOHONGSHU','DOUYIN','BILIBILI','ZHIHU','PUBLIC_WEB'):
            raise CandidateReviewError('invalid_request',422)
        if status is not None and status not in ('PENDING_REVIEW','IMPORTED','EXCLUDED','DUPLICATE'):
            raise CandidateReviewError('invalid_request',422)
        if ids is not None:
            if type(ids) is not list or not 1<=len(ids)<=100 or len(set(ids))!=len(ids): raise CandidateReviewError('invalid_request',422)
            for item in ids: _id(item)
        if review_request_id is not None:
            _id(review_request_id,opaque=True)
            if ids is None or len(ids)!=1 or page!=1 or page_size!=1: raise CandidateReviewError('invalid_request',422)
        with self._listing_snapshot(claims) as (cursor,tenant,now):
            # The whole data transaction, including strategy reads, shares MVCC.
            cursor.execute('''SELECT to_jsonb(q),v.version,v.status,v.payload,
                COALESCE((SELECT jsonb_agg(to_jsonb(r) ORDER BY r.created_at DESC,r.request_id DESC)
                    FROM pilot_candidate_review_requests r WHERE r.tenant_id=%s AND r.owner_user_id=%s
                    AND r.candidate_id=q.candidate_id AND r.status='SUCCEEDED' AND r.invocation_id IS NULL),'[]'::jsonb)
                FROM ('''+self._projection_sql+''') q JOIN business_profile_versions v
                ON v.tenant_id=%s AND v.profile_version_id=q.profile_version_id
                WHERE q.candidate_id IN(SELECT candidate_id FROM pilot_candidate_projections WHERE tenant_id=%s AND owner_user_id=%s)
                ORDER BY q.latest_observed_at DESC,q.candidate_id''', (tenant,claims.user_id,tenant,tenant,claims.user_id))
            rows = cursor.fetchall()
            items = []
            for raw,version,profile_status,profile,requests in rows:
                b = dict(candidateId=raw['candidate_id'],candidateRevision=raw['revision'],sourceVersionId=raw['version_id'],profileId=raw['profile_version_id'],profileVersion=version)
                if ids is not None and b['candidateId'] not in ids: continue
                if platform is not None and raw['platform']!=platform: continue
                if query is not None and query.casefold() not in _json(raw['content']).casefold(): continue
                snapshot = dict(raw=raw,binding=b)
                matching = [r for r in requests if r['snapshot']['binding']==b and r['snapshot']['description']==profile.get('description')]
                valid = profile_status=='CONFIRMED' and not raw['ambiguous']
                if valid and matching:
                    try:
                        resolved = self.strategy_snapshot_reader(cursor,claims,b['profileId'],raw['strategy_version_id']) if self.strategy_snapshot_reader else None
                        fields = {'profile_version_id','strategy_version_id','configuration','platforms',
                                  'max_records','max_runtime_seconds','configuration_sha256'}
                        valid = type(resolved) is dict and set(resolved)==fields
                        if valid:
                            current_strategy = {key:value for key,value in resolved.items() if key!='configuration_sha256'}
                            valid = (type(current_strategy['platforms']) is list
                                and current_strategy==matching[0]['snapshot']['strategy']
                                and resolved['configuration_sha256']==_hash(current_strategy)==matching[0]['snapshot']['strategyHash']
                                and current_strategy['profile_version_id']==b['profileId']
                                and current_strategy['strategy_version_id']==raw['strategy_version_id']
                                and raw['platform'] in current_strategy['platforms'])
                    except ExecutionRuntimeError as error:
                        mapped = _strategy_error(error)
                        if mapped.status!=409: raise mapped from None
                        valid=False
                    except (ValueError,TypeError,UnicodeError,RecursionError):
                        valid=False
                if review_request_id:
                    original = next((r for r in requests if r['request_id']==review_request_id and r['action'] in ('INCLUDE','EXCLUDE')),None)
                    if original is None: continue
                    candidate = dict(original['result']['candidate'])
                    historical_valid = valid and original in matching
                    candidate.update(historical=True,currentBindingValid=historical_valid,
                                     assessmentStale=not historical_valid)
                else:
                    assessment_request = next((r for r in matching if r['action']=='ASSESS'),None) if valid else None
                    review = next((r for r in matching if r['action'] in ('INCLUDE','EXCLUDE')),None) if valid else None
                    check = next((r for r in matching if r['action']=='VERIFY_SOURCE'),None) if valid else None
                    verification = check['result'] if check else None
                    if verification and now-datetime.fromisoformat(verification['checkedAt'])>timedelta(hours=24):
                        verification=verification | {'status':'EXPIRED'}
                    candidate = self._candidate(snapshot,assessed=assessment_request['result']['assessment'] if assessment_request else None,
                        receipt=review['result']['receipt'] if review else None,verification=verification,valid=valid)
                    candidate['assessmentStale'] = bool(any(r['action']=='ASSESS' for r in requests)) and assessment_request is None
                if status is None or candidate['status']==status: items.append(candidate)
            return dict(items=items[(page-1)*page_size:page*page_size],total=len(items),page=page,pageSize=page_size)
