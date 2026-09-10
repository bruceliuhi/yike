"""Device-attested replies to frozen dispatch; no current-draft dependency."""
from datetime import timedelta
from pydantic import Field
from pilot.contact_drafts import _Input, Id, Version
from pilot.execution_runtime import _json, _hash, _raw_model
from pilot.outreach_dispatch import timestamp
from pilot.reply_contract import PlatformReplyEvent
from pilot.reply_store import ReplyStoreError, decode_event, event_digest


class SignedReplyRequest(_Input):
    deviceId: Id
    credentialVersion: Version
    claimId: Id
    contextSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    event: PlatformReplyEvent


def signing_payload(tenant,claims,value):
    return _json(dict(protocol='yike-platform-reply-v1',tenant_id=tenant,
        user_id=claims.user_id,session_digest=claims.revocation_key,request=value.model_dump()))


def evidence_row(row):
    event=decode_event(row[0],row[1])
    proof=row[2]
    if proof is not None:
        if proof.get('replyEventSha256')!=row[1] or proof.get('authority')!='DEVICE_ATTESTED_PLATFORM_REPLY':
            raise ReplyStoreError('stored_reply_attestation_invalid',503)
    else:
        proof=dict(authority='MANUAL_RECORD' if event.kind=='MANUAL_FOLLOWUP' else 'OPERATOR_RECORDED')
    return dict(event=event.model_dump(),verification=proof)


class SignedReplyStore:
    def __init__(self,queue,replies):
        self.queue,self.replies=queue,replies

    def prepare(self,claims,raw):
        value=SignedReplyRequest.model_validate(_raw_model(raw)); q=self.queue
        with q.database.connect() as conn, conn.cursor() as cursor:
            tenant=q._lock(cursor,claims)
            q.execution._key(cursor,claims,tenant,value.deviceId,value.credentialVersion)
            result=dict(signing_payload=signing_payload(tenant,claims,value))
            q.drafts._active(cursor,claims)
            return result

    def record(self,claims,raw,signature):
        value=SignedReplyRequest.model_validate(_raw_model(raw)); q=self.queue; event=value.event
        with q.database.connect() as conn, conn.cursor() as cursor:
            tenant=q._lock(cursor,claims)
            key=q.execution._key(cursor,claims,tenant,value.deviceId,value.credentialVersion)
            q.execution._signature(key,signature,signing_payload(tenant,claims,value))
            if event.tenant_id!=tenant or event.user_id!=claims.user_id:
                raise ReplyStoreError('event_scope_mismatch',409)
            cursor.execute('SELECT q.context_payload,q.state,c.claim_id,c.claimed_at '
                'FROM pilot_outreach_queue q JOIN pilot_outreach_claims c '
                'USING(tenant_id,owner_user_id,request_id) '
                'WHERE q.tenant_id=%s AND q.owner_user_id=%s AND q.request_id=%s',
                (tenant,claims.user_id,event.outreach_request_id))
            row=cursor.fetchone()
            if row is None or row[1] not in ('SENT','UNKNOWN') or row[2]!=value.claimId:
                raise ReplyStoreError('reply_origin_unavailable',409)
            context=row[0]
            expected=(context['binding']['opportunityId'],context['source']['sourceId'],
                context['profileVersionId'],context['source']['platform'],context['draft']['channel'],
                context['target']['authorPublicId'],context['connection']['deviceId'],context['contextSha256'])
            actual=(event.opportunity_id,event.source_id,event.profile_version_id,event.platform,event.channel,
                event.sender_public_id,value.deviceId,value.contextSha256)
            if expected!=actual:
                raise ReplyStoreError('reply_origin_binding_conflict',409)
            now=q.execution._now(cursor)
            if timestamp(event.received_at)<row[3]-timedelta(seconds=5) or timestamp(event.observed_at)>now+timedelta(seconds=5):
                raise ReplyStoreError('reply_observation_time_invalid',409)
            self.replies._lock_events(cursor,tenant,claims.user_id,event)
            # A later poll is not a new reply fact. Preserve the first signed
            # observation rather than rewriting its timestamp or provenance.
            if event.state=='ACTIVE':
                cursor.execute('SELECT payload,payload_sha256,device_attestation FROM pilot_reply_events '
                    'WHERE tenant_id=%s AND owner_user_id=%s AND source_id=%s AND outreach_request_id=%s '
                    "AND platform=%s AND external_reply_id=%s AND state='ACTIVE' ORDER BY revision DESC LIMIT 1",
                    (tenant,claims.user_id,event.source_id,event.outreach_request_id,event.platform,event.external_reply_id))
                prior=cursor.fetchone()
                if prior:
                    previous=decode_event(prior[0],prior[1])
                    exclude={'event_id','observed_at'}
                    if (previous.model_dump(exclude=exclude)==event.model_dump(exclude=exclude)
                            and timestamp(event.observed_at)>=timestamp(previous.observed_at)):
                        cursor.execute('SELECT 1 FROM pilot_reply_events WHERE tenant_id=%s AND owner_user_id=%s '
                            'AND event_id=%s LIMIT 1',(tenant,claims.user_id,event.event_id))
                        if cursor.fetchone() is None or event.event_id==previous.event_id:
                            q.drafts._active(cursor,claims)
                            return evidence_row(prior)
            proof=dict(schemaVersion='device-reply-attestation-v1',authority='DEVICE_ATTESTED_PLATFORM_REPLY',
                deviceId=value.deviceId,credentialVersion=value.credentialVersion,claimId=value.claimId,
                contextSha256=value.contextSha256,requestSha256=_hash(value.model_dump()),
                replyEventSha256=event_digest(event),verifiedAt=now.isoformat())
            saved=self.replies.record_in_transaction(cursor,claims,event,device_attestation=proof)
            # Semantic deduplication may return an original, different event UUID.
            cursor.execute('SELECT payload,payload_sha256,device_attestation FROM pilot_reply_events '
                'WHERE tenant_id=%s AND owner_user_id=%s AND event_id=%s AND payload_sha256=%s '
                'ORDER BY revision DESC LIMIT 1',(tenant,claims.user_id,saved.event_id,event_digest(saved)))
            result=evidence_row(cursor.fetchone())
            q.drafts._active(cursor,claims)
            return result

    def list_evidence(self,claims,opportunity_id):
        from pilot.outreach_contract import canonical_uuid
        opportunity_id=canonical_uuid(opportunity_id)
        with self.queue.database.connect() as conn, conn.cursor() as cursor:
            tenant=self.replies._active(cursor,claims)
            cursor.execute('SELECT payload,payload_sha256,device_attestation FROM pilot_reply_events '
                'WHERE tenant_id=%s AND owner_user_id=%s AND opportunity_id=%s ORDER BY observed_at,revision',
                (tenant,claims.user_id,opportunity_id))
            result=[evidence_row(row) for row in cursor.fetchall()]
            self.replies._active(cursor,claims)
            return result
