"""Device-attested replies to frozen dispatch; no current-draft dependency."""
import re
from datetime import timedelta
from pydantic import Field
from pilot.contact_drafts import _Input, Id, Version
from pilot.execution_runtime import _json, _hash, _raw_model
from pilot.outreach_dispatch import timestamp, DispatchRequest
from pilot.outreach_queue import Confirmation
from pilot.reply_contract import PlatformReplyEvent
from pilot.reply_store import ReplyStoreError, decode_event, event_digest
from pilot.execution_contract import ExecutionRuntimeError
from pilot.outreach_contract import canonical_uuid


class SignedReplyRequest(_Input):
    deviceId: Id
    credentialVersion: Version
    claimId: Id
    contextSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    event: PlatformReplyEvent


class ReplySyncContextRequest(_Input):
    requestId: Id
    deviceId: Id
    credentialVersion: Version


_CONTEXT_KEYS={'schemaVersion','binding','ownerUserId','accountScope','profileVersionId','draft',
    'source','target','connection','channelCapability','authorization','contextSha256'}


def _sync_context(context, tenant, owner):
    try:
        unsigned={key:value for key,value in context.items() if key!='contextSha256'}
        binding,draft,source,target,connection=context['binding'],context['draft'],context['source'],context['target'],context['connection']
        valid=(type(context) is dict and set(context)==_CONTEXT_KEYS
            and context['schemaVersion']=='outreach-context-v1'
            and context['ownerUserId']==owner and context['accountScope']=={'id':tenant,'version':1}
            and context['contextSha256']==_hash(unsigned)
            and set(binding)=={'opportunityId','channel','requestId','contentHash'}
            and set(draft)=={'opportunityId','channel','content','savedContent','version','accountId','recipient'}
            and set(source)=={'sourceId','evidenceVersion','evidenceSha256','platform','kind','url','excerpt'}
            and set(target)=={'action','authorPublicId','postId','commentId'}
            and set(connection)=={'deviceId','connectionId','connectionVersion','accountPublicId','platform'}
            and binding['opportunityId']==draft['opportunityId'] and binding['channel']==draft['channel']=='comment'
            and draft['content']==draft['savedContent'] and draft['accountId']==connection['accountPublicId']
            and draft['recipient']==target['authorPublicId']
            and source['platform']==connection['platform']=='XIAOHONGSHU' and source['kind']=='POST'
            and target['action']=='POST_COMMENT' and target['commentId'] is None
            and re.fullmatch(r'[a-f0-9]{24}',target['postId']) is not None
            and re.fullmatch(r'[a-f0-9]{24}',target['authorPublicId']) is not None
            and re.fullmatch(r'[a-f0-9]{24}',connection['accountPublicId']) is not None
            and all(re.fullmatch(r'[a-f0-9]{64}',item) is not None for item in
                (binding['contentHash'],source['evidenceSha256'],context['contextSha256']))
            and context['channelCapability']=={'status':'UNVERIFIED','reason':'CHANNEL_CHECK_REQUIRED'}
            and context['authorization']=='NOT_GRANTED')
        if not valid:
            raise ValueError
        for item in (context['ownerUserId'],context['profileVersionId'],binding['opportunityId'],
                binding['requestId'],source['sourceId'],source['evidenceVersion'],connection['deviceId'],
                connection['connectionId']):
            canonical_uuid(item)
        return context
    except (KeyError, TypeError, ValueError):
        raise ReplyStoreError('reply_sync_origin_invalid',409) from None


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
    return dict(event=event.model_dump(),verification=proof,revision=row[3])


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

    def sync_context(self,claims,raw):
        value=ReplySyncContextRequest.model_validate(_raw_model(raw)); q=self.queue
        with q.database.connect() as conn, conn.cursor() as cursor:
            tenant=q._lock(cursor,claims)
            try:
                q.execution._key(cursor,claims,tenant,value.deviceId,value.credentialVersion)
            except ExecutionRuntimeError:
                raise ReplyStoreError('reply_sync_origin_unavailable',409) from None
            cursor.execute("SELECT q.request_payload,q.context_payload,q.state,q.request_sha256,"
                "c.claim_id,c.request_sha256,c.payload,c.claimed_at,"
                "r.request_sha256,r.payload,r.receipt "
                "FROM pilot_outreach_queue q JOIN pilot_outreach_claims c "
                "USING(tenant_id,owner_user_id,request_id) JOIN pilot_outreach_results r "
                "USING(tenant_id,owner_user_id,request_id,claim_id) "
                "WHERE q.tenant_id=%s AND q.owner_user_id=%s AND q.request_id=%s "
                "AND r.receipt->>'state'='SENT'",
                (tenant,claims.user_id,value.requestId))
            rows=cursor.fetchall()
            if len(rows)!=1 or rows[0][2]!='SENT':
                raise ReplyStoreError('reply_sync_origin_unavailable',409)
            row=rows[0]
            try:
                confirmation=Confirmation.model_validate(row[0])
                claim=DispatchRequest.model_validate(row[6])
                result=DispatchRequest.model_validate(row[9])
            except (ValueError,TypeError):
                raise ReplyStoreError('reply_sync_origin_invalid',409) from None
            context=_sync_context(row[1],tenant,claims.user_id)
            proof=result.outcome.proof if result.outcome else None
            expected=(value.requestId,value.deviceId,value.credentialVersion,context['contextSha256'])
            confirmation_context={'binding':context['binding'],'deviceId':context['connection']['deviceId'],
                'connectionId':context['connection']['connectionId'],
                'connectionVersion':context['connection']['connectionVersion']}
            if (row[3]!=_hash(confirmation.model_dump()) or row[5]!=_hash(claim.model_dump())
                    or row[8]!=_hash(result.model_dump())
                    or confirmation.context.model_dump()!=confirmation_context
                    or confirmation.contextSha256!=context['contextSha256']
                    or confirmation.credentialVersion!=value.credentialVersion
                    or (claim.requestId,claim.deviceId,claim.credentialVersion,claim.contextSha256)!=expected
                    or claim.action!='CLAIM' or claim.claimId!=row[4]
                    or (result.requestId,result.deviceId,result.credentialVersion,result.contextSha256)!=expected
                    or result.action!='RESULT' or result.claimId!=row[4]
                    or result.outcome is None or result.outcome.status!='SENT'
                    or proof is None or proof.kind!='ACCEPTED'
                    or not re.fullmatch(r'[a-f0-9]{24}',proof.externalId)
                    or row[10].get('requestId')!=value.requestId or row[10].get('claimId')!=row[4]
                    or row[10].get('resultId')!=result.resultId or row[10].get('state')!='SENT'):
                raise ReplyStoreError('reply_sync_origin_invalid',409)
            q.drafts._active(cursor,claims)
            return dict(schemaVersion='reply-sync-context-v1',context=context,claimId=row[4],
                claimedAt=row[7].isoformat(),rootCommentId=proof.externalId,
                deviceId=value.deviceId,credentialVersion=value.credentialVersion)

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
                cursor.execute('SELECT payload,payload_sha256,device_attestation,revision FROM pilot_reply_events '
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
            cursor.execute('SELECT payload,payload_sha256,device_attestation,revision FROM pilot_reply_events '
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
            cursor.execute('SELECT payload,payload_sha256,device_attestation,revision FROM pilot_reply_events '
                'WHERE tenant_id=%s AND owner_user_id=%s AND opportunity_id=%s ORDER BY observed_at,revision',
                (tenant,claims.user_id,opportunity_id))
            result=[evidence_row(row) for row in cursor.fetchall()]
            self.replies._active(cursor,claims)
            return result
