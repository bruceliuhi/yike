"""Durable human confirmations, not a dispatcher or proof of delivery."""
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from pilot.contact_drafts import _Input, Id, Version, OutreachContextInput, DraftError
from pilot.execution_runtime import _json, _hash, _raw_model


class ChannelCheck(_Input):
    status: Literal['AVAILABLE']
    observedAt: str = Field(max_length=48)

    @field_validator('observedAt')
    @classmethod
    def aware_time(cls, value):
        if datetime.fromisoformat(value.replace('Z', '+00:00')).utcoffset() is None:
            raise ValueError('timezone required')
        return value


class Confirmation(_Input):
    requestId: Id
    context: OutreachContextInput
    contextSha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    credentialVersion: Version
    humanConfirmed: bool
    channelCheck: ChannelCheck

    @field_validator('humanConfirmed')
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError('human confirmation required')
        return value


def signing_payload(tenant, claims, value):
    return _json(dict(protocol='yike-outreach-confirmation-v1', tenant_id=tenant,
        user_id=claims.user_id, session_digest=claims.revocation_key,
        request=value.model_dump()))


def receipt(row):
    return dict(requestId=row[0], state=row[1], deliveryConfirmed=False)


class OutreachQueueStore:
    def __init__(self, database, drafts, execution):
        self.database, self.drafts, self.execution = database, drafts, execution

    def _lock(self, cursor, claims):
        tenant = self.drafts._active(cursor, claims)
        # Same owner fence as draft CAS, before device -> connection -> profile.
        self.drafts._lock_owner(cursor, tenant, claims.user_id)
        return tenant

    def _row(self, cursor, tenant, owner, request_id):
        cursor.execute('SELECT request_id,state,request_sha256 FROM pilot_outreach_queue '
            'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s', (tenant,owner,request_id))
        return cursor.fetchone()

    def prepare(self, claims, raw):
        value = Confirmation.model_validate(_raw_model(raw))
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._lock(cursor, claims)
            self.execution._key(cursor, claims, tenant, value.context.deviceId, value.credentialVersion)
            result = dict(signing_payload=signing_payload(tenant, claims, value),
                requestId=value.requestId, requestSha256=_hash(value.model_dump()))
            self.drafts._active(cursor, claims)
            return result

    def confirm(self, claims, raw, signature):
        value = Confirmation.model_validate(_raw_model(raw))
        digest = _hash(value.model_dump())
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._lock(cursor, claims)
            key = self.execution._key(cursor, claims, tenant, value.context.deviceId, value.credentialVersion)
            self.execution._signature(key, signature, signing_payload(tenant, claims, value))
            original = self._row(cursor, tenant, claims.user_id, value.requestId)
            if original is not None:
                if original[2] != digest:
                    raise DraftError('confirmation_request_conflict')
                self.drafts._active(cursor, claims)
                return receipt(original)
            context = self.drafts.context_in_transaction(cursor, claims, value.context.model_dump())
            if context['contextSha256'] != value.contextSha256:
                raise DraftError('outreach_context_changed')
            observed = datetime.fromisoformat(value.channelCheck.observedAt.replace('Z', '+00:00'))
            age = (self.execution._now(cursor) - observed).total_seconds()
            if not -5 <= age <= 120:
                raise DraftError('channel_check_expired')
            binding = value.context.binding
            cursor.execute('SELECT 1 FROM pilot_outreach_queue WHERE tenant_id=%s '
                'AND owner_user_id=%s AND opportunity_id=%s AND channel=%s AND state=\'QUEUED\'',
                (tenant,claims.user_id,binding.opportunityId,binding.channel))
            if cursor.fetchone() is not None:
                raise DraftError('outreach_already_pending')
            cursor.execute('INSERT INTO pilot_outreach_queue '
                '(tenant_id,owner_user_id,request_id,opportunity_id,channel,request_sha256,request_payload,context_payload) '
                'VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)',
                (tenant,claims.user_id,value.requestId,binding.opportunityId,binding.channel,digest,
                 _json(value.model_dump()),_json(context)))
            self.drafts._active(cursor, claims)
            return receipt((value.requestId, 'QUEUED'))

    def original(self, claims, request_id, cancel=False):
        from pilot.outreach_contract import canonical_uuid
        request_id = canonical_uuid(request_id)
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._lock(cursor, claims)
            row = self._row(cursor, tenant, claims.user_id, request_id)
            if row is None:
                raise DraftError('outreach_request_not_found',404)
            if cancel and row[1] == 'QUEUED':
                cursor.execute('UPDATE pilot_outreach_queue SET state=\'CANCELLED\' '
                    'WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s AND state=\'QUEUED\' '
                    'RETURNING request_id,state', (tenant,claims.user_id,request_id))
                row = cursor.fetchone()
            self.drafts._active(cursor, claims)
            return receipt(row)
