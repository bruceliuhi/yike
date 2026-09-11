"""One server grant per confirmation; native workers must durably consume it."""
from datetime import datetime, timedelta
from typing import Literal

from pydantic import Field, field_validator, model_validator

from pilot.contact_drafts import _Input, Id, Version, DraftError
from pilot.candidate_contract import _opaque
from pilot.execution_runtime import _hash, _json, _raw_model
from pilot.outreach_queue import ChannelCheck, Confirmation, receipt


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


class PlatformReceipt(_Input):
    kind: Literal['ACCEPTED','REJECTED_NOT_DELIVERED']
    externalId: str = Field(min_length=1,max_length=512)
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    observedAt: str = Field(max_length=48)

    @field_validator('externalId')
    @classmethod
    def opaque_id(cls, value):
        return _opaque(value)

    @field_validator('observedAt')
    @classmethod
    def aware_time(cls, value):
        return ChannelCheck.aware_time(value)


class Outcome(_Input):
    status: Literal['UNKNOWN','SENT','FAILED']
    confirmed: bool | None = None
    confirmedNotDelivered: bool | None = None
    proof: PlatformReceipt | None = None

    @model_validator(mode='after')
    def check(self):
        if self.status=='UNKNOWN':
            if any(v is not None for v in (self.confirmed,self.confirmedNotDelivered,self.proof)):
                raise ValueError('unknown cannot confirm delivery')
        else:
            if self.confirmed is not True or self.proof is None:
                raise ValueError('explicit platform receipt required')
            if self.status=='SENT':
                if self.proof.kind!='ACCEPTED' or self.confirmedNotDelivered is not None:
                    raise ValueError('invalid delivery receipt')
            elif self.proof.kind!='REJECTED_NOT_DELIVERED' or self.confirmedNotDelivered is not True:
                raise ValueError('explicit non-delivery required')
        return self


class DispatchRequest(_Input):
    action: Literal['CLAIM','VALIDATE','RESULT']
    requestId: Id
    claimId: Id
    deviceId: Id
    credentialVersion: Version
    contextSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    resultId: Id | None = None
    outcome: Outcome | None = None

    @model_validator(mode='after')
    def shape(self):
        if self.action in ('CLAIM','VALIDATE'):
            if self.resultId is not None or self.outcome is not None:
                raise ValueError('claim cannot report result')
        elif self.resultId is None or self.outcome is None:
            raise ValueError('result requires outcome and original operation id')
        return self


def signing_payload(tenant, claims, request):
    return _json(dict(protocol='yike-outreach-dispatch-v1',tenant_id=tenant,
        user_id=claims.user_id,session_digest=claims.revocation_key,request=request.model_dump()))


class OutreachDispatch:
    def __init__(self, queue, allowed_platforms):
        self.queue = queue
        self.allowed_platforms = frozenset(allowed_platforms)

    def prepare(self, claims, raw):
        value=DispatchRequest.model_validate(_raw_model(raw))
        q=self.queue
        with q.database.connect() as conn, conn.cursor() as cursor:
            tenant=q._lock(cursor,claims)
            q.execution._key(cursor,claims,tenant,value.deviceId,value.credentialVersion)
            result=dict(signing_payload=signing_payload(tenant,claims,value))
            q.drafts._active(cursor,claims)
            return result

    def _claim_row(self,cursor,tenant,owner,request_id):
        cursor.execute('SELECT claim_id,request_sha256,dispatch_before,claimed_at FROM pilot_outreach_claims '
            'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',(tenant,owner,request_id))
        return cursor.fetchone()

    def decorate(self,cursor,tenant,owner,result):
        row=self._claim_row(cursor,tenant,owner,result['requestId'])
        if row:
            result.update(claimId=row[0],dispatchBefore=row[2].isoformat())
        return result

    def apply(self,claims,raw,signature):
        value=DispatchRequest.model_validate(_raw_model(raw))
        digest=_hash(value.model_dump())
        q=self.queue
        with q.database.connect() as conn, conn.cursor() as cursor:
            tenant=q._lock(cursor,claims)
            key=q.execution._key(cursor,claims,tenant,value.deviceId,value.credentialVersion)
            q.execution._signature(key,signature,signing_payload(tenant,claims,value))
            cursor.execute('SELECT request_payload,context_payload,confirmed_at,state,request_sha256 '
                'FROM pilot_outreach_queue WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
                (tenant,claims.user_id,value.requestId))
            row=cursor.fetchone()
            if row is None:
                raise DraftError('outreach_request_not_found',404)
            confirmation=Confirmation.model_validate(row[0])
            if _hash(confirmation.model_dump())!=row[4]:
                raise DraftError('outreach_confirmation_invalid')
            if (value.deviceId!=confirmation.context.deviceId
                    or value.contextSha256!=confirmation.contextSha256):
                raise DraftError('outreach_claim_binding_conflict')
            claim=self._claim_row(cursor,tenant,claims.user_id,value.requestId)
            if value.action=='CLAIM':
                result=self._claim(cursor,claims,tenant,value,digest,confirmation,row,claim)
            elif value.action=='VALIDATE':
                result=self._validate(cursor,claims,tenant,value,confirmation,row,claim)
            else:
                result=self._result(cursor,claims,tenant,value,digest,row,claim)
            q.drafts._active(cursor,claims)
            return result

    def _claim(self,cursor,claims,tenant,value,digest,confirmation,row,claim):
        q=self.queue
        if claim:
            if claim[0]!=value.claimId or claim[1]!=digest:
                raise DraftError('outreach_already_claimed')
            return self.decorate(cursor,tenant,claims.user_id,receipt((value.requestId,row[3])))
        if row[3]!='QUEUED':
            raise DraftError('outreach_not_queued')
        cursor.execute('SELECT 1 FROM pilot_outreach_claims '
            'WHERE tenant_id=%s AND owner_user_id=%s AND claim_id=%s',
            (tenant,claims.user_id,value.claimId))
        if cursor.fetchone():
            raise DraftError('outreach_claim_id_conflict')
        if value.credentialVersion!=confirmation.credentialVersion:
            raise DraftError('outreach_confirmation_changed')
        current=q.drafts.context_in_transaction(cursor,claims,confirmation.context.model_dump())
        if current['contextSha256']!=value.contextSha256:
            raise DraftError('outreach_context_changed')
        if current['source']['platform'] not in self.allowed_platforms:
            raise DraftError('outreach_dispatch_unavailable',501)
        now=q.execution._now(cursor)
        observed=timestamp(confirmation.channelCheck.observedAt)
        if not -5 <= (now-observed).total_seconds() <= 120 or not 0 <= (now-row[2]).total_seconds() <= 120:
            raise DraftError('outreach_confirmation_expired')
        deadline=min(now+timedelta(seconds=30),observed+timedelta(seconds=120),row[2]+timedelta(seconds=120))
        if deadline<=now:
            raise DraftError('outreach_confirmation_expired')
        cursor.execute('INSERT INTO pilot_outreach_claims '
            '(tenant_id,owner_user_id,request_id,claim_id,request_sha256,payload,dispatch_before) '
            'VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)',
            (tenant,claims.user_id,value.requestId,value.claimId,digest,_json(value.model_dump()),deadline))
        cursor.execute("UPDATE pilot_outreach_queue SET state='UNKNOWN' "
            'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
            (tenant,claims.user_id,value.requestId))
        return dict(receipt((value.requestId,'UNKNOWN')),dispatchAllowed=True,
            claimId=value.claimId,dispatchBefore=deadline.isoformat(),context=current)

    def _validate(self,cursor,claims,tenant,value,confirmation,row,claim):
        if claim is None or claim[0] != value.claimId or row[3] != 'UNKNOWN':
            raise DraftError('outreach_original_claim_required')
        if value.credentialVersion != confirmation.credentialVersion:
            raise DraftError('outreach_confirmation_changed')
        cursor.execute('SELECT payload FROM pilot_outreach_claims WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
                       (tenant,claims.user_id,value.requestId))
        original = DispatchRequest.model_validate(cursor.fetchone()[0])
        if (original.action != 'CLAIM' or original.claimId != value.claimId or original.deviceId != value.deviceId
                or original.credentialVersion != value.credentialVersion or original.contextSha256 != value.contextSha256):
            raise DraftError('outreach_claim_binding_conflict')
        now = self.queue.execution._now(cursor)
        if now >= claim[2]:
            raise DraftError('outreach_confirmation_expired')
        current = self.queue.drafts.context_in_transaction(cursor,claims,confirmation.context.model_dump())
        if current['contextSha256'] != value.contextSha256:
            raise DraftError('outreach_context_changed')
        return {'state':'QUALIFIED','requestId':value.requestId,'claimId':value.claimId,
                'contextSha256':value.contextSha256,'dispatchBefore':claim[2].isoformat()}

    def _result(self,cursor,claims,tenant,value,digest,row,claim):
        if claim is None or claim[0]!=value.claimId:
            raise DraftError('outreach_original_claim_required')
        cursor.execute('SELECT request_sha256,receipt,payload FROM pilot_outreach_results '
            'WHERE tenant_id=%s AND owner_user_id=%s AND result_id=%s',
            (tenant,claims.user_id,value.resultId))
        original=cursor.fetchone()
        if original:
            # Current credential was already authenticated above. Rotation changes
            # transport proof, not the immutable result under this original UUID.
            saved=original[2]
            if (original[0]!=_hash(saved) or
                    _hash({k:v for k,v in saved.items() if k!='credentialVersion'})!=
                    _hash(value.model_dump(exclude={'credentialVersion'}))):
                raise DraftError('outreach_result_conflict')
            return original[1]
        if row[3]!='UNKNOWN':
            raise DraftError('outreach_result_terminal')
        outcome=value.outcome
        if outcome.proof:
            observed=timestamp(outcome.proof.observedAt)
            now=self.queue.execution._now(cursor)
            if observed<claim[3]-timedelta(seconds=5) or observed>now+timedelta(seconds=5):
                raise DraftError('outreach_receipt_time_invalid')
        result=self.decorate(cursor,tenant,claims.user_id,receipt((value.requestId,outcome.status)))
        result['resultId']=value.resultId
        cursor.execute('INSERT INTO pilot_outreach_results '
            '(tenant_id,owner_user_id,result_id,request_id,claim_id,request_sha256,payload,receipt) '
            'VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)',
            (tenant,claims.user_id,value.resultId,value.requestId,value.claimId,digest,
             _json(value.model_dump()),_json(result)))
        if outcome.status!='UNKNOWN':
            cursor.execute('UPDATE pilot_outreach_queue SET state=%s '
                'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
                (outcome.status,tenant,claims.user_id,value.requestId))
        return result
