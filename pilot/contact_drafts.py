"""Owner-private, append-only manual drafts. Saving never authorizes sending."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

from pilot.auth import TokenClaims
from pilot.candidate_contract import _opaque, _validate_url
from pilot.connection_versions import ConnectionOperationStore
from pilot.opportunity_evidence import evidence_view
from pilot.outreach_contract import canonical_uuid
from pilot.sessions import PilotSessionRegistry


class DraftError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def _utf8(value):
    value.encode('utf-8')
    if '\0' in value:
        raise ValueError('invalid text')
    return value


Id = Annotated[str, AfterValidator(canonical_uuid)]
Text = Annotated[str, Field(max_length=8000), AfterValidator(_utf8)]
Version = Annotated[int, Field(ge=1, le=2_147_483_647)]
Channel = Literal['comment', 'dm']


class _Input(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid', hide_input_in_errors=True)


class DraftSaveBinding(_Input):
    opportunityId: Id
    channel: Channel
    requestId: Id
    contentHash: str = Field(pattern=r'^[a-f0-9]{64}$')


class Draft(_Input):
    opportunityId: Id
    channel: Channel
    content: Text = Field(min_length=1)
    savedContent: Text
    version: Version
    accountId: str = Field(max_length=512)
    recipient: str = Field(max_length=512)


class AccountScope(_Input):
    id: Id
    version: Annotated[int, Field(ge=1, le=1)]


class DraftSnapshot(_Input):
    draft: Draft
    accountScope: AccountScope | None
    profileVersionId: Id
    sourceEvidenceVersion: Id


def snapshot_digest(snapshot: DraftSnapshot) -> str:
    """Exact UTF-8 JSON array used by desktop domain/shortCoach.snapshotDigest."""
    d = snapshot.draft
    fields = [d.opportunityId, d.channel, d.version, d.content, d.accountId,
              d.recipient, snapshot.profileVersionId, snapshot.sourceEvidenceVersion,
              None if snapshot.accountScope is None else snapshot.accountScope.model_dump()]
    return hashlib.sha256(json.dumps(fields, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


class DraftSaveInput(_Input):
    binding: DraftSaveBinding
    snapshot: DraftSnapshot
    previousRequestId: Id | None = None

    @model_validator(mode='after')
    def matching(self):
        d = self.snapshot.draft
        if (d.opportunityId != self.binding.opportunityId or d.channel != self.binding.channel
                or not d.content.strip() or snapshot_digest(self.snapshot) != self.binding.contentHash):
            raise ValueError('invalid draft binding')
        return self


class OutreachContextInput(_Input):
    binding: DraftSaveBinding
    deviceId: Id
    connectionId: Id
    connectionVersion: Version


def _receipt(row):
    try:
        value = DraftSaveInput.model_validate(row[0])
        if value.binding.contentHash != row[1] or value.snapshot.draft.savedContent != value.snapshot.draft.content:
            raise ValueError('invalid stored draft')
    except (ValueError, TypeError):
        raise DraftError('stored_draft_invalid', 503) from None
    return dict(binding=value.binding.model_dump(), snapshot=value.snapshot.model_dump(),
                status='SUCCEEDED', confirmed=True)


class ContactDraftStore:
    def __init__(self, database):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        if not isinstance(claims, TokenClaims):
            raise DraftError('invalid_session', 401)
        return self.sessions.require_active(cursor, claims)

    @staticmethod
    def _lock_owner(cursor, tenant, owner):
        lock = int.from_bytes(hashlib.sha256(
            f'contact-drafts-v1\0{tenant}\0{owner}'.encode()).digest()[:8], 'big', signed=True)
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))

    @staticmethod
    def _current_facts(cursor, tenant, snapshot):
        draft = snapshot.draft
        if snapshot.accountScope is not None and snapshot.accountScope.id != tenant:
            raise DraftError('draft_scope_changed')
        cursor.execute('SELECT o.profile_version_id,o.source_status,o.intent_status,p.status,s.health,'
            'e.payload,e.payload_sha256,o.draft_comment,o.draft_dm,o.source_id,s.platform,s.public_url '
            'FROM pilot_opportunities o '
            'JOIN business_profile_versions p ON p.tenant_id=o.tenant_id AND p.profile_version_id=o.profile_version_id '
            'JOIN pilot_sources s ON s.tenant_id=o.tenant_id AND s.source_id=o.source_id '
            'LEFT JOIN pilot_opportunity_evidence e ON e.tenant_id=o.tenant_id AND e.opportunity_id=o.opportunity_id '
            'WHERE o.tenant_id=%s AND o.opportunity_id=%s FOR SHARE OF o,p,s',
            (tenant, draft.opportunityId))
        facts = cursor.fetchone()
        if facts is None:
            raise DraftError('opportunity_not_found', 404)
        if (facts[0] != snapshot.profileVersionId or facts[1] != 'OPEN'
                or facts[2] == 'CLOSED' or facts[3] != 'CONFIRMED' or facts[4] != 'OPEN'):
            raise DraftError('draft_facts_changed')
        proof = evidence_view(facts[5], facts[6], opportunity_id=draft.opportunityId,
                              profile_version_id=snapshot.profileVersionId)
        if (proof['status'] != 'CAPTURED'
                or proof['snapshot']['source']['version_id'] != snapshot.sourceEvidenceVersion
                or proof['snapshot']['source']['platform'] != facts[10]
                or proof['snapshot']['source']['public_url'] != facts[11]):
            raise DraftError('draft_evidence_changed')
        return facts, proof

    @staticmethod
    def _original(cursor, tenant, owner, binding):
        cursor.execute('SELECT payload,content_hash FROM pilot_contact_drafts '
            'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s',
            (tenant, owner, binding.requestId))
        row = cursor.fetchone()
        if row is None:
            return None
        receipt = _receipt(row)
        if receipt['binding'] != binding.model_dump():
            raise DraftError('draft_request_conflict')
        return receipt

    def operation(self, claims, binding):
        binding = DraftSaveBinding.model_validate(binding)
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            receipt = self._original(cursor, tenant, claims.user_id, binding)
            self._active(cursor, claims)
            if receipt is None:
                raise DraftError('draft_request_not_found', 404)
            return receipt

    def latest(self, claims, opportunity_id, channel):
        try:
            canonical_uuid(opportunity_id)
            if channel not in ('comment', 'dm'):
                raise ValueError
        except ValueError:
            raise DraftError('invalid_draft_request', 422) from None
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute('SELECT payload,content_hash FROM pilot_contact_drafts '
                'WHERE tenant_id=%s AND owner_user_id=%s AND opportunity_id=%s AND channel=%s '
                'ORDER BY draft_version DESC LIMIT 1', (tenant, claims.user_id, opportunity_id, channel))
            row = cursor.fetchone()
            self._active(cursor, claims)
            if row is None:
                raise DraftError('draft_not_found', 404)
            return _receipt(row)

    def save(self, claims, raw):
        value = DraftSaveInput.model_validate(raw)
        binding, snapshot = value.binding, value.snapshot
        draft = snapshot.draft
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            # Two different sessions of the same owner must serialize too.
            self._lock_owner(cursor, tenant, claims.user_id)
            self._active(cursor, claims)
            prior = self._original(cursor, tenant, claims.user_id, binding)
            if prior is not None:
                return prior
            facts, _proof = self._current_facts(cursor, tenant, snapshot)
            cursor.execute('SELECT payload,content_hash FROM pilot_contact_drafts '
                'WHERE tenant_id=%s AND owner_user_id=%s AND opportunity_id=%s AND channel=%s '
                'ORDER BY draft_version DESC LIMIT 1', (tenant, claims.user_id, draft.opportunityId, draft.channel))
            previous = cursor.fetchone()
            if previous is None:
                previous_content, previous_version = facts[7 if draft.channel == 'comment' else 8], 0
                previous_request_id = None
            else:
                previous_receipt = _receipt(previous)
                old = previous_receipt['snapshot']['draft']
                previous_request_id = previous_receipt['binding']['requestId']
                previous_content, previous_version = old['content'], old['version']
            if (value.previousRequestId != previous_request_id
                    or draft.savedContent != previous_content or draft.version <= previous_version):
                raise DraftError('draft_version_conflict')
            payload = value.model_dump()
            payload['snapshot']['draft']['savedContent'] = draft.content
            cursor.execute('INSERT INTO pilot_contact_drafts '
                '(tenant_id,owner_user_id,request_id,opportunity_id,channel,draft_version,content_hash,payload) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb)',
                (tenant,claims.user_id,binding.requestId,draft.opportunityId,draft.channel,
                 draft.version,binding.contentHash,json.dumps(payload,ensure_ascii=False)))
            self._active(cursor, claims)
            return _receipt((payload, binding.contentHash))

    def context(self, claims, raw):
        """Resolve current draft/source/owner connection, not channel permission.

        Everything used by a subsequent native channel check is server-resolved;
        this read never creates a confirmation or authorizes platform execution.
        """
        with self.database.connect() as conn, conn.cursor() as cursor:
            return self.context_in_transaction(cursor, claims, raw)

    def context_in_transaction(self, cursor, claims, raw):
        """Same-cursor revalidation for durable human confirmation."""
        request = OutreachContextInput.model_validate(raw)
        tenant = self._active(cursor, claims)
        self._lock_owner(cursor, tenant, claims.user_id)
        original = self._original(cursor, tenant, claims.user_id, request.binding)
        if original is None:
            raise DraftError('draft_request_not_found', 404)
        snapshot = DraftSnapshot.model_validate(original['snapshot'])
        draft = snapshot.draft
        cursor.execute('SELECT request_id FROM pilot_contact_drafts '
            'WHERE tenant_id=%s AND owner_user_id=%s AND opportunity_id=%s AND channel=%s '
            'ORDER BY draft_version DESC LIMIT 1',
            (tenant, claims.user_id, draft.opportunityId, draft.channel))
        if cursor.fetchone() != (request.binding.requestId,):
            raise DraftError('draft_version_conflict')
        cursor.execute('SELECT platform FROM pilot_platform_connections '
            'WHERE tenant_id=%s AND connection_id=%s', (tenant, request.connectionId))
        platform_row = cursor.fetchone()
        if platform_row is None:
            raise DraftError('connection_unavailable')
        # Match execution's device/connection -> profile lock order.
        connection = ConnectionOperationStore(self.database).lock_current(cursor, claims,
            device_id=request.deviceId, connection_id=request.connectionId,
            connection_version=request.connectionVersion, platform=platform_row[0])
        if draft.accountId != connection['account_public_id']:
            raise DraftError('outreach_account_changed')
        facts, proof = self._current_facts(cursor, tenant, snapshot)
        source = proof['snapshot']['source']
        if source['platform'] != connection['platform']:
            raise DraftError('outreach_account_changed')
        if source['kind'] not in ('POST','COMMENT') or source['platform']=='PUBLIC_WEB':
            raise DraftError('outreach_target_unavailable')
        try:
            _validate_url(source['public_url'], source['platform'])
            author = _opaque(source['author_public_id'])
            post_id = _opaque(source['external_source_id'])
            comment_id = _opaque(source['external_comment_id']) if source['kind']=='COMMENT' else None
        except (ValueError, TypeError):
            raise DraftError('outreach_target_unavailable') from None
        if draft.recipient and draft.recipient != author:
            raise DraftError('outreach_recipient_changed')
        result = dict(schemaVersion='outreach-context-v1', binding=request.binding.model_dump(),
            ownerUserId=claims.user_id, accountScope={'id':tenant,'version':1},
            profileVersionId=snapshot.profileVersionId, draft=draft.model_dump(),
            source={'sourceId':facts[9],'evidenceVersion':source['version_id'],
                'evidenceSha256':proof['snapshot_sha256'],'platform':source['platform'],
                'kind':source['kind'],'url':source['public_url'],'excerpt':source['body']},
            target={'action': 'DIRECT_MESSAGE' if draft.channel=='dm' else
                    ('COMMENT_REPLY' if source['kind']=='COMMENT' else 'POST_COMMENT'),
                'authorPublicId':author,'postId':post_id,'commentId':comment_id},
            connection={'deviceId':request.deviceId,'connectionId':connection['connection_id'],
                'connectionVersion':connection['connection_version'],
                'accountPublicId':connection['account_public_id'],'platform':connection['platform']},
            channelCapability={'status':'UNVERIFIED','reason':'CHANNEL_CHECK_REQUIRED'},
            authorization='NOT_GRANTED')
        result['contextSha256'] = hashlib.sha256(json.dumps(result,ensure_ascii=False,
            sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self._active(cursor, claims)
        return result
