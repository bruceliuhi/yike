"""Owner-private, append-only manual drafts. Saving never authorizes sending."""
from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, AfterValidator, model_validator

from pilot.auth import TokenClaims
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
            lock = int.from_bytes(hashlib.sha256(
                f'contact-drafts-v1\0{tenant}\0{claims.user_id}'.encode()).digest()[:8], 'big', signed=True)
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
            self._active(cursor, claims)
            prior = self._original(cursor, tenant, claims.user_id, binding)
            if prior is not None:
                return prior
            if snapshot.accountScope is not None and snapshot.accountScope.id != tenant:
                raise DraftError('draft_scope_changed')
            cursor.execute('SELECT o.profile_version_id,o.source_status,o.intent_status,p.status,s.health,'
                'e.payload,e.payload_sha256,o.draft_comment,o.draft_dm '
                'FROM pilot_opportunities o '
                'JOIN business_profile_versions p ON p.tenant_id=o.tenant_id AND p.profile_version_id=o.profile_version_id '
                'JOIN pilot_sources s ON s.tenant_id=o.tenant_id AND s.source_id=o.source_id '
                'LEFT JOIN pilot_opportunity_evidence e ON e.tenant_id=o.tenant_id AND e.opportunity_id=o.opportunity_id '
                'WHERE o.tenant_id=%s AND o.opportunity_id=%s FOR SHARE OF o,p,s',
                (tenant, binding.opportunityId))
            facts = cursor.fetchone()
            if facts is None:
                raise DraftError('opportunity_not_found', 404)
            if (facts[0] != snapshot.profileVersionId or facts[1] != 'OPEN'
                    or facts[2] == 'CLOSED' or facts[3] != 'CONFIRMED' or facts[4] != 'OPEN'):
                raise DraftError('draft_facts_changed')
            proof = evidence_view(facts[5], facts[6], opportunity_id=draft.opportunityId,
                                  profile_version_id=snapshot.profileVersionId)
            if (proof['status'] != 'CAPTURED'
                    or proof['snapshot']['source']['version_id'] != snapshot.sourceEvidenceVersion):
                raise DraftError('draft_evidence_changed')
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
