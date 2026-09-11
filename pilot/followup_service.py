"""Owner-scoped append-only structured follow-up records and receipts."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.sessions import PilotSessionRegistry
from pilot.signed_replies import evidence_row
from pilot.reply_store import ReplyStoreError

_ACTIONS = {"create", "correct", "void", "mark-read"}
_STATUSES = {"CONTACTED", "REPLIED", "MEETING", "QUOTED", "LOST", "WON"}
_STATES = {"ACTIVE", "CORRECTED", "VOID"}


class FollowupError(ValueError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def _uuid(value, *, empty=False):
    if empty and value == "":
        return value
    try:
        if type(value) is not str or str(UUID(value)) != value.lower():
            raise ValueError
        return value.lower()
    except (ValueError, AttributeError):
        raise FollowupError("invalid_request", 422) from None


def _time(value, nullable=True):
    if value is None and nullable:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed
    except (ValueError, TypeError, AttributeError):
        raise FollowupError("invalid_request", 422) from None


def parse_binding(raw):
    keys = {"opportunityId", "profileVersionId", "action", "targetId", "targetRevision", "requestId"}
    if type(raw) is not dict or set(raw) != keys or raw.get("action") not in _ACTIONS:
        raise FollowupError("invalid_request", 422)
    result = dict(raw)
    for key in ("opportunityId", "profileVersionId", "requestId"):
        result[key] = _uuid(result[key])
    result["targetId"] = _uuid(result["targetId"], empty=True)
    revision = result["targetRevision"]
    if type(revision) is not int or revision < 0:
        raise FollowupError("invalid_request", 422)
    if (result["action"] == "create") != (result["targetId"] == "" and revision == 0):
        raise FollowupError("invalid_request", 422)
    if result["action"] != "create" and (not result["targetId"] or revision < 1):
        raise FollowupError("invalid_request", 422)
    return result


def parse_mutation(raw):
    if type(raw) is not dict or not {"binding"} <= set(raw) or set(raw) - {"binding", "values", "reason"}:
        raise FollowupError("invalid_request", 422)
    binding = parse_binding(raw["binding"])
    values, reason = raw.get("values"), raw.get("reason")
    if binding["action"] in ("create", "correct"):
        expected = {"status", "note", "occurredAt", "nextStep", "nextFollowupAt", "ownerId"}
        if type(values) is not dict or set(values) != expected or values["status"] not in _STATUSES:
            raise FollowupError("invalid_request", 422)
        if type(values["note"]) is not str or not values["note"].strip() or len(values["note"].strip()) > 500:
            raise FollowupError("invalid_request", 422)
        if type(values["nextStep"]) is not str or len(values["nextStep"]) > 500:
            raise FollowupError("invalid_request", 422)
        values = dict(values, note=values["note"].strip(), ownerId=_uuid(values["ownerId"]))
        occurred = _time(values["occurredAt"])
        if occurred and occurred > datetime.now(UTC):
            raise FollowupError("occurred_at_future", 409)
        _time(values["nextFollowupAt"])
    elif values is not None:
        raise FollowupError("invalid_request", 422)
    if binding["action"] in ("correct", "void"):
        if type(reason) is not str or not reason.strip() or len(reason.strip()) > 500:
            raise FollowupError("invalid_request", 422)
        reason = reason.strip()
    elif reason is not None:
        raise FollowupError("invalid_request", 422)
    return {"binding": binding, **({"values": values} if values is not None else {}), **({"reason": reason} if reason is not None else {})}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _iso(value):
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class FollowupService:
    def __init__(self, database, reply_store=None):
        self.database, self.reply_store = database, reply_store
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        if not isinstance(claims, TokenClaims):
            raise FollowupError("invalid_session", 401)
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise FollowupError("invalid_session", 401) from None

    def _scope(self, cursor, claims):
        tenant = self._active(cursor, claims)
        cursor.execute("SELECT opportunity_id,profile_version_id,title FROM pilot_opportunities WHERE tenant_id=%s", (tenant,))
        return tenant

    @staticmethod
    def _row(cursor):
        row = cursor.fetchone()
        return None if row is None else dict(zip((c.name for c in cursor.description), row))

    def _opportunity(self, cursor, tenant, claims, binding):
        cursor.execute("SELECT o.title,o.profile_version_id,v.status FROM pilot_opportunities o JOIN business_profile_versions v USING(tenant_id,profile_version_id) WHERE o.tenant_id=%s AND o.opportunity_id=%s FOR UPDATE OF o,v",
                       (tenant, binding["opportunityId"]))
        row = cursor.fetchone()
        if row is None:
            raise FollowupError("opportunity_not_found", 404)
        if row[1] != binding["profileVersionId"] or row[2] != "CONFIRMED":
            raise FollowupError("profile_conflict", 409)
        return row[0]

    @staticmethod
    def _record(row):
        return {"id": row["record_id"], "opportunityId": row["opportunity_id"],
                "profileVersionId": row["profile_version_id"], "revision": row["revision"],
                "status": row["status"], "note": row["note"],
                "occurredAt": None if row["occurred_at"] is None else _iso(row["occurred_at"]),
                "nextStep": row["next_step"],
                "nextFollowupAt": None if row["next_followup_at"] is None else _iso(row["next_followup_at"]),
                "ownerId": row["assignee_user_id"], "ownerName": "成员" + row["assignee_user_id"][:8],
                "title": row["title"], "createdAt": _iso(row["created_at"]), "kind": "manual",
                "state": row["state"], "sample": False,
                **({"correctsId": row["corrects_id"]} if row["corrects_id"] else {}),
                **({"reason": row["reason"]} if row["reason"] else {})}

    def list(self, claims):
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute("""SELECT DISTINCT ON (r.record_id) r.*,o.title FROM pilot_structured_followup_revisions r
                JOIN pilot_opportunities o USING(tenant_id,opportunity_id)
                WHERE r.tenant_id=%s AND r.owner_user_id=%s ORDER BY r.record_id,r.revision DESC""", (tenant, claims.user_id))
            rows = [self._record(dict(zip((c.name for c in cursor.description), row))) for row in cursor.fetchall()]
            if len(rows) > 5000:
                raise FollowupError("snapshot_too_large", 503)
            cursor.execute("SELECT user_id FROM yike_followup_members() ORDER BY user_id")
            members = [{"id": row[0], "name": "成员" + row[0][:8]} for row in cursor.fetchall()]
            cursor.execute("""SELECT f.followup_id,f.opportunity_id,o.title,f.status,f.note,f.created_at
                FROM pilot_followups f JOIN pilot_opportunities o USING(tenant_id,opportunity_id)
                WHERE f.tenant_id=%s ORDER BY f.created_at DESC""", (tenant,))
            legacy = [{"id": r[0], "opportunityId": r[1], "title": r[2], "status": r[3],
                       "note": r[4], "createdAt": _iso(r[5]), "kind": "manual"} for r in cursor.fetchall()]
            if len(rows) + len(legacy) > 5000:
                raise FollowupError("snapshot_too_large", 503)
            return {"records": rows, "members": members, "legacyRecords": legacy}

    def _reply(self, cursor, row):
        try:
            verified = evidence_row((row["payload"], row["payload_sha256"], row["device_attestation"], row["revision"]))
        except ReplyStoreError as error:
            raise FollowupError(error.code, error.status) from None
        event = verified["event"]
        if verified["verification"].get("authority") != "DEVICE_ATTESTED_PLATFORM_REPLY" or event["kind"] != "PLATFORM_REPLY":
            raise FollowupError("stored_reply_attestation_invalid", 503)
        revision = row["read_revision"] or row["revision"]
        read = bool(row["read_value"]) if row["read_revision"] else event["read_state"] == "READ"
        return {"id": event["event_id"], "revision": revision, "opportunityId": event["opportunity_id"],
                "profileVersionId": event["profile_version_id"], "sendRequestId": event["outreach_request_id"],
                "platform": event["platform"], "content": event["body"], "receivedAt": _iso(datetime.fromisoformat(event["received_at"].replace("Z", "+00:00"))),
                "read": read, "sample": False}

    def replies(self, claims, opportunity_id=None):
        if opportunity_id is not None:
            opportunity_id = _uuid(opportunity_id)
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            if opportunity_id is None:
                return []
            cursor.execute("SELECT 1 FROM pilot_opportunities WHERE tenant_id=%s AND opportunity_id=%s", (tenant, opportunity_id))
            if cursor.fetchone() is None:
                raise FollowupError("opportunity_not_found", 404)
            cursor.execute("""SELECT DISTINCT ON (e.event_id) e.payload,e.payload_sha256,e.device_attestation,e.revision,
                rr.revision AS read_revision,rr.read AS read_value
                FROM pilot_reply_events e LEFT JOIN LATERAL (SELECT revision,read FROM pilot_followup_reply_reads x
                  WHERE x.tenant_id=e.tenant_id AND x.owner_user_id=e.owner_user_id AND x.reply_event_id=e.event_id
                  ORDER BY revision DESC LIMIT 1) rr ON true
                WHERE e.tenant_id=%s AND e.owner_user_id=%s AND e.opportunity_id=%s
                  AND e.kind='PLATFORM_REPLY' AND e.device_attestation->>'authority'='DEVICE_ATTESTED_PLATFORM_REPLY'
                ORDER BY e.event_id,e.revision DESC""", (tenant, claims.user_id, opportunity_id))
            desc = [c.name for c in cursor.description]
            result = [self._reply(cursor, dict(zip(desc, row))) for row in cursor.fetchall()]
            if len(result) > 5000:
                raise FollowupError("snapshot_too_large", 503)
            return result

    def _existing_operation(self, cursor, tenant, claims, binding, digest):
        cursor.execute("SELECT request_sha256,receipt FROM pilot_followup_operations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s", (tenant, claims.user_id, binding["requestId"]))
        row = cursor.fetchone()
        if row is None:
            return None
        if row[0] != digest:
            raise FollowupError("request_conflict", 409)
        return row[1]

    def mutate(self, claims, raw):
        request = parse_mutation(raw); binding = request["binding"]
        digest = hashlib.sha256(_json(request).encode()).hexdigest()
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute("SELECT pg_advisory_xact_lock(13101,hashtext(%s))", (binding["requestId"],))
            prior = self._existing_operation(cursor, tenant, claims, binding, digest)
            if prior is not None:
                return prior
            title = self._opportunity(cursor, tenant, claims, binding)
            action = binding["action"]
            if action == "mark-read":
                receipt = self._mark_read(cursor, tenant, claims, binding)
            else:
                receipt = self._mutate_record(cursor, tenant, claims, binding, request, title)
            cursor.execute("INSERT INTO pilot_followup_operations(tenant_id,owner_user_id,request_id,request_sha256,binding,receipt) VALUES(%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
                           (tenant, claims.user_id, binding["requestId"], digest, _json(binding), _json(receipt)))
            self._active(cursor, claims)
            return receipt

    def _target(self, cursor, tenant, claims, binding):
        cursor.execute("SELECT pg_advisory_xact_lock(13102,hashtext(%s))", (binding["targetId"],))
        cursor.execute("SELECT * FROM pilot_structured_followup_revisions WHERE tenant_id=%s AND owner_user_id=%s AND record_id=%s ORDER BY revision DESC LIMIT 1", (tenant, claims.user_id, binding["targetId"]))
        row = self._row(cursor)
        if row is None:
            raise FollowupError("followup_not_found", 404)
        if row["opportunity_id"] != binding["opportunityId"] or row["profile_version_id"] != binding["profileVersionId"]:
            raise FollowupError("followup_binding_conflict", 409)
        if row["revision"] != binding["targetRevision"] or row["state"] != "ACTIVE":
            raise FollowupError("followup_revision_conflict", 409)
        return row

    def _insert_record(self, cursor, tenant, claims, record_id, revision, binding, values, title, state="ACTIVE", corrects=None, reason=None, created=None):
        cursor.execute("SELECT 1 FROM pilot_users WHERE tenant_id=%s AND user_id=%s", (tenant, values["ownerId"]))
        if cursor.fetchone() is None:
            raise FollowupError("member_not_found", 409)
        created = created or datetime.now(UTC)
        cursor.execute("""INSERT INTO pilot_structured_followup_revisions
            (tenant_id,owner_user_id,record_id,revision,opportunity_id,profile_version_id,status,note,occurred_at,next_step,next_followup_at,assignee_user_id,state,corrects_id,reason,created_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *,%s AS title""",
            (tenant, claims.user_id, record_id, revision, binding["opportunityId"], binding["profileVersionId"],
             values["status"], values["note"], _time(values["occurredAt"]), values["nextStep"], _time(values["nextFollowupAt"]),
             values["ownerId"], state, corrects, reason, created, title))
        return self._record(self._row(cursor))

    def _mutate_record(self, cursor, tenant, claims, binding, request, title):
        if binding["action"] == "create":
            record = self._insert_record(cursor, tenant, claims, str(uuid4()), 1, binding, request["values"], title)
        else:
            old = self._target(cursor, tenant, claims, binding)
            next_revision = old["revision"] + 1
            if binding["action"] == "void":
                values = {"status": old["status"], "note": old["note"], "occurredAt": None if old["occurred_at"] is None else _iso(old["occurred_at"]),
                          "nextStep": old["next_step"], "nextFollowupAt": None if old["next_followup_at"] is None else _iso(old["next_followup_at"]), "ownerId": old["assignee_user_id"]}
                record = self._insert_record(cursor, tenant, claims, old["record_id"], next_revision, binding, values, title, "VOID", old["corrects_id"], request["reason"], old["created_at"])
            else:
                old_values = {"status": old["status"], "note": old["note"], "occurredAt": None if old["occurred_at"] is None else _iso(old["occurred_at"]),
                              "nextStep": old["next_step"], "nextFollowupAt": None if old["next_followup_at"] is None else _iso(old["next_followup_at"]), "ownerId": old["assignee_user_id"]}
                self._insert_record(cursor, tenant, claims, old["record_id"], next_revision, binding, old_values, title, "CORRECTED", old["corrects_id"], request["reason"], old["created_at"])
                record = self._insert_record(cursor, tenant, claims, str(uuid4()), 1, binding, request["values"], title, "ACTIVE", old["record_id"], request["reason"])
        return {"binding": binding, "status": "SUCCEEDED", "confirmed": True, "record": record}

    def _mark_read(self, cursor, tenant, claims, binding):
        cursor.execute("SELECT pg_advisory_xact_lock(13103,hashtext(%s))", (binding["targetId"],))
        rows = self.replies(claims, binding["opportunityId"])
        reply = next((row for row in rows if row["id"] == binding["targetId"]), None)
        if reply is None:
            raise FollowupError("reply_not_found", 404)
        if reply["profileVersionId"] != binding["profileVersionId"] or reply["revision"] != binding["targetRevision"]:
            raise FollowupError("reply_revision_conflict", 409)
        revision = reply["revision"] + 1
        cursor.execute("INSERT INTO pilot_followup_reply_reads(tenant_id,owner_user_id,reply_event_id,revision,read) VALUES(%s,%s,%s,%s,true)", (tenant, claims.user_id, reply["id"], revision))
        reply.update(revision=revision, read=True)
        return {"binding": binding, "status": "SUCCEEDED", "confirmed": True, "reply": reply}

    def operation(self, claims, raw_binding):
        binding = parse_binding(raw_binding)
        with self.database.connect() as conn, conn.cursor() as cursor:
            tenant = self._active(cursor, claims)
            cursor.execute("SELECT binding,receipt FROM pilot_followup_operations WHERE tenant_id=%s AND owner_user_id=%s AND request_id=%s", (tenant, claims.user_id, binding["requestId"]))
            row = cursor.fetchone()
            if row is None:
                raise FollowupError("operation_not_found", 404)
            if row[0] != binding:
                raise FollowupError("request_conflict", 409)
            return row[1]
