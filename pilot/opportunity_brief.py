"""Read-only, evidence-backed projection for the R4 homepage brief."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
import hashlib
import json
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import psycopg

from pilot.auth import InvalidPilotToken, TokenClaims
from pilot.opportunity_evidence import OpportunityEvidenceError, evidence_view
from pilot.sessions import PilotSessionRegistry


class OpportunityBriefError(ValueError):
    def __init__(self, code, status=422):
        self.code, self.status = code, status
        super().__init__(code)


def _uuid(value):
    try:
        if type(value) is not str or str(UUID(value)) != value.lower():
            raise ValueError
        return value.lower()
    except (ValueError, AttributeError):
        raise OpportunityBriefError("invalid_request") from None


def parse_query(raw):
    keys = {"contractVersion", "requestId", "userId", "accountScopeId", "scopeVersion",
            "profileId", "profileVersion", "businessDate", "timezone"}
    if type(raw) is not dict or set(raw) != keys or raw["contractVersion"] != 1 or raw["scopeVersion"] != 1:
        raise OpportunityBriefError("invalid_request")
    result = dict(raw)
    for key in ("requestId", "userId", "accountScopeId", "profileId"):
        result[key] = _uuid(result[key])
    if type(result["profileVersion"]) is not int or not 1 <= result["profileVersion"] <= 2_147_483_647:
        raise OpportunityBriefError("invalid_request")
    try:
        if type(result["businessDate"]) is not str or date.fromisoformat(result["businessDate"]).isoformat() != result["businessDate"]:
            raise ValueError
        if type(result["timezone"]) is not str or not 1 <= len(result["timezone"]) <= 100:
            raise ValueError
        ZoneInfo(result["timezone"])
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise OpportunityBriefError("invalid_request") from None
    return result


def validate_identity(claims, query, tenant):
    if not isinstance(claims, TokenClaims):
        raise OpportunityBriefError("invalid_session", 401)
    if claims.user_id != query["userId"] or tenant != query["accountScopeId"]:
        raise OpportunityBriefError("identity_conflict", 409)


def validate_business_day(day, timezone, now):
    if now.astimezone(ZoneInfo(timezone)).date().isoformat() != day:
        raise OpportunityBriefError("business_date_conflict", 409)


def _iso(value):
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise OpportunityBriefError("brief_store_unavailable", 503) from None
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _stable(prefix, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return prefix + hashlib.sha256(raw.encode()).hexdigest()


def _next_day(now, zone):
    local = now.astimezone(zone)
    tomorrow = local.date() + timedelta(days=1)
    return datetime.combine(tomorrow, datetime.min.time(), zone).astimezone(UTC)


def _clip(value, maximum):
    """Bound display text without altering the retained evidence record."""
    units = 0
    for index, character in enumerate(value):
        units += 2 if ord(character) > 0xFFFF else 1
        if units > maximum:
            return value[:index]
    return value


def _demand_excerpt(snapshot):
    source_body = snapshot["source"]["body"]
    for citation in snapshot["assessment"].get("citations") or []:
        quote = citation.get("quote")
        if (citation.get("dimension") == "intent"
                and citation.get("field") == "source.body" and isinstance(quote, str)
                and quote and quote in source_body):
            return _clip(quote, 4000)
    return None


def _window_id(run_id):
    return "window:" + run_id


class OpportunityBriefService:
    def __init__(self, database):
        self.database = database
        self.sessions = PilotSessionRegistry(database)

    def _active(self, cursor, claims):
        try:
            return self.sessions.require_active(cursor, claims)
        except (InvalidPilotToken, PermissionError):
            raise OpportunityBriefError("invalid_session", 401) from None

    @contextmanager
    def _snapshot(self, claims):
        try:
            with self.database.connect() as auth, auth.cursor() as auth_cursor:
                tenant = self._active(auth_cursor, claims)
                with self.database.connect() as conn, conn.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cursor.execute("SELECT set_config('yike.user_id',%s,true),set_config('yike.tenant_id',%s,true)",
                                   (claims.user_id, tenant))
                    cursor.execute("SELECT clock_timestamp()")
                    now = cursor.fetchone()[0]
                    yield cursor, tenant, now
                self._active(auth_cursor, claims)
        except OpportunityBriefError:
            raise
        except psycopg.errors.SerializationFailure:
            raise OpportunityBriefError("snapshot_changed", 409) from None
        except psycopg.Error:
            raise OpportunityBriefError("brief_store_unavailable", 503) from None

    @staticmethod
    def _rows(cursor):
        names = [column.name for column in cursor.description]
        return [dict(zip(names, row)) for row in cursor.fetchall()]

    def query(self, claims, raw):
        query = parse_query(raw)
        with self._snapshot(claims) as (cursor, tenant, now):
            validate_identity(claims, query, tenant)
            validate_business_day(query["businessDate"], query["timezone"], now)
            cursor.execute("""SELECT profile_version_id FROM business_profile_versions
                WHERE tenant_id=%s AND profile_version_id=%s AND version=%s AND status='CONFIRMED'""",
                           (tenant, query["profileId"], query["profileVersion"]))
            profile = cursor.fetchone()
            if profile is None:
                raise OpportunityBriefError("profile_unavailable", 409)
            profile_version_id = profile[0]
            cursor.execute("""SELECT o.opportunity_id,o.title,o.profile_version_id,o.source_status,o.intent_status,
                o.updated_at,e.include_request_id,e.included_by_user_id,e.payload,e.payload_sha256,
                EXISTS(SELECT 1 FROM pilot_followups f WHERE f.tenant_id=o.tenant_id AND f.opportunity_id=o.opportunity_id) AS legacy_contact,
                (SELECT cv.content_version FROM pilot_candidate_review_requests included
                  JOIN pilot_candidate_projections cp ON cp.tenant_id=included.tenant_id
                   AND cp.owner_user_id=included.owner_user_id AND cp.candidate_id=included.candidate_id
                  JOIN pilot_candidate_versions cv ON cv.tenant_id=cp.tenant_id AND cv.owner_user_id=cp.owner_user_id
                   AND cv.source_id=cp.source_id AND cv.version_id=cp.version_id
                  WHERE included.tenant_id=o.tenant_id AND included.owner_user_id=e.included_by_user_id
                   AND included.request_id=e.include_request_id) latest_source_hash,
                EXISTS(SELECT 1 FROM pilot_candidate_review_requests included
                  JOIN pilot_candidate_review_requests later ON later.tenant_id=included.tenant_id
                   AND later.owner_user_id=included.owner_user_id AND later.candidate_id=included.candidate_id
                  WHERE included.tenant_id=o.tenant_id AND included.owner_user_id=e.included_by_user_id
                   AND included.request_id=e.include_request_id AND later.action='EXCLUDE'
                   AND later.status='SUCCEEDED' AND later.created_at>included.created_at) AS later_excluded
                ,EXISTS(SELECT 1 FROM pilot_research_strategy_versions strategy
                  JOIN pilot_research_strategy_drafts draft ON draft.tenant_id=strategy.tenant_id
                   AND draft.owner_user_id=strategy.owner_user_id AND draft.draft_id=strategy.draft_id
                  WHERE strategy.tenant_id=o.tenant_id AND strategy.owner_user_id=e.included_by_user_id
                   AND strategy.strategy_version_id=e.payload->'assessment'->>'strategy_version_id'
                   AND strategy.state='CONFIRMED' AND draft.current_version_id=strategy.strategy_version_id
                   AND draft.current_revision=strategy.draft_revision) AS strategy_current
                FROM pilot_opportunities o LEFT JOIN pilot_opportunity_evidence e USING(tenant_id,opportunity_id)
                WHERE o.tenant_id=%s AND o.profile_version_id=%s ORDER BY o.updated_at DESC,o.opportunity_id LIMIT 1001""",
                           (tenant, profile_version_id))
            opportunities = self._rows(cursor)
            if len(opportunities) > 1000:
                raise OpportunityBriefError("snapshot_too_large", 503)
            cursor.execute("""WITH latest AS (
                  SELECT DISTINCT ON(record_id) record_id,revision,opportunity_id,profile_version_id,status,note,
                    next_step,next_followup_at,state,created_at,recorded_at
                  FROM pilot_structured_followup_revisions
                  WHERE tenant_id=%s AND owner_user_id=%s AND profile_version_id=%s
                  ORDER BY record_id,revision DESC)
                SELECT DISTINCT ON(opportunity_id) latest.*,
                  EXISTS(SELECT 1 FROM latest active WHERE active.opportunity_id=latest.opportunity_id
                    AND active.state='ACTIVE') AS has_active_contact
                FROM latest
                ORDER BY opportunity_id,recorded_at DESC,record_id DESC""", (tenant, claims.user_id, profile_version_id))
            followups = self._rows(cursor)
            if len(followups) > 1000:
                raise OpportunityBriefError("snapshot_too_large", 503)
            by_opportunity = {row["opportunity_id"]: row for row in opportunities}
            current_followups = {row["opportunity_id"] for row in followups if row["has_active_contact"]}
            zone = ZoneInfo(query["timezone"])
            local_start = datetime.combine(date.fromisoformat(query["businessDate"]), datetime.min.time(), zone).astimezone(UTC)
            local_end = _next_day(now, zone)
            contact = []; changes=[]
            for row in opportunities:
                if row["included_by_user_id"] != claims.user_id or row["payload"] is None:
                    continue
                try:
                    view = evidence_view(row["payload"], row["payload_sha256"], opportunity_id=row["opportunity_id"],
                                         profile_version_id=row["profile_version_id"])
                except OpportunityEvidenceError:
                    raise OpportunityBriefError("brief_store_unavailable", 503) from None
                snapshot = view["snapshot"]
                from pilot.source_content_changes import load_source_content_changes,SourceContentChangeError
                try: projected=load_source_content_changes(cursor,tenant=tenant,owner=claims.user_id,evidence=snapshot,now=now)
                except SourceContentChangeError as error:
                    raise OpportunityBriefError("snapshot_too_large" if "limit" in str(error) else "brief_store_unavailable",503) from None
                today=[change for change in projected["changes"]
                    if local_start<=datetime.fromisoformat(change["detectedAt"].replace("Z","+00:00"))<local_end]
                if today:
                    change=max(today,key=lambda item:(item["detectedAt"],item["id"]))
                    changes.append(self._item("changes",row,query,change["id"],change["toObservationId"],
                        change["to"]["quote"],"VERIFIED_CHANGE",change["detectedAt"],
                        "库内观察到来源正文不同；观察时间已保留，真实编辑时间未知，需求含义仍需人工复核。"))
                cursor.execute("""SELECT v.receipt FROM pilot_candidate_review_requests included
                    JOIN pilot_candidate_source_verifications v ON v.tenant_id=included.tenant_id
                     AND v.owner_user_id=included.owner_user_id AND v.binding_hash=included.binding_hash
                    WHERE included.tenant_id=%s AND included.owner_user_id=%s AND included.request_id=%s
                    ORDER BY v.checked_at DESC,v.verification_id DESC LIMIT 1""",
                    (tenant, claims.user_id, row["include_request_id"]))
                verification_row = cursor.fetchone()
                latest_verification = verification_row[0] if verification_row else None
                demand_excerpt = _demand_excerpt(snapshot)
                if (row["source_status"] != "OPEN" or row["intent_status"] in {"CONTACTED", "CLOSED"}
                        or row["legacy_contact"] or row["opportunity_id"] in current_followups or row["later_excluded"]
                        or not row["strategy_current"]
                        or row["latest_source_hash"] != snapshot["source"]["content_sha256"]
                        or not latest_verification or latest_verification.get("status") != "OPEN"
                        or latest_verification.get("contactMethod") not in {"COMMENT", "DM", "PUBLIC_CONTACT"}
                        or demand_excerpt is None):
                    continue
                checked = snapshot["verification"]["checked_at"]
                contact.append(self._item("contact", row, query, row["include_request_id"],
                                          snapshot["source"]["version_id"], demand_excerpt, "REVIEWED_DEMAND", checked,
                                          "人工核验时来源开放并已纳入。"))
            followup = []
            end = _next_day(now, ZoneInfo(query["timezone"]))
            for record in followups:
                row = by_opportunity.get(record["opportunity_id"])
                if (row is None or record["profile_version_id"] != profile_version_id or record["state"] != "ACTIVE"
                        or record["status"] in {"LOST", "WON"} or record["next_followup_at"] is None
                        or record["next_followup_at"] >= end):
                    continue
                followup.append(self._item("followup", row, query, record["record_id"], str(record["revision"]),
                                           record["next_step"] or record["note"], "MANUAL_FOLLOWUP", record["recorded_at"],
                                           record["next_step"] or "按已登记计划跟进。"))
            cursor.execute("""SELECT t.task_id,r.run_id,max(done.created_at) AS completed_at
                FROM pilot_collection_tasks t JOIN pilot_collection_runs r USING(tenant_id,owner_user_id,task_id)
                JOIN pilot_execution_operations done ON done.tenant_id=t.tenant_id AND done.owner_user_id=t.owner_user_id
                  AND done.task_id=t.task_id AND done.run_id=r.run_id AND done.operation='FINISH'
                WHERE t.tenant_id=%s AND t.owner_user_id=%s AND t.profile_version_id=%s
                  AND done.created_at >= %s AND done.created_at < %s
                  AND EXISTS(SELECT 1 FROM pilot_collection_platform_runs p WHERE p.tenant_id=t.tenant_id
                    AND p.owner_user_id=t.owner_user_id AND p.task_id=t.task_id AND p.run_id=r.run_id AND p.status='SUCCEEDED')
                GROUP BY t.task_id,r.run_id ORDER BY completed_at DESC,t.task_id,r.run_id LIMIT 101""",
                           (tenant, claims.user_id, profile_version_id, local_start, local_end))
            runs_raw = self._rows(cursor)
            if len(runs_raw) > 100:
                raise OpportunityBriefError("snapshot_too_large", 503)
            runs = [{"taskId":r["task_id"], "runId":r["run_id"], "windowId":_window_id(r["run_id"])} for r in runs_raw]
            completed = [r["completed_at"] for r in runs_raw if r["completed_at"] is not None]
            has_facts = bool(runs or followups or any(
                row["included_by_user_id"] == claims.user_id and row["payload"] is not None
                for row in opportunities
            ))
            coverage = "PARTIAL" if has_facts else "NOT_CHECKED"
            unchecked = (["原帖需求变化尚未核验", "真实未覆盖来源尚未检查"] if has_facts else ["尚无本人该画像的可读事实或已完成任务"])
            identity = query | {"generatedAt": _iso(now)}
            result = query | {"snapshotId": _stable("obs_", identity), "audience":"CUSTOMER",
                "generatedAt":_iso(now), "expiresAt":_iso(min(now + timedelta(minutes=5), end)),
                "coverage":coverage, "lastCompletedCheckAt":_iso(max(completed)) if completed else None,
                "checkedScope":["库内已核验机会与有效跟进"] if has_facts else [], "uncheckedScope":unchecked,
                "runs":runs, "groups":{"contact":{"items":contact,"total":len(contact)},
                "changes":{"items":changes,"total":len(changes)}, "followup":{"items":followup,"total":len(followup)}}}
            return result

    @staticmethod
    def _item(group, row, query, record_id, version, excerpt, kind, verified_at, reason):
        return {"id":_stable("obi_", [group, record_id, version]), "opportunityId":row["opportunity_id"],
                "opportunityVersion":_iso(row["updated_at"]), "title":_clip(row["title"], 300), "reason":_clip(reason, 4000),
                "profileId":query["profileId"], "profileVersion":query["profileVersion"], "sample":False,
                "validity":"VALID", "basis":{"recordId":record_id,"version":version,"excerpt":_clip(excerpt, 4000),
                "kind":kind,"verifiedAt":_iso(verified_at)}}
